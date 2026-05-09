import os,re,requests,subprocess,sys
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QPixmap, QIcon
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton,
                             QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                             QHBoxLayout, QProgressBar, QFrame)
def SoftWareStore(self):
    self.search_threads = []
    self.download_threads = []

    # 创建对话框
    dialog = QDialog(self)
    dialog.setWindowTitle("喵~ | 这是一个可爱的软件中心")
    dialog.setFixedSize(600, 750)
    dialog.setStyleSheet("""
        QDialog {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1, 
                        stop:0 #667eea, stop:1 #764ba2);
            border-radius: 15px;
        }
        QLabel {
            color: white;
            font-family: 'Microsoft YaHei', Arial;
        }
        QLineEdit {
            background-color: rgba(255, 255, 255, 0.9);
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 25px;
            padding: 12px 20px;
            font-size: 14px;
            color: #333;
        }
        QLineEdit:focus {
            border: 2px solid #4CAF50;
            background-color: white;
        }
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #4CAF50, stop:1 #45a049);
            color: white;
            border: none;
            border-radius: 25px;
            padding: 12px 24px;
            font-size: 14px;
            font-weight: bold;
            font-family: 'Microsoft YaHei';
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #45a049, stop:1 #3d8b40);
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #3d8b40, stop:1 #2e7d32);
        }
        QPushButton:disabled {
            background: #cccccc;
            color: #666666;
        }
        QListWidget {
            background-color: rgba(255, 255, 255, 0.95);
            border: none;
            border-radius: 15px;
            padding: 10px;
        }
        QListWidget::item {
            background-color: white;
            border: 1px solid #e0e0e0;
            border-radius: 10px;
            margin: 5px;
            padding: 15px;
            font-size: 13px;
        }
        QListWidget::item:selected {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #4CAF50, stop:1 #45a049);
            color: white;
        }
        QListWidget::item:hover {
            background-color: #f5f5f5;
            border: 1px solid #4CAF50;
        }
        QProgressBar {
            border: none;
            border-radius: 10px;
            background-color: rgba(255, 255, 255, 0.3);
            text-align: center;
            color: white;
            font-weight: bold;
        }
        QProgressBar::chunk {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #4CAF50, stop:1 #45a049);
            border-radius: 10px;
        }
    """)

    layout = QVBoxLayout(dialog)
    layout.setSpacing(20)
    layout.setContentsMargins(30, 30, 30, 30)

    # 标题区域
    # 标题区域（带圆角白色背景）
    title_frame = QFrame()
    title_frame.setStyleSheet("""
        QFrame {
            background-color: white;
            border-radius: 15px;
            padding: 3px;
        }
    """)
    title_layout = QVBoxLayout(title_frame)

    main_title = QLabel("软件中心")
    main_title.setFont(QFont("Microsoft YaHei", 24, QFont.Bold))
    main_title.setAlignment(Qt.AlignCenter)
    main_title.setStyleSheet("""
        QLabel {
            font-weight: bold;
            font-size: 28pt;
            color: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #4A90E2, stop:1 #9B59B6
            );
        }
    """)

    subtitle = QLabel("妈妈再也不用担心电脑乱种下崽器了~")
    subtitle.setFont(QFont("Microsoft YaHei", 12))
    subtitle.setAlignment(Qt.AlignCenter)
    subtitle.setStyleSheet("""
        QLabel {
            color: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 #1e90ff, stop:1 #8a2be2
            );
            font-weight: bold;
        }
    """)

    title_layout.addWidget(main_title)
    title_layout.addWidget(subtitle)
    layout.addWidget(title_frame)

    # 搜索区域
    search_frame = QFrame()
    search_frame.setStyleSheet("""
        QFrame {
            background-color: white;
            border-radius: 15px;
            padding: 6px 15px;  /* 修改这里：上下8px，左右15px */
        }
    """)
    search_layout = QHBoxLayout(search_frame)
    search_box = QLineEdit()
    search_box.setPlaceholderText("🔍 输入软件名称，如：QQ、微信、Chrome...")
    search_box.setFont(QFont("Microsoft YaHei", 12))

    btn_search = QPushButton("搜索")
    btn_search.setFixedSize(120, 40)

    btn_search.setStyleSheet("""
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #4CAF50, stop:1 #45a049);
            color: white;
            border: none;
            border-radius: 20px;
            font-size: 14px;
            font-weight: bold;
            font-family: 'Microsoft YaHei';
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #45a049, stop:1 #3d8b40);
        }
        QPushButton:pressed {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3d8b40, stop:1 #2e7d32);
        }
    """)

    search_layout.addWidget(search_box, 4)
    search_layout.addWidget(btn_search, 1)

    layout.addWidget(search_frame)

    # 搜索进度条
    search_progress = QProgressBar()
    search_progress.setVisible(False)
    search_progress.setRange(0, 0)
    search_progress.setFixedHeight(8)
    layout.addWidget(search_progress)

    # 结果列表
    result_list = QListWidget()
    result_list.setMinimumHeight(300)
    search_box.setStyleSheet("""
        background-color: #f5f5f5;
        border-radius: 12px;
        padding: 8px 12px;
        font-size: 14px;
    """)

    result_list.setStyleSheet("""
        QListWidget {
            background-color: #fafafa;
            border: none;
        }
        QListWidget::item:selected {
            background: #d0ebff;
            color: #333333;
            outline: none;
        }
        QListWidget:focus {
            outline: 0;
        }
        QListWidget::item:focus {
            outline: 0;
        }

        QScrollBar:vertical {
            background: #f0f0f0;
            width: 12px;
            margin: 0px 0px 0px 0px;
            border-radius: 6px;
        }
        QScrollBar::handle:vertical {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #4a90e2, stop:1 #6a1b9a);
            border-radius: 6px;
            min-height: 20px;
        }
        QScrollBar::handle:vertical:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 #6a1b9a, stop:1 #4a90e2);
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }

        QScrollBar:horizontal {
            background: #f0f0f0;
            height: 12px;
            border-radius: 6px;
        }
        QScrollBar::handle:horizontal {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #4a90e2, stop:1 #6a1b9a);
            border-radius: 6px;
            min-width: 20px;
        }
        QScrollBar::handle:horizontal:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #6a1b9a, stop:1 #4a90e2);
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0;
        }
    """)
    layout.addWidget(result_list)

    # 下载进度条
    download_progress = QProgressBar()
    download_progress.setVisible(False)
    download_progress.setFixedHeight(25)
    layout.addWidget(download_progress)

    # 按钮区域
    button_frame = QFrame()
    button_frame.setStyleSheet("""
        QFrame {
            background-color: white;
            border-radius: 15px;
            padding: 8px;
        }
    """)
    button_layout = QHBoxLayout(button_frame)
    btn_download = QPushButton("📥 下载选中")
    btn_view_files = QPushButton("📁 查看下载")
    btn_clear_cache = QPushButton("🗑️ 清空缓存")

    btn_view_files.setStyleSheet("""
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #2196F3, stop:1 #1976D2);
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #1976D2, stop:1 #1565C0);
        }
    """)

    btn_clear_cache.setStyleSheet("""
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #FF5722, stop:1 #D84315);
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                        stop:0 #D84315, stop:1 #BF360C);
        }
    """)

    button_layout.addWidget(btn_download)
    button_layout.addWidget(btn_view_files)
    button_layout.addWidget(btn_clear_cache)
    layout.addWidget(button_frame)

    # 下载目录
    save_dir = os.path.join(os.path.expanduser('~'), "PyCache", "SoftWare")
    os.makedirs(save_dir, exist_ok=True)

    # 请求头
    headers2 = {
        "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        "Connection": "keep-alive",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://pc.qq.com",
        "Referer": "https://pc.qq.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36 Edg/139.0.0.0",
    }

    # 搜索线程类
    class SearchThread(QThread):
        search_finished = pyqtSignal(list)
        search_error = pyqtSignal(str)
        search_progress_update = pyqtSignal(str)

        def __init__(self, keyword):
            super().__init__()
            self.keyword = keyword

        def run(self):
            try:
                self.search_progress_update.emit("正在搜索...")

                params = {
                    "type": "search",
                    "callback": "searchCallback",
                    "keyword": self.keyword,
                    "page": "1",
                    "pernum": "50",
                    "more": "0"
                }

                self.search_progress_update.emit("发送请求...")
                response = requests.get("https://luban.m.qq.com/api/public/software-manager/searchcgi",
                                        headers=headers, params=params, timeout=10)

                self.search_progress_update.emit("解析结果...")
                label = re.findall(r"{.*?}", response.text)
                ids = []
                for i in label:
                    SoftId = re.findall(r'"SoftID":(\d+)', i)
                    if SoftId:
                        ids.append(SoftId[0])

                results = []
                total_ids = len(ids)

                for idx, ID in enumerate(ids):
                    self.search_progress_update.emit(f"获取软件信息 {idx + 1}/{total_ids}")

                    data = {"cmdid": "3318", "jprxReq[req][soft_id_list][]": ID}
                    response2 = requests.post("https://luban.m.qq.com/api/public/software-manager/softwareProxy",
                                              headers=headers2, data=data, timeout=10).text

                    SoftName = re.findall(r'"display_name":"(.*?)"', response2)
                    ver_name = re.findall(r'"ver_name":"(.*?)"', response2)
                    file_size = re.findall(r'"file_size":"(\d+)"', response2)
                    file_name = re.findall(r'"file_name":"(.*?)"', response2)
                    publish_date = re.findall(r'"publish_date":"(.*?)"', response2)
                    download_url = re.findall(r'"download_url":"(.*?)"', response2)
                    SoftLogo = re.findall(r'"Logo48File":"(.*?)"', response2)
                    icon_url = f"https://{SoftLogo[0]}" if SoftLogo else None

                    if SoftName and download_url:
                        size_mb = round((float(file_size[0]) / 1024 / 1024), 2) if file_size else 0
                        results.append({
                            'name': SoftName[0],
                            'version': ver_name[0] if ver_name else 'Unknown',
                            'size': size_mb,
                            'date': publish_date[0] if publish_date else 'Unknown',
                            'url': download_url[0],
                            'filename': file_name[0] if file_name else f"{SoftName[0]}.exe",
                            'icon_url': icon_url
                        })

                self.search_finished.emit(results)

            except Exception as e:
                self.search_error.emit(str(e))

    # 下载线程类
    class DownloadThread(QThread):
        download_progress = pyqtSignal(int)
        download_finished = pyqtSignal(str)
        download_error = pyqtSignal(str)

        def __init__(self, url, save_path):
            super().__init__()
            self.url = url
            self.save_path = save_path

        def run(self):
            try:
                with requests.get(self.url, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    total = int(r.headers.get('content-length', 0))
                    downloaded = 0
                    with open(self.save_path, "wb") as f:
                        for chunk in r.iter_content(8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total > 0:
                                    self.download_progress.emit(int(downloaded * 100 / total))
                self.download_finished.emit(self.save_path)
            except Exception as e:
                self.download_error.emit(str(e))

    # 搜索函数
    def do_search():
        keyword = search_box.text().strip()
        if not keyword:
            msg_box = QMessageBox(dialog)
            msg_box.setWindowTitle("⚠️ 提示")
            msg_box.setTextFormat(Qt.RichText)
            msg_box.setText('<span style="color:red;">请输入搜索关键词！</span>')
            msg_box.setStyleSheet("""
                QMessageBox {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #80c0ff, stop:1 #a080ff);
                    border-radius: 10px;
                }
                QLabel {
                    background-color: transparent;
                }
            """)
            msg_box.exec_()
            return

        result_list.clear()
        search_progress.setVisible(True)
        btn_search.setEnabled(False)
        btn_search.setText("🔍 搜索中...")

        search_thread = SearchThread(keyword)
        self.search_threads.append(search_thread)

        def on_search_finished(results):
            search_progress.setVisible(False)
            btn_search.setEnabled(True)
            btn_search.setText("🚀 搜索")

            for result in results:
                item_text = f"{result['name']}\n🏷️ 版本: {result['version']} | 📏 大小: {result['size']}MB | 📅 发布: {result['date']}"
                item = QListWidgetItem(item_text)

                icon_url = result.get('icon_url')
                if icon_url:
                    try:
                        from urllib.request import urlopen
                        data = urlopen(icon_url).read()
                        pixmap = QPixmap()
                        pixmap.loadFromData(data)
                        item.setIcon(QIcon(pixmap))
                    except Exception as e:
                        print("图标加载失败:", e)

                item.setData(1000, result['url'])
                item.setData(1001, result['filename'])
                item.setSizeHint(QSize(0, 80))
                result_list.addItem(item)

            if not results:
                no_result = QListWidgetItem("😔 未找到相关软件，请尝试其他关键词")
                no_result.setSizeHint(QSize(0, 60))
                result_list.addItem(no_result)

            self.search_threads.remove(search_thread)

        def on_search_error(error):
            search_progress.setVisible(False)
            btn_search.setEnabled(True)
            btn_search.setText("🚀 搜索")
            QMessageBox.critical(dialog, "❌ 错误", f"搜索失败: {error}")
            self.search_threads.remove(search_thread)

        search_thread.search_finished.connect(on_search_finished)
        search_thread.search_error.connect(on_search_error)

        search_thread.start()

    # 下载函数
    def download_selected():
        item = result_list.currentItem()
        if not item or not item.data(1000):
            msg_box = QMessageBox(dialog)
            msg_box.setWindowTitle("⚠️ 提示")
            msg_box.setTextFormat(Qt.RichText)
            msg_box.setText('<span style="color:red;">请先选择一个软件！</span>')
            msg_box.setStandardButtons(QMessageBox.Ok)

            msg_box.setStyleSheet("""
                QMessageBox {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #80c0ff, stop:1 #a080ff);
                    border-radius: 12px;
                }
                QLabel {
                    background-color: transparent;
                }
                QPushButton {
                    min-width: 80px;
                    padding: 6px;
                    border-radius: 6px;
                    font-weight: bold;
                    color: white;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #4CAF50, stop:1 #45a049);
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #45a049, stop:1 #3d8b40);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #3d8b40, stop:1 #2e7d32);
                }
            """)

            msg_box.exec_()
            return

        url = item.data(1000)
        fname = item.data(1001)
        save_path = os.path.join(save_dir, fname)

        download_progress.setVisible(True)
        btn_download.setEnabled(False)
        btn_download.setText("📥 下载中...")

        download_thread = DownloadThread(url, save_path)
        self.download_threads.append(download_thread)

        def on_download_progress(value):
            download_progress.setValue(value)

        def on_download_finished(file_path):
            download_progress.setVisible(False)
            btn_download.setEnabled(True)
            btn_download.setText("📥 下载选中")

            msg_box = QMessageBox(dialog)
            msg_box.setWindowTitle("✅ 下载完成")
            msg_box.setTextFormat(Qt.RichText)
            msg_box.setText(f'<span style="color:red;">文件已下载到:{file_path}<br>是否立即打开？</span>')
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

            msg_box.setStyleSheet("""
                QMessageBox {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #80c0ff, stop:1 #a080ff);
                    border-radius: 12px;
                }
                QLabel {
                    background-color: transparent;
                }
                QPushButton {
                    min-width: 80px;
                    padding: 6px;
                    border-radius: 6px;
                    font-weight: bold;
                    color: white;
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #4CAF50, stop:1 #45a049);
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #45a049, stop:1 #3d8b40);
                }
                QPushButton:pressed {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                stop:0 #3d8b40, stop:1 #2e7d32);
                }
            """)

            reply = msg_box.exec_()

            if reply == QMessageBox.Yes:
                try:
                    if sys.platform == "win32":
                        os.startfile(file_path)
                    elif sys.platform == "darwin":
                        subprocess.call(["open", file_path])
                    else:
                        subprocess.call(["xdg-open", file_path])
                except Exception as e:
                    QMessageBox.warning(dialog, "⚠️ 提示", f"无法打开文件: {e}")

            self.download_threads.remove(download_thread)

        def on_download_error(error):
            download_progress.setVisible(False)
            btn_download.setEnabled(True)
            btn_download.setText("📥 下载选中")
            QMessageBox.critical(dialog, "❌ 错误", f"下载失败: {error}")
            self.download_threads.remove(download_thread)

        download_thread.download_progress.connect(on_download_progress)
        download_thread.download_finished.connect(on_download_finished)
        download_thread.download_error.connect(on_download_error)
        download_thread.start()

    # 查看下载文件
    def view_downloaded_files():
        try:
            if sys.platform == "win32":
                os.startfile(save_dir)
            elif sys.platform == "darwin":
                subprocess.call(["open", save_dir])
            else:
                subprocess.call(["xdg-open", save_dir])
        except Exception as e:
            QMessageBox.warning(dialog, "⚠️ 提示", f"无法打开文件夹: {e}")

    # 清空缓存
    def clear_cache():
        msg_box = QMessageBox(dialog)
        msg_box.setWindowTitle("🗑️ 确认删除")
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText('<span style="color:red;">确定要清空所有已下载的文件吗？<br>此操作不可撤销！</span>')
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)

        msg_box.setStyleSheet("""
            QMessageBox {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                            stop:0 #80c0ff, stop:1 #a080ff);
                border-radius: 12px;
            }
            QLabel {
                background-color: transparent;
            }
            QPushButton {
                min-width: 80px;
                padding: 6px;
                border-radius: 6px;
                font-weight: bold;
                color: white;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #4CAF50, stop:1 #45a049);
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #45a049, stop:1 #3d8b40);
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                            stop:0 #3d8b40, stop:1 #2e7d32);
            }
        """)

        reply = msg_box.exec_()

        if reply == QMessageBox.Yes:
            try:
                import shutil
                if os.path.exists(save_dir):
                    shutil.rmtree(save_dir)
                    os.makedirs(save_dir, exist_ok=True)
                msg_box = QMessageBox(dialog)
                msg_box.setWindowTitle("✅ 完成")
                msg_box.setTextFormat(Qt.RichText)
                msg_box.setText('<span style="color:red;">缓存已清空！</span>')
                msg_box.setStandardButtons(QMessageBox.Ok)

                msg_box.setStyleSheet("""
                    QMessageBox {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                    stop:0 #80c0ff, stop:1 #a080ff);
                        border-radius: 12px;
                    }
                    QLabel {
                        background-color: transparent;
                    }
                    QPushButton {
                        min-width: 80px;
                        padding: 6px;
                        border-radius: 6px;
                        font-weight: bold;
                        color: white;
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #4CAF50, stop:1 #45a049);
                    }
                    QPushButton:hover {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #45a049, stop:1 #3d8b40);
                    }
                    QPushButton:pressed {
                        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #3d8b40, stop:1 #2e7d32);
                    }
                """)

                msg_box.exec_()

            except Exception as e:
                QMessageBox.critical(dialog, "❌ 错误", f"清空失败: {e}")

    # 连接信号
    btn_search.clicked.connect(do_search)
    btn_download.clicked.connect(download_selected)
    btn_view_files.clicked.connect(view_downloaded_files)
    btn_clear_cache.clicked.connect(clear_cache)

    # 回车搜索
    search_box.returnPressed.connect(do_search)

    # 显示对话框
    dialog.exec_()
