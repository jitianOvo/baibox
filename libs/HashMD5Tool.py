import hashlib
import json
import os
import subprocess
import sys
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
                background-color: #f4f7fc;
                color: #1f2937;
            }
            QFrame#card {
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
            }
            QLabel#titleLabel {
                font-size: 16px;
                font-weight: 700;
                color: #0f172a;
            }
            QLabel#subTitleLabel {
                font-size: 12px;
                color: #64748b;
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
                min-height: 34px;
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
                padding: 6px 8px;
                border-bottom: 1px solid #edf2fb;
            }
            QListWidget::item:selected, QTreeWidget::item:selected {
                background-color: #e6efff;
                color: #0f172a;
            }
            QTreeWidget::item {
                padding: 4px 6px;
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

        header_card = QFrame()
        header_card.setObjectName("card")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(14, 10, 14, 12)
        header_layout.setSpacing(8)

        title_label = QLabel("Hash + MD5 重复文件清理")
        title_label.setObjectName("titleLabel")
        sub_title_label = QLabel("双重校验更准确，默认保留每组首个文件")
        sub_title_label.setObjectName("subTitleLabel")
        header_layout.addWidget(title_label)
        header_layout.addWidget(sub_title_label)

        path_layout = QHBoxLayout()
        path_layout.setSpacing(8)
        self.add_path_btn = QPushButton("添加扫描路径")
        self.add_path_btn.setProperty("role", "primary")
        self.add_path_btn.clicked.connect(self.add_path)
        path_layout.addWidget(self.add_path_btn)

        self.path_list = QListWidget()
        self.path_list.setAlternatingRowColors(True)
        self.path_list.setMinimumHeight(92)
        self.path_list.setMaximumHeight(120)
        path_layout.addWidget(self.path_list)
        header_layout.addLayout(path_layout)
        layout.addWidget(header_card)

        scan_layout = QHBoxLayout()
        scan_layout.setSpacing(8)
        self.scan_btn = QPushButton("开始扫描")
        self.scan_btn.setProperty("role", "primary")
        self.scan_btn.clicked.connect(self.start_scan)
        scan_layout.addWidget(self.scan_btn)

        self.stop_btn = QPushButton("停止扫描")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_scan)
        scan_layout.addWidget(self.stop_btn)
        layout.addLayout(scan_layout)

        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel("状态: 等待扫描")
        layout.addWidget(self.status_label)

        filter_layout = QHBoxLayout()
        self.exclude_input = QLineEdit()
        self.exclude_input.setPlaceholderText("排除扩展名, 用逗号分隔: .cpp,.dll")
        self.exclude_btn = QPushButton("刷新过滤")
        self.exclude_btn.clicked.connect(self.refresh_filter)
        filter_layout.addWidget(self.exclude_input)
        filter_layout.addWidget(self.exclude_btn)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索文件/路径")
        self.search_input.textChanged.connect(self.search_results)
        filter_layout.addWidget(self.search_input)
        layout.addLayout(filter_layout)

        result_card = QFrame()
        result_card.setObjectName("card")
        result_layout = QVBoxLayout(result_card)
        result_layout.setContentsMargins(10, 10, 10, 10)
        result_layout.setSpacing(8)

        self.tree = QTreeWidget(result_card)
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["路径", "大小", "修改时间"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setMinimumHeight(180)
        result_layout.addWidget(self.tree, 1)
        layout.addWidget(result_card, 1)

        action_bar = QFrame()
        action_bar.setObjectName("card")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(10, 8, 10, 8)
        action_layout.setSpacing(8)
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
        self.status_label.setText("状态: 扫描中...")
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
            self.status_label.setText("状态: 正在停止扫描...")
            self.stop_btn.setEnabled(False)

    def update_progress(self, processed, total, file_path):
        total = max(total, 1)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(min(processed, total))
        self.status_label.setText(f"状态: {processed}/{total} - {file_path}")

    def scan_finished(self, duplicates):
        self.duplicates = duplicates
        self.display_duplicates()
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText(f"扫描完成，重复组: {len(duplicates)}")

    def display_duplicates(self):
        self.tree.clear()
        total_files = 0

        for md5_value, files in self.duplicates.items():
            group_item = QTreeWidgetItem(self.tree, [f"重复组: {md5_value}", "", ""])
            for i, file_path in enumerate(files):
                try:
                    size = os.path.getsize(file_path)
                    mtime = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    size, mtime = 0, ""
                child = QTreeWidgetItem(group_item, [file_path, format_size(size), mtime])
                child.setCheckState(0, Qt.Checked if i == 0 else Qt.Unchecked)
                total_files += 1
            group_item.setExpanded(True)

        self.search_results()
        self.status_label.setText(f"状态: {len(self.duplicates)} 个重复组, {total_files} 个文件")

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

        confirm = QMessageBox.question(self, "确认删除", f"确认删除 {len(to_delete)} 个文件吗？")
        if confirm != QMessageBox.Yes:
            return

        for group, child in to_delete:
            file_path = child.text(0)
            try:
                os.remove(file_path)
            except Exception as e:
                print(f"删除失败: {file_path}, {e}")
            group.removeChild(child)

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
            try:
                os.remove(file_path)
            except Exception as e:
                print("删除失败", e)
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
