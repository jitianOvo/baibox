from PySide6.QtCore import QSize
from PySide6.QtGui import QFont, QTextBlockFormat, QTextCursor
from PySide6.QtWidgets import QDialog, QDoubleSpinBox, QFormLayout, QSpinBox, QVBoxLayout, QPushButton

from .widgets import ComboBox, TextBrowser, STYLE, style_widget
from .icons import action_icon

PALETTES = {"纸白": ("#ffffff", "#273449"), "暖纸": ("#f5ecd8", "#443b2c"),
            "护眼绿": ("#dfecdf", "#283c2c"), "夜读": ("#20252e", "#d1d5dd")}
DEFAULTS = dict(size=13, line=150, letter=0, width=900, margin=20, palette="暖纸")


class NovelReader(TextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.options = dict(DEFAULTS)
        self.setObjectName("novel_reader")

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(self.options["width"], hint.height())

    def configure(self, options):
        self.options.update(options)
        scroll = self.verticalScrollBar()
        fraction = scroll.value() / max(1, scroll.maximum())
        font = QFont("Microsoft YaHei UI", self.options["size"])
        font.setLetterSpacing(QFont.AbsoluteSpacing, self.options["letter"])
        self.setFont(font)
        self.document().setDefaultFont(font)
        background, ink = PALETTES.get(self.options["palette"], PALETTES["暖纸"])
        self.setStyleSheet(f"QTextBrowser#novel_reader {{font-size:{self.options['size']}pt;"
                          f"background:{background};color:{ink};border:1px solid {background};"
                          f"border-radius:9px;padding:{self.options['margin']}px;"
                          "selection-background-color:#9ebde8;selection-color:#173866;}")
        self.setMaximumWidth(self.options["width"])
        self.updateGeometry()
        self.format_blocks()
        scroll.setValue(round(fraction * scroll.maximum()))

    def setPlainText(self, text):
        super().setPlainText(text)
        self.format_blocks()

    def format_blocks(self):
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.Document)
        block = QTextBlockFormat()
        block.setLineHeight(self.options["line"], QTextBlockFormat.ProportionalHeight.value)
        cursor.mergeBlockFormat(block)


class ReadingSettings(QDialog):
    def __init__(self, options, changed, parent=None):
        super().__init__(parent)
        style_widget(self)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("阅读设置")
        self.setMinimumWidth(330)
        self.values = dict(options)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        layout.addLayout(form)
        for key, title, bounds, suffix in [("size", "字号", (8, 40), " pt"),
                ("line", "行间距", (100, 240), " %"), ("letter", "字间距", (-1, 12), " px"),
                ("width", "阅读列宽", (400, 1600), " px"), ("margin", "页边距", (8, 96), " px")]:
            control = QDoubleSpinBox() if key == "letter" else QSpinBox()
            style_widget(control)
            control.setRange(*bounds)
            control.setSuffix(suffix)
            control.setValue(options[key])
            if key == "letter":
                control.setSingleStep(.5)
                control.setDecimals(1)
            elif key in ("width", "line"):
                control.setSingleStep(20 if key == "width" else 10)
            control.valueChanged.connect(lambda value, k=key: self.update(k, value, changed))
            form.addRow(title, control)
        palette = ComboBox()
        palette.addItems(list(PALETTES))
        palette.setCurrentText(options["palette"])
        palette.currentTextChanged.connect(lambda value: self.update("palette", value, changed))
        form.addRow("阅读背景", palette)
        close = QPushButton("关闭")
        close.setIcon(action_icon("关闭"))
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    def update(self, key, value, changed):
        self.values[key] = value
        changed(dict(self.values))
