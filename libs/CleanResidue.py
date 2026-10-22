# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import sys

from PySide6.QtCore import Qt, QSize, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from libs.Android import _get_runtime_paths, adb_get_devices, _write_selected_device, _pick_device_dialog


# 屏蔽词记忆缓存（存到通用缓存 core 目录，受核心清理管制）
_KW_CACHE_DIR = os.path.join(os.path.expanduser("~"), "PyCache", "core")
_KW_CACHE_FILE = os.path.join(_KW_CACHE_DIR, "clean_residue_keywords.json")


def _load_keyword_cache():
    try:
        if os.path.exists(_KW_CACHE_FILE):
            with open(_KW_CACHE_FILE, "r", encoding="utf-8") as f:
                import json as _json
                data = _json.load(f)
            if isinstance(data, dict):
                return data.get("keywords", []), data.get("scope", "both")
    except Exception:
        pass
    return [], "both"


def _save_keyword_cache(keywords, scope):
    try:
        os.makedirs(_KW_CACHE_DIR, exist_ok=True)
        import json as _json
        with open(_KW_CACHE_FILE, "w", encoding="utf-8") as f:
            _json.dump({"keywords": list(keywords), "scope": scope},
                       f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class CleanResidueThread(QThread):
    """后台清理线程，避免扫描/删除过程卡住界面"""

    log_signal = Signal(str)
    done_signal = Signal(bool, str)

    def __init__(self, kind, target=None, device=None, parent=None, keywords=None, keyword_scope="both", pending_paths=None):
        super().__init__(parent)
        self.kind = kind
        self.target = target
        self.device = device
        self.keywords = keywords or []
        self.keyword_scope = keyword_scope
        self.pending_paths = list(pending_paths) if pending_paths else []

    def _hit_keyword(self, name):
        if not self.keywords:
            return False
        low = name.lower()
        return any(kw and kw.lower() in low for kw in self.keywords)

    def _skip_file(self, name):
        return self.keyword_scope in ("file", "both") and self._hit_keyword(name)

    def _skip_dir(self, name):
        return self.keyword_scope in ("dir", "both") and self._hit_keyword(name)

    def log(self, text):
        self.log_signal.emit(text)

    def run(self):
        try:
            if self.pending_paths:
                # 用户勾选路径清理：win_file/win_dir 直接删；android 走 adb 删
                deleted = 0
                if self.kind in ("android_file", "android_dir"):
                    is_dir = self.kind == "android_dir"
                    for p in self.pending_paths:
                        cmd = "rmdir " if is_dir else "rm -f "
                        self._adb(cmd + self._shell_quote(p))
                        deleted += 1
                        self.log(("已删空文件夹 " if is_dir else "已删空文件 ") + p)
                else:
                    is_dir_kind = self.kind == "win_dir"
                    for p in self.pending_paths:
                        try:
                            if os.path.isdir(p):
                                os.rmdir(p)
                                self.log("已删空文件夹 " + p)
                            else:
                                os.remove(p)
                                self.log("已删空文件 " + p)
                            deleted += 1
                        except OSError:
                            continue
                self.done_signal.emit(True, f"清理完成，共处理 {deleted} 项。")
                return

            if self.kind == "win_file":
                deleted = self._clean_win_files()
            elif self.kind == "win_dir":
                deleted = self._clean_win_dirs()
            elif self.kind == "android_file":
                deleted = self._clean_android_files()
            elif self.kind == "android_dir":
                deleted = self._clean_android_dirs()
            elif self.kind == "smart_win":
                deleted = self._smart_win()
            elif self.kind == "smart_android":
                deleted = self._smart_android()
            else:
                deleted = 0
            self.done_signal.emit(True, f"清理完成，共处理 {deleted} 项。")
        except Exception as exc:
            self.done_signal.emit(False, f"清理失败：{exc}")

    # ---------- Windows ----------
    def _scan_win_files(self):
        """扫描空文件，返回路径列表（不删除）"""
        found = []
        for dirpath, dirnames, filenames in os.walk(self.target):
            dirnames[:] = [d for d in dirnames if not self._skip_dir(d)]
            for name in filenames:
                if self._skip_file(name):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    if os.path.isfile(full) and os.path.getsize(full) == 0:
                        found.append(full)
                except OSError:
                    continue
        return found

    def _scan_win_dirs(self):
        """扫描空文件夹，返回路径列表（不删除）"""
        found = []
        for dirpath, dirnames, filenames in os.walk(self.target, topdown=False):
            for name in dirnames:
                if self._skip_dir(name):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    if os.path.isdir(full) and not os.listdir(full):
                        found.append(full)
                except OSError:
                    continue
        return found

    def _clean_win_files(self):
        root = self.target
        deleted = 0
        for full in self._scan_win_files():
            try:
                os.remove(full)
                deleted += 1
                self.log(f"[已删空文件] {full}")
            except OSError:
                continue
        return deleted

    def _clean_win_dirs(self):
        root = self.target
        deleted = 0
        for dirpath, dirnames, filenames in os.walk(root, topdown=False):
            for name in dirnames:
                if self._skip_dir(name):
                    continue
                full = os.path.join(dirpath, name)
                try:
                    if os.path.isdir(full) and not os.listdir(full):
                        os.rmdir(full)
                        deleted += 1
                        self.log(f"[已删空文件夹] {full}")
                except OSError:
                    continue
        return deleted

    def _smart_win(self):
        self.log("智能清理：先清理空文件...")
        files = self._clean_win_files()
        self.log(f"空文件清理完成，共 {files} 个。")
        dirs = 0
        for i in range(5):
            n = self._clean_win_dirs()
            dirs += n
            if n == 0:
                self.log("空文件夹清理完成，提前结束。")
                break
        return files + dirs

    # ---------- Android ----------
    def _adb(self, shell_cmd):
        adb = _get_runtime_paths()["adb_path"]
        cmd = [adb, "-s", self.device, "shell", shell_cmd]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        return result.returncode, result.stdout, result.stderr

    # /sdcard 是软链接，toybox find 不跟随符号链接，必须用真实路径；
    # -prune 直接剪掉 Android 目录，避免进入受限目录产生权限错误刷屏
    ANDROID_ROOT = "/storage/emulated/0"

    def _adb_scan_lines(self, shell_cmd):
        """执行 find 并只保留有效路径行，丢弃 find: ... Permission denied 等错误行"""
        code, out, err = self._adb(shell_cmd)
        lines = []
        for ln in (out or "").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("find:"):
                continue
            lines.append(ln)
        return code, lines

    def _android_file_list(self):
        code, lines = self._adb_scan_lines(
            f'find {self.ANDROID_ROOT} -type d -name Android -prune -o -type f -size 0 -print'
        )
        return [ln for ln in lines if not self._skip_file(os.path.basename(ln))]

    def _android_dir_list(self):
        code, lines = self._adb_scan_lines(
            f'find {self.ANDROID_ROOT} -type d -name Android -prune -o -type d -empty -print'
        )
        if not lines:
            # 兼容不支持 -empty 的系统：遍历后用 ls -A 判断（静默，不打扰用户）
            code, lines = self._adb_scan_lines(
                f'find {self.ANDROID_ROOT} -type d -name Android -prune -o -type d -print '
                '| while read d; do if [ -z "$(ls -A "$d" 2>/dev/null)" ]; then echo "$d"; fi; done'
            )
        return [ln for ln in lines if not self._skip_dir(os.path.basename(ln))]

    def _shell_quote(self, path):
        return "'" + path.replace("'", "'\\''") + "'"

    def _clean_android_files(self):
        paths = self._android_file_list()
        if not paths:
            self.log("未发现空文件。")
            return 0
        deleted = 0
        for p in paths:
            _, out, _ = self._adb("rm -f " + self._shell_quote(p))
            deleted += 1
            self.log(f"[已删空文件] {p}")
        return deleted

    def _clean_android_dirs(self):
        paths = self._android_dir_list()
        if not paths:
            self.log("未发现空文件夹。")
            return 0
        deleted = 0
        for p in paths:
            if self._skip_dir(os.path.basename(p)):
                continue
            _, out, _ = self._adb("rmdir " + self._shell_quote(p))
            deleted += 1
            self.log(f"[已删空文件夹] {p}")
        return deleted

    def _smart_android(self):
        self.log("智能清理：先清理空文件...")
        files = self._clean_android_files()
        self.log(f"空文件清理完成，共 {files} 个。")
        dirs = 0
        for i in range(5):
            n = self._clean_android_dirs()
            dirs += n
            if n == 0:
                self.log("空文件夹清理完成，提前结束。")
                break
        return files + dirs


class ConfirmCleanDialog(QDialog):
    """卡片式二次确认窗口：替代 QMessageBox 的黄色三角+大片空白"""

    def __init__(self, parent, title, text, ok_text="确认执行"):
        super().__init__(parent)
        self.setWindowTitle(title)
        if parent and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        self.setFixedWidth(420)
        self.result_ok = False
        self.setStyleSheet(
            """
            QDialog {
                background-color: #f3f6fb;
            }
            QFrame#card {
                background-color: #ffffff;
                border: 1px solid #dfe7f3;
                border-radius: 12px;
            }
            QLabel#icon {
                font-size: 26px;
            }
            QLabel#title {
                color: #b45309;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#text {
                color: #334155;
                font-size: 13px;
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 10px 12px;
            }
            QPushButton {
                min-width: 96px;
                min-height: 36px;
                border-radius: 8px;
                background-color: #eef3fb;
                border: 1px solid #d4deee;
                color: #1f2937;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #e6eefb;
            }
            QPushButton#danger {
                background-color: #dc2626;
                border-color: #dc2626;
                color: white;
            }
            QPushButton#danger:hover {
                background-color: #b91c1c;
            }
            """
        )

        card = QFrame(self)
        card.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        icon = QLabel("⚠")
        icon.setObjectName("icon")
        head.addWidget(icon)
        t = QLabel(title)
        t.setObjectName("title")
        head.addWidget(t)
        head.addStretch()
        layout.addLayout(head)

        body = QLabel(text)
        body.setObjectName("text")
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(body)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch()
        btn_cancel = QPushButton("取消")
        btn_ok = QPushButton(ok_text)
        btn_ok.setObjectName("danger")
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)

        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self._accept_ok)

    def _accept_ok(self):
        self.result_ok = True
        self.accept()


class PathSelectDialog(QDialog):
    """清理路径勾选确认窗口：默认全选，可手动取消不想清理的路径"""

    def __init__(self, parent, paths, kind_title):
        super().__init__(parent)
        self.setWindowTitle(f"{kind_title} · 确认清理")
        if parent and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        self.setMinimumSize(560, 460)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #f3f6fb;
            }
            QFrame#card {
                background-color: #ffffff;
                border: 1px solid #dfe7f3;
                border-radius: 12px;
            }
            QLabel#title {
                font-size: 15px;
                font-weight: 700;
                color: #111827;
            }
            QLabel#hint {
                font-size: 12px;
                color: #64748b;
            }
            QListWidget {
                background-color: #fbfdff;
                border: 1px solid #dbe4f0;
                border-radius: 8px;
                color: #334155;
                font-size: 12px;
                outline: none;
            }
            QListWidget::item {
                padding: 5px 6px;
                border-bottom: 1px solid #edf2fb;
            }
            QListWidget::item:selected {
                background-color: #e7f0ff;
                color: #0f172a;
            }
            QPushButton {
                min-width: 92px;
                min-height: 34px;
                border-radius: 8px;
                background-color: #eef3fb;
                border: 1px solid #d4deee;
                color: #1f2937;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e6eefb;
            }
            QPushButton#primary {
                background-color: #2563eb;
                border-color: #2563eb;
                color: white;
            }
            QPushButton#primary:hover {
                background-color: #1d4ed8;
            }
            QPushButton#danger {
                background-color: #dc2626;
                border-color: #dc2626;
                color: white;
            }
            QPushButton#danger:hover {
                background-color: #b91c1c;
            }
            """
        )

        card = QFrame(self)
        card.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel(f"{kind_title} · 确认清理")
        title.setObjectName("title")
        layout.addWidget(title)

        hint = QLabel(f"扫描到 {len(paths)} 个目标，默认全部勾选；可取消不想清理的路径。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.path_list = QListWidget()
        for p in paths:
            item = QListWidgetItem(p)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setSizeHint(QSize(0, 30))
            self.path_list.addItem(item)
        layout.addWidget(self.path_list, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_all = QPushButton("全部勾选")
        btn_none = QPushButton("全部取消")
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        btn_row.addStretch()
        btn_cancel = QPushButton("取消")
        btn_ok = QPushButton("确认清理")
        btn_ok.setObjectName("danger")
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        btn_all.clicked.connect(lambda: self._set_all(True))
        btn_none.clicked.connect(lambda: self._set_all(False))
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)

    def _set_all(self, checked):
        for i in range(self.path_list.count()):
            self.path_list.item(i).setCheckState(
                Qt.Checked if checked else Qt.Unchecked)

    def selected_paths(self):
        out = []
        for i in range(self.path_list.count()):
            item = self.path_list.item(i)
            if item.checkState() == Qt.Checked:
                out.append(item.text())
        return out


class KeywordFilterDialog(QDialog):
    """屏蔽词设置：关键词列表 + 作用范围（文件/文件夹/两者）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("屏蔽词设置")
        self.setFixedWidth(460)
        if parent and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        self.setStyleSheet(
            """
            QDialog {
                background-color: #f3f6fb;
            }
            QFrame#card {
                background-color: #ffffff;
                border: 1px solid #dfe7f3;
                border-radius: 12px;
            }
            QLabel#title {
                font-size: 15px;
                font-weight: 700;
                color: #111827;
            }
            QLabel#hint {
                font-size: 12px;
                color: #64748b;
            }
            QPlainTextEdit {
                background-color: #f8fafc;
                border: 1px solid #dbe4f0;
                border-radius: 8px;
                color: #1f2937;
                font-size: 12px;
            }
            QCheckBox {
                background: transparent;
                font-size: 12px;
                color: #1f2937;
                spacing: 8px;
                min-height: 26px;
                padding: 2px 0px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 1px solid #cbd5e1;
                border-radius: 4px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #2563eb;
                border-color: #2563eb;
            }
            QCheckBox::indicator:disabled {
                background-color: #eef2f6;
                border-color: #d8dee8;
            }
            QCheckBox:disabled {
                color: #94a3b8;
            }
            QPushButton {
                min-width: 90px;
                min-height: 32px;
                border-radius: 8px;
                background-color: #eef3fb;
                border: 1px solid #d4deee;
                color: #1f2937;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #e6eefb;
            }
            QPushButton#primary {
                background-color: #2563eb;
                border-color: #2563eb;
                color: white;
            }
            QPushButton#primary:hover {
                background-color: #1d4ed8;
            }
            """
        )

        from PySide6.QtWidgets import QCheckBox

        card = QFrame(self)
        card.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("屏蔽词设置")
        title.setObjectName("title")
        layout.addWidget(title)

        hint = QLabel("每行一个关键词。清理时会跳过命中屏蔽词的文件或文件夹，不读取也不处理。")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.keyword_edit = QPlainTextEdit()
        self.keyword_edit.setPlaceholderText("例如：\nsystem\ntemp\n.cache")
        self.keyword_edit.setMinimumHeight(120)
        layout.addWidget(self.keyword_edit)

        scope_label = QLabel("作用范围")
        scope_label.setObjectName("hint")
        layout.addWidget(scope_label)

        from PySide6.QtWidgets import QButtonGroup

        scope_row = QHBoxLayout()
        scope_row.setSpacing(12)
        self.scope_file = QCheckBox("仅文件")
        self.scope_dir = QCheckBox("仅文件夹")
        self.scope_both = QCheckBox("文件和文件夹")
        scope_row.addWidget(self.scope_file)
        scope_row.addWidget(self.scope_dir)
        scope_row.addWidget(self.scope_both)
        scope_row.addStretch()
        layout.addLayout(scope_row)

        # 互斥：文件/文件夹自由组合 与 文件和文件夹 二选一
        self.scope_file.toggled.connect(self._sync_scope)
        self.scope_dir.toggled.connect(self._sync_scope)
        self.scope_both.toggled.connect(self._sync_scope)
        self.scope_both.setChecked(True)
        self._sync_scope()

        buttons = QHBoxLayout()
        buttons.addStretch()
        ok_btn = QPushButton("保存")
        ok_btn.setObjectName("primary")
        cancel_btn = QPushButton("取消")
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)

    def _sync_scope(self):
        both = self.scope_both.isChecked()
        self.scope_file.setEnabled(not both)
        self.scope_dir.setEnabled(not both)
        self.scope_both.setEnabled(
            not (self.scope_file.isChecked() or self.scope_dir.isChecked())
        )

    def get_keywords(self):
        text = self.keyword_edit.toPlainText()
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    def get_scope(self):
        # 返回 "file" / "dir" / "both"
        if self.scope_both.isChecked():
            return "both"
        # 前两个都勾选 = 文件和文件夹都生效
        if self.scope_file.isChecked() and self.scope_dir.isChecked():
            return "both"
        if self.scope_file.isChecked():
            return "file"
        if self.scope_dir.isChecked():
            return "dir"
        return "both"


class CleanResidueDialog(QDialog):
    """电脑手机清理残留：Windows / Android 空文件与空文件夹清理"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("电脑手机清理残留")
        self.setMinimumSize(560, 560)
        if parent and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        self.target_dir = ""
        self.device = None
        # 记忆上次屏蔽词配置
        self.keywords, self.keyword_scope = _load_keyword_cache()
        self._build_ui()
        if self.keywords:
            self.kw_status.setText(f"屏蔽词：{len(self.keywords)} 个")

    def _build_ui(self):
        self.setStyleSheet(
            """
            QDialog {
                background-color: #f3f6fb;
                color: #1f2937;
            }
            QFrame#card {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
            }
            QLabel#title {
                font-size: 16px;
                font-weight: 700;
                color: #0f172a;
            }
            QLabel#subTitle {
                font-size: 11px;
                color: #64748b;
            }
            QLabel#section {
                font-size: 12px;
                font-weight: 700;
                color: #475569;
            }
            QLabel#hint {
                font-size: 11px;
                color: #64748b;
            }
            QLabel#path {
                font-size: 11px;
                color: #334155;
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 5px 8px;
            }
            QPushButton {
                background-color: #eef2f9;
                border: 1px solid #d8e0ec;
                border-radius: 7px;
                color: #1f2937;
                padding: 6px 10px;
                min-height: 28px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e6edf9;
            }
            QPushButton[role="primary"] {
                background-color: #2563eb;
                border: 1px solid #2563eb;
                color: white;
                font-weight: 600;
            }
            QPushButton[role="primary"]:hover {
                background-color: #1d4ed8;
            }
            QPushButton[role="danger"] {
                background-color: #ef4444;
                border: 1px solid #ef4444;
                color: white;
                font-weight: 600;
            }
            QPushButton[role="danger"]:hover {
                background-color: #dc2626;
            }
            QPushButton:disabled {
                color: #94a3b8;
                background-color: #f1f5f9;
                border-color: #e2e8f0;
            }
            QPlainTextEdit {
                background-color: #fbfdff;
                border: 1px solid #dfe7f3;
                border-radius: 8px;
                color: #334155;
                font-size: 11px;
                font-family: Consolas, monospace;
            }
            QPlainTextEdit QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 2px 2px 2px 0;
            }
            QPlainTextEdit QScrollBar::handle:vertical {
                background: #c5d1e4;
                min-height: 28px;
                border-radius: 5px;
            }
            QPlainTextEdit QScrollBar::handle:vertical:hover {
                background: #afc0d8;
            }
            QPlainTextEdit QScrollBar::add-line:vertical, QPlainTextEdit QScrollBar::sub-line:vertical {
                height: 0;
            }
            QPlainTextEdit QScrollBar::add-page:vertical, QPlainTextEdit QScrollBar::sub-page:vertical {
                background: transparent;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 标题卡
        header = QFrame()
        header.setObjectName("card")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(12, 10, 12, 10)
        hl.setSpacing(2)
        title = QLabel("电脑手机清理残留")
        title.setObjectName("title")
        sub = QLabel("纯自研残留检测引擎 · 高速智能清理")
        sub.setObjectName("subTitle")
        hl.addWidget(title)
        hl.addWidget(sub)
        hl_row = QHBoxLayout()
        hl_row.addStretch()
        self.kw_btn = QPushButton("屏蔽词")
        self.kw_btn.clicked.connect(self._open_keyword_dialog)
        hl_row.addWidget(self.kw_btn)
        self.kw_status = QLabel("屏蔽词：未设置")
        self.kw_status.setObjectName("hint")
        hl_row.addWidget(self.kw_status)
        hl.addLayout(hl_row)
        layout.addWidget(header)

        # Windows 卡
        win_card = QFrame()
        win_card.setObjectName("card")
        wl = QVBoxLayout(win_card)
        wl.setContentsMargins(12, 10, 12, 10)
        wl.setSpacing(6)
        win_title = QLabel("Windows 清理")
        win_title.setObjectName("section")
        wl.addWidget(win_title)

        pick_row = QHBoxLayout()
        self.pick_btn = QPushButton("选择目录")
        self.pick_btn.clicked.connect(self._pick_dir)
        pick_row.addWidget(self.pick_btn)
        self.win_path_label = QLabel("未选择目录")
        self.win_path_label.setObjectName("path")
        self.win_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        pick_row.addWidget(self.win_path_label, 1)
        wl.addLayout(pick_row)

        win_btn_row = QHBoxLayout()
        self.win_file_btn = QPushButton("清理空文件")
        self.win_file_btn.setProperty("role", "primary")
        self.win_file_btn.clicked.connect(lambda: self._start("win_file"))
        self.win_dir_btn = QPushButton("清理空文件夹")
        self.win_dir_btn.setProperty("role", "primary")
        self.win_dir_btn.clicked.connect(lambda: self._start("win_dir"))
        self.win_smart_btn = QPushButton("智能清理")
        self.win_smart_btn.setProperty("role", "danger")
        self.win_smart_btn.clicked.connect(lambda: self._start("smart_win"))
        win_btn_row.addWidget(self.win_file_btn)
        win_btn_row.addWidget(self.win_dir_btn)
        win_btn_row.addWidget(self.win_smart_btn)
        wl.addLayout(win_btn_row)
        layout.addWidget(win_card)

        # Android 卡
        android_card = QFrame()
        android_card.setObjectName("card")
        al = QVBoxLayout(android_card)
        al.setContentsMargins(12, 10, 12, 10)
        al.setSpacing(6)
        android_title = QLabel("Android 清理 · 可以完全放心，不会有任何风险")
        android_title.setObjectName("section")
        al.addWidget(android_title)

        dev_row = QHBoxLayout()
        self.dev_btn = QPushButton("选择设备")
        self.dev_btn.clicked.connect(self._pick_device)
        dev_row.addWidget(self.dev_btn)
        self.dev_label = QLabel("未选择设备")
        self.dev_label.setObjectName("path")
        dev_row.addWidget(self.dev_label, 1)
        al.addLayout(dev_row)

        android_btn_row = QHBoxLayout()
        self.android_file_btn = QPushButton("清理空文件")
        self.android_file_btn.setProperty("role", "primary")
        self.android_file_btn.clicked.connect(lambda: self._start("android_file"))
        self.android_dir_btn = QPushButton("清理空文件夹")
        self.android_dir_btn.setProperty("role", "primary")
        self.android_dir_btn.clicked.connect(lambda: self._start("android_dir"))
        self.android_smart_btn = QPushButton("智能清理")
        self.android_smart_btn.setProperty("role", "danger")
        self.android_smart_btn.clicked.connect(lambda: self._start("smart_android"))
        android_btn_row.addWidget(self.android_file_btn)
        android_btn_row.addWidget(self.android_dir_btn)
        android_btn_row.addWidget(self.android_smart_btn)
        al.addLayout(android_btn_row)
        layout.addWidget(android_card)

        # 日志区
        log_card = QFrame()
        log_card.setObjectName("card")
        ll = QVBoxLayout(log_card)
        ll.setContentsMargins(10, 8, 10, 8)
        ll.setSpacing(4)
        log_title = QLabel("执行日志")
        log_title.setObjectName("section")
        ll.addWidget(log_title)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        ll.addWidget(self.log_view, 1)
        layout.addWidget(log_card, 1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        close_row.addWidget(close_btn)
        layout.addLayout(close_row)

        self._set_busy(False)

    def _open_keyword_dialog(self):
        dlg = KeywordFilterDialog(self)
        dlg.keyword_edit.setPlainText("\n".join(self.keywords))
        if self.keyword_scope == "file":
            dlg.scope_file.setChecked(True)
        elif self.keyword_scope == "dir":
            dlg.scope_dir.setChecked(True)
        else:
            dlg.scope_both.setChecked(True)
        dlg._sync_scope()
        if dlg.exec() == QDialog.Accepted:
            self.keywords = dlg.get_keywords()
            self.keyword_scope = dlg.get_scope()
            _save_keyword_cache(self.keywords, self.keyword_scope)
            if self.keywords:
                self.kw_status.setText(f"屏蔽词：{len(self.keywords)} 个")
            else:
                self.kw_status.setText("屏蔽词：未设置")

    def _hit_keyword(self, name):
        """判断名称是否命中屏蔽词（大小写不敏感）"""
        if not self.keywords:
            return False
        low = name.lower()
        for kw in self.keywords:
            if kw and kw.lower() in low:
                return True
        return False

    def _skip_file(self, name):
        return self.keyword_scope in ("file", "both") and self._hit_keyword(name)

    def _skip_dir(self, name):
        return self.keyword_scope in ("dir", "both") and self._hit_keyword(name)

    def _log(self, text):
        self.log_view.appendPlainText(text)

    def _styled_msg(self, title, text, level):
        """统一背景的消息框：避免 QLabel 白色背景与窗口不一致"""
        box = QMessageBox()
        box.setWindowTitle(title)
        if self and not self.windowIcon().isNull():
            box.setWindowIcon(self.windowIcon())
        box.setIcon(
            QMessageBox.Information if level == "info"
            else QMessageBox.Warning if level == "warn"
            else QMessageBox.Critical
        )
        box.setText(text)
        box.setStyleSheet(
            """
            QMessageBox {
                background-color: #f3f6fb;
            }
            QMessageBox QLabel {
                background: transparent;
                color: #334155;
                min-width: 260px;
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
        )
        return box

    def _confirm(self, title, text):
        dlg = ConfirmCleanDialog(self, title, text)
        dlg.exec()
        return dlg.result_ok

    def _set_busy(self, busy):
        for btn in (
            self.win_file_btn,
            self.win_dir_btn,
            self.win_smart_btn,
            self.android_file_btn,
            self.android_dir_btn,
            self.android_smart_btn,
        ):
            btn.setEnabled(not busy)
        self.pick_btn.setEnabled(not busy)
        self.dev_btn.setEnabled(not busy)
        self.kw_btn.setEnabled(not busy)

    def _pick_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择要清理的目录")
        if folder:
            self.target_dir = folder
            self.win_path_label.setText(folder)
            self.win_path_label.setToolTip(folder)

    def _pick_device(self):
        devices = adb_get_devices(self)
        if not devices:
            QMessageBox.warning(self, "提示", "未检测到 ADB 设备，请先连接手机并开启 USB 调试。")
            self.device = None
            self.dev_label.setText("未选择设备")
            return
        if self.device and self.device in devices:
            return
        if len(devices) == 1:
            chosen = devices[0]
        else:
            chosen = _pick_device_dialog(self, devices)
        if chosen:
            _write_selected_device(chosen)
            self.device = chosen
            self.dev_label.setText(chosen)
            self.dev_label.setToolTip(chosen)

    def _start(self, kind):
        if kind.startswith("win") and not self.target_dir:
            QMessageBox.warning(self, "提示", "请先选择要清理的 Windows 目录。")
            return
        if kind.startswith("android") or kind.startswith("smart_android"):
            self._pick_device()
            if not self.device:
                return

        # 文件/文件夹清理：先扫描出路径列表，弹勾选确认窗（默认全选可取消）
        if kind in ("win_file", "win_dir", "android_file", "android_dir"):
            self._set_busy(True)
            self._log("正在扫描待清理路径...")
            QApplication.processEvents()
            scanner = CleanResidueThread(
                kind,
                target=self.target_dir,
                device=self.device,
                keywords=list(self.keywords),
                keyword_scope=self.keyword_scope,
            )
            if kind in ("win_file", "win_dir"):
                paths = (scanner._scan_win_files() if kind == "win_file"
                         else scanner._scan_win_dirs())
                root_label = self.target_dir
            else:
                paths = (scanner._android_file_list() if kind == "android_file"
                         else scanner._android_dir_list())
                root_label = CleanResidueThread.ANDROID_ROOT
            self._set_busy(False)

            if not paths:
                self._log("未扫描到目标，无需清理。")
                box = self._styled_msg("提示", "未扫描到空文件或空文件夹，无需清理。", "info")
                box.exec()
                return

            kind_names = {
                "win_file": "Windows 空文件",
                "win_dir": "Windows 空文件夹",
                "android_file": "手机空文件",
                "android_dir": "手机空文件夹",
            }
            dlg = PathSelectDialog(self, paths, kind_names[kind])
            dlg.exec()
            selected = dlg.selected_paths()
            if not selected:
                self._log("取消清理，未选择任何路径。")
                return

            self._set_busy(True)
            self._log(f"开始清理选中的 {len(selected)} 项...")
            worker = CleanResidueThread(
                kind,
                target=self.target_dir,
                device=self.device,
                keywords=list(self.keywords),
                keyword_scope=self.keyword_scope,
                pending_paths=selected,
            )
            worker.log_signal.connect(self._log)
            worker.done_signal.connect(self._on_done)
            worker.finished.connect(lambda: self._set_busy(False))
            self._worker = worker
            worker.start()
            return

        # 智能清理：保留原有确认弹窗（带路径提示）
        if kind == "smart_win":
            title, text = "确认清理", f"将对以下路径执行智能清理：\n{self.target_dir}\n\n是否继续？"
        else:
            title, text = "确认清理", f"将对以下手机路径执行智能清理：\n{CleanResidueThread.ANDROID_ROOT}\n\n是否继续？"

        if not self._confirm(title, text):
            self._log("已取消操作。")
            return

        self._set_busy(True)
        self._log("任务启动...")
        worker = CleanResidueThread(
            kind,
            target=self.target_dir,
            device=self.device,
            keywords=list(self.keywords),
            keyword_scope=self.keyword_scope,
        )
        worker.log_signal.connect(self._log)
        worker.done_signal.connect(self._on_done)
        worker.finished.connect(lambda: self._set_busy(False))
        self._worker = worker
        worker.start()

    def _on_done(self, ok, msg):
        self._log(msg)
        box = self._styled_msg("完成" if ok else "失败", msg, "info" if ok else "warn")
        box.exec()

    def closeEvent(self, event):
        worker = getattr(self, "_worker", None)
        if worker and worker.isRunning():
            worker.wait(2000)
        super().closeEvent(event)


def open_clean_residue(self):
    dlg = getattr(self, "_clean_residue_dlg", None)
    if dlg is None:
        dlg = CleanResidueDialog(self)
        setattr(self, "_clean_residue_dlg", dlg)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
