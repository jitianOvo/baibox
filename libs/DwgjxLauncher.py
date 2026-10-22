# -*- coding: utf-8 -*-
import os
import shutil
import subprocess

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from core_lib import get_path
import lanzoui
from assets.aira2c.aria2c_api import aria2_download

CORE_DIR = os.path.join(os.path.expanduser("~"), "PyCache", "core")
CORE_EXE = os.path.join(CORE_DIR, "dwgjx-core.exe")
CORE_7Z = os.path.join(CORE_DIR, "dwgjx-core.7z")
CORE_URL = "https://jitianna.lanzoul.com/ieIhb49z9vla"


def _core_ready():
    return os.path.isfile(CORE_EXE)


class CoreDownloadThread(QThread):
    progress = Signal(int)
    info = Signal(str)
    done = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def _on_progress(self, data):
        self.progress.emit(int(data.get("percent", 0)))
        self.info.emit(f"已下载 {data.get('downloaded', '0B')} / {data.get('total', '0B')}   速度 {data.get('speed', '0B')}")

    def run(self):
        try:
            os.makedirs(CORE_DIR, exist_ok=True)
            # 已下载且就绪直接跳过
            if _core_ready():
                self.progress.emit(100)
                self.done.emit(True, "核心组件已就绪，可以开始使用。")
                return

            self.info.emit("正在解析蓝奏直链...")
            self.progress.emit(3)
            direct = lanzoui.get_direct_link(CORE_URL)
            if not direct:
                self.done.emit(False, "蓝奏直链解析失败，请检查网络后重试。")
                return

            self.info.emit("开始下载核心组件...")
            self.progress.emit(5)
            aria2_download(
                url=direct,
                threads=16,
                filename="dwgjx-core.7z",
                path=CORE_DIR,
                min_split_size="1M",
                on_progress=self._on_progress,
            )

            if not os.path.exists(CORE_7Z):
                self.done.emit(False, "下载完成但未检测到核心组件文件，请重试。")
                return

            self.info.emit("正在解压核心组件...")
            self.progress.emit(96)
            if not _extract_7z(CORE_7Z, CORE_DIR):
                self.done.emit(False, "核心组件解压失败，请手动解压 dwgjx-core.7z 到 PyCache/core。")
                return
            # 解压成功后删除压缩包，释放磁盘空间
            try:
                if os.path.exists(CORE_7Z):
                    os.remove(CORE_7Z)
            except OSError:
                pass

            self.progress.emit(100)
            self.info.emit("核心组件就绪")
            self.done.emit(True, "核心组件下载完成，可以开始使用。")
        except Exception as exc:
            self.done.emit(False, f"核心组件初始化失败：{exc}")


def _extract_7z(archive, dest_dir):
    """解压 7z：优先系统 tar（bsdtar 支持 7z），再尝试 7z/7za 命令行"""
    candidates = [
        [os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe"), "-xf", archive, "-C", dest_dir],
    ]
    for exe in ("7z.exe", "7za.exe", "7zr.exe"):
        path = shutil.which(exe)
        if path:
            candidates.append([path, "x", archive, "-o" + dest_dir, "-y"])
    for cmd in candidates:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=600,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue
    return False


class CoreDownloadDialog(QDialog):
    """核心组件下载进度窗口"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("大丸视频压缩 - 组件准备")
        self.setFixedWidth(460)
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
                color: #111827;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#info {
                background: transparent;
                color: #64748b;
                font-size: 12px;
            }
            QProgressBar {
                border: 1px solid #dbe4f0;
                border-radius: 8px;
                background-color: #f8fafc;
                text-align: center;
                min-height: 20px;
            }
            QProgressBar::chunk {
                background-color: #2563eb;
                border-radius: 7px;
            }
            QPushButton {
                min-width: 90px;
                min-height: 32px;
                border-radius: 8px;
                background-color: #eef3fb;
                border: 1px solid #d4deee;
                color: #1f2937;
            }
            QPushButton:hover {
                background-color: #e6eefb;
            }
            QMessageBox {
                background-color: #f3f6fb;
            }
            QMessageBox QLabel {
                background: transparent;
                color: #334155;
            }
            """
        )

        card = QFrame(self)
        card.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("大丸视频压缩核心组件")
        title.setObjectName("title")
        layout.addWidget(title)

        self.info_label = QLabel("此组件需要下载才能使用，正在准备...")
        self.info_label.setObjectName("info")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        buttons = QHBoxLayout()
        self.close_btn = QPushButton("后台运行")
        self.close_btn.clicked.connect(self.reject)
        buttons.addStretch()
        buttons.addWidget(self.close_btn)
        layout.addLayout(buttons)

        self.thread = CoreDownloadThread()
        self.thread.progress.connect(self.progress_bar.setValue)
        self.thread.info.connect(self.info_label.setText)
        self.thread.done.connect(self._on_done)
        self.thread.start()

    def _on_done(self, ok, msg):
        self.info_label.setText(msg)
        if ok:
            self.close_btn.setText("完成")
            self.close_btn.setEnabled(True)
            QMessageBox.information(self, "完成", msg)
            self.accept()
        else:
            self.close_btn.setText("关闭")
            self.close_btn.setEnabled(True)
            QMessageBox.warning(self, "失败", msg)

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            self.thread.wait(3000)
        super().closeEvent(event)


def open_dwgjx(self):
    """大丸视频压缩入口：核心组件不存在时先下载，然后打开压缩窗口"""
    from libs.dwgjx.ui.main_window import MainWindow as DwgjxWindow

    if not _core_ready():
        dialog = CoreDownloadDialog(self)
        dialog.exec()
        if not _core_ready():
            return

    # 引用挂到 self 上，避免函数返回后被垃圾回收导致窗口闪退
    if getattr(self, "_dwgjx_window", None) is None:
        self._dwgjx_window = DwgjxWindow()
    self._dwgjx_window.show()
    self._dwgjx_window.raise_()
    self._dwgjx_window.activateWindow()
