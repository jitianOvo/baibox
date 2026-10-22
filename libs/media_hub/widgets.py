from pathlib import Path

from PySide6.QtCore import Qt, QLibraryInfo, QTranslator, QUrl, QSize
from PySide6.QtGui import QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFrame, QLineEdit, QListView, QMenu,
    QPlainTextEdit, QStyleFactory, QTextBrowser, QStyledItemDelegate,
)

from core_lib import get_path
from .icons import action_icon

STYLE = """
QDialog { background:#f5f7fb; color:#273449; }
QWidget { font-family:'Microsoft YaHei UI','Microsoft YaHei','Segoe UI'; color:#273449; }
QLabel { background:transparent; }
QLineEdit, QComboBox, QPlainTextEdit, QTextBrowser, QTreeWidget, QListWidget {
    background:#ffffff; color:#273449; border:1px solid #dce3ef; border-radius:9px;
    selection-background-color:#ddeafe; selection-color:#173866;
}
QLineEdit, QComboBox { padding:8px 11px; min-height:20px; }
QSpinBox, QDoubleSpinBox { background:#ffffff; color:#273449; border:1px solid #dce3ef; border-radius:8px; padding:7px 10px; min-height:22px; }
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width:22px; border:0; background:#eef4fc; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image:url("__CHEVRON_UP__"); width:12px; height:12px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image:url("__CHEVRON__"); width:12px; height:12px; }
QLineEdit:hover, QComboBox:hover { border-color:#afc5e9; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextBrowser:focus { border-color:#5b91e8; }
QLineEdit:disabled, QComboBox:disabled { background:#eef2f7; color:#94a3b8; }
QComboBox { padding-right:32px; }
QComboBox::drop-down { subcontrol-origin:padding; subcontrol-position:top right; width:30px; border:0; }
QComboBox::down-arrow { image:url("__CHEVRON__"); width:16px; height:16px; }
QComboBox QLineEdit { border:0; border-radius:0; padding:0; min-height:0; background:transparent; }
QComboBox QAbstractItemView, QListView#hub_popup {
    background:#ffffff; color:#273449; border:1px solid #dce3ef; border-radius:9px;
    padding:5px; outline:0; selection-background-color:#e4eeff; selection-color:#2463ce;
}
QComboBox QAbstractItemView::item, QListView#hub_popup::item {
    min-height:26px; padding:5px 10px; border:0; border-radius:5px;
}
QComboBox QAbstractItemView::item:hover, QListView#hub_popup::item:hover { background:#eff5ff; }
QComboBox QAbstractItemView::item:selected, QListView#hub_popup::item:selected { background:#e4eeff; color:#2463ce; }
QPlainTextEdit, QTextBrowser { padding:10px; }
QTreeWidget, QListWidget { padding:5px; outline:0; alternate-background-color:#f8fafc; }
QTreeWidget::item, QListWidget::item { padding:7px 6px; border:0; border-radius:5px; }
QTreeWidget::item:hover, QListWidget::item:hover { background:#eef4ff; }
QTreeWidget::item:selected, QListWidget::item:selected { background:#e4eeff; color:#2463ce; }
QHeaderView { background:transparent; }
QHeaderView::section { background:#f1f5fb; border:0; padding:9px 7px; color:#68778d; }
QAbstractScrollArea::corner { background:transparent; border:0; }
QPushButton { background:#ffffff; color:#334563; border:1px solid #dce3ef;
    border-radius:9px; padding:8px 12px; }
QPushButton:hover { background:#eaf1fd; border-color:#9ebbf0; }
QPushButton:pressed { background:#dce9fc; }
QPushButton:disabled { color:#a4adbb; background:#f6f8fb; }
QPushButton#primary { background:#2b6cdb; color:white; border-color:#2b6cdb; }
QPushButton#primary:hover { background:#235fc6; }
QPushButton::menu-indicator { image:url("__CHEVRON__"); width:12px; height:12px; subcontrol-position:right center; right:5px; }
QTabWidget::pane { border:0; }
QTabBar::tab { padding:10px 20px; color:#66748a; background:transparent; }
QTabBar::tab:selected { color:#2463ce; border-bottom:2px solid #2463ce; }
QSplitter::handle { background:transparent; width:8px; }
QScrollBar:vertical { background:transparent; width:9px; margin:2px; border:0; }
QScrollBar::handle:vertical { background:#c7d4e6; min-height:30px; border-radius:3px; }
QScrollBar::handle:vertical:hover { background:#91acd2; }
QScrollBar:horizontal { background:transparent; height:9px; margin:2px; border:0; }
QScrollBar::handle:horizontal { background:#c7d4e6; min-width:30px; border-radius:3px; }
QScrollBar::handle:horizontal:hover { background:#91acd2; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; border:0; background:transparent; }
QScrollBar::add-page, QScrollBar::sub-page { background:transparent; }
QSlider::groove:horizontal { height:5px; border:0; border-radius:2px; background:#d8e3f1; }
QSlider::sub-page:horizontal { background:#397ce0; border-radius:2px; }
QSlider::handle:horizontal { background:#ffffff; border:2px solid #397ce0; width:12px; height:12px; margin:-5px 0; border-radius:7px; }
QMenu { background:#ffffff; color:#273449; border:1px solid #dce3ef; border-radius:9px; padding:5px; }
QMenu::item { padding:8px 28px 8px 12px; border:0; border-radius:5px; }
QMenu::item:selected { background:#e4eeff; color:#2463ce; }
QMenu::item:disabled { color:#a4adbb; }
QMenu::separator { height:1px; background:#e8edf5; margin:4px 8px; }
QToolTip { background:#20385b; color:#ffffff; border:0; padding:6px; border-radius:5px; }
""".replace("__CHEVRON__", Path(get_path("assets/media_hub/chevron-down.svg")).as_posix()).replace(
    "__CHEVRON_UP__", Path(get_path("assets/media_hub/chevron-up.svg")).as_posix())


def fusion_style():
    app = QApplication.instance()
    if not hasattr(app, "_media_hub_fusion"):
        app._media_hub_fusion = QStyleFactory.create("Fusion")
        app._media_hub_fusion.setParent(app)
    return app._media_hub_fusion


def install_chinese():
    app = QApplication.instance()
    if hasattr(app, "_media_hub_translators"):
        return
    app._media_hub_translators = []
    folder = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    for name in ("qtbase_zh_CN", "qtwebengine_zh_CN"):
        translator = QTranslator(app)
        if translator.load(name, folder):
            app.installTranslator(translator)
            app._media_hub_translators.append(translator)


def style_widget(widget):
    widget.setStyle(fusion_style())
    widget.setFont(QFont("Microsoft YaHei UI", 10))


class Menu(QMenu):
    def __init__(self, parent=None):
        super().__init__(parent)
        style_widget(self)
        self.setStyleSheet(STYLE)

    def addAction(self, *args):
        action = super().addAction(*args)
        if action is not None:
            action.setIcon(action_icon(action.text()))
        return action


def add_action(menu, text, callback, enabled=True, shortcut=None):
    action = menu.addAction(text)
    action.setEnabled(enabled)
    if shortcut:
        action.setShortcut(QKeySequence(shortcut))
    action.triggered.connect(callback)
    return action


class LineEdit(QLineEdit):
    def create_chinese_menu(self):
        menu = Menu(self)
        editable = not self.isReadOnly()
        selected = self.hasSelectedText()
        if editable:
            add_action(menu, "撤销", self.undo, self.isUndoAvailable(), QKeySequence.Undo)
            add_action(menu, "重做", self.redo, self.isRedoAvailable(), QKeySequence.Redo)
            menu.addSeparator()
            add_action(menu, "剪切", self.cut, selected, QKeySequence.Cut)
        add_action(menu, "复制", self.copy, selected, QKeySequence.Copy)
        if editable:
            add_action(menu, "粘贴", self.paste, bool(QApplication.clipboard().text()), QKeySequence.Paste)
            add_action(menu, "删除", self.del_, selected)
        menu.addSeparator()
        add_action(menu, "全选", self.selectAll, bool(self.text()), QKeySequence.SelectAll)
        return menu

    def contextMenuEvent(self, event):
        menu = self.create_chinese_menu()
        menu.exec(event.globalPos())
        menu.deleteLater()


class SpacedItemDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        return QSize(hint.width(), max(hint.height(), option.fontMetrics.height() + 18))


class ComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        style_widget(self)
        view = QListView(self)
        style_widget(view)
        view.setObjectName("hub_popup")
        view.setStyleSheet(STYLE)
        view.setFrameShape(QFrame.NoFrame)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setView(view)
        self.setItemDelegate(SpacedItemDelegate(view))
        view.setUniformItemSizes(True)

    def setEditable(self, editable):
        super().setEditable(editable)
        if editable and not isinstance(self.lineEdit(), LineEdit):
            self.setLineEdit(LineEdit(self))


class TextBrowser(QTextBrowser):
    def create_chinese_menu(self, position=None):
        menu = Menu(self)
        add_action(menu, "复制", self.copy, self.textCursor().hasSelection(), QKeySequence.Copy)
        link = self.anchorAt(position) if position is not None else ""
        if link:
            resolved = self.document().baseUrl().resolved(QUrl(link)).toString()
            add_action(menu, "复制链接地址", lambda: QApplication.clipboard().setText(resolved))
        menu.addSeparator()
        add_action(menu, "全选", self.selectAll, not self.document().isEmpty(), QKeySequence.SelectAll)
        return menu

    def contextMenuEvent(self, event):
        menu = self.create_chinese_menu(event.pos())
        menu.exec(event.globalPos())
        menu.deleteLater()


class PlainTextEdit(QPlainTextEdit):
    def create_chinese_menu(self):
        menu = Menu(self)
        selected, editable = self.textCursor().hasSelection(), not self.isReadOnly()
        if editable:
            add_action(menu, "撤销", self.undo, self.document().isUndoAvailable(), QKeySequence.Undo)
            add_action(menu, "重做", self.redo, self.document().isRedoAvailable(), QKeySequence.Redo)
            menu.addSeparator()
            add_action(menu, "剪切", self.cut, selected, QKeySequence.Cut)
        add_action(menu, "复制", self.copy, selected, QKeySequence.Copy)
        if editable:
            add_action(menu, "粘贴", self.paste, bool(QApplication.clipboard().text()), QKeySequence.Paste)
            add_action(menu, "删除", self.delete_selection, selected)
        menu.addSeparator()
        add_action(menu, "全选", self.selectAll, not self.document().isEmpty(), QKeySequence.SelectAll)
        return menu

    def delete_selection(self):
        cursor = self.textCursor()
        cursor.removeSelectedText()
        self.setTextCursor(cursor)

    def contextMenuEvent(self, event):
        menu = self.create_chinese_menu()
        menu.exec(event.globalPos())
        menu.deleteLater()
