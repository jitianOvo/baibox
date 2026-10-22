import json
import os
import re
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal, QEvent, QSize
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QSlider, QSplitter, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget, QAbstractItemView, QCompleter, QHeaderView, QFormLayout, QSpinBox,
)

from core_lib import get_path
from . import adapters
from .catalog import ADAPTERS, Catalog, KINDS, parse_sources
from .services import Services, download, friendly_error
from .selection import episode_match
from .icons import action_icon, icon
from .music_search import PLATFORMS, MIGU_PREFERRED
from .reading import DEFAULTS, PALETTES, NovelReader, ReadingSettings
from .book_download import download_book
from .widgets import (
    STYLE, ComboBox as QComboBox, LineEdit as QLineEdit, Menu as QMenu,
    PlainTextEdit as QPlainTextEdit, TextBrowser as QTextBrowser,
    fusion_style, install_chinese, style_widget, SpacedItemDelegate,
)

class Job(QObject):
    progress = Signal(object)
    completed = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, function, parent):
        super().__init__(parent)
        self.function = function
        self.cancel = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        try:
            result = self.function(self.cancel, self.notify)
            if not self.cancel.is_set():
                self.completed.emit(result)
        except Exception as exc:
            if not self.cancel.is_set():
                self.failed.emit(friendly_error(exc))
        finally:
            try:
                self.finished.emit()
            except RuntimeError:
                pass

    def notify(self, value):
        if not self.cancel.is_set():
            self.progress.emit(value)


def button(text, callback, primary=False):
    widget = QPushButton(text)
    style_widget(widget)
    widget.setIcon(action_icon(text, '#ffffff' if primary else '#526581'))
    widget.setIconSize(QSize(18, 18))
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


def table(headers):
    widget = QTreeWidget()
    style_widget(widget)
    widget.header().setStyle(fusion_style())
    widget.setHeaderLabels(headers)
    widget.header().setFixedHeight(widget.fontMetrics().height() + 22)
    widget.setItemDelegate(SpacedItemDelegate(widget))
    widget.setUniformRowHeights(True)
    widget.setRootIsDecorated(False)
    widget.setAlternatingRowColors(True)
    widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
    widget.setSortingEnabled(False)
    return widget


class MediaHubDialog(QDialog):
    def __init__(self, parent=None, data_folder=None):
        super().__init__(parent)
        install_chinese()
        style_widget(self)
        self.setWindowTitle("听读看 · 超级白工具箱")
        self.setWindowIcon(icon('hub', '#2563eb'))
        area = self.screen().availableGeometry()
        width, height = min(960, area.width() - 30), min(650, area.height() - 50)
        self.resize(width, height)
        self.setMinimumSize(min(760, width), min(500, height))
        self.setStyleSheet(STYLE)
        if data_folder is None:
            packaged = getattr(sys, "frozen", False) or "__compiled__" in globals()
            data_folder = Path(sys.executable).parent / "data" / "media_hub" if packaged else get_path("data/media_hub")
        self.catalog = Catalog(data_folder)
        self.catalog.bootstrap(get_path("assets/media_hub/sources.json"))
        self.catalog.curate_defaults()
        self.services = Services(self.catalog)
        self.source_names = self.catalog.source_labels()
        self.jobs = []
        self.search_jobs = {}
        self.open_job = None
        self.download_job = None
        self.current_result = None
        self.current_source = None
        self.current_episodes = []
        self.current_episode = None
        self.media = None
        self.player = None
        self.proxy = None
        self.web_dialog = None
        self.logs = []
        self.pages = {}
        self.fullscreen_window = None
        self.reading_window = None
        self.video_attempts = []
        self.music_attempts = []
        self.resume_position = 0
        self.last_motion = time.monotonic()
        self.last_saved = 0
        self.switching = False
        self.build()
        self.watchdog = QTimer(self)
        self.watchdog.setInterval(2000)
        self.watchdog.timeout.connect(self.check_playback)
        self.reload_sources()
        QApplication.instance().aboutToQuit.connect(self.shutdown)

    def build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        head = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(icon('hub', '#2563eb').pixmap(28, 28))
        head.addWidget(mark)
        title = QLabel("听读看")
        title.setStyleSheet("font-size:24px;font-weight:600;color:#20385b;")
        head.addWidget(title)
        head.addWidget(QLabel("书、声音和画面，放在一起。"))
        head.addStretch()
        head.addWidget(button("打开链接", self.open_link))
        head.addWidget(button("最近使用", self.show_history))
        head.addWidget(button("设置", self.show_settings))
        layout.addLayout(head)
        self.tabs = QTabWidget()
        self.tabs.setIconSize(QSize(18, 18))
        for kind, name in KINDS.items():
            color = {'book': '#397ce0', 'music': '#8b5cf6', 'video': '#0d9488'}[kind]
            self.tabs.addTab(self.build_search_page(kind), icon(kind, color), name)
        self.sources_page = self.build_sources_page()
        self.sources_page.hide()
        layout.addWidget(self.tabs, 1)
        controls = QHBoxLayout()
        self.now = QLabel("尚未播放")
        self.now.setMinimumWidth(120)
        self.play_button = button("播放／暂停", self.toggle_play)
        controls.addWidget(self.now)
        controls.addWidget(self.play_button)
        controls.addWidget(button("停止", self.stop_play))
        controls.addWidget(button("换源", self.next_source))
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderReleased.connect(self.seek_to)
        controls.addWidget(self.seek, 1)
        self.clock = QLabel("00:00 / 00:00")
        controls.addWidget(self.clock)
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(70)
        self.volume.setFixedWidth(75)
        self.volume.valueChanged.connect(self.set_volume)
        controls.addWidget(QLabel("音量"))
        controls.addWidget(self.volume)
        self.controls_widget = QWidget()
        self.controls_widget.setLayout(controls)
        self.main_layout = layout
        layout.addWidget(self.controls_widget)
        footer = QHBoxLayout()
        self.status = QLabel("输入名称，双击结果打开。视频双击画面或按 F11 全屏。")
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        footer.addWidget(button("取消任务", self.cancel_jobs))
        footer.addWidget(button("详情", self.show_logs))
        layout.addLayout(footer)
        for key, callback in [("F11", self.toggle_fullscreen), ("Space", self.toggle_play),
                              ("Ctrl+Right", lambda: self.step_episode(1)), ("Ctrl+Left", lambda: self.step_episode(-1))]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)

    def build_search_page(self, kind):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        entry = QLineEdit()
        entry.addAction(icon('search'), QLineEdit.LeadingPosition)
        entry.setPlaceholderText({"book": "书名／作者", "music": "歌名／歌手／声音关键词", "video": "影片／剧集名称"}[kind])
        source_combo = QComboBox()
        source_combo.setMinimumWidth(190)
        source_combo.setMaximumWidth(260)
        row.addWidget(entry, 1)
        source_combo.hide()
        platform = QComboBox()
        platform.addItem("综合搜索", "auto")
        platform.addItem("网易", "wy")
        platform.addItem("酷我", "kw")
        platform.addItem("QQ", "tx")
        platform.addItem("咪咕", "mg")
        quality = QComboBox()
        quality.addItems(["128k", "320k", "flac", "flac24bit"])
        if kind == "music":
            platform.setCurrentIndex(max(0, platform.findData(self.catalog.setting("music_platform_v2", "auto"))))
            row.addWidget(platform)
            row.addWidget(quality)
        search_button = button("搜索", lambda: self.search(kind), True)
        entry.returnPressed.connect(lambda: self.search(kind))
        row.addWidget(search_button)
        row.addWidget(button("下一页", lambda: self.search(kind, next_page=True)))
        outer.addLayout(row)
        split = QSplitter(Qt.Horizontal)
        results = table(["歌名", "歌手", "专辑／平台"] if kind == "music" else ["名称", "作者／来源"])
        results.setSelectionMode(QAbstractItemView.SingleSelection)
        results.setColumnWidth(0, 230)
        results.header().setSectionResizeMode(QHeaderView.Stretch)
        results.itemDoubleClicked.connect(lambda node, _: self.open_result(node.data(0, Qt.UserRole)))
        split.addWidget(results)
        pane = QWidget()
        panel = QVBoxLayout(pane)
        panel.setContentsMargins(4, 0, 0, 0)
        caption = QLabel("双击搜索结果打开")
        caption.setWordWrap(True)
        caption.setStyleSheet("font-size:15px;font-weight:600;")
        panel.addWidget(caption)
        chapters = QComboBox()
        chapters.setMinimumWidth(150)
        chapters.setMaxVisibleItems(18)
        chapters.setEditable(True)
        chapters.setInsertPolicy(QComboBox.NoInsert)
        chapters.completer().setFilterMode(Qt.MatchContains)
        chapters.completer().setCompletionMode(QCompleter.PopupCompletion)
        completion = chapters.completer().popup()
        completion.setObjectName("hub_popup")
        style_widget(completion)
        completion.setStyleSheet(STYLE)
        completion.setItemDelegate(SpacedItemDelegate(completion))
        work_source = QComboBox()
        work_source.setToolTip("切换当前作品的来源，保留当前集／章节")
        road = QComboBox()
        road.setToolTip("同一来源的播放线路")
        if kind != "music":
            source_row = QHBoxLayout()
            source_row.addWidget(QLabel("来源"))
            source_row.addWidget(work_source, 1)
            if kind == "video":
                source_row.addWidget(QLabel("线路"))
                source_row.addWidget(road, 1)
            panel.addLayout(source_row)
        work_source.currentIndexChanged.connect(lambda index: self.switch_work_source(kind, index))
        road.currentIndexChanged.connect(lambda _: self.switch_road())
        resolution = QComboBox()
        if kind == "video":
            resolution.addItem("自动 · 源清晰度", None)
            resolution.setToolTip("显示当前源实际提供的清晰度；下载使用所选清晰度")
            resolution.currentIndexChanged.connect(self.change_resolution)
            resolution_row = QHBoxLayout()
            resolution_row.addWidget(QLabel("清晰度"))
            resolution_row.addWidget(resolution, 1)
            panel.addLayout(resolution_row)
        chapter_row = QHBoxLayout()
        chapter_row.addWidget(chapters, 1)
        if kind != "music":
            chapter_row.addWidget(button("上一章" if kind == "book" else "上一集", lambda: self.step_episode(-1, kind)))
            chapter_row.addWidget(button("下一章" if kind == "book" else "下一集", lambda: self.step_episode(1, kind)))
            panel.addLayout(chapter_row)
        chapters.currentIndexChanged.connect(lambda index: self.choose_episode(kind, index))
        reader = NovelReader() if kind == "book" else QTextBrowser()
        reader.setOpenExternalLinks(False)
        reader.setFont(QFont("Microsoft YaHei UI", 12))
        if kind == "book":
            reader.setObjectName("novel_reader")
            self.reader_options = dict(DEFAULTS, **self.catalog.setting("reader_options_v3", {}))
            self.reader_font_size = min(40, max(8, int(self.catalog.setting("reader_font_size", self.reader_options["size"]))))
            self.apply_reader_font(reader)
        reader.setPlainText({"book": "输入书名或作者，双击结果阅读。\n\n章节框可输入关键词定位；下方可调整字号和保存正文。最近使用会记住阅读位置。",
                             "music": "输入歌名或“歌手 歌名”，双击收听。\n\n综合搜索合并酷我、网易、QQ、咪咕，常规版本优先；获取地址失败会自动换音源。",
                             "video": "输入片名，双击播放。\n\n来源、线路和集数分别选择；失效线路自动尝试其他来源。双击画面全屏，Esc 返回。"}[kind])
        reading_container = QWidget()
        reading_layout = QHBoxLayout(reading_container)
        reading_layout.setContentsMargins(0, 0, 0, 0)
        reading_layout.addWidget(reader, 1)
        if kind == "book":
            reading_layout.setAlignment(reader, Qt.AlignHCenter)
        panel.addWidget(reading_container, 1)
        video_container = QWidget()
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(0, 0, 0, 0)
        video_container.hide()
        if kind == "video":
            panel.addWidget(video_container, 2)
        actions = QHBoxLayout()
        if kind != "book":
            actions.addWidget(button("打开选中", lambda: self.open_selected(kind), True))
        actions.addWidget(button("下载单章" if kind == "book" else "下载", lambda: self.save_content(kind)))
        if kind == "video":
            actions.addWidget(button("全屏", self.toggle_fullscreen))
        elif kind == "book":
            actions.addWidget(button("下载全本", self.download_book_range))
            reading_actions = QHBoxLayout()
            reading_actions.addWidget(button("全屏阅读", self.toggle_reading_fullscreen))
            reading_actions.addWidget(button("阅读设置", self.show_reading_settings))
            reading_actions.addWidget(button("字号＋", lambda: self.change_reader_font(1)))
            reading_actions.addWidget(button("字号－", lambda: self.change_reader_font(-1)))
            panel.addLayout(reading_actions)
        if kind != "music":
            more = QPushButton("更多")
            more.setIcon(action_icon('更多'))
            more.setIconSize(QSize(18, 18))
            menu = QMenu(more)
            menu.addAction("打开原网页", lambda: self.open_original(kind))
            if kind == "book":
                menu.addAction("下载全本／区间…", self.download_book_range)
                menu.addAction("字号＋", lambda: self.change_reader_font(1))
                menu.addAction("字号－", lambda: self.change_reader_font(-1))
            if kind == "video":
                menu.addAction("网页播放", self.web_play_current)
            more.setMenu(menu)
            actions.addWidget(more)
        panel.addLayout(actions)
        split.addWidget(pane)
        split.setSizes([390, 550])
        outer.addWidget(split, 1)
        self.pages[kind] = dict(entry=entry, source=source_combo, platform=platform, quality=quality, results=results,
                                chapters=chapters, caption=caption, reader=reader, video=video_container,
                                video_layout=video_layout, page=1, keyword="", episodes=[], result=None, text="")
        self.pages[kind].update(work_source=work_source, road=road, resolution=resolution,
                                reading_layout=reading_layout, reading_container=reading_container,
                                all_episodes=[], alternatives=[])
        return page

    def apply_reader_font(self, reader):
        if isinstance(reader, NovelReader):
            self.reader_options["size"] = self.reader_font_size
            reader.configure(self.reader_options)
            return
        font = QFont("Microsoft YaHei UI", self.reader_font_size)
        reader.setFont(font)
        reader.document().setDefaultFont(font)
        reader.setStyleSheet(f"""QTextBrowser#novel_reader {{
            font-size:{self.reader_font_size}pt; background:#ffffff; color:#273449;
            border:1px solid #dce3ef; border-radius:9px; padding:12px;
            selection-background-color:#ddeafe; selection-color:#173866;
        }}""")

    def change_reader_font(self, delta):
        self.reader_font_size = min(40, max(8, self.reader_font_size + delta))
        self.apply_reader_font(self.pages["book"]["reader"])
        self.catalog.save_setting("reader_font_size", self.reader_font_size)
        self.status.setText(f"小说字号：{self.reader_font_size} pt")

    def show_reading_settings(self):
        parent = self.reading_window if self.reading_window and self.reading_window.isVisible() else self
        dialog = ReadingSettings(self.reader_options, self.update_reading_options, parent)
        dialog.exec()

    def update_reading_options(self, options):
        self.reader_options = options
        self.reader_font_size = int(options["size"])
        self.apply_reader_font(self.pages["book"]["reader"])
        self.catalog.save_setting("reader_font_size", self.reader_font_size)
        self.catalog.save_setting("reader_options_v3", self.reader_options)
        if self.reading_window:
            background, ink = PALETTES[options["palette"]]
            self.reading_window.setStyleSheet(STYLE + f"QWidget#reading_window {{background:{background};}} QLabel {{color:{ink};}}")

    def toggle_reading_fullscreen(self):
        if self.reading_window and self.reading_window.isVisible():
            self.exit_reading_fullscreen()
            return
        if self.reading_window is None:
            self.reading_window = QWidget(None, Qt.Window)
            self.reading_window.setObjectName("reading_window")
            style_widget(self.reading_window)
            self.reading_window.setWindowTitle("听读看 · 全屏阅读")
            self.reading_window.setWindowIcon(icon("book"))
            self.reading_window.installEventFilter(self)
            self.reading_full_layout = QVBoxLayout(self.reading_window)
            top = QHBoxLayout()
            self.reading_title = QLabel()
            top.addWidget(self.reading_title, 1)
            for name, callback in [("上一章", lambda: self.step_episode(-1, "book")),
                                   ("下一章", lambda: self.step_episode(1, "book")),
                                   ("阅读设置", self.show_reading_settings), ("退出全屏", self.exit_reading_fullscreen)]:
                top.addWidget(button(name, callback))
            self.reading_full_layout.addLayout(top)
            for key, callback in [("Escape", self.exit_reading_fullscreen), ("F11", self.exit_reading_fullscreen),
                                   ("Ctrl+Right", lambda: self.step_episode(1, "book")),
                                   ("Ctrl+Left", lambda: self.step_episode(-1, "book"))]:
                shortcut = QShortcut(QKeySequence(key), self.reading_window)
                shortcut.activated.connect(callback)
        page = self.pages["book"]
        self.reading_title.setText(page["caption"].text() + " · " + page["chapters"].currentText())
        self.reading_full_layout.addWidget(page["reader"], 1, Qt.AlignHCenter)
        self.update_reading_options(dict(self.reader_options))
        self.reading_window.showFullScreen()
        page["reader"].show()
        self.reading_window.raise_()
        self.reading_window.activateWindow()

    def exit_reading_fullscreen(self):
        if not self.reading_window or not self.reading_window.isVisible():
            return
        page = self.pages["book"]
        page["reading_layout"].addWidget(page["reader"], 1)
        page["reading_layout"].setAlignment(page["reader"], Qt.AlignHCenter)
        page["reader"].show()
        self.reading_window.hide()
        self.raise_()
        self.activateWindow()

    def build_sources_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        row = QHBoxLayout()
        self.source_filter = QLineEdit()
        self.source_filter.addAction(icon('search'), QLineEdit.LeadingPosition)
        self.source_filter.setPlaceholderText("筛选名称、类别、状态、接口")
        self.source_filter.textChanged.connect(self.filter_sources)
        row.addWidget(self.source_filter, 1)
        row.addWidget(button("导入文件", self.import_files, True))
        row.addWidget(button("导入网址", self.import_url))
        row.addWidget(button("粘贴配置", self.paste_config))
        subscriptions = QPushButton("网址订阅")
        subscriptions.setIcon(action_icon('网址订阅'))
        subscriptions.setIconSize(QSize(18, 18))
        menu = QMenu(subscriptions)
        menu.addAction("刷新全部订阅", self.refresh_subscriptions)
        menu.addAction("管理／移除订阅", self.manage_subscriptions)
        subscriptions.setMenu(menu)
        row.addWidget(subscriptions)
        row.addWidget(button("恢复备份", self.restore_backup))
        layout.addLayout(row)
        self.source_summary = QLabel()
        layout.addWidget(self.source_summary)
        self.source_table = table(["编号／后台名称", "类别", "启用", "状态", "兼容性／维护说明"])
        self.source_table.setColumnWidth(0, 200)
        self.source_table.setColumnWidth(1, 55)
        self.source_table.setColumnWidth(2, 55)
        self.source_table.setColumnWidth(3, 90)
        self.source_table.itemDoubleClicked.connect(lambda *_: self.edit_source())
        layout.addWidget(self.source_table, 1)
        actions = QHBoxLayout()
        for name, action in [("检测选中", self.check_selected), ("启用／恢复", lambda: self.change_selected(True)),
                             ("停用", lambda: self.change_selected(False)), ("清理失效", self.archive_failed),
                             ("编辑", self.edit_source), ("导出备份", self.export_sources),
                             ("导出原始", self.export_original), ("存储目录", self.open_storage)]:
            actions.addWidget(button(name, action))
        layout.addLayout(actions)
        note = QLabel("连续失败 3 次自动停用；没有搜到结果不算失效。清理会归档，可选中后恢复。导入前自动备份，保留最近 10 份。")
        note.setWordWrap(True)
        note.setStyleSheet("color:#78869c;font-size:12px;")
        layout.addWidget(note)
        return page

    def start_job(self, function, completed, failed=None):
        job = Job(function, self)
        self.jobs.append(job)
        job.progress.connect(lambda event: self.on_progress(event) if not job.cancel.is_set() else None)
        job.completed.connect(lambda result: completed(result) if not job.cancel.is_set() else None)
        job.failed.connect(lambda message: (failed or self.on_error)(message) if not job.cancel.is_set() else None)
        job.finished.connect(lambda: self.finish_job(job))
        job.thread.start()
        return job

    def finish_job(self, job):
        if job in self.jobs:
            self.jobs.remove(job)
        if self.download_job is job:
            self.download_job = None
        job.deleteLater()

    def on_error(self, message):
        self.status.setText(message.splitlines()[0])
        self.logs.append(message)
        self.logs = self.logs[-60:]
        self.reload_sources()

    def on_progress(self, event):
        kind = event.get("type")
        if kind in ("status", "download"):
            self.status.setText(event["text"])
        elif kind == "sources":
            self.reload_sources()
        elif kind == "results":
            for row in event["rows"]:
                self.add_result(row)

    def add_result(self, row):
        alternatives = row.get("alternatives", [])
        subtitle = row["subtitle"] or self.source_label(row["source_id"])
        if row["kind"] == "video" and len(alternatives) > 1:
            subtitle += f" · {len(alternatives)} 个来源"
        columns = [row["title"], subtitle]
        if row["kind"] == "music":
            platforms = "/".join(dict.fromkeys(PLATFORMS.get(r.get("platform"), "直链") for r in alternatives or [row]))
            columns.append(row.get("music_info", {}).get("albumName", "") + " · " + platforms)
        node = QTreeWidgetItem(columns)
        node.setIcon(0, icon(row['kind']))
        for index, text in enumerate(columns):
            node.setToolTip(index, text)
        node.setData(0, Qt.UserRole, row)
        self.pages[row["kind"]]["results"].addTopLevelItem(node)

    def reload_sources(self):
        rows = self.catalog.rows()
        self.source_names = self.catalog.source_labels()
        selected = {s["id"] for s in self.selected_sources()}
        self.source_table.clear()
        state_names = {"unknown": "未检测", "ok": "请求正常", "empty": "无匹配结果", "error": "失败", "init": "初始化通过"}
        for row in rows:
            enabled = "归档" if row["archived"] else "是" if row["enabled"] else "否"
            state = state_names.get(row["health"], row["health"])
            if row["failures"]:
                state += f" ({row['failures']})"
            node = QTreeWidgetItem([self.source_label(row["id"]) + " · " + row["name"], KINDS[row["kind"]], enabled, state, row["note"]])
            node.setIcon(0, icon(row['kind']))
            node.setData(0, Qt.UserRole, row)
            node.setToolTip(4, row["error"] or row["note"])
            self.source_table.addTopLevelItem(node)
            node.setSelected(row["id"] in selected)
        active = sum(bool(s["enabled"] and not s["archived"] and s["adapter"] in ADAPTERS) for s in rows)
        self.source_summary.setText(f"共 {len(rows)} 个源 · {active} 个已启用兼容源 · {len(self.catalog.subscriptions())} 个网址订阅")
        for kind, page in self.pages.items():
            chosen = page["source"].currentData()
            combo = page["source"]
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("自动选源（优先正常，最多 8 个）" if kind != "music" else "自动音源（失败换源）", None)
            for row in rows:
                if row["kind"] == kind and row["adapter"] in ADAPTERS and row["enabled"] and not row["archived"]:
                    combo.addItem(row["name"], row["id"])
            index = combo.findData(chosen)
            combo.setCurrentIndex(max(0, index))
            combo.blockSignals(False)
        self.filter_sources()

    def filter_sources(self):
        query = self.source_filter.text().strip().lower()
        for index in range(self.source_table.topLevelItemCount()):
            node = self.source_table.topLevelItem(index)
            row = node.data(0, Qt.UserRole)
            text = " ".join(node.text(i) for i in range(5)) + " " + row["endpoint"]
            node.setHidden(query not in text.lower())

    def selected_sources(self):
        if not hasattr(self, "source_table"):
            return []
        return [node.data(0, Qt.UserRole) for node in self.source_table.selectedItems()]

    def search(self, kind, next_page=False):
        page = self.pages[kind]
        keyword = page["entry"].text().strip()
        if not keyword:
            page["entry"].setFocus()
            return
        old = self.search_jobs.get(kind)
        if old:
            old.cancel.set()
        page["page"] = page["page"] + 1 if next_page and keyword == page["keyword"] else 1
        page["keyword"] = keyword
        page["results"].clear()
        source_id, platform, number = page["source"].currentData(), page["platform"].currentData(), page["page"]
        if kind == "music":
            self.catalog.save_setting("music_platform_v2", platform)
        self.status.setText(f"搜索 {keyword} · 第 {number} 页")
        self.search_jobs[kind] = self.start_job(
            lambda cancel, notify: self.services.search(kind, keyword, source_id, platform, number, cancel, notify),
            self.search_done)

    def search_done(self, result):
        page = self.pages[result["kind"]]
        selected = page["results"].currentItem()
        title = selected.text(0) if selected else ""
        page["results"].clear()
        for row in result["rows"]:
            self.add_result(row)
            if title == row["title"]:
                page["results"].setCurrentItem(page["results"].topLevelItem(page["results"].topLevelItemCount() - 1))
        opened = page["result"]
        if opened:
            same = next((r for r in result["rows"] if any(
                alternative.get("source_id") == opened.get("source_id") and alternative.get("url") == opened.get("url")
                for alternative in r.get("alternatives", [r]))), None)
            if same:
                page["alternatives"] = same.get("alternatives", [same])
                opened["alternatives"] = page["alternatives"]
                self.populate_work_sources(result["kind"])
        self.status.setText(f"找到 {result['count']} 条 · 检索 {result['searched']} 个源 · {len(result['errors'])} 个失败，详情可查看")
        self.logs.extend(result["errors"])
        self.reload_sources()

    def source_by_id(self, key):
        return next((s for s in self.catalog.rows() if s["id"] == key), None)

    def open_selected(self, kind):
        node = self.pages[kind]["results"].currentItem()
        if node:
            self.open_result(node.data(0, Qt.UserRole))

    def open_result(self, result):
        source = self.source_by_id(result["source_id"])
        if result["kind"] == "music" and result.get("music_info"):
            chosen = self.pages["music"]["source"].currentData()
            available = [s for s in self.catalog.rows("music", active=True) if s["adapter"] == "lx"]
            available.sort(key=lambda s: s["priority"])
            if not chosen and result.get("platform") == "mg":
                preferred = self.catalog.setting("music_migu_preferred", MIGU_PREFERRED)
                available.sort(key=lambda s: preferred.index(s["name"]) if s["name"] in preferred else len(preferred))
            source = next((s for s in available if s["id"] == chosen), available[0] if available else None)
        if not source:
            self.on_error("对应的源已移除，请重新导入")
            return
        if self.open_job:
            self.open_job.cancel.set()
        self.switching = False
        kind, page = result["kind"], self.pages[result["kind"]]
        if not page["result"] or page["result"]["title"] != result["title"]:
            page["cycle_index"] = -1
        if kind != "video":
            self.exit_fullscreen()
        if kind != "book":
            self.exit_reading_fullscreen()
        self.tabs.setCurrentIndex(list(KINDS).index(kind))
        self.current_result, self.current_source = result, source
        page["result"] = result
        page["alternatives"] = result.get("alternatives") or [dict(result)]
        self.populate_work_sources(kind)
        page["caption"].setText(result["title"] + " · " + self.source_label(source["id"]))
        self.media = None
        self.video_attempts = []
        self.music_attempts = []
        self.resume_position = result.get("position", 0)
        self.stop_play()
        if kind == "music":
            page["caption"].setText(result["title"] + " · " + result.get("subtitle", ""))
            page["reader"].setPlainText(result["title"] + "\n\n" + result.get("subtitle", "") + "\n" +
                                       result.get("music_info", {}).get("albumName", "") + "\n\n正在准备播放…")
            quality = page["quality"].currentText()
            self.open_job = self.start_job(
                lambda cancel, notify: self.services.resolve_music(source, result, quality, cancel, notify),
                lambda media: self.play_resolved(media, result))
        else:
            self.status.setText("正在读取章节／线路")
            self.open_job = self.start_job(lambda *_: adapters.chapters(source, result),
                                            lambda episodes: self.show_episodes(kind, result, episodes),
                                            lambda error: self.directory_failed(kind, error))

    def populate_work_sources(self, kind):
        page = self.pages[kind]
        combo = page["work_source"]
        combo.blockSignals(True)
        combo.clear()
        for row in page["alternatives"]:
            combo.addItem(self.source_label(row["source_id"]), row)
        result = page["result"]
        index = next((i for i, r in enumerate(page["alternatives"]) if result and r["source_id"] == result["source_id"]), 0)
        combo.setCurrentIndex(index)
        if page.get("cycle_index", -1) < 0:
            page["cycle_index"] = index
        combo.blockSignals(False)

    def switch_work_source(self, kind, index):
        page = self.pages[kind]
        if not page["result"] or index < 0:
            return
        page["cycle_index"] = index
        row = page["work_source"].itemData(index)
        if not row or row["source_id"] == page["result"]["source_id"]:
            return
        wanted = page["chapters"].currentText()
        position = self.player.position() if self.player and kind == "video" else 0
        self.open_result({**row, "alternatives": page["alternatives"], "wanted_episode": wanted, "position": position})

    def directory_failed(self, kind, error):
        page = self.pages[kind]
        self.logs.append(error)
        index = page["work_source"].currentIndex()
        if index + 1 < page["work_source"].count():
            self.status.setText("目录读取失败，自动尝试另一个来源")
            page["work_source"].setCurrentIndex(index + 1)
        else:
            self.on_error(error)

    def show_episodes(self, kind, result, episodes):
        page = self.pages[kind]
        if page["result"] is not result:
            return
        page["all_episodes"] = episodes
        if kind == "video":
            road = page["road"]
            road.blockSignals(True)
            road.clear()
            for name in dict.fromkeys(e.get("road", "直连") for e in episodes):
                road.addItem(f"线路 {road.count()}", name)
            requested = result.get("road", "")
            road.setCurrentIndex(max(0, road.findData(requested)))
            road.blockSignals(False)
            episodes = [e for e in episodes if e.get("road", "直连") == road.currentData()]
        self.fill_episodes(kind, result, episodes)

    def fill_episodes(self, kind, result, episodes):
        page = self.pages[kind]
        page["episodes"] = episodes
        combo = page["chapters"]
        combo.blockSignals(True)
        combo.clear()
        for episode in episodes:
            combo.addItem(episode["title"])
        index = min(max(0, result.get("chapter_index", 0)), len(episodes) - 1)
        matched = episode_match(episodes, {"title": result.get("wanted_episode", "")})
        if matched:
            index = episodes.index(matched)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)
        self.choose_episode(kind, index)

    def switch_road(self):
        page = self.pages["video"]
        if not page["result"]:
            return
        result = page["result"]
        result["wanted_episode"] = page["chapters"].currentText()
        result["road"] = page["road"].currentData()
        self.resume_position = self.player.position() if self.player else 0
        episodes = [e for e in page["all_episodes"] if e.get("road", "直连") == page["road"].currentData()]
        self.fill_episodes("video", result, episodes)

    def step_episode(self, step, kind=None):
        kind = kind or (self.current_result or {}).get("kind")
        if kind not in ("book", "video"):
            return
        combo = self.pages[kind]["chapters"]
        index = combo.currentIndex() + step
        if 0 <= index < combo.count():
            self.resume_position = 0
            combo.setCurrentIndex(index)

    def choose_episode(self, kind, index):
        page = self.pages[kind]
        if not page["result"] or not 0 <= index < len(page["episodes"]):
            return
        if self.open_job:
            self.open_job.cancel.set()
        result = page["result"]
        source = self.source_by_id(result["source_id"])
        episode = page["episodes"][index]
        self.media = None
        result["chapter_index"] = index
        result["wanted_episode"] = episode["title"]
        result["road"] = episode.get("road", "")
        if self.current_episode and episode_match([episode], self.current_episode) is None:
            self.resume_position = 0
            result["position"] = 0
            result["reader_scroll"] = 0
        self.current_episode, self.current_result, self.current_source = episode, result, source
        self.catalog.remember(kind, result["title"], result)
        self.status.setText("正在打开 " + episode["title"])
        self.stop_play()
        if kind == "book":
            page["text"] = ""
            page["reader"].setPlainText("正在读取 " + episode["title"] + "…")
            self.open_job = self.start_job(lambda *_: adapters.chapter_text(source, episode),
                                            lambda content: self.show_chapter(result, content),
                                            lambda error: self.directory_failed(kind, error))
        else:
            self.pages["video"]["resolution"].blockSignals(True)
            self.pages["video"]["resolution"].clear()
            self.pages["video"]["resolution"].addItem("正在读取清晰度…", None)
            self.pages["video"]["resolution"].blockSignals(False)
            self.video_attempts = []
            self.resolve_current_video()

    def resolve_current_video(self):
        page = self.pages["video"]
        result, episode = page["result"], self.current_episode
        excluded = list(self.video_attempts)
        self.switching = True
        def failed(error):
            self.switching = False
            self.on_error(error)
        self.open_job = self.start_job(
            lambda cancel, notify: self.services.resolve_video(result, episode, page["all_episodes"], cancel, notify, excluded),
            self.video_resolved, failed)

    def video_resolved(self, resolved):
        page = self.pages["video"]
        result, episode = resolved["result"], resolved["episode"]
        result["alternatives"] = page["alternatives"]
        page["result"] = result
        if resolved.get("episodes"):
            page["all_episodes"] = resolved["episodes"]
        self.current_result, self.current_episode = result, episode
        self.current_source = self.source_by_id(result["source_id"])
        self.video_attempts = resolved["attempts"]
        result["wanted_episode"], result["road"] = episode["title"], episode.get("road", "")
        self.populate_work_sources("video")
        road = page["road"]
        road.blockSignals(True)
        road.clear()
        for name in dict.fromkeys(e.get("road", "直连") for e in page["all_episodes"]):
            road.addItem(f"线路 {road.count()}", name)
        road.setCurrentIndex(max(0, road.findData(episode.get("road", "直连"))))
        road.blockSignals(False)
        episodes = [e for e in page["all_episodes"] if e.get("road", "直连") == road.currentData()]
        page["episodes"] = episodes
        combo = page["chapters"]
        combo.blockSignals(True)
        combo.clear()
        combo.addItems([e["title"] for e in episodes])
        index = next((i for i, e in enumerate(episodes) if e["url"] == episode["url"]), 0)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)
        result["chapter_index"] = index
        page["caption"].setText(result["title"] + " · " + self.source_label(result["source_id"]))
        self.populate_resolutions(resolved["media"])
        self.play_resolved(resolved["media"], result)
        self.switching = False

    def show_chapter(self, result, content):
        page = self.pages["book"]
        if content["url"]:
            self.play_resolved(dict(url=content["url"], headers={}), result)
            return
        page["text"] = content["text"]
        scroll = result.get("reader_scroll", 0)
        page["reader"].verticalScrollBar().blockSignals(True)
        page["reader"].setPlainText(content["title"] + "\n\n" + content["text"])
        page["reader"].verticalScrollBar().blockSignals(False)
        QTimer.singleShot(0, lambda: page["reader"].verticalScrollBar().setValue(scroll))
        if not page.get("scroll_connected"):
            page["reader"].verticalScrollBar().valueChanged.connect(self.save_reader_position)
            page["scroll_connected"] = True
        self.status.setText(f"{content['title']} · {len(content['text'])} 字")
        if self.reading_window:
            self.reading_title.setText(result["title"] + " · " + content["title"])

    def populate_resolutions(self, media):
        combo = self.pages["video"]["resolution"]
        combo.blockSignals(True)
        combo.clear()
        variants = media.get("variants", [])
        for variant in variants:
            combo.addItem(variant["label"], variant)
        if not variants:
            combo.addItem("源清晰度（单一）", None)
        selected = media.get("selected_variant", media["url"])
        combo.setCurrentIndex(next((i for i, v in enumerate(variants) if v["url"] == selected), 0))
        combo.blockSignals(False)

    def change_resolution(self, index):
        variant = self.pages["video"]["resolution"].itemData(index)
        if not variant or not self.media or not self.current_result or self.current_result["kind"] != "video":
            return
        if variant["url"] == self.media.get("selected_variant", self.media["url"]):
            return
        original, result = dict(self.media), self.current_result
        self.resume_position = self.player.position() if self.player else 0
        if self.open_job:
            self.open_job.cancel.set()
        self.switching = True
        self.stop_play()
        def done(media):
            self.populate_resolutions(media)
            self.play_resolved(media, result)
            self.switching = False
        def failed(error):
            self.populate_resolutions(original)
            self.play_resolved(original, result)
            self.switching = False
            self.on_error(error)
        self.open_job = self.start_job(lambda *_: adapters.validate_video({**original, "url": variant["url"],
                                                                          "selected_variant": variant["url"]}), done, failed)

    def save_reader_position(self, position):
        result = self.pages["book"]["result"]
        if result:
            result["reader_scroll"] = position
            if time.monotonic() - self.last_saved > 2:
                self.catalog.remember("book", result["title"], result)
                self.last_saved = time.monotonic()

    def source_label(self, key):
        return self.source_names.get(key, "自动")

    def next_source(self, kind=None):
        if isinstance(kind, bool):
            kind = None
        kind = kind or (self.current_result or {}).get("kind")
        if kind not in self.pages or not self.pages[kind]["result"]:
            return
        page = self.pages[kind]
        if kind == "music":
            combo = page["source"]
            index = combo.currentIndex() + 1
            combo.setCurrentIndex(index if index < combo.count() else 1 if combo.count() > 1 else 0)
            self.open_result(page["result"])
        elif page["work_source"].count() > 1:
            combo = page["work_source"]
            index = (page.get("cycle_index", combo.currentIndex()) + 1) % combo.count()
            page["cycle_index"] = index
            combo.setCurrentIndex(index)
        elif kind == "video" and self.current_episode:
            self.retry_video("正在尝试其他线路")
        else:
            self.status.setText("本次搜索只有一个匹配来源，请重新搜索以获取其他来源")

    def show_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("听读看 · 设置")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("默认自动选源，失效时自动尝试其他来源。\n源编号固定，更新配置后仍可对应查找。"))
        layout.addWidget(button("高级维护…", lambda: self.show_maintenance(dialog)))
        layout.addWidget(button("关闭", dialog.accept))
        dialog.exec()

    def show_maintenance(self, parent):
        dialog = QDialog(parent)
        dialog.setWindowTitle("高级维护 · 原始源名称、导入与备份")
        dialog.resize(1000, 650)
        dialog.setStyleSheet(STYLE)
        layout = QVBoxLayout(dialog)
        layout.addWidget(self.sources_page)
        self.sources_page.show()
        dialog.exec()
        layout.removeWidget(self.sources_page)
        self.sources_page.setParent(self)
        self.sources_page.hide()

    def ensure_player(self):
        if self.player:
            return
        import PySide6
        qt_folder = str(Path(PySide6.__file__).resolve().parent)
        self._dll_handles = []
        if os.name == "nt":
            # Qt 媒体插件的 FFmpeg 依赖需要可见于 Windows DLL 搜索路径。
            if hasattr(os, "add_dll_directory"):
                self._dll_handles.append(os.add_dll_directory(qt_folder))
            current_path = os.environ.get("PATH", "")
            if qt_folder not in current_path.split(os.pathsep):
                os.environ["PATH"] = qt_folder + os.pathsep + current_path
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget
        from .media_proxy import MediaProxy
        self.player = QMediaPlayer(self)
        if not self.player.isAvailable():
            self.player.deleteLater()
            self.player = None
            raise ValueError("Qt 媒体插件未就绪，请修复 PySide6 的媒体依赖或使用网页播放")
        self.proxy = MediaProxy()
        self.audio = QAudioOutput(self)
        self.audio.setVolume(self.volume.value() / 100)
        self.player.setAudioOutput(self.audio)
        self.video_widget = QVideoWidget(self)
        self.video_widget.installEventFilter(self)
        self.pages["video"]["video_layout"].addWidget(self.video_widget)
        self.player.setVideoOutput(self.video_widget)
        self.video_widget.videoSink().videoSizeChanged.connect(self.video_size_changed)
        self.player.durationChanged.connect(lambda duration: self.seek.setRange(0, duration))
        self.player.durationChanged.connect(self.check_music_duration)
        self.player.positionChanged.connect(self.update_position)
        self.player.playbackStateChanged.connect(self.playback_changed)
        self.player.errorOccurred.connect(self.media_error)
        self.player.mediaStatusChanged.connect(self.media_status_changed)

    def video_size_changed(self):
        if not self.media or not self.current_result or self.current_result["kind"] != "video":
            return
        size = self.video_widget.videoSink().videoSize()
        if size.height() <= 0:
            return
        combo = self.pages["video"]["resolution"]
        index = combo.currentIndex()
        variant = combo.itemData(index)
        if not variant or not variant.get("resolution"):
            combo.setItemText(index, f"{size.height()}p" + ("（单一）" if combo.count() == 1 else " · " + variant["label"]))

    def play_resolved(self, media, result):
        if not media.get("url"):
            self.status.setText("此地址使用网页播放器，正在打开网页")
            self.show_web_player(media.get("page", result["url"]), result)
            return
        self.ensure_player()
        self.player.stop()
        self.media = media
        if result["kind"] == "video":
            self.populate_resolutions(media)
        if result["kind"] == "music":
            self.music_attempts = media.get("attempts", [])
        self.player.setSource(QUrl(self.proxy.start({**media, "headers": {"User-Agent": adapters.UA, **media.get("headers", {})}})))
        self.last_motion = time.monotonic()
        self.watchdog.start()
        self.player.play()
        self.now.setText(result["title"][:18])
        self.now.setToolTip(result["title"])
        self.status.setText("正在加载媒体 · " + self.source_label(media.get("source_id") or result.get("source_id", "")))
        if result["kind"] == "music":
            self.pages["music"]["reader"].setPlainText(result["title"] + "\n\n" + result.get("subtitle", "") + "\n" +
                    result.get("music_info", {}).get("albumName", "") + "\n\n" + self.source_label(media.get("source_id", "")) +
                    " · 获取成功\n下方可暂停、拖动进度或调节音量。")
        if self.fullscreen_window and self.fullscreen_window.isVisible():
            self.fullscreen_title.setText(result["title"] + " · " + (self.current_episode or {}).get("title", ""))
        if result["kind"] == "video":
            self.pages["video"]["reader"].hide()
            self.pages["video"]["reading_container"].hide()
            self.pages["video"]["video"].show()
        self.catalog.remember(result["kind"], result["title"], result)
        self.reload_sources()

    def playback_changed(self, state):
        from PySide6.QtMultimedia import QMediaPlayer
        color = '#edf2fa' if self.fullscreen_window and self.fullscreen_window.isVisible() else '#526581'
        if state == QMediaPlayer.PlayingState:
            self.play_button.setIcon(icon('pause', color))
            self.status.setText("播放中 · " + self.now.text())
        elif state == QMediaPlayer.PausedState:
            self.play_button.setIcon(icon('play', color))
            self.status.setText("已暂停 · " + self.now.text())
        else:
            self.play_button.setIcon(icon('play', color))

    def update_position(self, position):
        if position != getattr(self, "last_position", -1):
            self.last_motion = time.monotonic()
            self.last_position = position
        if not self.seek.isSliderDown():
            self.seek.setValue(position)
        def formatted(ms):
            seconds = max(0, ms // 1000)
            return f"{seconds // 60:02d}:{seconds % 60:02d}"
        self.clock.setText(formatted(position) + " / " + formatted(self.player.duration()))
        if self.current_result and time.monotonic() - self.last_saved > 5 and position > 0:
            self.current_result["position"] = position
            self.catalog.remember(self.current_result["kind"], self.current_result["title"], self.current_result)
            self.last_saved = time.monotonic()

    def toggle_play(self):
        if self.player:
            from PySide6.QtMultimedia import QMediaPlayer
            self.player.pause() if self.player.playbackState() == QMediaPlayer.PlayingState else self.player.play()

    def stop_play(self):
        if hasattr(self, "watchdog"):
            self.watchdog.stop()
        if self.player:
            self.player.stop()

    def media_status_changed(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if status in (QMediaPlayer.LoadedMedia, QMediaPlayer.BufferedMedia) and self.resume_position:
            position, self.resume_position = self.resume_position, 0
            self.player.setPosition(position)
        elif status == QMediaPlayer.EndOfMedia:
            self.watchdog.stop()
            if self.current_result and self.current_result["kind"] == "video":
                QTimer.singleShot(0, lambda: self.step_episode(1, "video"))
        elif status == QMediaPlayer.StalledMedia:
            self.status.setText("正在缓冲，持续异常时自动换源")

    def media_error(self, _, reason):
        if not self.media:
            return
        self.logs.append("播放失败：" + reason)
        if self.current_result and self.current_result["kind"] == "video" and self.current_episode:
            QTimer.singleShot(0, lambda: self.retry_video("播放异常，自动换源"))
        elif self.current_result and self.current_result["kind"] == "music":
            QTimer.singleShot(0, self.retry_music)
        else:
            self.on_error("播放失败，可点击换源重试")

    def check_music_duration(self, duration):
        if not self.media or not self.current_result or self.current_result["kind"] != "music":
            return
        expected = self.media.get("expected_duration", 0) * 1000
        if duration > 1000 and expected and abs(expected - duration) > max(20000, expected * .08):
            self.logs.append("返回音频时长与搜索信息不符，自动尝试其他地址")
            QTimer.singleShot(0, self.retry_music)

    def retry_music(self):
        if self.switching or not self.current_result or self.current_result["kind"] != "music":
            return
        if not self.current_source:
            self.on_error("当前音频链接不可用，请重新打开链接")
            return
        self.switching = True
        result, source = self.current_result, self.current_source
        if self.open_job:
            self.open_job.cancel.set()
        self.stop_play()
        self.status.setText("音频异常，正在自动换源")
        attempts = list(self.music_attempts)
        def done(media):
            self.play_resolved(media, result)
            self.switching = False
        def failed(error):
            self.switching = False
            self.on_error(error)
        self.open_job = self.start_job(lambda cancel, notify: self.services.resolve_music(
            source, result, self.pages['music']['quality'].currentText(), cancel, notify, attempts), done, failed)

    def check_playback(self):
        from PySide6.QtMultimedia import QMediaPlayer
        if not self.player or self.player.playbackState() == QMediaPlayer.PausedState:
            self.last_motion = time.monotonic()
            return
        if self.current_result and self.current_result["kind"] == "video" and time.monotonic() - self.last_motion > 22:
            self.retry_video("缓冲超时，自动换源")
        elif self.current_result and self.current_result["kind"] == "music" and time.monotonic() - self.last_motion > 22:
            self.retry_music()

    def retry_video(self, message):
        if self.switching or not self.current_episode or not self.pages["video"]["result"]:
            return
        self.resume_position = self.player.position() if self.player else 0
        self.stop_play()
        self.status.setText(message)
        self.resolve_current_video()

    def eventFilter(self, watched, event):
        if watched is self.reading_window and event.type() == QEvent.Close:
            self.exit_reading_fullscreen()
            event.ignore()
            return True
        if watched is getattr(self, "video_widget", None) and event.type() == QEvent.MouseButtonDblClick:
            self.toggle_fullscreen()
            return True
        if watched is self.fullscreen_window and event.type() == QEvent.Close:
            self.exit_fullscreen()
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    def toggle_fullscreen(self):
        if self.tabs.currentIndex() == list(KINDS).index("book"):
            self.toggle_reading_fullscreen()
            return
        if self.fullscreen_window and self.fullscreen_window.isVisible():
            self.exit_fullscreen()
            return
        if not self.player or not self.current_result or self.current_result["kind"] != "video":
            return
        if self.fullscreen_window is None:
            self.fullscreen_window = QWidget(None, Qt.Window)
            self.fullscreen_window.setWindowTitle("听读看 · 全屏")
            self.fullscreen_window.setStyleSheet("QWidget {background:#111827;color:#edf2fa;} QPushButton {padding:7px;} ")
            self.fullscreen_window.installEventFilter(self)
            self.fullscreen_layout = QVBoxLayout(self.fullscreen_window)
            self.fullscreen_layout.setContentsMargins(0, 0, 0, 0)
            self.fullscreen_top = QHBoxLayout()
            self.fullscreen_title = QLabel()
            self.fullscreen_top.addWidget(self.fullscreen_title, 1)
            for name, callback in [("上一集", lambda: self.step_episode(-1, "video")),
                                   ("下一集", lambda: self.step_episode(1, "video")),
                                   ("换源", lambda: self.next_source("video")), ("退出全屏", self.exit_fullscreen)]:
                control = button(name, callback)
                control.setIcon(action_icon(name, '#edf2fa'))
                self.fullscreen_top.addWidget(control)
            self.fullscreen_layout.addLayout(self.fullscreen_top)
            for key, callback in [("Escape", self.exit_fullscreen), ("F11", self.exit_fullscreen),
                                   ("Space", self.toggle_play), ("Right", lambda: self.player.setPosition(self.player.position() + 10000)),
                                   ("Left", lambda: self.player.setPosition(max(0, self.player.position() - 10000)))]:
                shortcut = QShortcut(QKeySequence(key), self.fullscreen_window)
                shortcut.activated.connect(callback)
        self.fullscreen_title.setText(self.current_result["title"] + " · " + (self.current_episode or {}).get("title", ""))
        self.fullscreen_layout.addWidget(self.video_widget, 1)
        self.fullscreen_layout.addWidget(self.controls_widget)
        self.fullscreen_window.showFullScreen()
        self.color_player_icons('#edf2fa')
        self.video_widget.show()
        self.controls_widget.show()
        self.fullscreen_window.raise_()
        self.fullscreen_window.activateWindow()

    def exit_fullscreen(self):
        if not self.fullscreen_window:
            return
        self.pages["video"]["video_layout"].addWidget(self.video_widget)
        self.main_layout.insertWidget(self.main_layout.count() - 1, self.controls_widget)
        self.fullscreen_window.hide()
        self.color_player_icons('#526581')
        self.video_widget.show()
        self.controls_widget.show()
        self.raise_()
        self.activateWindow()

    def color_player_icons(self, color):
        for control in self.controls_widget.findChildren(QPushButton):
            control.setIcon(action_icon(control.text(), color))
        if self.player:
            from PySide6.QtMultimedia import QMediaPlayer
            name = 'pause' if self.player.playbackState() == QMediaPlayer.PlayingState else 'play'
            self.play_button.setIcon(icon(name, color))

    def seek_to(self):
        if self.player:
            self.player.setPosition(self.seek.value())

    def set_volume(self, number):
        if self.player:
            self.audio.setVolume(number / 100)

    def open_original(self, kind):
        page = self.pages[kind]
        result = page["result"]
        if not result:
            return
        source = self.source_by_id(result["source_id"])
        url = result["url"]
        if not url.startswith("http"):
            url = source["raw"].get("baseURL") or source["raw"].get("api") or source["endpoint"].split("|")[0]
        if url.startswith("http"):
            QDesktopServices.openUrl(QUrl(url))

    def save_content(self, kind):
        page = self.pages[kind]
        if kind == "book":
            if not page["text"]:
                self.on_error("先打开一章正文")
                return
            title = self.safe_name((page["result"] or {}).get("title", "小说") + " " + page["chapters"].currentText())
            folder = self.catalog.setting("download_folder", str(self.catalog.folder / "downloads"))
            path, _ = QFileDialog.getSaveFileName(self, "下载当前章节", str(Path(folder) / (title + ".txt")), "正文 (*.txt)")
            if path:
                Path(path).write_text(page["reader"].toPlainText(), encoding="utf-8")
                self.catalog.save_setting("download_folder", str(Path(path).parent))
                self.catalog.remember("download", title, dict(path=path, state="完成"))
                self.status.setText("单章已下载：" + path)
            return
        if self.download_job:
            self.on_error("已有一个下载任务，请等待完成或取消后重试")
            return
        if kind == "video" and self.switching:
            self.on_error("正在切换清晰度／线路，播放就绪后再下载")
            return
        if not self.media or not self.current_result or self.current_result["kind"] != kind:
            self.on_error("先打开目标音频／视频，取得播放链接后再下载")
            return
        title = self.safe_name(self.current_result["title"] + (" " + self.current_episode["title"] if kind == "video" and self.current_episode else ""))
        extension = Path(adapters.urlsplit(self.media["url"]).path).suffix.lower()
        if extension not in (".mp3", ".m4a", ".flac", ".wav", ".ogg", ".aac", ".mp4", ".webm", ".mkv"):
            extension = ".mp4" if kind == "video" else ".mp3"
        folder = self.catalog.setting("download_folder", str(self.catalog.folder / "downloads"))
        path, _ = QFileDialog.getSaveFileName(self, "下载当前媒体", str(Path(folder) / (title + extension)), "媒体文件 (*.*)")
        if not path:
            return
        self.catalog.save_setting("download_folder", str(Path(path).parent))
        media = dict(self.media)
        self.catalog.remember("download", title, dict(path=path, media=media, state="开始"))
        def done(saved):
            self.status.setText("下载完成：" + saved)
            self.catalog.remember("download", title, dict(path=saved, state="完成"))
        def failed(error):
            self.on_error(error)
            self.catalog.remember("download", title, dict(path=path, media=media, state="失败／可重试"))
        self.download_job = self.start_job(lambda cancel, notify: download(media, path, cancel, notify), done, failed)

    def download_book_range(self):
        page = self.pages["book"]
        episodes = list(page["all_episodes"])
        if not page["result"] or not episodes:
            self.on_error("先打开小说并读取目录")
            return
        if self.download_job:
            self.on_error("已有一个下载任务，请等待完成或取消后重试")
            return
        dialog, start, end = self.book_range_dialog(episodes)
        if dialog.exec() != QDialog.Accepted:
            return
        result = dict(page["result"])
        source = self.source_by_id(result["source_id"])
        if not source:
            self.on_error("对应的书源已移除，请重新打开小说")
            return
        first, last = start.value(), end.value()
        title = self.safe_name(result["title"])
        suffix = "全本" if first == 1 and last == len(episodes) else f"{first}-{last}章"
        folder = self.catalog.setting("download_folder", str(self.catalog.folder / "downloads"))
        path, _ = QFileDialog.getSaveFileName(self, "下载小说正文", str(Path(folder) / f"{title} {suffix}.txt"), "正文 (*.txt)")
        if not path:
            return
        self.catalog.save_setting("download_folder", str(Path(path).parent))
        selected = episodes[first - 1:last]
        record = dict(path=path, book=result, first=first, last=last, first_title=selected[0]["title"],
                      last_title=selected[-1]["title"], state="开始")
        self.start_book_download(source, result, selected, record, title + " " + suffix)

    def start_book_download(self, source, result, selected, record, title):
        self.catalog.remember("download", title, dict(record, state="开始"))
        def done(saved):
            self.status.setText(f"小说下载完成 · {len(selected)} 章：{saved}")
            self.catalog.remember("download", title, dict(path=saved, state="完成"))
        def failed(error):
            self.on_error(error)
            self.catalog.remember("download", title, dict(record, state="失败／可重试"))
        self.download_job = self.start_job(lambda cancel, notify: download_book(
            source, result["title"], selected, record["path"], cancel, notify), done, failed)
        job = self.download_job
        job.finished.connect(lambda: self.catalog.remember("download", title, dict(record, state="已取消／可继续"))
                             if job.cancel.is_set() else None)

    def retry_book_download(self, payload, title):
        if self.download_job:
            self.on_error("已有一个下载任务，请等待完成或取消后重试")
            return
        result = payload["book"]
        source = self.source_by_id(result["source_id"])
        if not source:
            self.on_error("对应的书源已移除，请重新打开小说")
            return
        def directory_done(episodes):
            selected = episodes[payload["first"] - 1:payload["last"]]
            if not selected or selected[0]["title"] != payload["first_title"] or selected[-1]["title"] != payload["last_title"]:
                self.on_error("目录已经变化，请重新选择下载范围")
                return
            self.start_book_download(source, result, selected, payload, title)
        # 目录获取也占用下载任务，避免连续双击启动多个任务。
        self.download_job = self.start_job(lambda *_: adapters.chapters(source, result), directory_done)

    def book_range_dialog(self, episodes):
        dialog = QDialog(self)
        dialog.setWindowTitle("下载全本／区间")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"共 {len(episodes)} 章，默认下载全本。按当前目录顺序保存为 UTF-8 文本。"))
        form = QFormLayout()
        start, end = QSpinBox(), QSpinBox()
        for spin in (start, end):
            style_widget(spin)
            spin.setRange(1, len(episodes))
        start.setValue(1)
        end.setValue(len(episodes))
        form.addRow("起始章", start)
        form.addRow("结束章", end)
        layout.addLayout(form)
        preview = QLabel()
        preview.setWordWrap(True)
        layout.addWidget(preview)
        def update():
            end.setMinimum(start.value())
            preview.setText(episodes[start.value() - 1]["title"] + "\n至 " + episodes[end.value() - 1]["title"] +
                            f"\n选中 {end.value() - start.value() + 1} 章")
        start.valueChanged.connect(update)
        end.valueChanged.connect(update)
        update()
        row = QHBoxLayout()
        row.addWidget(button("取消", dialog.reject))
        row.addWidget(button("开始下载", dialog.accept, True))
        layout.addLayout(row)
        return dialog, start, end

    @staticmethod
    def safe_name(text):
        return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip(" .")[:140] or "媒体"

    def open_link(self):
        url, accepted = QInputDialog.getText(self, "打开媒体链接", "音频、视频直链或播放网页地址：")
        if not accepted or not url.strip():
            return
        try:
            if self.open_job:
                self.open_job.cancel.set()
            self.media = None
            url = adapters.http_url(url.strip())
            kind = "music" if re.search(r"\.(mp3|m4a|flac|wav|aac|ogg)(?:[?#]|$)", url, re.I) else "video"
            result = dict(kind=kind, title="链接播放", url=url, source_name="直链", source_id="")
            self.current_result = result
            self.current_source = None
            self.current_episode = None
            self.tabs.setCurrentIndex(list(KINDS).index(kind))
            resolve = adapters.resolve_video_link if kind == "video" else adapters.resolve_media
            self.open_job = self.start_job(lambda *_: resolve(url), lambda media: self.play_resolved(media, result))
        except Exception as exc:
            self.on_error(friendly_error(exc))

    def web_play_current(self):
        if self.current_episode:
            self.show_web_player(self.current_episode["url"], self.current_result)

    def show_web_player(self, url, result):
        try:
            from .web_player import WebPlayer
            if self.web_dialog:
                self.web_dialog.close()
            self.web_dialog = WebPlayer(url, self)
            instance = self.web_dialog
            instance.destroyed.connect(lambda *_: self.web_closed(instance))
            self.web_dialog.media.connect(lambda media: self.detected_web_media(media, result))
            self.web_dialog.show()
        except ImportError:
            self.on_error("当前 Python 没有 QtWebEngine，已交给默认浏览器播放")
            QDesktopServices.openUrl(QUrl(url))

    def web_closed(self, instance):
        if self.web_dialog is instance:
            self.web_dialog = None

    def detected_web_media(self, media, result):
        if self.open_job:
            self.open_job.cancel.set()
        self.open_job = self.start_job(lambda *_: adapters.validate_video(media),
                                      lambda ready: self.play_resolved(ready, result))

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "导入书源／音源／视频源", "", "源文件 (*.json *.js *.txt);;所有文件 (*)")
        if not paths:
            return
        def work(cancel, notify):
            total = dict(added=0, updated=0, unchanged=0, errors=[])
            for name in paths:
                if cancel.is_set():
                    break
                try:
                    path = Path(name)
                    if path.stat().st_size > 16_000_000:
                        raise ValueError("源文件超过 16 MB")
                    result = self.catalog.import_text(path.read_text(encoding="utf-8-sig"), name)
                    for key in ("added", "updated", "unchanged"):
                        total[key] += result[key]
                except Exception as exc:
                    total["errors"].append(Path(name).name + "：" + friendly_error(exc))
            return total
        self.start_job(work, self.import_done)

    def import_url(self):
        url, accepted = QInputDialog.getText(self, "导入网址订阅", "JSON／JS 原始文件网址；可自动识别 GitHub blob 地址：")
        if accepted and url.strip():
            self.status.setText("正在读取网址配置")
            self.start_job(lambda *_: self.services.import_url(url), self.import_done)

    def paste_config(self):
        text, accepted = QInputDialog.getMultiLineText(self, "粘贴源配置", "阅读 JSON、LX 脚本、视频配置或媒体直链：")
        if accepted and text.strip():
            self.start_job(lambda *_: self.catalog.import_text(text, "粘贴配置.js" if "@name" in text and "script" not in text else "粘贴配置"), self.import_done)

    def import_done(self, result):
        self.reload_sources()
        self.status.setText(f"新增 {result['added']} · 更新 {result['updated']} · 相同 {result['unchanged']}")
        if result.get("errors"):
            self.logs.extend(result["errors"])
            self.status.setText(self.status.text() + f" · {len(result['errors'])} 项失败，详情可查看")

    def refresh_subscriptions(self):
        if not self.catalog.subscriptions():
            self.on_error("先通过“导入网址”添加订阅")
            return
        self.start_job(self.services.refresh_subscriptions, self.import_done)

    def manage_subscriptions(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("网址订阅 · 听读看")
        dialog.resize(800, 380)
        layout = QVBoxLayout(dialog)
        rows = table(["配置网址", "最近刷新", "结果"])
        rows.setColumnWidth(0, 400)
        layout.addWidget(rows)
        def reload():
            rows.clear()
            for subscription in self.catalog.subscriptions():
                node = QTreeWidgetItem([subscription["url"], subscription["checked"], subscription["error"] or "成功"])
                node.setData(0, Qt.UserRole, subscription["url"])
                rows.addTopLevelItem(node)
        def remove():
            if self.jobs:
                self.on_error("先等待后台任务结束，再移除订阅")
                return
            self.catalog.remove_subscriptions([n.data(0, Qt.UserRole) for n in rows.selectedItems()])
            reload()
            self.reload_sources()
        layout.addWidget(QLabel("移除订阅后不再刷新该网址，已经导入的源仍保留。变更网址可重新导入，再移除旧订阅。"))
        layout.addWidget(button("移除选中的订阅", remove))
        reload()
        dialog.exec()

    def change_selected(self, enabled):
        rows = self.selected_sources()
        if rows:
            self.catalog.backup()
            for row in rows:
                flags = dict(enabled=int(enabled and row["adapter"] in ADAPTERS))
                if enabled:
                    flags.update(archived=0, failures=0, health="unknown", error="")
                self.catalog.set_flags([row["id"]], **flags)
            self.reload_sources()
            unsupported = sum(row["adapter"] not in ADAPTERS for row in rows)
            if enabled and unsupported:
                self.status.setText(f"已恢复配置；其中 {unsupported} 项需对应引擎，不参与当前搜索")

    def archive_failed(self):
        rows = [s for s in self.catalog.rows() if s["failures"] >= 3 and not s["archived"]]
        if rows:
            self.catalog.backup()
            self.catalog.set_flags([s["id"] for s in rows], archived=1, enabled=0)
        self.status.setText(f"归档 {len(rows)} 个连续失败源；仍保留配置，可选中后恢复")
        self.reload_sources()

    def check_selected(self):
        rows = self.selected_sources()
        if not rows:
            self.on_error("先在列表中选择需要检测的源，可按 Ctrl 多选")
            return
        self.start_job(lambda cancel, notify: self.services.check_sources(rows, cancel, notify), self.check_done)

    def check_done(self, result):
        self.reload_sources()
        self.status.setText(f"检测 {result['checked']} · 失败 {result['failed']} · 跳过需其他引擎 {result['skipped']}；音源初始化通过后仍需实际播放验证")

    def edit_source(self):
        rows = self.selected_sources()
        if len(rows) != 1:
            self.on_error("选择一个源编辑")
            return
        row = rows[0]
        dialog = QDialog(self)
        dialog.setWindowTitle("源详情 · " + row["name"])
        dialog.resize(780, 570)
        layout = QVBoxLayout(dialog)
        info = QLabel(row["note"] + "\n最近错误：" + (row["error"] or "无") + "\n来源：" + row["origin"])
        info.setWordWrap(True)
        layout.addWidget(info)
        updates = self.catalog.setting("updates:" + row["id"], [])
        if updates:
            label = QLabel("音源更新提示：" + str(updates[0].get("log", ""))[:300])
            label.setWordWrap(True)
            layout.addWidget(label)
        editor = QPlainTextEdit()
        script = row["adapter"] == "lx"
        editor.setPlainText(row["raw"]["script"] if script else json.dumps(row["raw"], ensure_ascii=False, indent=2))
        layout.addWidget(editor, 1)
        def save():
            try:
                if row["adapter"] == "tvbox_config":
                    self.catalog.import_text(editor.toPlainText(), row["origin"])
                    self.reload_sources()
                    dialog.accept()
                    return
                changed = dict(row)
                changed["raw"] = {"script": editor.toPlainText()} if script else json.loads(editor.toPlainText())
                if script or row["adapter"].startswith("legado") or row["adapter"] == "kazumi":
                    parsed = parse_sources(editor.toPlainText(), row["origin"] or ("音源.js" if script else ""))[0]
                    for key in ("adapter", "name", "note", "endpoint"):
                        changed[key] = parsed[key]
                elif row["adapter"] in ("tvbox", "maccms"):
                    entry = dict(changed["raw"])
                    entry.setdefault("name", row["name"])
                    if row["adapter"] == "maccms":
                        entry.setdefault("type", 1)
                    parsed = parse_sources(json.dumps({"sites": [entry]}))[0]
                    for key in ("adapter", "name", "note", "endpoint"):
                        changed[key] = parsed[key]
                changed.update(health="unknown", failures=0)
                if changed["adapter"] not in ADAPTERS:
                    changed["enabled"] = 0
                self.catalog.import_text(json.dumps({"format": "media-hub-v1", "sources": [changed]}))
                self.reload_sources()
                dialog.accept()
            except Exception as exc:
                QMessageBox.warning(dialog, "保存失败", friendly_error(exc))
        layout.addWidget(button("保存", save, True))
        dialog.exec()

    def export_sources(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出全部源（含原配置与状态）", "听读看源备份.json", "配置 (*.json)")
        if path:
            Path(path).write_text(self.catalog.export(), encoding="utf-8")
            self.status.setText("已导出：" + path)

    def export_original(self):
        rows = self.selected_sources()
        if len(rows) != 1:
            self.on_error("选择一个源导出其原始格式")
            return
        row = rows[0]
        script = row["adapter"] == "lx"
        raw = row["raw"]
        if row["adapter"].startswith("legado"):
            raw = [raw]
        elif row["adapter"] == "tvbox":
            raw = dict(spider=raw.get("_spider", ""), sites=[{k: v for k, v in raw.items() if k != "_spider"}])
        path, _ = QFileDialog.getSaveFileName(self, "导出原始源", self.safe_name(row["name"]) + (".js" if script else ".json"), "所有文件 (*)")
        if path:
            Path(path).write_text(row["raw"]["script"] if script else json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")

    def open_storage(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.catalog.folder)))

    def restore_backup(self):
        if self.jobs:
            self.on_error("先等待任务完成或取消，任务结束后可恢复数据库备份")
            return
        path, _ = QFileDialog.getOpenFileName(self, "恢复听读看备份（会先备份当前状态）",
                                              str(self.catalog.folder / "backups"), "数据库备份 (*.sqlite3)")
        if path:
            try:
                self.catalog.restore(path)
                self.reload_sources()
                self.status.setText("已恢复备份；恢复前的状态也保留在备份目录")
            except Exception as exc:
                self.on_error(friendly_error(exc))

    def show_history(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("最近使用 · 听读看")
        dialog.resize(580, 400)
        layout = QVBoxLayout(dialog)
        items = QListWidget()
        for record in self.catalog.recent():
            payload = json.loads(record["payload"])
            state = payload.get("state", "")
            node = QListWidgetItem(f"{KINDS.get(record['kind'], '下载')} · {record['title']} {state}")
            node.setIcon(icon(record['kind'] if record['kind'] in KINDS else 'download'))
            node.setData(Qt.UserRole, (record["kind"], payload, record["title"]))
            items.addItem(node)
        layout.addWidget(items)
        def open_record(node):
            kind, payload, title = node.data(Qt.UserRole)
            if kind == "download":
                path = payload.get("path", "")
                if path and Path(path).exists() and payload.get("state") == "完成":
                    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                elif payload.get("media") and not self.download_job:
                    self.download_job = self.start_job(lambda cancel, notify: download(payload["media"], path, cancel, notify),
                                                       lambda saved: self.status.setText("重试完成：" + saved))
                elif payload.get("book"):
                    self.retry_book_download(payload, title)
            elif payload.get("source_id"):
                self.open_result(payload)
            else:
                self.current_result = payload
                resolve = adapters.resolve_video_link if kind == "video" else adapters.resolve_media
                self.open_job = self.start_job(lambda *_: resolve(payload["url"]),
                                                lambda media: self.play_resolved(media, payload))
            dialog.accept()
        items.itemDoubleClicked.connect(open_record)
        dialog.exec()

    def show_logs(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("任务详情")
        dialog.resize(740, 400)
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText("\n\n".join(self.logs[-60:]) or "当前没有错误记录。")
        layout.addWidget(editor)
        dialog.exec()

    def cancel_jobs(self):
        self.switching = False
        for job in list(self.jobs):
            job.cancel.set()
        self.status.setText("已取消任务；正在进行的网络请求会在超时后结束")

    def shutdown(self):
        self.exit_reading_fullscreen()
        self.exit_fullscreen()
        self.cancel_jobs()
        self.stop_play()
        if self.web_dialog:
            self.web_dialog.close()
        if self.proxy:
            self.proxy.close()
            self.proxy = None

    def closeEvent(self, event):
        self.exit_reading_fullscreen()
        self.exit_fullscreen()
        self.cancel_jobs()
        self.stop_play()
        if self.web_dialog:
            self.web_dialog.close()
        super().closeEvent(event)
