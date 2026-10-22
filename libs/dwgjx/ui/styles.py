"""粉色可爱紧凑风格 QSS。

设计目标：
- 窗口高度略大于宽度、不可调整大小（由 main_window 调用 setFixedSize）
- 控件密集、圆角、淡粉色渐变
- 字号统一、padding 收紧，整体小巧精致
"""

PINK_QSS = """
* {
    font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
    font-size: 9pt;
    outline: 0;
}

QMainWindow, QWidget#central {
    background-color: #fff5f8;
}

QLabel {
    background: transparent;
    color: #6a3a52;
}

/* 普通按钮 */
QPushButton {
    background-color: #ffd9e6;
    border: 1px solid #f7a8c4;
    border-radius: 10px;
    padding: 5px 12px;
    min-height: 22px;
    color: #6a3a52;
    font-weight: 500;
}
QPushButton:hover {
    background-color: #ffc2d8;
    border-color: #ff8fb5;
}
QPushButton:pressed {
    background-color: #ff8fb5;
}
QPushButton:disabled {
    background-color: #f0e0e8;
    color: #b0a0a8;
    border-color: #d8c0cc;
}

/* 主按钮 */
QPushButton#start_btn {
    background-color: #ff8fb5;
    color: #ffffff;
    font-weight: 600;
    padding: 6px 18px;
}
QPushButton#start_btn:hover {
    background-color: #ff70a0;
}
QPushButton#start_btn:disabled {
    background-color: #e0c8d4;
    color: #f0e0e8;
}

/* 文件列表 */
QListWidget {
    background-color: #fffafc;
    border: 1.5px solid #f7c8dc;
    border-radius: 8px;
    padding: 3px;
}
QListWidget::item {
    padding: 3px 6px;
    border-radius: 4px;
    color: #6a3a52;
}
QListWidget::item:hover {
    background-color: #ffe9f2;
}
QListWidget::item:selected {
    background-color: #ffd6e7;
    color: #5a2a42;
}

/* 进度条 */
QProgressBar {
    background-color: #fff0f5;
    border: 1.5px solid #f7c8dc;
    border-radius: 8px;
    text-align: center;
    color: #6a3a52;
    min-height: 18px;
    max-height: 18px;
}
QProgressBar::chunk {
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #ffb0d0, stop:1 #ff7eb0
    );
    border-radius: 7px;
    margin: 0px;
}

/* 下拉框 */
QComboBox {
    background-color: #fff0f5;
    border: 1.5px solid #f7c8dc;
    border-radius: 6px;
    padding: 4px 10px;
    min-height: 22px;
    color: #6a3a52;
}
QComboBox:hover {
    border-color: #ff8fb5;
}
QComboBox::drop-down {
    border: 0;
    width: 18px;
}
QComboBox QAbstractItemView {
    background-color: #fffafc;
    border: 1px solid #f7c8dc;
    border-radius: 4px;
    selection-background-color: #ffd6e7;
    selection-color: #5a2a42;
    outline: 0;
}

/* 输入框 */
QLineEdit {
    background-color: #fffafc;
    border: 1.5px solid #f7c8dc;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 22px;
    color: #6a3a52;
}
QLineEdit:read-only {
    background-color: #fbeef3;
    color: #8a5a6e;
}
QLineEdit:focus {
    border-color: #ff8fb5;
}

/* ETA / 进度文字 */
QLabel#eta_label, QLabel#progress_label {
    color: #c45a82;
    font-weight: 600;
}

/* 滚动条 */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #f7c8dc;
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover {
    background: #ff8fb5;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
}

/* 提示框 */
QMessageBox {
    background-color: #fff5f8;
}
QMessageBox QLabel {
    color: #6a3a52;
}
"""
