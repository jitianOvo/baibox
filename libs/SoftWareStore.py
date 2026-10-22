import os
import json
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    QWidget,
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


class DownloadDoneDialog(QDialog):
    """下载完成提示：文件名加粗、路径换行可复制、三个操作按钮"""

    OPEN_FILE = "open_file"
    OPEN_DIR = "open_dir"
    CLOSE = "close"

    def __init__(self, parent, file_path):
        super().__init__(parent)
        self.file_path = file_path
        self.choice = self.CLOSE
        self.setWindowTitle("下载完成")
        self.setWindowIcon(parent.windowIcon() if parent and not parent.windowIcon().isNull() else QIcon())
        self.setFixedWidth(460)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #f3f6fb;
            }
            QFrame#card {
                background-color: #ffffff;
                border: 1px solid #dfe7f3;
                border-radius: 12px;
            }
            QLabel#title {
                color: #15803d;
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#file {
                color: #111827;
                font-size: 14px;
                font-weight: 600;
            }
            QLabel#dirCaption {
                color: #64748b;
                font-size: 12px;
            }
            QLabel#path {
                color: #334155;
                font-size: 12px;
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 8px 10px;
            }
            QLabel#meta {
                color: #64748b;
                font-size: 12px;
            }
            QLabel#hint {
                color: #334155;
                font-size: 13px;
            }
            QPushButton {
                min-width: 104px;
                min-height: 36px;
                border-radius: 9px;
                background-color: #eef3fb;
                border: 1px solid #d4deee;
                color: #1f2937;
                font-size: 13px;
                font-weight: 600;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #e6eefb;
            }
            QPushButton#primary {
                background-color: #2563eb;
                border-color: #2563eb;
                color: white;
            }
            QPushButton#primary:hover {
                background-color: #1d4ed8;
            }
            """
        )

        card = QFrame(self)
        card.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("下载完成", card)
        title.setObjectName("title")
        layout.addWidget(title)

        file_name = os.path.basename(file_path)
        file_label = QLabel("文件：" + file_name, card)
        file_label.setObjectName("file")
        file_label.setWordWrap(True)
        file_label.setToolTip(file_path)
        layout.addWidget(file_label)

        dir_caption = QLabel("保存位置：", card)
        dir_caption.setObjectName("dirCaption")
        layout.addWidget(dir_caption)

        path_label = QLabel(os.path.dirname(file_path), card)
        path_label.setObjectName("path")
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_label.setToolTip(file_path)
        layout.addWidget(path_label)

        meta = QLabel("", card)
        meta.setObjectName("meta")
        try:
            size_mb = round(os.path.getsize(file_path) / 1024 / 1024, 2)
            meta.setText(f"大小：{size_mb} MB")
        except OSError:
            meta.setText("大小：未知")
        layout.addWidget(meta)

        hint = QLabel("是否立即打开安装包？", card)
        hint.setObjectName("hint")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_open = QPushButton("打开文件", card)
        btn_open.setObjectName("primary")
        btn_dir = QPushButton("打开所在目录", card)
        btn_later = QPushButton("稍后再说", card)
        buttons.addWidget(btn_open)
        buttons.addWidget(btn_dir)
        buttons.addWidget(btn_later)
        layout.addSpacing(2)
        layout.addLayout(buttons)

        btn_open.clicked.connect(self._on_open_file)
        btn_dir.clicked.connect(self._on_open_dir)
        btn_later.clicked.connect(self._on_close)

    def _on_open_file(self):
        self.choice = self.OPEN_FILE
        self.accept()

    def _on_open_dir(self):
        self.choice = self.OPEN_DIR
        self.accept()

    def _on_close(self):
        self.choice = self.CLOSE
        self.reject()


class ClearCacheDialog(QDialog):
    """清空下载缓存确认框：显示缓存统计、危险操作提示"""

    CONFIRMED = "confirmed"
    CANCELED = "canceled"

    def __init__(self, parent, save_dir):
        super().__init__(parent)
        self.save_dir = save_dir
        self.choice = self.CANCELED
        self.setWindowTitle("清空下载缓存")
        if parent and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        self.setFixedWidth(440)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #f3f6fb;
            }
            QFrame#card {
                background-color: #ffffff;
                border: 1px solid #dfe7f3;
                border-radius: 12px;
            }
            QLabel#title {
                color: #b91c1c;
                font-size: 17px;
                font-weight: 700;
            }
            QLabel#desc {
                color: #334155;
                font-size: 13px;
            }
            QLabel#stat {
                color: #0f172a;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#path {
                color: #64748b;
                font-size: 12px;
                background-color: #fef2f2;
                border: 1px solid #fecaca;
                border-radius: 8px;
                padding: 8px 10px;
            }
            QLabel#warn {
                color: #b91c1c;
                font-size: 12px;
            }
            QPushButton {
                min-width: 104px;
                min-height: 36px;
                border-radius: 9px;
                background-color: #eef3fb;
                border: 1px solid #d4deee;
                color: #1f2937;
                font-size: 13px;
                font-weight: 600;
                padding: 6px 14px;
            }
            QPushButton:hover {
                background-color: #e6eefb;
            }
            QPushButton#danger {
                background-color: #dc2626;
                border-color: #dc2626;
                color: white;
            }
            QPushButton#danger:hover {
                background-color: #b91c1c;
            }
            """
        )

        file_count, total_size = 0, 0
        if os.path.isdir(save_dir):
            for fname in os.listdir(save_dir):
                fpath = os.path.join(save_dir, fname)
                if os.path.isfile(fpath):
                    file_count += 1
                    try:
                        total_size += os.path.getsize(fpath)
                    except OSError:
                        pass

        card = QFrame(self)
        card.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel("清空下载缓存", card)
        title.setObjectName("title")
        layout.addWidget(title)

        desc = QLabel("将删除已下载的全部安装包缓存，释放磁盘空间。", card)
        desc.setObjectName("desc")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        if file_count:
            stat = QLabel(f"共 {file_count} 个文件，占用 {format_size_for_dialog(total_size)}", card)
            stat.setObjectName("stat")
        else:
            stat = QLabel("当前缓存为空，无需清理", card)
            stat.setObjectName("stat")
        layout.addWidget(stat)

        path_label = QLabel(save_dir, card)
        path_label.setObjectName("path")
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_label.setToolTip(save_dir)
        layout.addWidget(path_label)

        warn = QLabel("此操作不可撤销，删除后需要重新下载。", card)
        warn.setObjectName("warn")
        layout.addWidget(warn)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_ok = QPushButton("确认清空", card)
        btn_ok.setObjectName("danger")
        btn_ok.setEnabled(file_count > 0)
        btn_cancel = QPushButton("取消", card)
        buttons.addWidget(btn_ok)
        buttons.addWidget(btn_cancel)
        layout.addSpacing(2)
        layout.addLayout(buttons)

        btn_ok.clicked.connect(self._on_confirm)
        btn_cancel.clicked.connect(self._on_cancel)

    def _on_confirm(self):
        self.choice = self.CONFIRMED
        self.accept()

    def _on_cancel(self):
        self.choice = self.CANCELED
        self.reject()


def format_size_for_dialog(size):
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


class SearchThread(QThread):
    search_finished = Signal(list)
    search_error = Signal(str)
    search_status = Signal(str)

    def __init__(self, keyword, headers):
        super().__init__()
        self.keyword = keyword
        self.headers = headers

    def _parse_xml_soft(self, xml_text, soft_id):
        """从搜索接口返回的 xmlInfo（已解转义的 XML）中解析软件完整信息"""
        display = re.findall(r"<displayname>\s*<!\[CDATA\[(.*?)\]\]>", xml_text)
        ver = re.findall(r"<versionname>([^<]*)</versionname>", xml_text)
        size = re.findall(r"<filesize>(\d+)</filesize>", xml_text)
        fname = re.findall(r"filename>([^<]*)</", xml_text)
        date = re.findall(r"<publishdate>([^<]*)</publishdate>", xml_text)
        url = re.findall(r"<url>\s*<!\[CDATA\[(.*?)\]\]>", xml_text)
        logo48 = re.findall(r"<logo48>([^<]*)</logo48>", xml_text)

        if not display or not url:
            return None

        size_mb = 0
        if size:
            try:
                size_mb = round(float(size[0]) / 1024 / 1024, 2)
            except Exception:
                size_mb = 0

        icon_url = None
        if logo48:
            icon_url = f"https://pc3.gtimg.com/softmgr/logo/48/{logo48[0]}"

        return {
            "id_seed": soft_id,
            "name": display[0].strip(),
            "version": ver[0].strip() if ver else "未知版本",
            "size": size_mb,
            "date": date[0].strip() if date else "未知日期",
            "url": url[0].strip(),
            "filename": fname[0].strip() if fname else f"{display[0].strip()}.exe",
            "icon_url": icon_url,
        }

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

            # 搜索接口一次返回全部软件完整信息，无需再逐个请求详情
            response = requests.get(
                "https://luban.m.qq.com/api/public/software-manager/searchcgi",
                headers=self.headers,
                params=params,
                timeout=12,
            )
            response.raise_for_status()

            # 取出 searchCallback(...) 内的 JSON 并真正解析（xmlInfo 会自动解转义）
            body = response.text
            start_idx = body.find("(")
            end_idx = body.rfind(")")
            payload = body[start_idx + 1:end_idx] if start_idx != -1 and end_idx != -1 else body
            try:
                data = json.loads(payload)
            except Exception:
                data = {}

            results = []
            for item in data.get("list", []):
                soft_id = str(item.get("SoftID", ""))
                xml_text = item.get("xmlInfo", "")
                if not soft_id or not xml_text:
                    continue
                result = self._parse_xml_soft(xml_text, soft_id)
                if result:
                    results.append(result)

            self.search_finished.emit(results)
        except Exception as exc:
            self.search_error.emit(str(exc))


class IconLoadThread(QThread):
    loaded = Signal(QListWidgetItem, QIcon)

    def __init__(self, targets):
        super().__init__()
        self.targets = targets

    def _fetch_one(self, session, item, icon_url):
        try:
            resp = session.get(icon_url, timeout=8)
            resp.raise_for_status()
            pix = QPixmap()
            if pix.loadFromData(resp.content):
                self.loaded.emit(item, QIcon(pix))
        except Exception:
            pass

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
        # 并发下载图标，加快图标显示速度
        targets = [(item, icon_url) for item, icon_url in self.targets if icon_url]
        with ThreadPoolExecutor(max_workers=max(1, min(len(targets), 8))) as pool:
            futures = [pool.submit(self._fetch_one, session, item, url) for item, url in targets]
            for future in as_completed(futures):
                future.result()


class DownloadThread(QThread):
    progress = Signal(int)
    info = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, url, save_dir, filename, soft_id=None, headers2=None):
        super().__init__()
        self.url = url
        self.save_dir = save_dir
        self.filename = filename
        self.soft_id = soft_id
        self.headers2 = headers2
        self.save_path = os.path.join(save_dir, filename)

    def _resolve_real_url(self):
        """用 softwareProxy 实时解析真实下载直链（旧版稳定链路），失败时回退到列表里的 URL"""
        if not self.soft_id or not self.headers2:
            return self.url
        try:
            data = {"cmdid": "3318", "jprxReq[req][soft_id_list][]": str(self.soft_id)}
            resp = requests.post(
                "https://luban.m.qq.com/api/public/software-manager/softwareProxy",
                headers=self.headers2,
                data=data,
                timeout=12,
            )
            links = re.findall(r'"download_url":"(.*?)"', resp.text)
            if links:
                return links[0]
        except Exception:
            pass
        return self.url

    def _on_aria_progress(self, data):
        pct = data.get("percent", 0)
        done = data.get("downloaded", "0B")
        total = data.get("total", "0B")
        speed = data.get("speed", "0B")
        eta = data.get("eta", "")
        self.progress.emit(pct)
        eta_txt = f" 剩余 {eta}" if eta else ""
        self.info.emit(f"已下载 {done} / {total}   速度 {speed}{eta_txt}")

    def run(self):
        try:
            os.makedirs(self.save_dir, exist_ok=True)
            # 文件已存在则视为完成，避免重复下载报错
            if os.path.exists(self.save_path):
                self.progress.emit(100)
                self.finished.emit(self.save_path)
                return

            self.progress.emit(5)
            self.info.emit("正在连接下载源...")
            # 首选 searchcgi 返回的 webcdn 直链（实测 aria2 可稳定下载）；
            # 失败时再回退 softwareProxy 解析的签名直链
            try:
                aria2_download(
                    url=self.url,
                    threads=16,
                    filename=self.filename,
                    path=self.save_dir,
                    min_split_size="1M",
                    on_progress=self._on_aria_progress,
                )
            except Exception as primary_exc:
                fallback_url = self._resolve_real_url()
                if fallback_url and fallback_url != self.url:
                    self.info.emit("主下载源失败，正在切换备用源...")
                    # 清理可能残留的半成品，避免续传错乱
                    for fname in os.listdir(self.save_dir):
                        if fname.startswith(os.path.splitext(self.filename)[0]) or fname.endswith(".aria2"):
                            try:
                                os.remove(os.path.join(self.save_dir, fname))
                            except OSError:
                                pass
                    aria2_download(
                        url=fallback_url,
                        threads=16,
                        filename=self.filename,
                        path=self.save_dir,
                        min_split_size="1M",
                        on_progress=self._on_aria_progress,
                    )
                else:
                    raise primary_exc
            self.progress.emit(100)
            # aria2 遇到同名文件会改成 .1 / .2 之类，这里兜底找到实际落盘文件
            target = self.save_path
            if not os.path.exists(target):
                candidates = []
                base = os.path.basename(target)
                for fname in os.listdir(self.save_dir):
                    if fname.startswith(os.path.splitext(base)[0]):
                        candidates.append(os.path.join(self.save_dir, fname))
                if candidates:
                    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                    target = candidates[0]
            if not os.path.exists(target):
                raise RuntimeError("下载任务已结束，但未检测到目标文件。")
            self.finished.emit(target)
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

    # 每次搜索生成一个 token，防止连续搜索时旧结果污染新结果
    search_state = {"token": 0}

    def do_search():
        keyword = search_box.text().strip()
        if not keyword:
            _build_message_box(dialog, "提示", "请输入搜索关键词。", level="warn").exec()
            return

        search_state["token"] += 1
        current_token = search_state["token"]

        result_list.clear()
        status_label.setText("状态：正在搜索...")
        search_progress.setVisible(True)
        btn_search.setEnabled(False)
        btn_search.setText("搜索中")

        search_thread = SearchThread(keyword, headers)
        self.search_threads.append(search_thread)

        def on_search_status(text):
            if current_token != search_state["token"]:
                return
            status_label.setText(f"状态：{text}")

        def on_search_finished(results):
            if current_token != search_state["token"]:
                if search_thread in self.search_threads:
                    self.search_threads.remove(search_thread)
                return
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
                item.setData(Qt.UserRole + 3, result.get("id_seed", ""))
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
            if search_thread in self.search_threads:
                self.search_threads.remove(search_thread)
            if current_token != search_state["token"]:
                return
            search_progress.setVisible(False)
            btn_search.setEnabled(True)
            btn_search.setText("搜索")
            status_label.setText("状态：搜索失败")
            _build_message_box(dialog, "搜索失败", f"搜索失败：{error}", level="error").exec()

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

        soft_id = item.data(Qt.UserRole + 3) or None
        thread = DownloadThread(url, save_dir, filename, soft_id=soft_id, headers2=headers2)
        self.download_threads.append(thread)

        def on_progress(value):
            download_progress.setValue(max(0, min(100, value)))

        def on_info(text):
            status_label.setText(f"状态：{text}")

        def on_finished(file_path):
            download_progress.setVisible(False)
            btn_download.setEnabled(True)
            btn_download.setText("下载选中")
            status_label.setText("状态：下载完成")

            msg = DownloadDoneDialog(dialog, file_path)
            msg.exec()
            if msg.choice == DownloadDoneDialog.OPEN_FILE:
                err = _safe_open_path(file_path)
                if err:
                    _build_message_box(dialog, "提示", f"无法打开文件：{err}", level="warn").exec()
            elif msg.choice == DownloadDoneDialog.OPEN_DIR:
                err = _safe_open_path(os.path.dirname(file_path))
                if err:
                    _build_message_box(dialog, "提示", f"无法打开目录：{err}", level="warn").exec()

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
        thread.info.connect(on_info)
        thread.finished.connect(on_finished)
        thread.error.connect(on_error)
        thread.start()

    def view_downloaded_files():
        err = _safe_open_path(save_dir)
        if err:
            _build_message_box(dialog, "提示", f"无法打开目录：{err}", level="warn").exec()

    def clear_cache():
        msg = ClearCacheDialog(dialog, save_dir)
        msg.exec()
        if msg.choice != ClearCacheDialog.CONFIRMED:
            return
        try:
            if os.path.exists(save_dir):
                shutil.rmtree(save_dir)
            os.makedirs(save_dir, exist_ok=True)
            _build_message_box(dialog, "完成", "缓存已清空，磁盘空间已释放。", level="info").exec()
        except Exception as exc:
            _build_message_box(dialog, "清空失败", f"清空失败：{exc}", level="error").exec()

    btn_search.clicked.connect(do_search)
    btn_download.clicked.connect(download_selected)
    btn_view_files.clicked.connect(view_downloaded_files)
    btn_clear_cache.clicked.connect(clear_cache)
    search_box.returnPressed.connect(do_search)

    dialog.exec()
