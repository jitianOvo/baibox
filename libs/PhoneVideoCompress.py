# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import sys
import tempfile

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtWidgets import QScrollBar
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
    _read_selected_device,
    _write_selected_device,
)
from libs.dwgjx.paths import ffmpeg_path
from libs.dwgjx.constants import PRESETS, DWGJX_MARK, DWGJX_MARK_KEY, ENCODER_SUFFIX
from libs.dwgjx.compressor import has_dwgjx_mark, compress_generic_ffmpeg

VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".avi", ".wmv", ".flv", ".webm",
              ".m4v", ".ts", ".mts", ".m2ts", ".3gp", ".mpeg", ".mpg")

# 统一消息框样式：背景一致，标签透明
PVC_MSG_STYLE = """
QMessageBox {
    background-color: #f3f6fb;
}
QMessageBox QLabel {
    background: transparent;
    color: #334155;
    min-width: 300px;
}
QPushButton {
    background-color: #eef2f9;
    border: 1px solid #d8e0ec;
    border-radius: 7px;
    color: #1f2937;
    padding: 6px 14px;
    min-height: 30px;
    min-width: 80px;
}
QPushButton:hover {
    background-color: #e6edf9;
}
"""


def _adb(device, shell_cmd):
    adb = _get_runtime_paths()["adb_path"]
    r = subprocess.run(
        [adb, "-s", device, "shell", shell_cmd],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
    )
    return r.returncode, r.stdout, r.stderr


def _quote(p):
    return "'" + p.replace("'", "'\\''") + "'"


class PhoneVideoCompressDialog(QDialog):
    """手机视频一键无损压缩：扫描→勾选→预设→覆盖选择→压缩→回传"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("手机视频无损压缩")
        self.setMinimumSize(620, 640)
        if parent and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        self.device = None
        self.videos = []
        self.worker = None
        self.show_full_path = False
        self._build_ui()
        self._pick_device()
        if not os.path.exists(ffmpeg_path()):
            from libs.DwgjxLauncher import CoreDownloadDialog, _core_ready
            QMessageBox.information(self, "组件准备", "大丸压缩核心组件未就绪，需要先下载后才能使用。")
            dlg = CoreDownloadDialog(self)
            dlg.exec()

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
            QComboBox {
                background-color: #ffffff; border: 1px solid #dbe4f0;
                border-radius: 7px; padding: 4px 8px; min-height: 30px;
                color: #1f2937;
            }
            QComboBox:focus {
                border-color: #2563eb;
            }
            QComboBox::drop-down {
                border: none; width: 24px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid #64748b;
                margin-right: 6px;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                border: 1px solid #dbe4f0;
                border-radius: 8px;
                outline: none;
                padding: 4px;
            }
            QComboBox QAbstractItemView::item {
                min-height: 26px;
                padding: 2px 8px;
                color: #1f2937;
            }
            QComboBox QAbstractItemView::item:selected {
                background-color: #e7f0ff;
                color: #0f172a;
            }
            QCheckBox { font-size: 12px; color: #1f2937; spacing: 6px; }
            QPushButton {
                background-color: #eef2f9; border: 1px solid #d8e0ec;
                border-radius: 8px; color: #1f2937; padding: 6px 14px;
                min-height: 32px;
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
            QListWidget::item:hover { background-color: #f2f7ff; }
            QListWidget QScrollBar:vertical {
                background: transparent; width: 10px; margin: 2px 2px 2px 0;
            }
            QListWidget QScrollBar::handle:vertical {
                background: #c5d1e4; min-height: 28px; border-radius: 5px;
            }
            QListWidget QScrollBar::handle:vertical:hover { background: #afc0d8; }
            QListWidget QScrollBar::add-line:vertical, QListWidget QScrollBar::sub-line:vertical { height: 0; }
            QListWidget QScrollBar::add-page:vertical, QListWidget QScrollBar::sub-page:vertical { background: transparent; }
            QListWidget QScrollBar:horizontal {
                background: transparent; height: 10px; margin: 0 2px 2px 2px;
            }
            QListWidget QScrollBar::handle:horizontal {
                background: #c5d1e4; min-width: 28px; border-radius: 5px;
            }
            QListWidget QScrollBar::handle:horizontal:hover { background: #afc0d8; }
            QListWidget QScrollBar::add-line:horizontal, QListWidget QScrollBar::sub-line:horizontal { width: 0; }
            QListWidget QScrollBar::add-page:horizontal, QListWidget QScrollBar::sub-page:horizontal { background: transparent; }
            QLineEdit {
                background-color: #ffffff; border: 1px solid #dbe4f0;
                border-radius: 7px; padding: 6px 10px; color: #1f2937;
                selection-background-color: #2563eb;
            }
            QLineEdit:focus { border-color: #2563eb; }
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

        # 标题 + 设备
        header = QFrame()
        header.setObjectName("card")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 10, 12, 10)
        hl.setSpacing(8)
        tb = QVBoxLayout()
        tb.setSpacing(2)
        t = QLabel("手机视频无损压缩")
        t.setObjectName("title")
        h = QLabel("扫描手机常规目录（自动排除 /sdcard/Android），调用大丸引擎压缩")
        h.setObjectName("hint")
        tb.addWidget(t)
        tb.addWidget(h)
        hl.addLayout(tb)
        hl.addStretch()
        self.dev_label = QLabel("设备：未选择")
        self.dev_label.setObjectName("path")
        hl.addWidget(self.dev_label)
        layout.addWidget(header)

        # 扫描卡
        scan_card = QFrame()
        scan_card.setObjectName("card")
        sl = QVBoxLayout(scan_card)
        sl.setContentsMargins(12, 10, 12, 10)
        sl.setSpacing(8)
        scan_row = QHBoxLayout()
        self.scan_btn = QPushButton("扫描手机视频")
        self.scan_btn.setProperty("role", "primary")
        self.scan_btn.clicked.connect(self._scan)
        scan_row.addWidget(self.scan_btn)
        self.scan_info = QLabel("尚未扫描")
        self.scan_info.setObjectName("hint")
        scan_row.addWidget(self.scan_info)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索视频名称…")
        self.search_edit.setMaximumWidth(180)
        self.search_edit.textChanged.connect(self._apply_search)
        scan_row.addWidget(self.search_edit)
        self.search_clear_btn = QPushButton("✕")
        self.search_clear_btn.setFixedWidth(30)
        self.search_clear_btn.setToolTip("清空搜索，恢复完整列表")
        self.search_clear_btn.clicked.connect(self._clear_search)
        scan_row.addWidget(self.search_clear_btn)
        sl.addLayout(scan_row)
        self.video_list = QListWidget()
        self.video_list.setMinimumHeight(200)
        # 长路径可横向拖动查看最右侧；始终保留底部横向滚动条
        self.video_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.video_list.setTextElideMode(Qt.ElideNone)
        sl.addWidget(self.video_list, 1)
        # 列表底部的横向滚动条（独立控件，避免被布局压缩掉）
        self.h_scroll = QScrollBar(Qt.Horizontal)
        self.h_scroll.setMaximum(0)
        self.video_list.horizontalScrollBar().valueChanged.connect(self.h_scroll.setValue)
        self.h_scroll.valueChanged.connect(self.video_list.horizontalScrollBar().setValue)
        self.video_list.horizontalScrollBar().rangeChanged.connect(
            lambda mn, mx: self.h_scroll.setRange(mn, mx))
        self.video_list.horizontalScrollBar().rangeChanged.connect(
            lambda mn, mx: self.h_scroll.setVisible(mx > mn))
        sl.addWidget(self.h_scroll)

        # 显示完整路径开关
        path_row = QHBoxLayout()
        self.path_switch = QPushButton("显示完整路径")
        self.path_switch.setCheckable(True)
        self.path_switch.clicked.connect(self._toggle_path)
        path_row.addWidget(self.path_switch)
        path_row.addStretch()
        sl.addLayout(path_row)
        btn_row = QHBoxLayout()
        btn_all = QPushButton("全部勾选")
        btn_none = QPushButton("全部取消")
        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch()
        sl.addLayout(btn_row)
        layout.addWidget(scan_card)

        # 预设 + 覆盖
        opt_card = QFrame()
        opt_card.setObjectName("card")
        ol = QHBoxLayout(opt_card)
        ol.setContentsMargins(12, 10, 12, 10)
        ol.setSpacing(8)
        ol.addWidget(QLabel("预设"))
        self.preset_box = QComboBox()
        for p in PRESETS:
            self.preset_box.addItem(p["name"])
        ol.addWidget(self.preset_box, 1)
        self.overwrite_check = QCheckBox("覆盖到手机原路径（删除原文件）")
        self.overwrite_check.setChecked(False)
        ol.addWidget(self.overwrite_check)
        layout.addWidget(opt_card)

        # 进度
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 日志
        log_card = QFrame()
        log_card.setObjectName("card")
        ll = QVBoxLayout(log_card)
        ll.setContentsMargins(10, 8, 10, 8)
        ll.setSpacing(4)
        lt = QLabel("执行日志")
        lt.setObjectName("hint")
        ll.addWidget(lt)
        from PySide6.QtWidgets import QPlainTextEdit
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(400)
        ll.addWidget(self.log_view, 1)
        layout.addWidget(log_card, 1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        self.compress_btn = QPushButton("开始压缩")
        self.compress_btn.setProperty("role", "danger")
        self.compress_btn.clicked.connect(self._compress)
        close_row.addWidget(self.compress_btn)
        self.replace_btn = QPushButton("一键替换同路径")
        self.replace_btn.setProperty("role", "primary")
        self.replace_btn.setToolTip("保留同目录下体积最小的 _av/_x265/_hv 压缩版本，删除原文件与其余版本")
        self.replace_btn.clicked.connect(self._replace_existing)
        close_row.addWidget(self.replace_btn)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self.video_list.itemChanged.connect(self._on_item_changed)
        self._set_busy(False)

    def _on_item_changed(self, item):
        """用户直接勾选/取消时同步到全量勾选状态"""
        path = item.data(Qt.UserRole)
        if path and path in self._checked:
            self._checked[path] = (item.checkState() == Qt.Checked)

    def _log(self, text):
        self.log_view.appendPlainText(text)

    def _set_busy(self, busy):
        self.scan_btn.setEnabled(not busy)
        self.compress_btn.setEnabled(not busy)
        self.replace_btn.setEnabled(not busy)
        self.preset_box.setEnabled(not busy)
        self.overwrite_check.setEnabled(not busy)

    def _pick_device(self):
        devices = adb_get_devices(self)
        if not devices:
            QMessageBox.warning(self, "提示", "未检测到 ADB 设备，请先连接手机并开启 USB 调试。")
            return
        if len(devices) == 1:
            chosen = devices[0]
        else:
            chosen = _pick_device_dialog(self, devices)
        if chosen:
            _write_selected_device(chosen)
            self.device = chosen
            self.dev_label.setText("设备：" + chosen)

    def _adb(self, shell_cmd):
        return _adb(self.device, shell_cmd)

    def _scan(self):
        if not self.device:
            self._pick_device()
            if not self.device:
                return
        self._log("正在扫描手机视频...")
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        # 一次取回「大小|路径」，并排除 /sdcard/Android
        ext_conditions = []
        for ext in VIDEO_EXTS:
            ext_conditions.append(
                f'-o -type f -iname "*{ext}" -exec stat -c \'%s|%n\' {{}} \\; '
            )
        cmd = (
            'find /storage/emulated/0 -type d -name Android -prune '
            + "".join(ext_conditions)
        ).rstrip()
        code, out, _ = self._adb(cmd)
        items = []
        for line in (out or "").splitlines():
            line = line.strip()
            if not line or line.startswith("find:") or "|" not in line:
                continue
            size_str, path = line.split("|", 1)
            path = path.strip()
            if not path.lower().endswith(VIDEO_EXTS):
                continue
            try:
                size_mb = int(size_str) / 1024 / 1024
            except ValueError:
                size_mb = 0.0
            items.append((path, size_mb))

        # 全量列表 + 默认全勾选
        self.videos = [p for p, _ in items]
        self._size_map = {p: s for p, s in items}
        self._checked = {p: False for p in self.videos}
        self._rebuild_list()
        self.scan_info.setText(f"找到 {len(self.videos)} 个视频")
        self._log(f"扫描完成：{len(self.videos)} 个视频（已排除 /sdcard/Android）")

    def _fmt_size(self, mb):
        if mb >= 1000:
            return f"{mb/1024:.2f} GB"
        return f"{mb:.1f} MB"

    def _rebuild_list(self):
        """按当前搜索关键词重建列表，勾选状态取 _checked"""
        kw = (self.search_edit.text() or "").strip().lower()
        self.video_list.clear()
        for p in self.videos:
            if kw and kw not in os.path.basename(p).lower():
                continue
            size_mb = self._size_map.get(p, 0.0)
            if self.show_full_path:
                label = f"{p}    {self._fmt_size(size_mb)}"
            else:
                label = f"{os.path.basename(p)}    {self._fmt_size(size_mb)}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, p)
            item.setToolTip(p)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if self._checked.get(p, True) else Qt.Unchecked)
            item.setSizeHint(QSize(0, 30))
            self.video_list.addItem(item)

    def _toggle_path(self, checked):
        self.show_full_path = checked
        self._rebuild_list()

    def _apply_search(self):
        self._rebuild_list()

    def _clear_search(self):
        self.search_edit.clear()
        self._rebuild_list()

    def _set_all(self, checked):
        for p in self.videos:
            self._checked[p] = checked
        self._rebuild_list()

    def _selected(self):
        # 勾选状态以全量 _checked 为准（搜索只是临时定位显示）
        return [p for p in self.videos if self._checked.get(p, False)]

    def _compress(self):
        if not self.device:
            QMessageBox.warning(self, "提示", "请先连接设备。")
            return
        paths = self._selected()
        if not paths:
            QMessageBox.warning(self, "提示", "请至少勾选一个视频。")
            return
        if not os.path.exists(ffmpeg_path()):
            # 自动下载大丸压缩核心组件（与「大丸视频压缩」共用下载流程）
            from libs.DwgjxLauncher import CoreDownloadDialog, _core_ready
            QMessageBox.information(self, "组件准备", "大丸压缩核心组件未就绪，需要先下载后才能使用。")
            dlg = CoreDownloadDialog(self)
            dlg.exec()
            if not _core_ready():
                return
        preset = PRESETS[self.preset_box.currentIndex()]
        overwrite = self.overwrite_check.isChecked()
        self._set_busy(True)
        self._log(f"开始压缩 {len(paths)} 个视频（预设：{preset['name']}）")
        self.worker = CompressWorker(paths, preset, overwrite, self.device, self._size_map)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.log.connect(self._log)
        self.worker.summary.connect(self._show_summary)
        self.worker.done.connect(self._on_done)
        self.worker.finished.connect(lambda: self._set_busy(False))
        self.worker.start()

    def _on_done(self, msg, ok):
        self.progress_bar.setValue(100)
        self._log(msg)
        box = QMessageBox(self)
        box.setWindowTitle("完成" if ok else "失败")
        box.setIcon(QMessageBox.Information if ok else QMessageBox.Warning)
        box.setText(msg)
        box.setStyleSheet(PVC_MSG_STYLE)
        box.exec()

    def _show_summary(self, results):
        """压缩/替换共用的数据整理：总体积、压缩率、省去大小"""
        if not results:
            return
        total_orig = sum(r.get("orig", 0) for r in results)
        total_final = sum(r.get("final", 0) for r in results)
        saved = total_orig - total_final
        ratio = (saved / total_orig * 100) if total_orig else 0
        text = (
            f"本轮作用视频总体积：{self._fmt_size(total_orig)}\n"
            f"压缩后总体积：{self._fmt_size(total_final)}\n"
            f"压缩率：{ratio:.1f}%\n"
            f"省去大小：{self._fmt_size(saved)}"
        )
        box = QMessageBox(self)
        box.setWindowTitle("数据整理")
        box.setIcon(QMessageBox.Information)
        box.setText(text)
        box.setStyleSheet(PVC_MSG_STYLE)
        box.exec()

    def _replace_existing(self):
        """一键替换同路径：保留体积最小的压缩版本，删除原文件与其余版本"""
        if not self.device:
            QMessageBox.warning(self, "提示", "请先连接设备。")
            return
        paths = self._selected()
        if not paths:
            QMessageBox.warning(self, "提示", "请先勾选需要替换的视频。")
            return
        if self.worker and self.worker.isRunning():
            QMessageBox.warning(self, "提示", "当前有任务正在执行，请稍候。")
            return
        box = QMessageBox(self)
        box.setWindowTitle("确认替换")
        box.setIcon(QMessageBox.Question)
        box.setText(
            f"将对勾选的 {len(paths)} 个视频执行一键替换：\n"
            "保留同目录下体积最小的 _av/_x265/_hv 压缩版本，\n"
            "删除原文件及其余压缩版本。是否继续？"
        )
        box.setStyleSheet(PVC_MSG_STYLE)
        ok_btn = box.addButton("确认替换", QMessageBox.AcceptRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() != ok_btn:
            return
        self._set_busy(True)
        self._log(f"开始一键替换 {len(paths)} 个视频...")
        self.worker = ReplaceWorker(paths, self.device)
        self.worker.progress.connect(self.progress_bar.setValue)
        self.worker.log.connect(self._log)
        self.worker.summary.connect(self._show_summary)
        self.worker.done.connect(self._on_done)
        self.worker.finished.connect(lambda: self._set_busy(False))
        self.worker.start()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.wait(3000)
        super().closeEvent(event)


class CompressWorker(QThread):
    progress = Signal(int)
    log = Signal(str)
    done = Signal(str, bool)
    summary = Signal(list)

    def __init__(self, paths, preset, overwrite, device, size_map):
        super().__init__()
        self.paths = paths
        self.preset = preset
        self.overwrite = overwrite
        self.device = device
        self.size_map = size_map

    def run(self):
        self.results = []
        try:
            total = len(self.paths)
            for idx, src in enumerate(self.paths):
                # 跳过已带大丸标识的视频（防二次压缩）
                if has_dwgjx_mark(src) or self._remote_has_mark(src):
                    self.log.emit(f"跳过（已压缩过）：{src}")
                    self._record_remote(src)
                    self.progress.emit(int((idx + 1) / total * 100))
                    continue
                # 拉到本地临时目录
                tmp_dir = tempfile.mkdtemp(prefix="dwgjx_phone_")
                local_src = os.path.join(tmp_dir, os.path.basename(src))
                self.log.emit(f"拉取：{src}")
                code = self._pull(src, local_src)
                if code != 0:
                    self.log.emit(f"拉取失败：{src}")
                    continue

                # 压缩
                from pathlib import Path
                output_dir = Path(tmp_dir)
                params = dict(self.preset["params"])
                params["suffix"] = "mp4"
                encoder = self.preset["encoder"]
                name_suffix = {
                    "av1": "_av", "x265": "_x265", "nvenc_h265": "_hv",
                }.get(encoder, "")
                stem = os.path.splitext(os.path.basename(local_src))[0]
                out_name = f"{stem}{name_suffix}.mp4"
                self.log.emit(f"压缩中：{os.path.basename(src)}")
                compress_generic_ffmpeg(
                    [Path(local_src)],
                    output_dir,
                    codec=self._codec(encoder),
                    encoder_key=encoder,
                    on_progress=lambda p, i, t: self.progress.emit(
                        int(((idx + p / 100.0) / total) * 100)),
                    cq=params.get("cq"),
                    crf=params.get("crf"),
                    preset=params.get("preset", "p5"),
                    suffix="mp4",
                )
                local_out = os.path.join(tmp_dir, out_name)
                if not os.path.exists(local_out):
                    self.log.emit(f"压缩失败（无输出）：{src}")
                    continue

                # 回传手机
                remote_dir = src.rsplit("/", 1)[0]
                final_mb = os.path.getsize(local_out) / 1024 / 1024
                if self.overwrite:
                    self.log.emit(f"覆盖原路径：{src}")
                    self._push(local_out, src)
                    self._rm(src)
                else:
                    # 远程路径必须用正斜杠拼接（os.path.join 在 Windows 会输出反斜杠导致 adb 转义失败）
                    remote_out = remote_dir.rstrip("/") + "/" + out_name
                    self.log.emit(f"回传（保留原文件）：{remote_out}")
                    self._push(local_out, remote_out)
                self.results.append({
                    "src": src,
                    "orig": self.size_map.get(src, final_mb),
                    "final": final_mb,
                })
                self.progress.emit(int((idx + 1) / total * 100))
                shutil.rmtree(tmp_dir, ignore_errors=True)
            if self.results:
                self.summary.emit(self.results)
            self.done.emit(f"压缩完成，共处理 {total} 个视频。", True)
        except Exception as exc:
            self.done.emit(f"压缩失败：{exc}", False)

    def _codec(self, encoder):
        return {
            "av1": "av1_nvenc", "x265": "libx265", "nvenc_h265": "nvenc_h265",
        }.get(encoder, "libx265")

    def _remote_has_mark(self, remote_path):
        # 用 ffmpeg -i 无法直接读远端，改为先拉到本地临时再检查太重；
        # 通过文件名后缀 + 元数据策略：已压缩输出带 _av/_x265/_hv 后缀，且覆盖模式会删除源。
        base = os.path.basename(remote_path).lower()
        return base.endswith("_av.mp4") or base.endswith("_x265.mp4") or base.endswith("_hv.mp4")

    def _record_remote(self, remote):
        adb = _get_runtime_paths()["adb_path"]
        try:
            r = subprocess.run(
                [adb, "-s", self.device, "shell", "stat", "-c", "%s", _quote(remote)],
                capture_output=True, text=True, errors="ignore")
            size_b = int((r.stdout or "").strip())
        except Exception:
            size_b = 0
        mb = size_b / 1024 / 1024
        self.results.append({"src": remote, "orig": mb, "final": mb})

    def _pull(self, remote, local):
        adb = _get_runtime_paths()["adb_path"]
        r = subprocess.run([adb, "-s", self.device, "pull", remote, local],
                           capture_output=True, text=True, errors="ignore")
        return r.returncode

    def _push(self, local, remote):
        adb = _get_runtime_paths()["adb_path"]
        r = subprocess.run([adb, "-s", self.device, "push", local, remote],
                           capture_output=True, text=True, errors="ignore")
        return r.returncode

    def _rm(self, remote):
        self._adb_rm(remote)

    def _adb_rm(self, remote):
        adb = _get_runtime_paths()["adb_path"]
        subprocess.run([adb, "-s", self.device, "shell", "rm", "-f", remote],
                       capture_output=True, text=True, errors="ignore")


class ReplaceWorker(QThread):
    """一键替换线程：adb 远端操作，避免卡 UI"""

    progress = Signal(int)
    log = Signal(str)
    done = Signal(str, bool)
    summary = Signal(list)

    def __init__(self, paths, device):
        super().__init__()
        self.paths = paths
        self.device = device

    def run(self):
        results = []
        try:
            total = len(self.paths)
            for idx, src in enumerate(self.paths):
                base = os.path.basename(src)
                stem = os.path.splitext(base)[0]
                d = src.rsplit("/", 1)[0]
                candidates = [
                    d + "/" + stem + s + ".mp4"
                    for s in ENCODER_SUFFIX.values()
                ]
                sizes = {}
                for c in candidates:
                    mb = self._remote_size(c)
                    if mb is not None:
                        sizes[c] = mb
                orig_mb = self._remote_size(src)
                if orig_mb is None:
                    orig_mb = 0
                if not sizes:
                    self.log.emit(f"跳过（未找到压缩版本）：{src}")
                    continue
                best = min(sizes, key=sizes.get)
                for c in sizes:
                    if c != best:
                        self._rm(c)
                self._rm(src)
                self._mv(best, src)
                results.append({
                    "src": src,
                    "orig": orig_mb + sum(sizes.values()),
                    "final": sizes[best],
                })
                self.log.emit(
                    f"已替换（保留 {os.path.basename(best)}）：{src}")
                self.progress.emit(int((idx + 1) / total * 100))
            if results:
                self.summary.emit(results)
            self.done.emit(
                f"一键替换完成，共处理 {len(results)} 个视频。", True)
        except Exception as exc:
            self.done.emit(f"一键替换失败：{exc}", False)

    def _remote_size(self, remote):
        adb = _get_runtime_paths()["adb_path"]
        try:
            r = subprocess.run(
                [adb, "-s", self.device, "shell", "stat", "-c", "%s", _quote(remote)],
                capture_output=True, text=True, errors="ignore")
            return int((r.stdout or "").strip()) / 1024 / 1024
        except Exception:
            return None

    def _rm(self, remote):
        adb = _get_runtime_paths()["adb_path"]
        subprocess.run(
            [adb, "-s", self.device, "shell", "rm", "-f", _quote(remote)],
            capture_output=True, text=True, errors="ignore")

    def _mv(self, old, new):
        adb = _get_runtime_paths()["adb_path"]
        subprocess.run(
            [adb, "-s", self.device, "shell", "mv", _quote(old), _quote(new)],
            capture_output=True, text=True, errors="ignore")


def open_phone_video_compress(self):
    dlg = getattr(self, "_pvc_dlg", None)
    if dlg is None:
        dlg = PhoneVideoCompressDialog(self)
        setattr(self, "_pvc_dlg", dlg)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
