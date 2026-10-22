from PySide6.QtCore import QUrl, Signal, Qt, QSize
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton, QVBoxLayout
from PySide6.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEngineProfile, QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from .widgets import Menu, STYLE, add_action, install_chinese, style_widget
from .icons import icon
import re


class Sniffer(QWebEngineUrlRequestInterceptor):
    found = Signal(str)

    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        if re.search(r"\.(m3u8|mp4|mp3|m4a)(?:[?#]|$)", url, re.I):
            self.found.emit(url)


class ChineseWebView(QWebEngineView):
    def contextMenuEvent(self, event):
        from PySide6.QtWebEngineCore import QWebEnginePage
        request = self.lastContextMenuRequest()
        menu = Menu(self)
        if request and request.selectedText():
            add_action(menu, "复制", lambda: self.page().triggerAction(QWebEnginePage.Copy))
        if request and request.linkUrl().isValid():
            link = request.linkUrl().toString()
            add_action(menu, "复制链接地址", lambda: QApplication.clipboard().setText(link))
        if request and request.mediaType() in (request.MediaType.MediaTypeVideo, request.MediaType.MediaTypeAudio):
            add_action(menu, "播放／暂停", lambda: self.page().triggerAction(QWebEnginePage.ToggleMediaPlayPause))
            add_action(menu, "静音／取消静音", lambda: self.page().triggerAction(QWebEnginePage.ToggleMediaMute))
        add_action(menu, "全选", lambda: self.page().triggerAction(QWebEnginePage.SelectAll))
        menu.addSeparator()
        add_action(menu, "重新加载", self.reload)
        menu.exec(event.globalPos())
        menu.deleteLater()


class WebPlayer(QDialog):
    media = Signal(object)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        install_chinese()
        style_widget(self)
        self.setStyleSheet(STYLE)
        self.setWindowTitle("网页播放 · 听读看")
        self.setWindowIcon(icon('video'))
        self.resize(860, 590)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.page_url = url
        self.detected = ""
        layout = QVBoxLayout(self)
        self.label = QLabel("网页加载后点击播放；检测到媒体链接后可转内置播放或下载。")
        self.label.setWordWrap(True)
        layout.addWidget(self.label)
        self.view = ChineseWebView(self)
        self.profile = QWebEngineProfile(self)
        self.view.setPage(QWebEnginePage(self.profile, self.view))
        self.sniffer = Sniffer(self)
        self.sniffer.found.connect(self.on_found)
        self.profile.setUrlRequestInterceptor(self.sniffer)
        self.profile.downloadRequested.connect(lambda download: download.cancel())
        layout.addWidget(self.view, 1)
        self.use = QPushButton("使用检测到的媒体链接")
        self.use.setIcon(icon('link'))
        self.use.setIconSize(QSize(18, 18))
        self.use.setEnabled(False)
        self.use.clicked.connect(self.use_media)
        layout.addWidget(self.use)
        self.view.load(QUrl(url))

    def on_found(self, url):
        if self.detected:
            return
        self.detected = url
        self.label.setText("已检测到媒体链接。可在网页继续播放，或点击下方按钮转入听读看。")
        self.use.setEnabled(True)

    def use_media(self):
        self.media.emit(dict(url=self.detected, headers={"Referer": self.view.url().toString()}))
        self.close()

    def closeEvent(self, event):
        self.view.stop()
        self.profile.setUrlRequestInterceptor(None)
        self.view.page().deleteLater()
        super().closeEvent(event)
