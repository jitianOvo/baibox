import os
import json
import platform
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTreeWidget, QTreeWidgetItem, QFileDialog, QMessageBox, QHeaderView, QMenu
)
from PySide6.QtCore import Qt, QPoint

# --- 配置文件路径 ---
USER_HOME = Path.home()
CACHE_DIR = USER_HOME / "PyCache"
CACHE_DIR.mkdir(exist_ok=True)
CONFIG_FILE = CACHE_DIR / ".deepsearch_config.json"


class FileSearcherDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("深度搜索 - jitian")
        self.resize(800, 600)
        self.setMinimumSize(400, 300)

        # 上次状态
        self.last_path = ""
        self.last_keyword = ""
        self.last_results = []

        self.load_config()
        self.init_ui()
        self.restore_results()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # --- 搜索路径 ---
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("搜索目录:"))
        self.path_edit = QLineEdit(self.last_path)
        path_layout.addWidget(self.path_edit)
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self.choose_folder)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # --- 搜索关键字 ---
        keyword_layout = QHBoxLayout()
        keyword_layout.addWidget(QLabel("搜索内容:"))
        self.keyword_edit = QLineEdit(self.last_keyword)
        keyword_layout.addWidget(self.keyword_edit)
        search_btn = QPushButton("开始搜索")
        search_btn.clicked.connect(self.start_search)
        keyword_layout.addWidget(search_btn)
        layout.addLayout(keyword_layout)

        # --- 结果列表 ---
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["文件路径", "匹配内容"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tree.itemDoubleClicked.connect(self.open_file)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.tree)

    # --- 配置管理 ---
    def load_config(self):
        if CONFIG_FILE.exists():
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.last_path = cfg.get("path", "")
                    self.last_keyword = cfg.get("keyword", "")
                    self.last_results = cfg.get("results", [])
            except Exception:
                pass

    def save_config(self):
        """保存当前设置到配置文件"""
        try:
            results = []
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                results.append([item.text(0), item.text(1)])
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "path": self.path_edit.text(),
                    "keyword": self.keyword_edit.text(),
                    "results": results
                }, f, indent=4)
        except Exception as e:
            print("保存配置失败:", e)

    # --- 界面操作 ---
    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择目录", self.path_edit.text())
        if folder:
            self.path_edit.setText(folder)

    def restore_results(self):
        for r in self.last_results:
            QTreeWidgetItem(self.tree, r)

    def start_search(self):
        folder = self.path_edit.text()
        keyword = self.keyword_edit.text().strip()

        if not folder or not os.path.isdir(folder):
            QMessageBox.critical(self, "错误", "请选择有效目录")
            return
        if not keyword:
            QMessageBox.critical(self, "错误", "请输入搜索内容")
            return

        self.tree.clear()
        QApplication.processEvents()  # 刷新UI

        results_found = False
        for rootdir, dirs, files in os.walk(folder):
            for file in files:
                file_path = os.path.join(rootdir, file)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                except Exception:
                    continue

                for i, line in enumerate(lines):
                    if keyword.lower() in line.lower():
                        display_line = f"[行 {i+1}] {line.strip()}"
                        QTreeWidgetItem(self.tree, [file_path, display_line])
                        results_found = True

        count = self.tree.topLevelItemCount()
        if results_found:
            QMessageBox.information(self, "完成", f"搜索完成！共找到 {count} 条匹配项。双击结果可打开文件。")
        else:
            QMessageBox.information(self, "完成", "搜索完成，未找到匹配项。")

    def open_file(self, item, _):
        file_path = item.text(0)
        if not os.path.exists(file_path):
            QMessageBox.critical(self, "错误", f"文件不存在：\n{file_path}")
            return
        try:
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":
                subprocess.call(["open", file_path])
            else:
                subprocess.call(["xdg-open", file_path])
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开文件：\n{e}")

    # --- 右键菜单 ---
    def show_context_menu(self, pos: QPoint):
        item = self.tree.itemAt(pos)
        if not item:
            return
        menu = QMenu()
        open_folder_action = menu.addAction("打开所在文件夹")
        action = menu.exec(self.tree.mapToGlobal(pos))
        if action == open_folder_action:
            file_path = item.text(0)
            folder_path = os.path.dirname(file_path)
            if os.path.exists(folder_path):
                try:
                    if platform.system() == "Windows":
                        os.startfile(folder_path)
                    elif platform.system() == "Darwin":
                        subprocess.call(["open", folder_path])
                    else:
                        subprocess.call(["xdg-open", folder_path])
                except Exception as e:
                    QMessageBox.critical(self, "错误", f"无法打开文件夹：\n{e}")

    def closeEvent(self, event):
        self.save_config()
        super().closeEvent(event)


# --- 工具箱接口函数 ---
def open_file_searcher(parent=None):
    """
    在其他 PyQt 程序中调用这个函数即可打开搜索工具。
    parent: 可选的父窗口
    """
    dlg = FileSearcherDialog(parent)
    dlg.exec()  # 模态对话框，不可点击父窗口


if __name__ == "__main__":
    pass
    # app = QApplication(sys.argv)
    # dlg = FileSearcherDialog()
    # dlg.show()
    # sys.exit(app.exec())