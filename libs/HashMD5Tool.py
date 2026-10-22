import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)


CACHE_DIR = os.path.join(os.path.expanduser("~"), "PyCache")
os.makedirs(CACHE_DIR, exist_ok=True)
CACHE_FILE = os.path.join(CACHE_DIR, "hash_md5_scan_result.json")


def format_size(size):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def quick_hash(file_path, size=4096):
    try:
        with open(file_path, "rb") as f:
            data = f.read(size)
        return hashlib.md5(data).hexdigest()
    except Exception:
        return None


def full_md5(file_path, chunk_size=8192):
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return None


def save_scan_result(duplicates, ui_state, filename=CACHE_FILE):
    data = {
        "duplicates": duplicates,
        "ui_state": ui_state,
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_scan_result(filename=CACHE_FILE):
    if not os.path.exists(filename):
        return {}, {}
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("duplicates", {}), data.get("ui_state", {})
    except Exception:
        return {}, {}


def _is_wal_shm_file(file_path):
    """判断是否为 SQLite 运行期间产生的 -wal / -shm 文件"""
    lower = file_path.lower()
    return lower.endswith(".db-wal") or lower.endswith(".db-shm")


def delete_file_with_retry(file_path, max_retries=3, wait_seconds=0.5):
    """
    删除文件，处理 WinError 32（文件被占用）等常见失败。
    返回 (是否成功, 结果说明文本)
    """
    if not os.path.exists(file_path):
        return True, f"文件不存在（已跳过）: {file_path}"

    # 先去掉只读属性
    try:
        os.chmod(file_path, stat.S_IWRITE)
    except OSError as e:
        print("设置可写属性失败:", e)

    for attempt in range(1, max_retries + 1):
        try:
            os.remove(file_path)
            if os.path.exists(file_path):
                raise OSError("文件删除后仍然存在")
            return True, f"删除成功: {file_path}"
        except FileNotFoundError:
            return True, f"文件不存在（已跳过）: {file_path}"
        except PermissionError as e:
            winerror = getattr(e, "winerror", None)
            if winerror in (32, 33):
                # WinError 32 文件被占用；先尝试结束常见占用进程
                name = os.path.basename(file_path).lower()
                if _is_wal_shm_file(file_path) or "wechat" in name or "weixin" in name:
                    _kill_wechat_processes()
                if attempt < max_retries:
                    time.sleep(wait_seconds)
                    continue
                return False, f"删除失败，文件被其他程序占用 (WinError {winerror}): {file_path}"
            if winerror == 5:
                return False, f"删除失败，权限不足 (WinError 5): {file_path}"
            return False, f"删除失败 (WinError {winerror}): {e}"
        except OSError as e:
            winerror = getattr(e, "winerror", None)
            print("删除异常:", e)
            if winerror in (32, 33) and attempt < max_retries:
                if _is_wal_shm_file(file_path):
                    _kill_wechat_processes()
                time.sleep(wait_seconds)
                continue
            return False, f"删除失败，其他错误: {e}"

    return False, f"达到最大重试次数仍失败: {file_path}"


def _kill_wechat_processes():
    """尝试结束微信相关进程，释放 .db-wal / .db-shm 文件句柄"""
    for proc in ("WeChat.exe", "Weixin.exe", "wechat.exe", "WeChatAppEx.exe"):
        try:
            subprocess.run(
                ["taskkill", "/f", "/im", proc],
                shell=True,
                capture_output=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000),
            )
        except Exception:
            pass


class ScanThread(QThread):
    progress_signal = Signal(int, int, str)
    finished_signal = Signal(dict)

    def __init__(self, paths, exclude_ext=None):
        super().__init__()
        self.paths = list(paths)
        self.exclude_ext = set(exclude_ext or [])
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        size_map = {}
        all_files = []

        for path in self.paths:
            if not os.path.isdir(path):
                continue
            for root, _, files in os.walk(path):
                for file_name in files:
                    if self._stop:
                        self.finished_signal.emit({})
                        return
                    ext = os.path.splitext(file_name)[1].lower()
                    if ext in self.exclude_ext:
                        continue
                    full_path = os.path.join(root, file_name)
                    try:
                        size = os.path.getsize(full_path)
                    except Exception:
                        continue
                    size_map.setdefault(size, []).append(full_path)
                    all_files.append(full_path)

        total = len(all_files)
        if total == 0:
            self.finished_signal.emit({})
            return

        processed = 0
        candidate_files = {}
        for size, files in size_map.items():
            if len(files) < 2:
                processed += len(files)
                continue
            for file_path in files:
                if self._stop:
                    self.finished_signal.emit({})
                    return
                qh = quick_hash(file_path)
                if qh:
                    candidate_files.setdefault((size, qh), []).append(file_path)
                processed += 1
                if processed % 50 == 0 or processed == total:
                    self.progress_signal.emit(processed, total, f"快速哈希: {file_path}")

        duplicates = {}
        processed = 0
        total_candidates = sum(len(v) for v in candidate_files.values()) or 1
        workers = min(4, max(1, os.cpu_count() or 1))

        for (_, _), files in candidate_files.items():
            if len(files) < 2:
                processed += len(files)
                continue
            md5_map = {}
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_file = {executor.submit(full_md5, f): f for f in files}
                for future in as_completed(future_to_file):
                    if self._stop:
                        self.finished_signal.emit({})
                        return
                    file_path = future_to_file[future]
                    md5_value = future.result()
                    if md5_value:
                        md5_map.setdefault(md5_value, []).append(file_path)
                    processed += 1
                    if processed % 10 == 0 or processed == total_candidates:
                        self.progress_signal.emit(processed, total_candidates, f"完整MD5: {file_path}")
            for md5_value, same_files in md5_map.items():
                if len(same_files) > 1:
                    duplicates[md5_value] = same_files

        self.finished_signal.emit(duplicates)


class HashMD5ToolDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Hash+MD5重复文件清理工具 - BY jitian")
        self.resize(1250, 900)
        self.setMinimumSize(760, 520)
        if parent and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())

        self.paths = []
        self.duplicates = {}
        self.exclude_ext = set()
        self.thread = None

        self._apply_styles()
        self._build_ui()
        self._load_state()

    def _apply_styles(self):
        self.setObjectName("hashDialog")
        self.setStyleSheet(
            """
            QDialog#hashDialog {
                background-color: #eef2f8;
                color: #1f2937;
            }
            QFrame#card {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
            QLabel#titleLabel {
                font-size: 17px;
                font-weight: 700;
                color: #0f172a;
            }
            QLabel#subTitleLabel {
                font-size: 12px;
                color: #64748b;
            }
            QLabel#sectionLabel {
                font-size: 12px;
                font-weight: 600;
                color: #475569;
            }
            QLabel#statValue {
                font-size: 13px;
                font-weight: 700;
                color: #2563eb;
            }
            QLabel#statusLabel {
                font-size: 12px;
                color: #475569;
                background-color: #f1f5f9;
                border-radius: 8px;
                padding: 6px 10px;
            }
            QLabel {
                color: #334155;
            }
            QLineEdit {
                background-color: #f8fafc;
                border: 1px solid #dbe4f0;
                border-radius: 8px;
                padding: 7px 10px;
                color: #1e293b;
                selection-background-color: #3b82f6;
            }
            QLineEdit:focus {
                background-color: #ffffff;
                border: 1px solid #3b82f6;
            }
            QPushButton {
                background-color: #eef2f9;
                border: 1px solid #d8e0ec;
                border-radius: 8px;
                color: #1f2937;
                padding: 7px 12px;
                min-height: 32px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e6edf9;
            }
            QPushButton:pressed {
                background-color: #dde6f7;
            }
            QPushButton:disabled {
                color: #94a3b8;
                background-color: #f1f5f9;
                border-color: #e2e8f0;
            }
            QPushButton[role="primary"] {
                background-color: #2563eb;
                border: 1px solid #2563eb;
                color: white;
                font-weight: 600;
            }
            QPushButton[role="primary"]:hover {
                background-color: #1d4ed8;
                border-color: #1d4ed8;
            }
            QPushButton[role="danger"] {
                background-color: #ef4444;
                border: 1px solid #ef4444;
                color: white;
                font-weight: 600;
            }
            QPushButton[role="danger"]:hover {
                background-color: #dc2626;
                border-color: #dc2626;
            }
            QListWidget, QTreeWidget {
                background-color: #fbfdff;
                border: 1px solid #dfe7f3;
                border-radius: 10px;
                outline: none;
                padding: 2px;
                alternate-background-color: #f6f9ff;
            }
            QListWidget::item {
                padding: 5px 8px;
                border-bottom: 1px solid #edf2fb;
            }
            QListWidget::item:selected, QTreeWidget::item:selected {
                background-color: #e6efff;
                color: #0f172a;
            }
            QTreeWidget::item {
                padding: 3px 5px;
            }
            QTreeWidget::item:hover {
                background-color: #f2f7ff;
            }
            QHeaderView::section {
                background-color: #f3f7ff;
                color: #334155;
                border: none;
                border-bottom: 1px solid #dfe7f3;
                padding: 7px 8px;
                font-weight: 600;
            }
            QProgressBar {
                border: 1px solid #dbe4f0;
                border-radius: 8px;
                background-color: #f8fafc;
                text-align: center;
                color: #334155;
                min-height: 20px;
                font-size: 11px;
            }
            QProgressBar::chunk {
                border-radius: 7px;
                background-color: #2563eb;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 11px;
                margin: 3px 2px 3px 0;
            }
            QScrollBar::handle:vertical {
                background: #c5d1e4;
                min-height: 28px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover {
                background: #afc0d8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 11px;
                margin: 0 3px 2px 3px;
            }
            QScrollBar::handle:horizontal {
                background: #c5d1e4;
                min-width: 28px;
                border-radius: 5px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #afc0d8;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }
            QAbstractScrollArea::corner {
                background: transparent;
            }
            """
        )

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # ===== 顶部标题卡 =====
        header_card = QFrame()
        header_card.setObjectName("card")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(14, 12, 14, 12)
        header_layout.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_label = QLabel("Hash + MD5 重复文件清理")
        title_label.setObjectName("titleLabel")
        sub_title_label = QLabel("纯自研高速搜索引擎 · 智能过滤 · 由 jitian 独立算法开发")
        sub_title_label.setObjectName("subTitleLabel")
        title_box.addWidget(title_label)
        title_box.addWidget(sub_title_label)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        self.stat_label = QLabel("0 个重复组")
        self.stat_label.setObjectName("statValue")
        header_layout.addWidget(self.stat_label)
        layout.addWidget(header_card)

        # ===== 扫描路径卡 =====
        path_card = QFrame()
        path_card.setObjectName("card")
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(12, 10, 12, 12)
        path_layout.setSpacing(8)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_caption = QLabel("扫描路径")
        path_caption.setObjectName("sectionLabel")
        path_row.addWidget(path_caption)
        path_row.addStretch()
        self.add_path_btn = QPushButton("添加扫描路径")
        self.add_path_btn.setProperty("role", "primary")
        self.add_path_btn.clicked.connect(self.add_path)
        path_row.addWidget(self.add_path_btn)
        path_layout.addLayout(path_row)

        self.path_list = QListWidget()
        self.path_list.setAlternatingRowColors(True)
        self.path_list.setMinimumHeight(70)
        self.path_list.setMaximumHeight(104)
        path_layout.addWidget(self.path_list)
        layout.addWidget(path_card)

        # ===== 扫描控制卡 =====
        scan_card = QFrame()
        scan_card.setObjectName("card")
        scan_layout = QVBoxLayout(scan_card)
        scan_layout.setContentsMargins(12, 10, 12, 12)
        scan_layout.setSpacing(8)

        scan_row = QHBoxLayout()
        scan_row.setSpacing(8)
        self.scan_btn = QPushButton("开始扫描")
        self.scan_btn.setProperty("role", "primary")
        self.scan_btn.clicked.connect(self.start_scan)
        scan_row.addWidget(self.scan_btn)

        self.stop_btn = QPushButton("停止扫描")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_scan)
        scan_row.addWidget(self.stop_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        scan_row.addWidget(self.progress_bar, 1)
        scan_layout.addLayout(scan_row)

        self.status_label = QLabel("状态：等待扫描")
        self.status_label.setObjectName("statusLabel")
        scan_layout.addWidget(self.status_label)
        layout.addWidget(scan_card)

        # ===== 过滤与搜索 =====
        filter_card = QFrame()
        filter_card.setObjectName("card")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(8)

        exclude_label = QLabel("排除扩展名")
        exclude_label.setObjectName("sectionLabel")
        filter_layout.addWidget(exclude_label)
        self.exclude_input = QLineEdit()
        self.exclude_input.setPlaceholderText(".cpp,.dll，逗号分隔")
        self.exclude_input.setMinimumWidth(180)
        filter_layout.addWidget(self.exclude_input, 1)

        self.exclude_btn = QPushButton("刷新过滤")
        self.exclude_btn.clicked.connect(self.refresh_filter)
        filter_layout.addWidget(self.exclude_btn)

        search_label = QLabel("搜索文件")
        search_label.setObjectName("sectionLabel")
        filter_layout.addWidget(search_label)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入关键词过滤结果")
        self.search_input.setMinimumWidth(160)
        self.search_input.textChanged.connect(self.search_results)
        filter_layout.addWidget(self.search_input, 1)
        layout.addWidget(filter_card)

        # ===== 结果卡 =====
        result_card = QFrame()
        result_card.setObjectName("card")
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(10, 10, 10, 10)
        result_layout.setSpacing(8)

        result_row = QHBoxLayout()
        result_caption = QLabel("扫描结果")
        result_caption.setObjectName("sectionLabel")
        result_row.addWidget(result_caption)
        result_row.addStretch()
        self.expand_btn = QPushButton("全部展开")
        self.expand_btn.clicked.connect(lambda: self.tree.expandAll())
        result_row.addWidget(self.expand_btn)
        self.collapse_btn = QPushButton("全部折叠")
        self.collapse_btn.clicked.connect(lambda: self.tree.collapseAll())
        result_row.addWidget(self.collapse_btn)
        result_layout.addLayout(result_row)

        self.tree = QTreeWidget(result_card)
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["路径", "大小", "修改时间"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumHeight(180)
        self.tree.setColumnWidth(0, 520)
        self.tree.setColumnWidth(1, 90)
        self.tree.setColumnWidth(2, 150)
        result_layout.addWidget(self.tree, 1)
        layout.addWidget(result_card, 1)

        # ===== 底部操作栏 =====
        action_bar = QFrame()
        action_bar.setObjectName("card")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(12, 8, 12, 8)
        action_layout.setSpacing(8)
        self.delete_hint_label = QLabel("勾选状态决定保留与删除")
        self.delete_hint_label.setObjectName("sectionLabel")
        action_layout.addWidget(self.delete_hint_label)
        action_layout.addStretch()
        self.delete_btn = QPushButton("删除未勾选文件")
        self.delete_btn.setProperty("role", "danger")
        self.delete_btn.clicked.connect(self.delete_files)
        action_layout.addWidget(self.delete_btn)
        layout.addWidget(action_bar)

        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.tree_right_click)
        self.path_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.path_list.customContextMenuRequested.connect(self.path_list_right_click)

    def _load_state(self):
        duplicates, ui_state = load_scan_result()
        self.duplicates = duplicates
        self.display_duplicates()
        if hasattr(self, "stat_label"):
            self.stat_label.setText(f"{len(duplicates)} 个重复组")

        window_size = ui_state.get("window_size", [1000, 700])
        if len(window_size) == 2:
            self.resize(max(window_size[0], self.minimumWidth()), max(window_size[1], self.minimumHeight()))

        for i, width in enumerate(ui_state.get("column_widths", [500, 100, 150])):
            self.tree.setColumnWidth(i, width)

    def _collect_duplicates_from_tree(self):
        new_duplicates = {}
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            md5_label = group.text(0)
            if not md5_label.startswith("重复组: "):
                continue
            md5_value = md5_label.replace("重复组: ", "", 1).strip()
            files = []
            for j in range(group.childCount()):
                files.append(group.child(j).text(0))
            if len(files) > 1:
                new_duplicates[md5_value] = files
        self.duplicates = new_duplicates

    def path_list_right_click(self, pos):
        item = self.path_list.itemAt(pos)
        if not item:
            return

        menu = QMenu(self)
        delete_action = menu.addAction("删除选中路径")

        def delete_path():
            row = self.path_list.row(item)
            self.path_list.takeItem(row)
            if 0 <= row < len(self.paths):
                self.paths.pop(row)

        delete_action.triggered.connect(delete_path)
        menu.exec(self.path_list.viewport().mapToGlobal(pos))

    def add_path(self):
        path = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if path and path not in self.paths:
            self.paths.append(path)
            self.path_list.addItem(path)

    def start_scan(self):
        if self.thread and self.thread.isRunning():
            QMessageBox.information(self, "提示", "扫描正在进行中")
            return
        if not self.paths:
            QMessageBox.warning(self, "提示", "请先添加扫描路径")
            return

        self.tree.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("状态：扫描中...")
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.exclude_ext = {
            e.strip().lower() for e in self.exclude_input.text().split(",") if e.strip()
        }
        self.thread = ScanThread(self.paths, self.exclude_ext)
        self.thread.progress_signal.connect(self.update_progress)
        self.thread.finished_signal.connect(self.scan_finished)
        self.thread.start()

    def stop_scan(self):
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.status_label.setText("状态：正在停止扫描...")
            self.stop_btn.setEnabled(False)

    def update_progress(self, processed, total, file_path):
        total = max(total, 1)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(min(processed, total))
        pct = int(min(processed, total) / max(total, 1) * 100)
        self.progress_bar.setFormat(f"扫描中 {pct}%  (%v / %m)")
        self.status_label.setText(f"状态：{processed}/{total} - {file_path}")

    def scan_finished(self, duplicates):
        self.duplicates = duplicates
        self.display_duplicates()
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText(f"扫描完成，找到 {len(duplicates)} 组重复文件")

    def display_duplicates(self):
        self.tree.clear()
        total_files = 0

        for md5_value, files in self.duplicates.items():
            group_item = QTreeWidgetItem(self.tree, [f"重复组: {md5_value}", "", ""])
            # 找到文件名最短的下标
            min_idx = 0
            min_len = float('inf')
            for idx, file_path in enumerate(files):
                name_len = len(os.path.basename(file_path))
                if name_len < min_len:
                    min_len = name_len
                    min_idx = idx
            for i, file_path in enumerate(files):
                try:
                    size = os.path.getsize(file_path)
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    size, mtime = 0, ""
                child = QTreeWidgetItem(group_item, [file_path, format_size(size), mtime])
                # 只勾选文件名最短的，其他全部不勾选
                child.setCheckState(0, Qt.Checked if i == min_idx else Qt.Unchecked)
                total_files += 1
            group_item.setExpanded(True)

        self.search_results()
        self.status_label.setText(f"状态：{len(self.duplicates)} 个重复组，共 {total_files} 个文件")
        if hasattr(self, "stat_label"):
            self.stat_label.setText(f"{len(self.duplicates)} 个重复组")

    def search_results(self):
        keyword = self.search_input.text().lower().strip()
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            show_group = False
            for j in range(group.childCount()):
                child = group.child(j)
                text = child.text(0).lower()
                hidden = keyword not in text
                child.setHidden(hidden)
                if not hidden:
                    show_group = True
            group.setHidden(not show_group)

    def refresh_filter(self):
        self.exclude_ext = {
            e.strip().lower() for e in self.exclude_input.text().split(",") if e.strip()
        }

        new_duplicates = {}
        for md5_value, files in self.duplicates.items():
            new_files = []
            for file_path in files:
                ext = os.path.splitext(file_path)[1].lower()
                if ext in self.exclude_ext:
                    continue
                if not os.path.exists(file_path):
                    continue
                new_files.append(file_path)
            if len(new_files) > 1:
                new_duplicates[md5_value] = new_files

        self.duplicates = new_duplicates
        self.display_duplicates()

    def delete_files(self):
        to_delete = []
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            for j in range(group.childCount()):
                child = group.child(j)
                if child.checkState(0) != Qt.Checked:
                    to_delete.append((group, child))

        if not to_delete:
            QMessageBox.information(self, "提示", "没有选择要删除的文件")
            return

        box = QMessageBox(self)
        box.setWindowTitle("确认删除")
        box.setIcon(QMessageBox.Warning)
        box.setText(f"确认删除 {len(to_delete)} 个文件吗？\n\n删除后不可恢复，请谨慎操作。")
        btn_ok = box.addButton("确认删除", QMessageBox.AcceptRole)
        btn_cancel = box.addButton("取消", QMessageBox.RejectRole)
        box.setDefaultButton(btn_cancel)
        box.exec()
        if box.clickedButton() != btn_ok:
            return

        failed = []
        deleted_count = 0
        for group, child in to_delete:
            file_path = child.text(0)
            ok, msg = delete_file_with_retry(file_path)
            if ok:
                deleted_count += 1
                group.removeChild(child)
            else:
                print(msg)
                failed.append(msg)

        if failed:
            QMessageBox.warning(self, "删除失败", f"以下文件未能删除:\n" + "\n\n".join(failed))
        elif deleted_count:
            QMessageBox.information(self, "删除完成", f"成功删除 {deleted_count} 个文件。")

        for i in reversed(range(root.childCount())):
            group = root.child(i)
            if group.childCount() == 0:
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(group))

        self._collect_duplicates_from_tree()
        self.display_duplicates()

    def tree_right_click(self, pos):
        item = self.tree.itemAt(pos)
        if not item or not item.parent():
            return

        menu = QMenu(self)
        open_dir = menu.addAction("打开所在目录")
        delete_file = menu.addAction("删除文件")

        def open_dir_func():
            folder = os.path.dirname(item.text(0))
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.run(["open", folder])
            else:
                subprocess.run(["xdg-open", folder])

        def delete_file_func():
            file_path = item.text(0)
            ok, msg = delete_file_with_retry(file_path)
            if not ok:
                print(msg)
                QMessageBox.warning(self, "删除失败", f"{msg}")
                return
            parent = item.parent()
            parent.removeChild(item)
            if parent.childCount() == 0:
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(parent))
            self._collect_duplicates_from_tree()
            self.display_duplicates()

        open_dir.triggered.connect(open_dir_func)
        delete_file.triggered.connect(delete_file_func)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            self.thread.stop()
            self.thread.wait(1500)

        self._collect_duplicates_from_tree()
        ui_state = {
            "window_size": [self.width(), self.height()],
            "column_widths": [self.tree.columnWidth(i) for i in range(3)],
        }
        save_scan_result(self.duplicates, ui_state)
        super().closeEvent(event)


def open_hash_md5_tool(self):
    dlg = HashMD5ToolDialog(self)
    dlg.exec()
