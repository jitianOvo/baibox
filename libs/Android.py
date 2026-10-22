import os
import re
import shutil
import subprocess
import sys
from core_lib import get_path
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import (
    QLabel, QMessageBox, QListWidget, QListWidgetItem, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QCheckBox, QPushButton, QScrollArea, QLineEdit, QFileDialog, QComboBox
)
from PySide6 import QtWidgets, QtGui, QtCore

_RUNTIME_PATHS_CACHE = None
_RUNTIME_ADBFASTBOOT_DIR = None
_ADB_SERVER_WARMED = False


def set_qt_application_attribute(attr_name):
    """
    Qt5 -> Qt6 兼容辅助：
    若 QApplication 已创建，Qt6 下这些属性无法再安全设置，直接忽略即可。
    """
    app = QtWidgets.QApplication.instance()
    enum_val = None
    if hasattr(QtCore.Qt, "ApplicationAttribute"):
        enum_val = getattr(QtCore.Qt.ApplicationAttribute, attr_name, None)
    if enum_val is None:
        enum_val = getattr(QtCore.Qt, attr_name, None)
    if enum_val is None:
        return False
    if app is None:
        QtWidgets.QApplication.setAttribute(enum_val)
        return True
    return False
def _build_dialog_font(point_size=11, weight=QFont.Normal):
    font = QFont("Microsoft YaHei UI", point_size, weight)
    style_hint_enum = getattr(QFont, "StyleHint", None)
    if style_hint_enum is not None and hasattr(style_hint_enum, "System"):
        font.setStyleHint(style_hint_enum.System)

    style_strategy_enum = getattr(QFont, "StyleStrategy", None)
    if style_strategy_enum is not None and hasattr(style_strategy_enum, "PreferAntialias"):
        style_strategy = style_strategy_enum.PreferAntialias
        for name in ("PreferOutline", "PreferQuality"):
            if hasattr(style_strategy_enum, name):
                style_strategy |= getattr(style_strategy_enum, name)
        if hasattr(style_strategy_enum, "ForceIntegerMetrics"):
            style_strategy |= style_strategy_enum.ForceIntegerMetrics
        font.setStyleStrategy(style_strategy)

    hinting_enum = getattr(QFont, "HintingPreference", None)
    if hinting_enum is not None:
        if hasattr(hinting_enum, "PreferFullHinting"):
            font.setHintingPreference(hinting_enum.PreferFullHinting)
        elif hasattr(hinting_enum, "PreferVerticalHinting"):
            font.setHintingPreference(hinting_enum.PreferVerticalHinting)
    return font


def _get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_writable_base_dir():
    if not getattr(sys, "frozen", False):
        return _get_base_dir()
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return os.path.join(local_appdata, "超级白工具箱")
    return _get_base_dir()


def _copy_file_if_needed(src_path, dst_path):
    if not os.path.isfile(src_path):
        return False

    if os.path.isfile(dst_path):
        src_stat = os.stat(src_path)
        dst_stat = os.stat(dst_path)
        if src_stat.st_size == dst_stat.st_size and int(src_stat.st_mtime) == int(dst_stat.st_mtime):
            return False

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    shutil.copy2(src_path, dst_path)
    return True


def _prepare_runtime_adbfastboot_dir():
    global _RUNTIME_ADBFASTBOOT_DIR
    if _RUNTIME_ADBFASTBOOT_DIR and os.path.isdir(_RUNTIME_ADBFASTBOOT_DIR):
        return _RUNTIME_ADBFASTBOOT_DIR

    if not getattr(sys, "frozen", False):
        return None

    src_dir = os.path.dirname(get_path("tools/adb-fastboot/adb.exe"))
    if not os.path.isdir(src_dir):
        return None

    dst_dir = os.path.join(_get_writable_base_dir(), "runtime", "adb-fastboot")
    os.makedirs(dst_dir, exist_ok=True)

    for name in os.listdir(src_dir):
        src = os.path.join(src_dir, name)
        dst = os.path.join(dst_dir, name)
        if os.path.isfile(src):
            _copy_file_if_needed(src, dst)

    _RUNTIME_ADBFASTBOOT_DIR = dst_dir
    return dst_dir


def _resolve_tool_path(relative_path, fallback_cmd):
    normalized = relative_path.replace("\\", "/")
    if normalized.startswith("tools/adb-fastboot/"):
        runtime_dir = _prepare_runtime_adbfastboot_dir()
        if runtime_dir:
            runtime_tool = os.path.join(runtime_dir, os.path.basename(normalized))
            if os.path.isfile(runtime_tool):
                return runtime_tool

    candidates = [
        get_path(normalized),  # 开发态项目目录 / 打包态 _MEIPASS
        os.path.join(_get_base_dir(), *normalized.split("/")),  # exe 同级目录兜底
    ]
    seen = set()
    for candidate in candidates:
        if not candidate:
            continue
        norm = os.path.normpath(candidate)
        if norm in seen:
            continue
        seen.add(norm)
        if os.path.isfile(norm):
            return norm
    return fallback_cmd  # 最后兜底系统 PATH（如已安装 adb/fastboot）


def _get_runtime_paths():
    global _RUNTIME_PATHS_CACHE
    if _RUNTIME_PATHS_CACHE is not None:
        return _RUNTIME_PATHS_CACHE

    base_dir = _get_base_dir()
    writable_base = _get_writable_base_dir()
    data_dir = os.path.join(writable_base, "data")
    cache_dir = os.path.join(data_dir, "cache")
    _RUNTIME_PATHS_CACHE = {
        "base_dir": base_dir,
        "writable_base": writable_base,
        "data_dir": data_dir,
        "cache_dir": cache_dir,
        "devices_path": os.path.join(cache_dir, "devices.txt"),
        "my_devices_path": os.path.join(cache_dir, "my_devices.txt"),
        "adb_path": _resolve_tool_path("tools/adb-fastboot/adb.exe", "adb"),
        "fastboot_path": _resolve_tool_path("tools/adb-fastboot/fastboot.exe", "fastboot"),
    }
    return _RUNTIME_PATHS_CACHE
def _read_selected_device():
    paths = _get_runtime_paths()
    device_file = paths["my_devices_path"]
    if not os.path.exists(device_file):
        return None
    try:
        with open(device_file, "r", encoding="utf-8") as f:
            value = f.read().strip()
            return value or None
    except Exception:
        return None
def _write_selected_device(device_id):
    paths = _get_runtime_paths()
    os.makedirs(paths["cache_dir"], exist_ok=True)
    with open(paths["my_devices_path"], "w", encoding="utf-8") as f:
        f.write(device_id.strip())
def _pick_device_dialog(parent, devices):
    dialog = QDialog(parent)
    dialog.setWindowTitle("选择设备")
    dialog.setMinimumSize(360, 280)
    if parent and not parent.windowIcon().isNull():
        dialog.setWindowIcon(parent.windowIcon())

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(10)

    title = QLabel("请选择要使用的设备")
    title.setAlignment(Qt.AlignCenter)
    title.setStyleSheet("font-size: 15px; font-weight: bold;")
    layout.addWidget(title)

    selected = {"value": None}

    for dev in devices:
        btn = QPushButton(dev)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            """
            QPushButton {
                padding: 9px 10px;
                border-radius: 6px;
                background: #F4F4F4;
                border: 1px solid #CCCCCC;
                text-align: center;
            }
            QPushButton:hover {
                background: #E7F0FF;
            }
            """
        )
        btn.clicked.connect(lambda _, d=dev: (selected.update({"value": d}), dialog.accept()))
        layout.addWidget(btn)

    cancel = QPushButton("取消")
    cancel.clicked.connect(dialog.reject)
    layout.addWidget(cancel)

    if dialog.exec() == QDialog.Accepted:
        return selected["value"]
    return None


def _tool_exists(tool_path):
    return tool_path and (
        os.path.isfile(tool_path) or os.path.basename(tool_path).lower() in ("adb", "adb.exe", "fastboot", "fastboot.exe")
    )


def _show_missing_tool_message(parent, tool_name, configured_path):
    hint = configured_path or "（空）"
    ConfirmDialog(
        parent,
        "错误提示",
        f"未找到 {tool_name} 可执行文件。\n当前路径：{hint}\n请检查打包是否包含 tools/adb-fastboot 目录。",
    ).exec_confirm()


def _warmup_adb_server():
    global _ADB_SERVER_WARMED
    if _ADB_SERVER_WARMED:
        return

    paths = _get_runtime_paths()
    adb_path = paths["adb_path"]
    if not _tool_exists(adb_path):
        return

    try:
        subprocess.run(
            [adb_path, "start-server"],
            shell=False,
            timeout=4,
            capture_output=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return

    _ADB_SERVER_WARMED = True
def _ensure_adb_target(parent=None, action_name="该功能"):
    devices = adb_get_devices(parent)
    if not devices:
        if parent:
            ConfirmDialog(parent, "错误提示", f"未检测到 ADB 设备，无法执行：{action_name}").exec_confirm()
        return None

    selected = _read_selected_device()
    if selected and selected in devices:
        return selected

    if len(devices) == 1:
        _write_selected_device(devices[0])
        return devices[0]

    chosen = _pick_device_dialog(parent, devices) if parent else None
    if chosen:
        _write_selected_device(chosen)
        return chosen

    if parent:
        ConfirmDialog(parent, "提示", f"检测到多个设备，请先完成设备选择后再执行：{action_name}").exec_confirm()
    return None
def _resolve_target_for_fastboot(parent=None, action_name="该功能"):
    """
    fastboot动作优先沿用已选序列号；
    若还未选过，则尝试从当前ADB设备中引导选择一次。
    """
    selected = _read_selected_device()
    if selected:
        return selected
    return _ensure_adb_target(parent, action_name)


def _adb_run_raw(args, device=None, timeout=12):
    if not isinstance(args, list):
        args = [args]
    paths = _get_runtime_paths()
    _warmup_adb_server()
    adb_path = paths["adb_path"]
    if not _tool_exists(adb_path):
        raise FileNotFoundError(adb_path)

    cmd = [adb_path]
    if device:
        cmd += ["-s", device]
    cmd += args
    return subprocess.run(
        cmd,
        shell=False,
        timeout=timeout,
        capture_output=True,
        encoding="utf-8",
        errors="ignore",
    )


def _extract_wireless_ip_from_route(route_text):
    if not route_text:
        return None
    lines = [line.strip() for line in route_text.splitlines() if line.strip()]
    src_pattern = re.compile(r"\bsrc\s+(\d{1,3}(?:\.\d{1,3}){3})\b")

    for line in lines:
        if "dev ccmni1" in line:
            match = src_pattern.search(line)
            if match:
                return match.group(1)

    for line in lines:
        match = src_pattern.search(line)
        if match:
            return match.group(1)

    return None


def _resolve_usb_target_for_wireless(parent=None):
    devices = adb_get_devices(parent) or []
    usb_devices = [d for d in devices if ":" not in d and not d.startswith("emulator-")]
    if not usb_devices:
        if parent:
            ConfirmDialog(parent, "错误提示", "未检测到可用于无线连接的 USB 设备，请先插线并开启USB调试。").exec_confirm()
        return None

    selected = _read_selected_device()
    if selected and selected in usb_devices:
        return selected

    if len(usb_devices) == 1:
        return usb_devices[0]

    chosen = _pick_device_dialog(parent, usb_devices) if parent else None
    if chosen:
        _write_selected_device(chosen)
    return chosen


def _normalize_adb_target(target):
    if not target:
        return None
    value = target.strip()
    if not value:
        return None
    if ":" in value:
        return value
    return f"{value}:5555"
def _ask_directory_with_input(parent, title, tip_text, default_path="D:/backup"):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumSize(520, 190)
    if parent and not parent.windowIcon().isNull():
        dialog.setWindowIcon(parent.windowIcon())

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)

    tip = QLabel(tip_text)
    tip.setWordWrap(True)
    layout.addWidget(tip)

    row = QHBoxLayout()
    path_edit = QLineEdit(default_path)
    browse = QPushButton("选择目录")
    row.addWidget(path_edit, 1)
    row.addWidget(browse)
    layout.addLayout(row)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    ok_btn = QPushButton("确定")
    cancel_btn = QPushButton("取消")
    btn_row.addWidget(ok_btn)
    btn_row.addWidget(cancel_btn)
    layout.addLayout(btn_row)

    def do_browse():
        selected = QFileDialog.getExistingDirectory(parent, "选择目录", path_edit.text().strip() or default_path)
        if selected:
            path_edit.setText(selected)

    browse.clicked.connect(do_browse)
    ok_btn.clicked.connect(dialog.accept)
    cancel_btn.clicked.connect(dialog.reject)

    if dialog.exec() != QDialog.Accepted:
        return None

    value = path_edit.text().strip()
    if not value:
        QMessageBox.warning(parent, "提示", "目录不能为空")
        return None
    return value

# 镜像选择窗口
class CheckListDialog(QDialog):
    def __init__(self, parent=None, data_list=None, title="请选择镜像文件", font_size=9):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(500, 400)

        # 自动继承父窗口图标
        if parent and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())

        self.data_list = data_list or []
        self.vars_list = []
        self.columns = 4  # 固定4列
        self.choose = []  # 勾选结果
        self.result = False  # 返回 True/False

        main_layout = QVBoxLayout(self)

        # 显示总条目数量
        self.label_count = QLabel(f"总条目: {len(self.data_list)}")
        main_layout.addWidget(self.label_count)

        # 字体设置
        self.font = QFont()
        self.font.setPointSize(font_size)

        # 顶部快捷按钮
        btn_layout = QHBoxLayout()
        btn_select_all = QPushButton("全选")
        btn_select_all.setFont(self.font)
        btn_select_all.setMinimumHeight(25)
        btn_select_all.clicked.connect(self.select_all)

        btn_invert = QPushButton("反选")
        btn_invert.setFont(self.font)
        btn_invert.setMinimumHeight(25)
        btn_invert.clicked.connect(self.invert_selection)

        btn_clear = QPushButton("全取消")
        btn_clear.setFont(self.font)
        btn_clear.setMinimumHeight(25)
        btn_clear.clicked.connect(self.clear_all)

        btn_layout.addWidget(btn_select_all)
        btn_layout.addWidget(btn_invert)
        btn_layout.addWidget(btn_clear)
        main_layout.addLayout(btn_layout)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QGridLayout(scroll_content)
        scroll_layout.setSpacing(4)  # 间距小
        scroll_layout.setContentsMargins(4, 4, 4, 4)

        # 添加checkbox到网格布局
        for index, item in enumerate(self.data_list):
            chk = QCheckBox(item)
            chk.setFont(self.font)
            chk.setStyleSheet("QCheckBox::indicator { width: 16px; height: 16px; }")  # 勾选框稍小
            chk.setChecked(True)
            row = index // self.columns
            col = index % self.columns
            scroll_layout.addWidget(chk, row, col)
            self.vars_list.append((chk, item))

        scroll_content.setLayout(scroll_layout)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # 确认和取消按钮
        btn_confirm = QPushButton("确认")
        btn_confirm.setFont(self.font)
        btn_confirm.setMinimumHeight(30)
        btn_confirm.clicked.connect(self.confirm)

        btn_cancel = QPushButton("取消")
        btn_cancel.setFont(self.font)
        btn_cancel.setMinimumHeight(30)
        btn_cancel.clicked.connect(self.cancel)

        btn_bottom_layout = QHBoxLayout()
        btn_bottom_layout.addWidget(btn_confirm)
        btn_bottom_layout.addWidget(btn_cancel)
        main_layout.addLayout(btn_bottom_layout)

        # 弹窗阻塞
        self.exec()

    # 确认
    def confirm(self):
        self.choose = [item for chk, item in self.vars_list if chk.isChecked()]
        self.result = True
        self.accept()

    # 取消
    def cancel(self):
        self.choose = []
        self.result = False
        self.reject()

    # 快捷功能
    def select_all(self):
        for chk, _ in self.vars_list:
            chk.setChecked(True)

    def invert_selection(self):
        for chk, _ in self.vars_list:
            chk.setChecked(not chk.isChecked())

    def clear_all(self):
        for chk, _ in self.vars_list:
            chk.setChecked(False)
# 安装apk窗口
class ApkInstallWindow(QDialog):
        def __init__(self, apk_dir, adb_path, preselected=None):
            super().__init__()
            self.setWindowTitle("安装 APK")
            self.resize(350, 420)
            self.apk_dir = apk_dir
            self.adb_path = adb_path
            self.preselected = set(os.path.abspath(p) for p in (preselected or []))
            self.setWindowIcon(QIcon(get_path('assets/logos/iconic.ico')))
            self.apk_files = self.get_all_apk_files()
            self.layout = QVBoxLayout()
            self.list_widget = QListWidget()
            self.checkbox_map = {}

            for apk_path in self.apk_files:
                rel_path = os.path.relpath(apk_path, self.apk_dir)
                item = QListWidgetItem()
                checkbox = QCheckBox(rel_path)
                if os.path.abspath(apk_path) in self.preselected:
                    checkbox.setChecked(True)
                item.setSizeHint(checkbox.sizeHint())
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, checkbox)
                self.checkbox_map[apk_path] = checkbox

            self.layout.addWidget(QLabel("请选择要安装的 APK 文件："))
            self.layout.addWidget(self.list_widget)

            btn_layout = QHBoxLayout()
            self.install_btn = QPushButton("安装选中 APK")
            self.install_btn.clicked.connect(self.install_selected_apks)
            btn_layout.addWidget(self.install_btn)

            self.layout.addLayout(btn_layout)
            self.setLayout(self.layout)

        def get_all_apk_files(self):
            apk_list = []
            for root, _, files in os.walk(self.apk_dir):
                for f in files:
                    if f.endswith(".apk"):
                        apk_list.append(os.path.join(root, f))
            return apk_list

        def install_selected_apks(self):
            selected_apks = [path for path, checkbox in self.checkbox_map.items() if checkbox.isChecked()]
            if not selected_apks:
                print("未选择任何 APK。")
                return
            for apk in selected_apks:
                print(f"安装中: {apk}")
                subprocess.run([self.adb_path, "install", "-r", apk], shell=True)
            self.close()
# 发送文件窗口
class FileSendWindow(QDialog):
        def __init__(self, file_dir, adb_path, preselected=None):
            super().__init__()
            self.setWindowTitle("发送文件到手机 Download 文件夹")
            self.resize(350, 420)
            self.file_dir = file_dir
            self.adb_path = adb_path
            self.preselected = set(os.path.abspath(p) for p in (preselected or []))
            self.setWindowIcon(QIcon(get_path('assets/logos/iconic.ico')))
            self.file_list = self.get_all_target_files()
            self.layout = QVBoxLayout()
            self.list_widget = QListWidget()
            self.checkbox_map = {}

            for file_path in self.file_list:
                rel_path = os.path.relpath(file_path, self.file_dir)
                item = QListWidgetItem()
                checkbox = QCheckBox(rel_path)
                if os.path.abspath(file_path) in self.preselected:
                    checkbox.setChecked(True)
                item.setSizeHint(checkbox.sizeHint())
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, checkbox)
                self.checkbox_map[file_path] = checkbox

            self.layout.addWidget(QLabel("请选择要发送的文件："))
            self.layout.addWidget(self.list_widget)

            btn_layout = QHBoxLayout()
            self.send_btn = QPushButton("发送选中文件")
            self.send_btn.clicked.connect(self.send_selected_files)
            btn_layout.addWidget(self.send_btn)

            self.layout.addLayout(btn_layout)
            self.setLayout(self.layout)

        def get_all_target_files(self):
            """扫描目录，获取指定类型文件"""
            allowed_exts = (".zip", ".sh", ".txt", ".json", ".png", ".jpg")
            target_list = []
            for root, _, files in os.walk(self.file_dir):
                for f in files:
                    if f.lower().endswith(allowed_exts):
                        target_list.append(os.path.join(root, f))
            return target_list

        def send_selected_files(self):
            selected_files = [path for path, checkbox in self.checkbox_map.items() if checkbox.isChecked()]
            if not selected_files:
                print("未选择任何文件。")
                return
            for file_path in selected_files:
                remote_path = f"/sdcard/Download/{os.path.basename(file_path)}"
                print(f"发送中: {file_path} -> {remote_path}")
                subprocess.run(f'"{self.adb_path}" push "{file_path}" "{remote_path}"', shell=True)
            QMessageBox.information(self, "完成", "选中文件已发送到手机 Download 文件夹。")
            self.close()
# 二次确认窗口
class ConfirmDialog(QtWidgets.QMessageBox):
    def __init__(self, parent=None, title="确认", text="是否继续？"):
        super().__init__(parent)

        # 启用高DPI缩放和平滑图标
        set_qt_application_attribute("AA_EnableHighDpiScaling")
        set_qt_application_attribute("AA_UseHighDpiPixmaps")

        self.setWindowTitle(title)
        self.setText(text)
        self.setTextFormat(Qt.PlainText)
        self.setIcon(QtWidgets.QMessageBox.Question)

        # 设置字体
        font = _build_dialog_font(11)
        self.setFont(font)

        # 自定义按钮
        self.btn_yes = self.addButton("是", QtWidgets.QMessageBox.AcceptRole)
        self.btn_cancel = self.addButton("取消", QtWidgets.QMessageBox.RejectRole)

        # 美化按钮
        self._style_buttons()

        # 设置圆角和文本样式（避免使用过重字重导致发虚）
        self.setStyleSheet("""
            QMessageBox {
                border-radius: 12px;
            }
            QLabel#qt_msgbox_label {
                padding: 10px;
                font-family: "Microsoft YaHei UI";
                font-size: 12px;
                font-weight: 400;
                color: #1d1d1d;
            }
        """)
        self._polish_text_label()

    def _style_buttons(self):
        # 设置按钮样式
        for btn in [self.btn_yes, self.btn_cancel]:
            btn.setStyleSheet("""
                QPushButton {
                    min-width: 80px;
                    min-height: 32px;
                    border-radius: 6px;
                    padding: 5px 15px;
                    background-color: #4CAF50;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
                QPushButton:pressed {
                    background-color: #3e8e41;
                }
            """)

        # 取消按钮颜色区分
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                min-width: 80px;
                min-height: 32px;
                border-radius: 6px;
                padding: 5px 15px;
                background-color: #f44336;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e53935;
            }
            QPushButton:pressed {
                background-color: #d32f2f;
            }
        """)

    def exec_confirm(self):
        self.exec()
        return self.clickedButton() == self.btn_yes

    def _polish_text_label(self):
        label = self.findChild(QLabel, "qt_msgbox_label")
        if label is not None:
            label.setFont(_build_dialog_font(11, QFont.Normal))

def open_scrcpy(self):
    dialog = QDialog(self)
    dialog.setWindowTitle("投屏控制")

    if self and not self.windowIcon().isNull():
        dialog.setWindowIcon(self.windowIcon())

    screen = dialog.screen() or QtWidgets.QApplication.primaryScreen()
    if screen:
        available = screen.availableGeometry()
        scale = min(max(available.height() / 1080, 0.85), 1.05)
        dialog_width = max(320, min(420, available.width() - 120))
        dialog_height = max(220, min(280, available.height() - 140))
    else:
        scale = 1.0
        dialog_width, dialog_height = 360, 240

    dialog.resize(max(dialog_width, 460), max(dialog_height, 300))
    dialog.setMinimumSize(460, 300)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(18, 16, 18, 16)
    layout.setSpacing(10)

    title = QLabel("请选择投屏模式")
    title.setFont(QFont("Microsoft YaHei UI", max(13, int(round(15 * scale))), QFont.Bold))
    title.setWordWrap(True)
    title.setStyleSheet("margin-bottom: 4px;")
    layout.addWidget(title)

    selected = _read_selected_device() or "自动（未指定）"
    selected_label = QLabel(f"当前目标设备：{selected}")
    selected_label.setStyleSheet("color:#555;")
    layout.addWidget(selected_label)

    mode_row = QHBoxLayout()
    mode_row.addWidget(QLabel("连接方式"))
    mode_combo = QComboBox()
    mode_combo.addItems(["有线模式", "无线模式"])
    mode_row.addWidget(mode_combo, 1)
    layout.addLayout(mode_row)

    audio_row = QHBoxLayout()
    audio_row.addWidget(QLabel("音频选项"))
    audio_combo = QComboBox()
    audio_combo.addItems(["带音频", "不投音频"])
    audio_row.addWidget(audio_combo, 1)
    layout.addLayout(audio_row)

    button_font = QFont("Microsoft YaHei UI", max(11, int(round(12 * scale))))
    button_min_height = max(42, int(round(46 * scale)))
    button_style = """
    QPushButton {
        background-color: #4CAF50;
        border: none;
        color: white;
        padding: 8px 18px;
        margin: 4px 0px;
        border-radius: 8px;
    }
    QPushButton:hover {
        background-color: #45a049;
    }
    """

    def run_scrcpy(mode, with_audio):
        action_name = f"{mode}投屏"
        device = _ensure_adb_target(self, action_name)
        cmd = [get_path("tools/bin/scrcpy-win64-v3.3.4/scrcpy.exe")]

        if device:
            cmd += ["-s", device]

        if mode == "无线模式":
            # scrcpy v3.3.4: --bit-rate 已移除，改为 --video-bit-rate
            # 游戏无线投屏：在清晰度与稳定性间平衡，尽量减少复杂画面卡顿。
            cmd += ["--tcpip", "--video-bit-rate", "10M", "--max-fps", "60"]
        if not with_audio:
            cmd += ["--no-audio"]

        subprocess.Popen(cmd)
        dialog.accept()

    launch = QPushButton("启动投屏")
    launch.setFont(button_font)
    launch.setMinimumHeight(button_min_height)
    launch.setCursor(Qt.PointingHandCursor)
    launch.setStyleSheet(button_style)
    launch.clicked.connect(
        lambda: run_scrcpy(
            mode_combo.currentText(),
            audio_combo.currentText() == "带音频",
        )
    )
    layout.addWidget(launch)

    choose_btn = QPushButton("切换设备")
    choose_btn.setMinimumHeight(36)

    def refresh_selected_label():
        selected_label.setText(f"当前目标设备：{_read_selected_device() or '自动（未指定）'}")

    def on_choose_clicked():
        on_choose_devices_clicked(self)
        refresh_selected_label()

    choose_btn.clicked.connect(on_choose_clicked)
    layout.addWidget(choose_btn)

    layout.addStretch()

    dialog.exec()

def on_choose_devices_clicked(self):
    devices = adb_get_devices(self)
    if not devices:
        ConfirmDialog(self, "错误提示", "未检测到 ADB 设备，请检查 USB 调试与数据线连接。").exec_confirm()
        return

    if len(devices) == 1:
        _write_selected_device(devices[0])
        QMessageBox.information(self, "完成", f"当前已锁定设备：{devices[0]}")
        return

    chosen = _pick_device_dialog(self, devices)
    if chosen:
        _write_selected_device(chosen)
        QMessageBox.information(self, "完成", f"当前已锁定设备：{chosen}")


def adb_wireless_manager(self):
    dialog = QDialog(self)
    dialog.setWindowTitle("连接无线设备")
    dialog.setMinimumSize(520, 280)
    if self and not self.windowIcon().isNull():
        dialog.setWindowIcon(self.windowIcon())

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)

    tip = QLabel(
        "连接：先通过USB识别设备，自动读取手机IP并执行 tcpip/connect。\n"
        "断开：输入已连接的无线设备IP（例如 10.96.39.178）后执行断开。"
    )
    tip.setWordWrap(True)
    tip.setStyleSheet("color: #444;")
    layout.addWidget(tip)

    selected_label = QLabel(f"当前设备选择：{_read_selected_device() or '自动（未指定）'}")
    selected_label.setStyleSheet("color:#555;")
    layout.addWidget(selected_label)

    connect_row = QHBoxLayout()
    connect_row.addWidget(QLabel("连接目标"))
    connect_target_edit = QLineEdit()
    connect_target_edit.setReadOnly(True)
    connect_target_edit.setPlaceholderText("点击“连接”后自动填充为检测到的IP")
    connect_row.addWidget(connect_target_edit, 1)
    layout.addLayout(connect_row)

    ip_row = QHBoxLayout()
    ip_row.addWidget(QLabel("断开目标"))
    ip_edit = QLineEdit()
    ip_edit.setPlaceholderText("例如：10.96.39.178 或 10.96.39.178:5555")
    ip_row.addWidget(ip_edit, 1)
    layout.addLayout(ip_row)

    log_label = QLabel("状态：等待操作")
    log_label.setWordWrap(True)
    log_label.setStyleSheet("color: #1d1d1d;")
    layout.addWidget(log_label)

    btn_row = QHBoxLayout()
    btn_connect = QPushButton("连接")
    btn_disconnect = QPushButton("断开")
    btn_close = QPushButton("关闭")
    btn_row.addWidget(btn_connect)
    btn_row.addWidget(btn_disconnect)
    btn_row.addStretch()
    btn_row.addWidget(btn_close)
    layout.addLayout(btn_row)

    def do_connect():
        target = _resolve_usb_target_for_wireless(self)
        if not target:
            return

        try:
            route_res = _adb_run_raw(["shell", "ip", "route"], device=target, timeout=12)
        except subprocess.TimeoutExpired:
            ConfirmDialog(self, "错误提示", "读取设备网络信息超时，请重试。").exec_confirm()
            return

        route_output = ((route_res.stdout or "") + "\n" + (route_res.stderr or "")).strip()
        phone_ip = _extract_wireless_ip_from_route(route_output)
        if not phone_ip:
            ConfirmDialog(self, "错误提示", "未能从 `adb shell ip route` 中提取手机IP。").exec_confirm()
            return

        connect_target = _normalize_adb_target(phone_ip)
        connect_target_edit.setText(connect_target)
        ip_edit.setText(connect_target)

        try:
            tcpip_res = _adb_run_raw(["tcpip", "5555"], device=target, timeout=15)
            connect_res = _adb_run_raw(["connect", connect_target], timeout=15)
        except subprocess.TimeoutExpired:
            ConfirmDialog(self, "错误提示", "无线连接命令执行超时，请重试。").exec_confirm()
            return

        tcpip_out = ((tcpip_res.stdout or "") + "\n" + (tcpip_res.stderr or "")).strip()
        connect_out = ((connect_res.stdout or "") + "\n" + (connect_res.stderr or "")).strip()

        log_label.setText(
            f"状态：连接完成\n目标USB设备：{target}\n手机IP：{phone_ip}\n连接目标：{connect_target}\n"
            f"tcpip结果：{tcpip_out or '无输出'}\nconnect结果：{connect_out or '无输出'}"
        )
        QMessageBox.information(
            self,
            "连接完成",
            f"无线连接流程已执行完成。\n设备：{target}\nIP：{phone_ip}\n连接目标：{connect_target}\n\n"
            f"接下来可以直接使用无线投屏。",
        )

    def do_disconnect():
        ip = ip_edit.text().strip()
        if not ip:
            ConfirmDialog(self, "提示", "请先输入要断开的设备IP。").exec_confirm()
            return
        target = _normalize_adb_target(ip)
        try:
            res = _adb_run_raw(["disconnect", target], timeout=10)
        except subprocess.TimeoutExpired:
            ConfirmDialog(self, "错误提示", "断开命令执行超时，请重试。").exec_confirm()
            return
        output = ((res.stdout or "") + "\n" + (res.stderr or "")).strip()
        log_label.setText(f"状态：断开执行完成\n目标：{target}\n结果：{output or '无输出'}")
        QMessageBox.information(self, "完成", f"已执行断开：{target}")

    btn_connect.clicked.connect(do_connect)
    btn_disconnect.clicked.connect(do_disconnect)
    btn_close.clicked.connect(dialog.accept)

    dialog.exec()

def open_adb(self):
    subprocess.Popen(['cmd.exe', '/k', get_path("tools/adb-fastboot/打开CMD命令行.bat")],
                     creationflags=subprocess.CREATE_NEW_CONSOLE)

def backup_IMG(self):
    device = _ensure_adb_target(self, "一键备份基带")
    if not device:
        return

    backup_dir = _ask_directory_with_input(
        self,
        "备份输出目录",
        "请指定本次基带镜像备份到电脑的目录（可手动输入或点击选择）。",
        "",
    )
    if not backup_dir:
        return
    os.makedirs(backup_dir, exist_ok=True)

    box = QMessageBox(self)
    box.setWindowTitle("高危功能提示 - 基带备份")
    box.setText(f"""
    <b>请确认以下事项：</b><br><br>
    • 目标设备：<b>{device}</b><br>
    • 备份目录：<b>{backup_dir}</b><br><br>
    <b>请选择备份模式：</b><br>
     ①防格机镜像备份（完整）<br>
     ②面具修补还原镜像（部分）
    """)

    box.setStyleSheet("""
    QMessageBox {
        font-family: "Microsoft YaHei UI";
        font-size: 13px;
    }
    QPushButton {
        font-size: 12px;
        padding: 6px 16px;
    }
    """)
    btn_full = box.addButton("防格机备份", QMessageBox.AcceptRole)
    btn_patch = box.addButton("面具修补备份", QMessageBox.ActionRole)
    btn_cancel = box.addButton("取消", QMessageBox.RejectRole)
    box.exec()
    clicked = box.clickedButton()

    if clicked == btn_cancel:
        return

    cpu = adb_commander(['shell', 'su -c', '"cd /dev/block/bootdevice/by-name && ls -1"'], device=device)
    byname = 'bootdevice/by-name' if cpu else 'by-name'

    if clicked == btn_full: # 防格机备份就是备份整个基带目录，但是排除掉一些不必要的分区，避免占用过大空间
        result = adb_commander(['shell', 'su -c', f'"cd /dev/block/{byname} && ls -1"'], device=device)  # 得到基带目录名
        result = result.strip().splitlines()
        # 要删除的元素
        to_remove = ['bootloader1','bootloader2','userdata','sda','sdb','sdc']
        # 删除操作
        result = [x for x in result if x not in to_remove]


        # 弹出子窗口选择
        windows = CheckListDialog(self, result)  # 自动继承父窗口图标
        if windows.result:
            result = windows.choose
            print("已选择刷入镜像", result)
            # 创建临时目录
            adb_commander(["shell", "su -c 'mkdir -p /sdcard/tmp'"], device=device)
            for file_name in result:
                # dd 备份到手机临时目录
                res = adb_commander([
                    "shell",
                    f"su -c 'dd if=/dev/block/{byname}/{file_name} of=/sdcard/tmp/{file_name}.img && echo get_done'"
                ], device=device)
                print(f"dd {file_name}:", res)

                # pull 到电脑
                res2 = adb_commander([
                    "pull",
                    f"/sdcard/tmp/{file_name}.img",
                    backup_dir
                ], device=device)
                print(f"pull {file_name}:", res2)

                # 删除手机临时文件
                res3 = adb_commander([
                    "shell",
                    f"su -c 'rm /sdcard/tmp/{file_name}.img && echo removed_done'"
                ], device=device)
                print(f"rm {file_name}:", res3)
            dlg = ConfirmDialog(self, "确认", "备份完毕，请确认！")
            dlg.exec_confirm()



    elif clicked == btn_patch: # 面具基带只需要这两个
        files_name = [
            'init_boot_b',
            'boot_b'
        ]

        # 创建临时目录
        adb_commander(["shell", "su -c 'mkdir -p /sdcard/tmp'"], device=device)

        # 循环备份
        for file_name in files_name:
            # dd 备份到手机临时目录
            res = adb_commander([
                "shell",
                f"su -c 'dd if=/dev/block/{byname}/{file_name} of=/sdcard/tmp/{file_name}.img && echo get_done'"
            ], device=device)
            print(f"dd {file_name}:", res)

            # pull 到电脑
            res2 = adb_commander([
                "pull",
                f"/sdcard/tmp/{file_name}.img",
                backup_dir
            ], device=device)
            print(f"pull {file_name}:", res2)

            # 删除手机临时文件
            res3 = adb_commander([
                "shell",
                f"su -c 'rm /sdcard/tmp/{file_name}.img && echo removed_done'"
            ], device=device)
            print(f"rm {file_name}:", res3)
        dialog = ConfirmDialog(self, "确认", "面具原镜像备份成功，请确认！").exec_confirm()
        print("面具原镜像备份成功")

def restore_IMG(self):
    device = _ensure_adb_target(self, "一键还原基带")
    if not device:
        return

    restore_dir = _ask_directory_with_input(
        self,
        "还原镜像目录",
        "请指定包含镜像文件的目录（可手动输入或点击选择）。",
        "",
    )
    if not restore_dir:
        return
    os.makedirs(restore_dir, exist_ok=True)
    img = [x for x in os.listdir(restore_dir) if x.lower().endswith(".img")]
    if not img:
        info = ConfirmDialog(self,'错误提示',f'请把镜像文件放入\n{restore_dir}')
        info.exec_confirm()
        return
    windows = CheckListDialog(self, img)  # 自动继承父窗口图标
    img = windows.choose
    for i in img:
        name = i.split('.')[0]
        full_path = os.path.join(restore_dir, i)
        result = fastboot_commander(['flash', name, full_path], device=device)
        print(f"刷入成功{name}") if result else print(f'刷入失败{name}')

def flash_boot(self):
    selected_fastboot_device = _resolve_target_for_fastboot(self, "[FB]一键刷入boot.img")
    boot_dir = _ask_directory_with_input(
        self,
        "boot镜像目录",
        "请指定 boot 镜像所在目录（可手动输入或点击选择）。",
        "",
    )
    if not boot_dir:
        return
    os.makedirs(boot_dir, exist_ok=True)

    box = QMessageBox(self)
    box.setWindowTitle("【高危操作】⚠若操作不当将会变砖哦~")
    box.setText(
        f"请确保手机处于fastboot模式下\n当前镜像目录：{boot_dir}\n文件名是init_boot_a/b.img\n请选择刷入分区\n您可以选择init_boot_a或init_boot_b分区\n手动刷入时\n请把有且仅有一个镜像文件放入该目录\n文件名就是刷入分区名")
    font = QFont("Microsoft YaHei UI", 12)  # 字体"微软雅黑"，字号12，可改大
    box.setFont(font)
    btn_boot_A = box.addButton("刷入init_boot_a", QMessageBox.ActionRole)
    btn_boot_B = box.addButton("刷入init_boot_b", QMessageBox.ActionRole)
    btn_boot_C = box.addButton("手动刷入", QMessageBox.ActionRole)
    btn_cancel = box.addButton("取消", QMessageBox.RejectRole)
    box.exec()
    clicked = box.clickedButton()
    if clicked == btn_boot_A:
        result = fastboot_commander(
            ['flash', 'init_boot_a', os.path.join(boot_dir, 'init_boot_a.img')],
            device=selected_fastboot_device
        )
        print("刷入成功A") if result else print('刷入失败')
    elif clicked == btn_boot_B:
        result = fastboot_commander(
            ['flash', 'init_boot_b', os.path.join(boot_dir, 'init_boot_b.img')],
            device=selected_fastboot_device
        )
        print("刷入成功B") if result else print('刷入失败')
    elif clicked == btn_boot_C:
        path = [x for x in os.listdir(boot_dir) if x.lower().endswith(".img")]
        if not path:
            dialog = ConfirmDialog(self,'错误',f'{boot_dir} 目录下未发现镜像文件')
            dialog.exec_confirm()
            return
        elif len(path) == 1:
            name = path[0].split('.')[0]
        else:
            ConfirmDialog(self, '错误', '手动刷入模式下，img文件只能为1个').exec_confirm()
            return
        result = fastboot_commander(
            ['flash', name, os.path.join(boot_dir, path[0])],
            device=selected_fastboot_device
        )
        print(f"刷入成功{name}") if result else print(f'刷入失败{name}')
    elif clicked == btn_cancel:
        print("已取消操作")


###################安装apk↓#######################

def install_apks(preselect_list=None):
    paths = _get_runtime_paths()
    dlg = ApkInstallWindow(get_path("tools/android"), paths["adb_path"], preselect_list)
    dlg.exec()

def install_environment_apks(self):
    install_apks([get_path('tools/android/环境检测/牛头30.apk'),
                  get_path('tools/android/环境检测/橘子检测.apk'),
                  get_path('tools/android/环境检测/Ruru_1.1.1.apk'),
                  get_path('tools/android/环境检测/Momo_4.4.1.apk'),
                  get_path('tools/android/环境检测/Luna_1.4.2.7.apk'),
                  get_path('tools/android/环境检测/Hunter_6.42.apk'),
                  get_path('tools/android/环境检测/放大镜2.1.apk'),
                  get_path('tools/android/环境检测/春秋检测.apk'),
                  get_path('tools/android/环境检测/Applist Detector_2.4.apk')])

def install_alpha_apks(self):
    install_apks([get_path('tools/android/阿尔法环境/Alpha30400.apk'),
                  get_path('tools/android/阿尔法环境/隐藏BL列表.apk'),
                  get_path('tools/android/阿尔法环境/密钥认证修改版.apk'),
                  get_path('tools/android/阿尔法环境/超级用户列表.apk'),
                  get_path('tools/android/阿尔法环境/隐藏应用列表改包名版.apk'),
                  get_path('tools/android/阿尔法环境/MT管理器_2.19.3-clone.apk')])

def install_sukisu_apks(self):
    install_apks([get_path('tools/android/Sukisu环境/Kernel Flasher_1.0.0-alpha21.apk')])

def install_root_apks(self):
    install_apks()

def Leetiaotiao(self):
    install_apks([get_path('tools/android/李跳跳2.2正式版.apk')])
    send_files([
        get_path('tools/android/李跳跳规则/【推荐】B站热心站友冇名之辈分享的去重规则(890条).txt'),
        get_path('tools/android/李跳跳规则/【精简】常用软件精简规则.txt'),
        get_path('tools/android/李跳跳规则/【更新】Github更新规则，比较多但是可能有重复的.txt')
    ])

# 文件发送处理
def send_files(preselect_list=None):
    paths = _get_runtime_paths()
    dlg = FileSendWindow(get_path("tools/android"), paths["adb_path"], preselect_list)
    dlg.exec()

def send_al_environment_files(self):
    send_files([
        get_path('tools/android/过环境文件/Keybox.xml一键更新(1218).sh'),
        get_path('tools/android/过环境文件/隐藏应用列表jitian_11.19.json'),
        get_path('tools/android/过环境文件/阿尔法一键隐藏v5.0(1228).zip')
    ])

def send_su_environment_files(self):
    send_files([
        get_path('tools/android/Sukisu环境/Tricky Store-v1.4.0.zip'),
        get_path('tools/android/Sukisu环境/Tricky Addon - Update Target List-v4.1.zip'),
        get_path('tools/android/Sukisu环境/SUSFS-FOR-KERNELSU-v1.5.2-R23.zip')
    ])

# adb-fastboot核心功能

def adb_get_devices(parent=None):
    """
    返回devices列表
    把结果写入硬盘，作为选择设备的前置函数
    也可在任意需要使用adb命令前进行设备判断
    """
    listDevices = []
    paths = _get_runtime_paths()
    _warmup_adb_server()
    adb_path = paths["adb_path"]
    if not _tool_exists(adb_path):
        if parent:
            _show_missing_tool_message(parent, "adb", adb_path)
        else:
            print(f"未找到 adb 可执行文件: {adb_path}")
        return None

    try:
        result = subprocess.run(
            [adb_path, "devices"],
            shell=False,
            encoding='utf-8',
            errors='ignore',
            capture_output=True
        )
    except FileNotFoundError:
        if parent:
            _show_missing_tool_message(parent, "adb", adb_path)
        else:
            print(f"adb 启动失败（FileNotFoundError）: {adb_path}")
        return None
    for line in result.stdout.splitlines()[1:]:  # 处理原始返回结果
        if '\tdevice' in line:
            listDevices.append(line.split('\tdevice')[0].strip())

    if len(listDevices) == 0:  # 如果没有设备
        if os.path.exists(paths["cache_dir"]):
            shutil.rmtree(paths["cache_dir"])  # 删除整个文件夹及内容
        return None

    os.makedirs(paths["cache_dir"], exist_ok=True)
    with open(paths["devices_path"], 'w+', encoding='utf-8') as f:  # 初始化写入本地
        for device in listDevices:
            f.write(device + '\n')
    return listDevices
def adb_commander(args, device=None):
    if type(args) is not list:
        args = [args]

    paths = _get_runtime_paths()
    _warmup_adb_server()
    adb_path = paths["adb_path"]
    if not _tool_exists(adb_path):
        print(f"adb_commander 未找到 adb: {adb_path}")
        return ""

    cmd = [adb_path]
    if device:
        cmd += ["-s", device]
    cmd += args

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8",
            errors="ignore"
        )
        return result.stdout
    except FileNotFoundError:
        print(f"adb_commander 启动失败（FileNotFoundError）: {adb_path}")
        return ""
    except Exception as e:
        print("adb_commander 调用失败:", e)
        return ""
def fastboot_commander(command, device=None):
    paths = _get_runtime_paths()
    fastboot_path = paths["fastboot_path"]
    if not _tool_exists(fastboot_path):
        print(f"fastboot_commander 未找到 fastboot: {fastboot_path}")
        return None

    try:
        args = command if isinstance(command, list) else str(command).split()
        cmd = [fastboot_path]
        if device:
            cmd += ["-s", device]
        cmd += args
        result = subprocess.run(
            cmd,
            shell=False,
            timeout=3,
            capture_output=True,
            encoding="utf-8",
            errors="ignore"
        )
        output = (result.stdout or "") + (result.stderr or "")
        return output.strip() if output else None

    except FileNotFoundError:
        print(f"fastboot 启动失败（FileNotFoundError）: {fastboot_path}")
        return None
    except subprocess.TimeoutExpired:
        print("未检测到 fastboot 设备")
        return None

def adb_reboot(self):
    device = _ensure_adb_target(self, "ADB重启设备")
    if not device:
        return
    dlg = ConfirmDialog(self, "确认", "是否继续？")
    result = dlg.exec_confirm()
    if result:
        adb_commander(['reboot'], device=device)

def fastboot_reboot(self):
    dlg = ConfirmDialog(self, "确认", "是否继续？")
    result = dlg.exec_confirm()
    if result:
        fastboot_commander(['reboot'])

def clean_file_dir(dir_path):
    """删除指定目录下的所有文件夹"""
    dirs = adb_commander(["shell", "find", dir_path, "-maxdepth", "1", "-type", "d"]).strip().splitlines()
    for d in dirs:
        if d != dir_path:  # 避免删除根目录
            adb_commander(["shell", "rm", "-rf", f'"{d}"'])
            print(f"已删除目录: {d}")

# ------------------ 主程序 ------------------
if __name__ == "__main__":
    pass
    # adb_commander(["shell", "find", "/sdcard/", "-maxdepth", "1", "-type", "d"])
    # 示例调用
    #delete_dirs_with_confirmation("/sdcard")

    #print(adb_commander(["shell", "find /sdcard/", "-maxdepth 1", "-type d"]))
