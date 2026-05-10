import os
import re
import shutil
import subprocess
import sys

import requests
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QVBoxLayout,
)

from core_lib import get_path

ARIA2_API_DIR = get_path("assets/aira2c")
if ARIA2_API_DIR not in sys.path:
    sys.path.insert(0, ARIA2_API_DIR)
from aria2c_api import aria2_download


def _build_message_box(parent, title, text, level="info", buttons=None):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(
        QMessageBox.Information
        if level == "info"
        else QMessageBox.Warning
        if level == "warn"
        else QMessageBox.Critical
    )
    box.setStyleSheet(
        """
        QMessageBox {
            background-color: #f7f9fc;
        }
        QLabel {
            color: #1f2937;
            min-width: 280px;
            font-size: 13px;
        }
        QPushButton {
            min-width: 86px;
            min-height: 32px;
            border-radius: 8px;
            background-color: #eef2f7;
            border: 1px solid #d6deea;
            color: #1f2937;
            padding: 4px 10px;
        }
        QPushButton:hover {
            background-color: #e6edf8;
        }
        """
    )
    if buttons:
        for btn_text, role in buttons:
            box.addButton(btn_text, role)
    else:
        box.setStandardButtons(QMessageBox.Ok)
    return box


def _safe_open_path(target):
    try:
        if sys.platform == "win32":
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.call(["open", target])
        else:
            subprocess.call(["xdg-open", target])
        return None
    except Exception as exc:
        return str(exc)


class SearchThread(QThread):
    search_finished = Signal(list)
    search_error = Signal(str)
    search_status = Signal(str)

    def __init__(self, keyword, headers, headers2):
        super().__init__()
        self.keyword = keyword
        self.headers = headers
        self.headers2 = headers2

    def run(self):
        try:
            self.search_status.emit("正在检索软件列表...")

            params = {
                "type": "search",
                "callback": "searchCallback",
                "keyword": self.keyword,
                "page": "1",
                "pernum": "50",
                "more": "0",
            }

            response = requests.get(
                "https://luban.m.qq.com/api/public/software-manager/searchcgi",
                headers=self.headers,
                params=params,
                timeout=12,
            )
            response.raise_for_status()
            label = re.findall(r"{.*?}", response.text)

            ids = []
            for one in label:
                soft_id = re.findall(r'"SoftID":(\d+)', one)
                if soft_id:
                    ids.append(soft_id[0])

            results = []
            total = len(ids)
            for idx, sid in enumerate(ids):
                self.search_status.emit(f"正在获取详情 {idx + 1}/{total}")

                data = {"cmdid": "3318", "jprxReq[req][soft_id_list][]": sid}
                response2 = requests.post(
                    "https://luban.m.qq.com/api/public/software-manager/softwareProxy",
                    headers=self.headers2,
                    data=data,
                    timeout=12,
                ).text

                soft_name = re.findall(r'"display_name":"(.*?)"', response2)
                ver_name = re.findall(r'"ver_name":"(.*?)"', response2)
                file_size = re.findall(r'"file_size":"(\d+)"', response2)
                file_name = re.findall(r'"file_name":"(.*?)"', response2)
                publish_date = re.findall(r'"publish_date":"(.*?)"', response2)
                download_url = re.findall(r'"download_url":"(.*?)"', response2)
                soft_logo = re.findall(r'"Logo48File":"(.*?)"', response2)

                if not soft_name or not download_url:
                    continue

                icon_url = None
                if soft_logo:
                    logo = soft_logo[0]
                    icon_url = logo if logo.startswith("http") else f"https://{logo.lstrip('/')}"

                size_mb = 0
                if file_size:
                    try:
                        size_mb = round(float(file_size[0]) / 1024 / 1024, 2)
                    except Exception:
                        size_mb = 0

                results.append(
                    {
                        "name": soft_name[0],
                        "version": ver_name[0] if ver_name else "未知版本",
                        "size": size_mb,
                        "date": publish_date[0] if publish_date else "未知日期",
                        "url": download_url[0],
                        "filename": file_name[0] if file_name else f"{soft_name[0]}.exe",
                        "icon_url": icon_url,
                    }
                )

            self.search_finished.emit(results)
        except Exception as exc:
            self.search_error.emit(str(exc))


class IconLoadThread(QThread):
    loaded = Signal(QListWidgetItem, QIcon)

    def __init__(self, targets):
        super().__init__()
        self.targets = targets

    def run(self):
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"
                )
            }
        )
        for item, icon_url in self.targets:
            if not icon_url:
                continue
            try:
                resp = session.get(icon_url, timeout=8)
                resp.raise_for_status()
                pix = QPixmap()
                if pix.loadFromData(resp.content):
                    self.loaded.emit(item, QIcon(pix))
            except Exception:
                continue


class DownloadThread(QThread):
    progress = Signal(int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, url, save_dir, filename):
        super().__init__()
        self.url = url
        self.save_dir = save_dir
        self.filename = filename
        self.save_path = os.path.join(save_dir, filename)

    def run(self):
        try:
            os.makedirs(self.save_dir, exist_ok=True)
            self.progress.emit(5)
            aria2_download(
                url=self.url,
                threads=16,
                filename=self.filename,
                path=self.save_dir,
                min_split_size="1M",
            )
            self.progress.emit(100)
            if not os.path.exists(self.save_path):
                raise RuntimeError("下载任务已结束，但未检测到目标文件。")
            self.finished.emit(self.save_path)
        except Exception as exc:
            self.error.emit(str(exc))


def SoftWareStore(self):
    self.search_threads = []
    self.download_threads = []
    self.icon_threads = []

    dialog = QDialog(self)
    dialog.setWindowTitle("软件中心")
    dialog.resize(690, 760)
    if self and not self.windowIcon().isNull():
        dialog.setWindowIcon(self.windowIcon())
    dialog.setStyleSheet(
        """
        QDialog {
            background-color: #f3f6fb;
        }
        QFrame#Card {
            background-color: #ffffff;
            border: 1px solid #dfe7f3;
            border-radius: 12px;
        }
        QLabel#MainTitle {
            color: #111827;
            font-size: 22px;
            font-weight: 700;
        }
        QLabel#SubTitle {
            color: #64748b;
            font-size: 12px;
        }
        QLabel#StatusLabel {
            color: #334155;
            font-size: 12px;
        }
        QLineEdit {
            background-color: #f8fafc;
            border: 1px solid #dbe4f0;
            border-radius: 9px;
            padding: 8px 11px;
            color: #111827;
            font-size: 13px;
        }
        QLineEdit:focus {
            border: 1px solid #2563eb;
            background-color: #ffffff;
        }
        QPushButton {
            background-color: #eef3fb;
            border: 1px solid #d4deee;
            border-radius: 9px;
            min-height: 34px;
            padding: 6px 12px;
            color: #1f2937;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #e6eefb;
        }
        QPushButton:disabled {
            color: #94a3b8;
            background-color: #f1f5f9;
        }
        QPushButton[role="primary"] {
            background-color: #2563eb;
            border-color: #2563eb;
            color: white;
        }
        QPushButton[role="primary"]:hover {
            background-color: #1d4ed8;
        }
        QPushButton[role="danger"] {
            background-color: #ef4444;
            border-color: #ef4444;
            color: white;
        }
        QPushButton[role="danger"]:hover {
            background-color: #dc2626;
        }
        QListWidget {
            background-color: #fbfdff;
            border: 1px solid #dfe7f3;
            border-radius: 10px;
            outline: none;
            font-size: 13px;
            color: #0f172a;
        }
        QListWidget::item {
            padding: 10px 8px;
            border-bottom: 1px solid #edf2fb;
        }
        QListWidget::item:selected {
            background-color: #e7f0ff;
            color: #0f172a;
        }
        QProgressBar {
            border: 1px solid #dbe4f0;
            border-radius: 8px;
            background-color: #f8fafc;
            text-align: center;
            color: #334155;
            min-height: 18px;
        }
        QProgressBar::chunk {
            background-color: #2563eb;
            border-radius: 7px;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 11px;
            margin: 2px 2px 2px 0;
        }
        QScrollBar::handle:vertical {
            background: #c5d1e4;
            min-height: 28px;
            border-radius: 5px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: transparent;
        }
        """
    )

    layout = QVBoxLayout(dialog)
    layout.setSpacing(10)
    layout.setContentsMargins(16, 16, 16, 16)

    title_card = QFrame()
    title_card.setObjectName("Card")
    title_layout = QVBoxLayout(title_card)
    title_layout.setContentsMargins(14, 12, 14, 12)
    title_layout.setSpacing(4)
    title = QLabel("软件中心")
    title.setObjectName("MainTitle")
    title.setAlignment(Qt.AlignCenter)
    subtitle = QLabel("输入软件名称后搜索，选中即可高速下载到本地")
    subtitle.setObjectName("SubTitle")
    subtitle.setAlignment(Qt.AlignCenter)
    title_layout.addWidget(title)
    title_layout.addWidget(subtitle)
    layout.addWidget(title_card)

    search_card = QFrame()
    search_card.setObjectName("Card")
    search_layout = QVBoxLayout(search_card)
    search_layout.setContentsMargins(12, 10, 12, 10)
    search_layout.setSpacing(8)

    row = QHBoxLayout()
    row.setSpacing(8)
    search_box = QLineEdit()
    search_box.setPlaceholderText("输入软件名称，例如：QQ、微信、Chrome")
    search_box.setFont(QFont("Microsoft YaHei UI", 11))
    btn_search = QPushButton("搜索")
    btn_search.setProperty("role", "primary")
    btn_search.setFixedWidth(116)
    row.addWidget(search_box, 1)
    row.addWidget(btn_search)
    search_layout.addLayout(row)

    status_label = QLabel("状态：等待搜索")
    status_label.setObjectName("StatusLabel")
    search_layout.addWidget(status_label)

    search_progress = QProgressBar()
    search_progress.setVisible(False)
    search_progress.setRange(0, 0)
    search_progress.setFormat("正在查询...")
    search_layout.addWidget(search_progress)
    layout.addWidget(search_card)

    result_list = QListWidget()
    result_list.setIconSize(QSize(36, 36))
    result_list.setMinimumHeight(350)
    layout.addWidget(result_list, 1)

    download_progress = QProgressBar()
    download_progress.setVisible(False)
    download_progress.setValue(0)
    layout.addWidget(download_progress)

    button_card = QFrame()
    button_card.setObjectName("Card")
    button_layout = QHBoxLayout(button_card)
    button_layout.setContentsMargins(10, 8, 10, 8)
    button_layout.setSpacing(8)

    btn_download = QPushButton("下载选中")
    btn_download.setProperty("role", "primary")
    btn_view_files = QPushButton("打开下载目录")
    btn_clear_cache = QPushButton("清空下载缓存")
    btn_clear_cache.setProperty("role", "danger")

    button_layout.addWidget(btn_download)
    button_layout.addWidget(btn_view_files)
    button_layout.addWidget(btn_clear_cache)
    layout.addWidget(button_card)

    save_dir = os.path.join(os.path.expanduser("~"), "PyCache", "SoftWare")
    os.makedirs(save_dir, exist_ok=True)

    headers2 = {
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://pc.qq.com",
        "Referer": "https://pc.qq.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0"
        ),
    }
    headers = {"User-Agent": headers2["User-Agent"]}

    def do_search():
        keyword = search_box.text().strip()
        if not keyword:
            _build_message_box(dialog, "提示", "请输入搜索关键词。", level="warn").exec()
            return

        result_list.clear()
        status_label.setText("状态：正在搜索...")
        search_progress.setVisible(True)
        btn_search.setEnabled(False)
        btn_search.setText("搜索中")

        search_thread = SearchThread(keyword, headers, headers2)
        self.search_threads.append(search_thread)

        def on_search_status(text):
            status_label.setText(f"状态：{text}")

        def on_search_finished(results):
            search_progress.setVisible(False)
            btn_search.setEnabled(True)
            btn_search.setText("搜索")

            icon_targets = []
            for result in results:
                name = result["name"]
                version = result["version"]
                size = result["size"]
                date = result["date"]
                text = f"{name}\n版本：{version}   大小：{size} MB   发布：{date}"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, result["url"])
                item.setData(Qt.UserRole + 1, result["filename"])
                item.setData(Qt.UserRole + 2, result["icon_url"])
                item.setSizeHint(QSize(0, 66))
                result_list.addItem(item)

                icon_url = result.get("icon_url")
                if icon_url:
                    icon_targets.append((item, icon_url))

            if icon_targets:
                icon_thread = IconLoadThread(icon_targets)
                self.icon_threads.append(icon_thread)

                def on_icon_loaded(item, icon):
                    item.setIcon(icon)

                def on_icon_finished():
                    if icon_thread in self.icon_threads:
                        self.icon_threads.remove(icon_thread)

                icon_thread.loaded.connect(on_icon_loaded)
                icon_thread.finished.connect(on_icon_finished)
                icon_thread.start()

            if not results:
                result_list.addItem(QListWidgetItem("未找到相关软件，请尝试其他关键词。"))
                status_label.setText("状态：未找到匹配结果")
            else:
                status_label.setText(f"状态：已找到 {len(results)} 条结果")

            if search_thread in self.search_threads:
                self.search_threads.remove(search_thread)

        def on_search_error(error):
            search_progress.setVisible(False)
            btn_search.setEnabled(True)
            btn_search.setText("搜索")
            status_label.setText("状态：搜索失败")
            _build_message_box(dialog, "搜索失败", f"搜索失败：{error}", level="error").exec()
            if search_thread in self.search_threads:
                self.search_threads.remove(search_thread)

        search_thread.search_status.connect(on_search_status)
        search_thread.search_finished.connect(on_search_finished)
        search_thread.search_error.connect(on_search_error)
        search_thread.start()

    def download_selected():
        item = result_list.currentItem()
        if not item or not item.data(Qt.UserRole):
            _build_message_box(dialog, "提示", "请先在结果列表中选择一个软件。", level="warn").exec()
            return

        url = item.data(Qt.UserRole)
        filename = item.data(Qt.UserRole + 1)

        download_progress.setVisible(True)
        download_progress.setValue(0)
        btn_download.setEnabled(False)
        btn_download.setText("下载中")
        status_label.setText("状态：正在下载...")

        thread = DownloadThread(url, save_dir, filename)
        self.download_threads.append(thread)

        def on_progress(value):
            download_progress.setValue(max(0, min(100, value)))

        def on_finished(file_path):
            download_progress.setVisible(False)
            btn_download.setEnabled(True)
            btn_download.setText("下载选中")
            status_label.setText("状态：下载完成")

            msg = _build_message_box(
                dialog,
                "下载完成",
                f"文件已下载到：\n{file_path}\n\n是否立即打开文件？",
                level="info",
                buttons=[
                    ("打开文件", QMessageBox.AcceptRole),
                    ("稍后再说", QMessageBox.RejectRole),
                ],
            )
            msg.exec()
            clicked = msg.clickedButton()
            if clicked and clicked.text() == "打开文件":
                err = _safe_open_path(file_path)
                if err:
                    _build_message_box(dialog, "提示", f"无法打开文件：{err}", level="warn").exec()

            if thread in self.download_threads:
                self.download_threads.remove(thread)

        def on_error(error):
            download_progress.setVisible(False)
            btn_download.setEnabled(True)
            btn_download.setText("下载选中")
            status_label.setText("状态：下载失败")
            _build_message_box(dialog, "下载失败", f"下载失败：{error}", level="error").exec()
            if thread in self.download_threads:
                self.download_threads.remove(thread)

        thread.progress.connect(on_progress)
        thread.finished.connect(on_finished)
        thread.error.connect(on_error)
        thread.start()

    def view_downloaded_files():
        err = _safe_open_path(save_dir)
        if err:
            _build_message_box(dialog, "提示", f"无法打开目录：{err}", level="warn").exec()

    def clear_cache():
        msg = _build_message_box(
            dialog,
            "确认操作",
            "确定要清空已下载缓存吗？此操作不可撤销。",
            level="warn",
            buttons=[
                ("确认清空", QMessageBox.AcceptRole),
                ("取消", QMessageBox.RejectRole),
            ],
        )
        msg.exec()
        clicked = msg.clickedButton()
        if not clicked or clicked.text() != "确认清空":
            return
        try:
            if os.path.exists(save_dir):
                shutil.rmtree(save_dir)
            os.makedirs(save_dir, exist_ok=True)
            _build_message_box(dialog, "完成", "缓存已清空。", level="info").exec()
        except Exception as exc:
            _build_message_box(dialog, "清空失败", f"清空失败：{exc}", level="error").exec()

    btn_search.clicked.connect(do_search)
    btn_download.clicked.connect(download_selected)
    btn_view_files.clicked.connect(view_downloaded_files)
    btn_clear_cache.clicked.connect(clear_cache)
    search_box.returnPressed.connect(do_search)

    dialog.exec()
