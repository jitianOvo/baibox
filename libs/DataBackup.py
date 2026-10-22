# -*- coding: utf-8 -*-
import json
import os
import tarfile
import tempfile
import threading
import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from libs.Android import (
    _get_runtime_paths,
    adb_get_devices,
    _pick_device_dialog,
    _write_selected_device,
)

# 通用缓存目录（预设清单持久化位置）
CORE_DIR = os.path.join(os.path.expanduser("~"), "PyCache", "core")
PRESETS_FILE = os.path.join(CORE_DIR, "backup_presets.json")

# 手机常用预设（可增删，持久化到 core）
DEFAULT_PHONE_PRESETS = [
    "/storage/emulated/0/Download",
    "/storage/emulated/0/DCIM",
    "/storage/emulated/0/Documents",
    "/storage/emulated/0/Movies",
    "/storage/emulated/0/Pictures",
]

# 电脑常用预设
def _desktop_dir():
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        # CSIDL_DESKTOPDIRECTORY 当前用户桌面
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buf)
        p = buf.value
        if p and os.path.isdir(p):
            return p
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def default_desktop_presets():
    return [
        _desktop_dir(),
        os.path.join(os.path.expanduser("~"), "Downloads"),
    ]


def load_presets():
    try:
        os.makedirs(CORE_DIR, exist_ok=True)
        defaults = {
            "phone": list(DEFAULT_PHONE_PRESETS),
            "desktop": default_desktop_presets(),
        }
        if not os.path.exists(PRESETS_FILE):
            return defaults
        with open(PRESETS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults
        # 用户已保存的清单为权威（删除操作永久生效）；
        # 首次无文件时用默认，一旦用户手动保存过就尊重文件内容
        if "phone" not in data:
            data["phone"] = list(DEFAULT_PHONE_PRESETS)
        data.setdefault("desktop", default_desktop_presets())
        return data
    except Exception:
        return {"phone": list(DEFAULT_PHONE_PRESETS), "desktop": default_desktop_presets()}


def save_presets(data):
    try:
        os.makedirs(CORE_DIR, exist_ok=True)
        with open(PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _adb(device, shell_cmd):
    adb = _get_runtime_paths()["adb_path"]
    import subprocess
    r = subprocess.run([adb, "-s", device, "shell", shell_cmd],
                       capture_output=True, text=True,
                       encoding="utf-8", errors="ignore")
    return r.returncode, r.stdout


class BackupWorker(QThread):
    """后台备份：手机走 adb pull，电脑直接复制，统一打包 tar.gz"""

    progress = Signal(int)
    log = Signal(str)
    done = Signal(bool, str)

    def __init__(self, targets, device, out_tar):
        super().__init__()
        self.targets = targets  # [("phone"|"desktop", path), ...]
        self.device = device
        self.out_tar = out_tar

    def run(self):
        try:
            staging = tempfile.mkdtemp(prefix="dawanj_backup_")
            total = len(self.targets)
            for idx, (kind, path) in enumerate(self.targets):
                self.log.emit(f"备份：{path}")
                try:
                    if kind == "phone":
                        self._backup_phone(path, staging)
                    else:
                        self._backup_desktop(path, staging)
                except Exception as exc:
                    self.log.emit(f"  跳过（{exc}）")
                self.progress.emit(int((idx + 1) / total * 100))
            self.log.emit(f"打包为：{self.out_tar}")
            self._make_tar(staging, self.out_tar)
            size_mb = round(os.path.getsize(self.out_tar) / 1024 / 1024, 2)
            self.log.emit(f"完成：{self.out_tar}（{size_mb} MB）")
            self.done.emit(True, f"备份完成：\n{self.out_tar}\n大小：{size_mb} MB")
        except Exception as exc:
            self.done.emit(False, f"备份失败：{exc}")

    def _backup_phone(self, remote, staging):
        adb = _get_runtime_paths()["adb_path"]
        import subprocess
        # 远端路径名做安全化
        tag = remote.strip("/").replace("/", "_") or "phone_root"
        local = os.path.join(staging, "phone", tag)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        if remote.endswith("/"):
            remote = remote.rstrip("/")
        r = subprocess.run([adb, "-s", self.device, "pull", remote, local],
                           capture_output=True, text=True, errors="ignore")
        if r.returncode != 0 and not os.path.exists(local):
            raise RuntimeError("adb pull 失败")

    def _backup_desktop(self, path, staging):
        import shutil
        tag = os.path.basename(path.rstrip("/\\")) or "desktop"
        local = os.path.join(staging, "desktop", tag)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        if os.path.isdir(path):
            shutil.copytree(path, local, dirs_exist_ok=True)
        elif os.path.isfile(path):
            shutil.copy2(path, local + ".file")

    def _make_tar(self, staging, out_tar):
        os.makedirs(os.path.dirname(out_tar), exist_ok=True)
        with tarfile.open(out_tar, "w:gz") as tar:
            tar.add(staging, arcname="backup")


class BackupDialog(QDialog):
    """电脑手机数据备份：勾选路径 → 打包单个 .tar.gz"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("电脑手机数据备份")
        self.setMinimumSize(640, 660)
        if parent and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        self.device = None
        self.worker = None
        self.presets = load_presets()
        self._build_ui()
        self._pick_device()

    def _build_ui(self):
        self.setStyleSheet(
            """
            QDialog { background-color: #eef2f8; }
            QFrame#card {
                background-color: #ffffff; border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
            QLabel#title { font-size: 16px; font-weight: 700; color: #0f172a; }
            QLabel#hint { font-size: 11px; color: #64748b; }
            QLabel#path {
                font-size: 11px; color: #334155; background-color: #f8fafc;
                border: 1px solid #e2e8f0; border-radius: 6px; padding: 5px 8px;
            }
            QPushButton {
                background-color: #eef2f9; border: 1px solid #d8e0ec;
                border-radius: 8px; color: #1f2937; padding: 6px 12px;
                min-height: 30px; font-size: 12px;
            }
            QPushButton:hover { background-color: #e6edf9; }
            QPushButton#primary {
                background-color: #2563eb; border-color: #2563eb; color: white;
                font-weight: 600;
            }
            QPushButton#primary:hover { background-color: #1d4ed8; }
            QPushButton#danger {
                background-color: #ef4444; border-color: #ef4444; color: white;
                font-weight: 600;
            }
            QPushButton#danger:hover { background-color: #dc2626; }
            QListWidget {
                background-color: #fbfdff; border: 1px solid #dbe4f0;
                border-radius: 8px; color: #334155; font-size: 12px; outline: none;
            }
            QListWidget::item { padding: 5px 6px; border-bottom: 1px solid #edf2fb; }
            QListWidget::item:selected { background-color: #e7f0ff; color: #0f172a; }
            QProgressBar {
                border: 1px solid #dbe4f0; border-radius: 8px;
                background-color: #f8fafc; text-align: center; color: #334155;
                min-height: 18px;
            }
            QProgressBar::chunk { background-color: #2563eb; border-radius: 7px; }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QFrame()
        header.setObjectName("card")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 10, 12, 10)
        hl.setSpacing(8)
        tb = QVBoxLayout()
        tb.setSpacing(2)
        t = QLabel("电脑手机数据备份")
        t.setObjectName("title")
        h = QLabel("勾选路径 → 一键打包为单个 .tar.gz（可上传云端）")
        h.setObjectName("hint")
        tb.addWidget(t)
        tb.addWidget(h)
        hl.addLayout(tb)
        hl.addStretch()
        self.dev_label = QLabel("手机：未选择")
        self.dev_label.setObjectName("path")
        hl.addWidget(self.dev_label)
        layout.addWidget(header)

        # 路径列表
        list_card = QFrame()
        list_card.setObjectName("card")
        ll = QVBoxLayout(list_card)
        ll.setContentsMargins(12, 10, 12, 10)
        ll.setSpacing(8)
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("备份路径"))
        top_row.addStretch()
        btn_phone_pre = QPushButton("手机预设")
        btn_phone_pre.clicked.connect(lambda: self._apply_preset("phone"))
        btn_desktop_pre = QPushButton("电脑预设")
        btn_desktop_pre.clicked.connect(lambda: self._apply_preset("desktop"))
        top_row.addWidget(btn_phone_pre)
        top_row.addWidget(btn_desktop_pre)
        ll.addLayout(top_row)

        self.path_list = QListWidget()
        self.path_list.setMinimumHeight(240)
        ll.addWidget(self.path_list, 1)

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        from PySide6.QtWidgets import QLineEdit
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("输入路径后回车添加…")
        self.path_input.returnPressed.connect(self._add_custom_path)
        add_row.addWidget(self.path_input, 1)
        btn_add = QPushButton("添加")
        btn_add.clicked.connect(self._add_custom_path)
        btn_del = QPushButton("删除选中")
        btn_del.clicked.connect(self._del_selected_paths)
        add_row.addWidget(btn_add)
        add_row.addWidget(btn_del)
        ll.addLayout(add_row)

        btn_all = QPushButton("全选")
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none = QPushButton("全不选")
        btn_none.clicked.connect(lambda: self._set_all(False))
        ctl_row = QHBoxLayout()
        ctl_row.addWidget(btn_all)
        ctl_row.addWidget(btn_none)
        ctl_row.addStretch()
        ll.addLayout(ctl_row)
        layout.addWidget(list_card)

        # 输出 + 进度
        opt_card = QFrame()
        opt_card.setObjectName("card")
        ol = QVBoxLayout(opt_card)
        ol.setContentsMargins(12, 10, 12, 10)
        ol.setSpacing(8)
        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("输出文件"))
        from PySide6.QtWidgets import QLineEdit as _QL
        self.out_edit = _QL()
        default_out = os.path.join(
            os.path.expanduser("~"), "PyCache",
            "backup_" + time.strftime("%Y%m%d_%H%M%S") + ".tar.gz")
        self.out_edit.setText(default_out)
        out_row.addWidget(self.out_edit, 1)
        ol.addLayout(out_row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        ol.addWidget(self.progress_bar)
        layout.addWidget(opt_card)

        # 日志
        from PySide6.QtWidgets import QPlainTextEdit
        log_card = QFrame()
        log_card.setObjectName("card")
        lg = QVBoxLayout(log_card)
        lg.setContentsMargins(10, 8, 10, 8)
        lg.setSpacing(4)
        lt = QLabel("执行日志")
        lt.setObjectName("hint")
        lg.addWidget(lt)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(300)
        lg.addWidget(self.log_view, 1)
        layout.addWidget(log_card, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.backup_btn = QPushButton("开始备份")
        self.backup_btn.setProperty("role", "primary")
        self.backup_btn.clicked.connect(self._backup)
        btn_row.addWidget(self.backup_btn)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        # 初始同时加载手机 + 电脑两组预设（按钮点击才单独切换）
        self.path_list.clear()
        for kind in ("phone", "desktop"):
            for p in self.presets.get(kind, []):
                self._add_item(kind, p)

    def _log(self, text):
        self.log_view.appendPlainText(text)

    def _pick_device(self):
        devices = adb_get_devices(self)
        if not devices:
            self.dev_label.setText("手机：未检测到设备")
            return
        if len(devices) == 1:
            chosen = devices[0]
        else:
            chosen = _pick_device_dialog(self, devices)
        if chosen:
            _write_selected_device(chosen)
            self.device = chosen
            self.dev_label.setText("手机：" + chosen)

    def _add_item(self, kind, path):
        item = QListWidgetItem(f"[{'手机' if kind=='phone' else '电脑'}] {path}")
        item.kind = kind
        item.path = path
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.path_list.addItem(item)

    def _apply_preset(self, kind):
        self.path_list.clear()
        # 手机预设自动补齐默认项（Pictures 等），避免旧配置缺新预设
        if kind == "phone":
            defaults = DEFAULT_PHONE_PRESETS
            merged = []
            for p in defaults + self.presets.get(kind, []):
                if p not in merged:
                    merged.append(p)
            self.presets[kind] = merged
        for p in self.presets.get(kind, []):
            self._add_item(kind, p)
        save_presets(self.presets)

    def _add_custom_path(self):
        p = self.path_input.text().strip()
        if not p:
            return
        kind = "phone" if p.startswith("/storage") or p.startswith("/sdcard") else "desktop"
        self._add_item(kind, p)
        self.path_input.clear()
        # 追加到预设持久化
        arr = self.presets.setdefault(kind, [])
        if p not in arr:
            arr.append(p)
            save_presets(self.presets)

    def _del_selected_paths(self):
        removed = []
        for it in self.path_list.selectedItems():
            removed.append((it.kind, it.path))
            self.path_list.takeItem(self.path_list.row(it))
        # 同步移除对应预设并永久保存到 core
        for kind, path in removed:
            arr = self.presets.get(kind)
            if arr and path in arr:
                arr.remove(path)
        save_presets(self.presets)

    def _set_all(self, checked):
        for i in range(self.path_list.count()):
            self.path_list.item(i).setCheckState(
                Qt.Checked if checked else Qt.Unchecked)

    def _backup(self):
        targets = []
        for i in range(self.path_list.count()):
            it = self.path_list.item(i)
            if it.checkState() == Qt.Checked:
                targets.append((it.kind, it.path))
        phone_targets = [t for t in targets if t[0] == "phone"]
        if phone_targets and not self.device:
            QMessageBox.warning(self, "提示", "选择了手机路径但未检测到设备。")
            return
        if not targets:
            QMessageBox.warning(self, "提示", "请至少勾选一个路径。")
            return
        out = self.out_edit.text().strip()
        if not out.endswith(".tar.gz"):
            out += ".tar.gz"
        self.out_edit.setText(out)
        self.backup_btn.setEnabled(False)
        self.worker = BackupWorker(targets, self.device, out)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.log.connect(self._log)
        self.worker.done.connect(self._on_done)
        self.worker.finished.connect(lambda: self.backup_btn.setEnabled(True))
        self.worker.start()

    def _on_done(self, ok, msg):
        self._log(msg)
        box = QMessageBox(self)
        box.setWindowTitle("完成" if ok else "失败")
        box.setIcon(QMessageBox.Information if ok else QMessageBox.Warning)
        box.setText(msg)
        if ok:
            box.setInformativeText("可将 .tar.gz 上传到云端保存。")
        box.exec()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.wait(3000)
        # 关闭时把当前清单按种类写回预设并保存到 core
        for kind in ("phone", "desktop"):
            items = [self.path_list.item(i) for i in range(self.path_list.count())
                     if self.path_list.item(i).kind == kind]
            if items:
                self.presets[kind] = [it.path for it in items]
        save_presets(self.presets)
        super().closeEvent(event)


def open_data_backup(self):
    dlg = BackupDialog(self)
    dlg.exec()
