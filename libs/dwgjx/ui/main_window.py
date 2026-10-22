"""主窗口：紧凑粉色布局 + 进度 ETA + 配置持久化。"""

import ctypes
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import config as cfg
from ..constants import (
    APP_NAME,
    APP_USER_MODEL_ID,
    APP_VERSION,
    CONTACT_QQ,
    PRESETS,
    VIDEO_EXTENSIONS,
    VIDEO_FILE_FILTER,
)
from ..paths import get_resource
from .styles import PINK_QSS
from .widgets import VideoDropList
from ..worker import CompressWorker

# Windows 任务栏分组 ID
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        APP_USER_MODEL_ID
    )
except Exception:
    pass


def _format_hms(seconds: float) -> str:
    """把秒数格式化为 HH:MM:SS。"""
    if seconds < 0 or seconds != seconds:  # NaN 判断
        return "--:--:--"
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class MainWindow(QMainWindow):
    # 固定尺寸：高度略大于宽度，不可调整
    WINDOW_W = 480
    WINDOW_H = 560

    def __init__(self):
        super().__init__()

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION} - jitianV2 - QQ:{CONTACT_QQ}")
        self.setWindowIcon(QIcon(get_resource("assets/logos/dwgjx_icon.png")))
        self.setFixedSize(self.WINDOW_W, self.WINDOW_H)
        self.setAcceptDrops(True)

        # ===== 内部状态 =====
        self.files: list = []
        cfg_data = cfg.load_config()
        self.output_dir = cfg.resolve_output_dir(cfg_data)
        self.worker: CompressWorker | None = None
        self._compress_start_time: datetime | None = None

        # ===== 中央控件 =====
        central = QWidget(objectName="central")
        central.setAcceptDrops(True)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        # ===== 预设行 =====
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        preset_row.addWidget(QLabel("预设"))
        self.preset_box = QComboBox()
        for p in PRESETS:
            self.preset_box.addItem(p["name"])
        # 自动恢复上次预设
        self.preset_box.setCurrentIndex(
            cfg.resolve_preset_index(cfg_data, len(PRESETS))
        )
        self.help_btn = QPushButton("说明")
        self.help_btn.setFixedWidth(48)
        preset_row.addWidget(self.preset_box, stretch=1)
        preset_row.addWidget(self.help_btn)
        root.addLayout(preset_row)

        # ===== 文件列表 =====
        tip = QLabel("拖拽视频到下方，或点击「添加文件」")
        tip.setStyleSheet("color:#a0607a; font-size:8.5pt;")
        root.addWidget(tip)
        self.file_list = VideoDropList()
        self.file_list.setMinimumHeight(280)
        root.addWidget(self.file_list, stretch=1)

        # ===== 输出目录行 =====
        out_row = QHBoxLayout()
        out_row.setSpacing(6)
        out_row.addWidget(QLabel("输出"))
        self.output_path_edit = QLineEdit(str(self.output_dir))
        self.output_path_edit.setReadOnly(True)
        self.choose_output_btn = QPushButton("选择")
        self.open_output_btn = QPushButton("打开")
        self.choose_output_btn.setFixedWidth(52)
        self.open_output_btn.setFixedWidth(52)
        out_row.addWidget(self.output_path_edit, stretch=1)
        out_row.addWidget(self.choose_output_btn)
        out_row.addWidget(self.open_output_btn)
        root.addLayout(out_row)

        # ===== 操作按钮行 =====
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self.add_btn = QPushButton("添加文件")
        self.clear_btn = QPushButton("清空")
        self.remove_btn = QPushButton("删除选中")
        self.start_btn = QPushButton("开始压缩")
        self.start_btn.setObjectName("start_btn")
        for b in (self.add_btn, self.clear_btn, self.remove_btn):
            btn_row.addWidget(b)
        btn_row.addStretch()
        btn_row.addWidget(self.start_btn)
        root.addLayout(btn_row)

        # ===== 进度行：进度条 + 计数 + ETA =====
        prog_row = QHBoxLayout()
        prog_row.setSpacing(6)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("0/0")
        self.progress_label.setObjectName("progress_label")
        self.progress_label.setFixedWidth(40)
        self.progress_label.setAlignment(Qt.AlignCenter)
        self.eta_label = QLabel("剩余 --:--:--")
        self.eta_label.setObjectName("eta_label")
        self.eta_label.setFixedWidth(95)
        self.eta_label.setAlignment(Qt.AlignCenter)
        prog_row.addWidget(self.progress_bar, stretch=1)
        prog_row.addWidget(self.progress_label)
        prog_row.addWidget(self.eta_label)
        root.addLayout(prog_row)

        # ===== 应用 QSS =====
        self.setStyleSheet(PINK_QSS)

        # ===== 信号绑定 =====
        self.add_btn.clicked.connect(self.add_files)
        self.clear_btn.clicked.connect(self.clear_files)
        self.remove_btn.clicked.connect(self.remove_selected_files)
        self.start_btn.clicked.connect(self.start_or_stop_compress)
        self.file_list.filesDropped.connect(self.add_dropped_files)
        self.choose_output_btn.clicked.connect(self.choose_output_dir)
        self.open_output_btn.clicked.connect(self.open_output_dir)
        self.help_btn.clicked.connect(self.show_preset_help)

    # =================================================================
    # 拖拽
    # =================================================================
    def _video_paths_from_event(self, event):
        if not event.mimeData().hasUrls():
            return []
        paths = []
        for url in event.mimeData().urls():
            p = Path(url.toLocalFile())
            if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
                paths.append(p)
        return paths

    def dragEnterEvent(self, event):
        if self._video_paths_from_event(event):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._video_paths_from_event(event):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = self._video_paths_from_event(event)
        if paths:
            self.add_dropped_files(paths)
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    # =================================================================
    # 文件管理
    # =================================================================
    def _add_file(self, path: Path):
        if path not in self.files:
            self.files.append(path)
            self.file_list.addItem(path.name)

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", "", VIDEO_FILE_FILTER
        )
        for p in paths:
            self._add_file(Path(p))

    def add_dropped_files(self, paths):
        for path in paths:
            self._add_file(path)

    def clear_files(self):
        self.files.clear()
        self.file_list.clear()

    def remove_selected_files(self):
        selected = self.file_list.selectedItems()
        if not selected:
            return
        # 从大到小删，避免索引错乱
        rows = sorted(
            (self.file_list.row(it) for it in selected), reverse=True
        )
        for r in rows:
            self.file_list.takeItem(r)
            del self.files[r]

    # =================================================================
    # 输出目录
    # =================================================================
    def choose_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择输出文件夹", str(self.output_dir)
        )
        if path:
            self.output_dir = Path(path)
            self.output_path_edit.setText(str(self.output_dir))

    def open_output_dir(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_dir)))

    # =================================================================
    # 预设说明
    # =================================================================
    def show_preset_help(self):
        lines = [
            "使用方式：添加或拖入视频，选择预设，再点击「开始压缩」。",
            "输出统一为 MP4，并附加后缀 _av/_x265/_hv 防止覆盖原视频。\n",
        ]
        for i, p in enumerate(PRESETS, 1):
            lines.append(f"预设{i}：{p['desc']}\n")
        lines.append(
            f"本软件由 jitian 开发，永久免费使用。"
            f"若有 BUG 请联系 QQ：{CONTACT_QQ}"
        )
        QMessageBox.information(self, "预设说明", "\n".join(lines))

    # =================================================================
    # 压缩入口
    # =================================================================
    def start_or_stop_compress(self):
        # 正在压缩 -> 询问后取消
        if self.worker is not None and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "确认取消",
                "压缩还未完成，确定要取消吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                self.worker.cancel()
                self.start_btn.setEnabled(False)
                self.start_btn.setText("正在结束…")
            return

        # ===== 开始压缩 =====
        if not self.files:
            QMessageBox.warning(self, "提示", "请先添加视频文件")
            return

        preset = PRESETS[self.preset_box.currentIndex()]
        params = dict(preset["params"])
        params["suffix"] = "mp4"

        self.start_btn.setText("结束压缩")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"0/{len(self.files)}")
        self.eta_label.setText("剩余 --:--:--")

        self._compress_start_time = datetime.now()

        self.worker = CompressWorker(
            self.files,
            self.output_dir,
            compress_func=preset["encoder"],
            ffmpeg_params=params,
        )
        self.worker.done.connect(self.compress_finished)
        self.worker.error.connect(self.compress_error)
        self.worker.progress.connect(self.update_progress)
        self.worker.skipped.connect(self._on_skipped)
        self.worker.start()

    def _on_skipped(self, paths):
        """检测到已被大丸工具箱压缩过的视频，跳过压缩并提示"""
        self._skipped_paths = list(paths)

    def compress_finished(self):
        elapsed = datetime.now() - self._compress_start_time
        self._reset_progress_ui()
        skipped = getattr(self, "_skipped_paths", None) or []
        if skipped:
            names = "\n".join(Path(p).name for p in skipped[:5])
            more = f"\n...等 {len(skipped)} 个文件" if len(skipped) > 5 else ""
            QMessageBox.information(
                self,
                "已跳过已压缩文件",
                f"以下视频已被大丸工具箱压缩过，已自动跳过压缩：\n{names}{more}",
            )
        else:
            QMessageBox.information(
                self, "完成", f"全部视频压缩完成\n耗时：{_format_hms(elapsed.total_seconds())}"
            )

    def compress_error(self, msg: str):
        self._reset_progress_ui()
        QMessageBox.critical(self, "错误", msg)

    def _reset_progress_ui(self):
        self.start_btn.setText("开始压缩")
        self.start_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.progress_bar.setValue(0)
        self.eta_label.setText("剩余 --:--:--")

    def update_progress(self, percent, current_idx, total_files):
        self.progress_bar.setValue(percent)
        self.progress_label.setText(f"{current_idx}/{total_files}")

        # 估算剩余时间：用总体进度比例外推
        if self._compress_start_time is None:
            return
        elapsed = (datetime.now() - self._compress_start_time).total_seconds()
        overall = ((current_idx - 1) + max(percent, 0) / 100.0) / max(total_files, 1)
        if overall > 0.001:
            remaining = elapsed * (1.0 - overall) / overall
            self.eta_label.setText(f"剩余 {_format_hms(remaining)}")
        else:
            self.eta_label.setText("剩余 --:--:--")

    # =================================================================
    # 关闭事件：保存配置；压缩中二次确认
    # =================================================================
    def closeEvent(self, event):
        # 正在压缩时先确认
        if self.worker is not None and self.worker.isRunning():
            reply = QMessageBox.question(
                self,
                "确认退出",
                "压缩尚未完成，确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(3000)

        # 保存配置到 C:\Users\用户名\Pyffmpeg\config.json
        cfg.save_config(
            {
                "output_dir": str(self.output_dir),
                "preset_index": self.preset_box.currentIndex(),
                "version": APP_VERSION,
            }
        )
        event.accept()
