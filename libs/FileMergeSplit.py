from PyQt5.QtWidgets import (
    QDialog, QLabel, QLineEdit, QPushButton,
    QFileDialog, QVBoxLayout, QHBoxLayout, QGroupBox
)
from PyQt5.QtCore import Qt
import core_lib
from PyQt5.QtWidgets import QMessageBox
import os
import sys
from PyQt5.QtWidgets import QApplication

# ========= 路径安全检测函数 ==========


def is_valid_file(path):
    return (
        path
        and os.path.isfile(path)
        and os.access(path, os.R_OK)
    )

def is_valid_dir(path):
    return (
            path
            and os.path.isdir(path)
            and os.access(path, os.W_OK)
    )


def is_valid_output_file(path):
    if not path:
        return False

    parent = os.path.dirname(path)
    if not parent:
        return False

    return os.path.isdir(parent) and os.access(parent, os.W_OK)


class FileMergeSplitDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("文件合成与拆解")
        self.resize(600, 350)

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # ========== 拆解区域 ==========
        split_group = QGroupBox("拆解")
        split_layout = QVBoxLayout()

        self.split_input = QLineEdit()
        self.split_input.setPlaceholderText("请选择分券文件")
        btn_split_input = QPushButton("选择")

        self.split_output = QLineEdit()
        self.split_output.setPlaceholderText("请选择拆解输出文件夹")
        btn_split_output = QPushButton("选择")

        btn_split_run = QPushButton("开始拆解")

        split_layout.addLayout(self._row("分券文件路径：", self.split_input, btn_split_input))
        split_layout.addLayout(self._row("输出文件夹：", self.split_output, btn_split_output))
        split_layout.addWidget(btn_split_run, alignment=Qt.AlignCenter)

        split_group.setLayout(split_layout)

        # ========== 合成区域 ==========
        merge_group = QGroupBox("合成")
        merge_layout = QVBoxLayout()

        self.merge_input = QLineEdit()
        self.merge_input.setPlaceholderText("请选择用于合成的文件夹")
        btn_merge_input = QPushButton("选择")

        self.merge_output = QLineEdit()
        self.merge_output.setPlaceholderText("请选择合成后文件路径")
        btn_merge_output = QPushButton("选择")

        btn_merge_run = QPushButton("开始合成")

        merge_layout.addLayout(self._row("输入文件夹：", self.merge_input, btn_merge_input))
        merge_layout.addLayout(self._row("输出文件路径：", self.merge_output, btn_merge_output))
        merge_layout.addWidget(btn_merge_run, alignment=Qt.AlignCenter)

        merge_group.setLayout(merge_layout)

        # ========== 总布局 ==========
        main_layout.addWidget(split_group)
        main_layout.addWidget(merge_group)

        # ========== 信号绑定 ==========
        btn_split_input.clicked.connect(self.choose_split_file)
        btn_split_output.clicked.connect(self.choose_split_output)

        btn_merge_input.clicked.connect(self.choose_merge_input)
        btn_merge_output.clicked.connect(self.choose_merge_output)

        btn_split_run.clicked.connect(self.run_split)
        btn_merge_run.clicked.connect(self.run_merge)

    def _row(self, label_text, line_edit, button):
        layout = QHBoxLayout()
        layout.addWidget(QLabel(label_text))
        layout.addWidget(line_edit)
        layout.addWidget(button)
        return layout

    # ========== 路径选择 ==========
    def choose_split_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择分券文件")
        if path:
            self.split_input.setText(path)

    def choose_split_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if path:
            self.split_output.setText(path)

    def choose_merge_input(self):
        path = QFileDialog.getExistingDirectory(self, "选择输入文件夹")
        if path:
            self.merge_input.setText(path)

    def choose_merge_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:  # 只有选了有效路径才设置
            self.merge_output.setText(path)

    # ========== 逻辑接口（你来接） ==========
    def run_split(self):
        input_file = self.split_input.text()
        output_dir = self.split_output.text()

        if not is_valid_file(input_file):
            QMessageBox.warning(self, "路径错误", "分券文件不存在或不可读取")
            return

        if not is_valid_dir(output_dir):
            QMessageBox.warning(self, "路径错误", "输出文件夹不存在或不可写")
            return

        try:
            # 拆解逻辑
            core_lib.split_file(input_file, output_dir)
            pass
        except Exception as e:
            QMessageBox.critical(self, "拆解失败", str(e))
            return

        QMessageBox.information(self, "成功", "文件拆解完成")

    def run_merge(self):
        input_dir = self.merge_input.text()
        output_file = self.merge_output.text()

        if not is_valid_dir(input_dir):
            QMessageBox.warning(self, "路径错误", "输入文件夹不存在或不可访问")
            return

        if not is_valid_output_file(output_file):
            QMessageBox.warning(self, "路径错误", "输出文件路径非法或不可写")
            return

        try:
            # 合成逻辑
            core_lib.merge_file(input_dir, output_file)
            pass
        except Exception as e:
            QMessageBox.critical(self, "合成失败", str(e))
            return

        QMessageBox.information(self, "成功", "文件合成完成")

def Open_FileMergeSplit(parent=None):
    dialog = FileMergeSplitDialog(parent=parent)
    dialog.exec_()


if __name__ == "__main__":
    pass
    # app = QApplication(sys.argv)
    # dialog = FileMergeSplitDialog()
    # dialog.show()
    # sys.exit(app.exec_())