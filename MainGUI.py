import sys,ctypes,lanzoui
from core_lib import *
from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import (Qt,QSize,QPoint,QEvent,QTimer,QThread,Signal,QRegularExpression,)
from PySide6.QtGui import (QFont,QFontDatabase,QPixmap,QIcon,QColor,QTextCursor,QMouseEvent,QSyntaxHighlighter,QTextCharFormat,)
from PySide6.QtWidgets import (QApplication,QWidget,QDialog,QFrame,QLabel,QPushButton,QLineEdit,QTextEdit,QListWidget,
QListWidgetItem,QFileDialog,QMessageBox,QVBoxLayout,QHBoxLayout,QProgressBar,QScrollArea,QStackedWidget,QSizePolicy,)

VERSION = "v2.2"

def VERSION_CODE():
    version = int(float(VERSION.split('v')[1]) * 100)
    return version

def build_ui_font(point_size=10, weight=QFont.Normal):
    font = QFont("Microsoft YaHei UI", point_size, weight)

    style_hint_enum = getattr(QFont, "StyleHint", None)
    if style_hint_enum is not None and hasattr(style_hint_enum, "System"):
        font.setStyleHint(style_hint_enum.System)

    style_strategy_enum = getattr(QFont, "StyleStrategy", None)
    if style_strategy_enum is not None and hasattr(style_strategy_enum, "PreferAntialias"):
        style_strategy = style_strategy_enum.PreferAntialias
        for name in ("PreferOutline", "PreferQuality"):
            if hasattr(style_strategy_enum, name):
                style_strategy |= getattr(style_strategy_enum, name)
        font.setStyleStrategy(style_strategy)

    hinting_enum = getattr(QFont, "HintingPreference", None)
    if hinting_enum is not None and hasattr(hinting_enum, "PreferVerticalHinting"):
        font.setHintingPreference(hinting_enum.PreferVerticalHinting)

    return font

class NoHorizontalScrollArea(QScrollArea):
    """锁定横向滚动，防止触摸板横向手势把页面带偏。"""
    def wheelEvent(self, event):
        super().wheelEvent(event)
        hbar = self.horizontalScrollBar()
        if hbar.value() != 0:
            hbar.setValue(0)

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("超级白工具箱")
        self.resize(150, 500)
        self.setWindowIcon(QIcon(get_path('assets/logos/iconic.ico')))
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setStyleSheet("background-color: white;")
        self.old_pos = self.pos()
        self.init_ui()
        self.is_minimized = False  # 添加最小化状态标志
        # 控制台窗口
        self.console_window = None
        self.init_console()

        QTimer.singleShot(100, self.bring_to_front)

    def bring_to_front(self):
        self.raise_()  # 把窗口置顶
        self.activateWindow()  # 获取焦点

    def init_console(self):
        """初始化扁平控制台窗口"""
        self.console_window = QWidget()
        self.console_window.setWindowTitle(f"【控制台】超级白工具箱 {VERSION} - ©2026–2027")
        self.console_window.setWindowFlags(Qt.Tool | Qt.WindowCloseButtonHint)
        self.console_window.resize(850, 600)

        # 主布局
        main_layout = QVBoxLayout(self.console_window)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 顶部工具栏
        toolbar = QWidget()
        toolbar.setFixedHeight(40)
        toolbar.setStyleSheet("""
            background: #2D2D30;
            border-bottom: 1px solid #1E1E1E;
        """)

        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(10, 0, 10, 0)

        # 标题
        title = QLabel("控制台")
        title.setStyleSheet("""
            color: #D4D4D4;
            font-size: 14px;
            font-weight: bold;
        """)
        toolbar_layout.addWidget(title)
        toolbar_layout.addStretch()

        # 工具栏按钮
        buttons = [
            ("清除", "#569CD6", self.clear_console),
            ("复制", "#D7BA7D", self.copy_console),
            ("保存", "#B5CEA8", self.save_console),
            ("关闭", "#D16969", self.console_window.hide)
        ]

        for text, color, callback in buttons:
            btn = QPushButton(text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    color: {color};
                    background: transparent;
                    border: none;
                    padding: 5px 10px;
                    font-size: 12px;
                    min-width: 60px;
                }}
                QPushButton:hover {{
                    background: rgba(255, 255, 255, 0.1);
                }}
            """)
            btn.clicked.connect(callback)
            toolbar_layout.addWidget(btn)

        main_layout.addWidget(toolbar)

        # 控制台文本区域
        self.console_text = QTextEdit()
        self.console_text.setReadOnly(True)
        self.console_text.setFont(QFont("Consolas", 10))
        self.console_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: none;
                padding: 10px;
            }
        """)

        main_layout.addWidget(self.console_text)

        # 底部状态栏
        status_bar = QWidget()
        status_bar.setFixedHeight(24)
        status_bar.setStyleSheet("""
            background: #252526;
            border-top: 1px solid #1E1E1E;
            color: #858585;
            font-size: 11px;
        """)

        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(10, 0, 10, 0)

        self.status_label = QLabel("就绪")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        main_layout.addWidget(status_bar)

        # ===== 读取 update_logs.txt 并显示 =====
        try:
            log_path = get_path("data/update_logs.txt")
            with open(log_path, "r", encoding="utf-8") as f:
                log_content = f.read()
            self.console_text.setPlainText(log_content)
        except Exception as e:
            self.console_text.setPlainText(f"无法读取更新日志: {str(e)}")

        # 重定向输出
        sys.stdout = self
        sys.stderr = self

    class ConsoleHighlighter(QSyntaxHighlighter):
        """控制台语法高亮"""

        def __init__(self, parent=None):
            super().__init__(parent)

            self.highlight_rules = []

            # 错误消息 (红色)
            error_format = QTextCharFormat()
            error_format.setForeground(QColor("#D16969"))
            self.highlight_rules.append((r"(error|fail|failed|exception)", error_format))

            # 警告消息 (黄色)
            warning_format = QTextCharFormat()
            warning_format.setForeground(QColor("#D7BA7D"))
            self.highlight_rules.append((r"(warning|注意|提醒)", warning_format))

            # 成功消息 (绿色)
            success_format = QTextCharFormat()
            success_format.setForeground(QColor("#B5CEA8"))
            self.highlight_rules.append((r"(success|完成|成功)", success_format))

            # 路径 (蓝色)
            path_format = QTextCharFormat()
            path_format.setForeground(QColor("#569CD6"))
            self.highlight_rules.append((r"[A-Za-z]:\\(?:[^\\/:*?\"<>|\r\n]+\\)*", path_format))

            # 命令 (紫色)
            command_format = QTextCharFormat()
            command_format.setForeground(QColor("#C586C0"))
            self.highlight_rules.append((r"(adb|cmd|命令|command)", command_format))

        def highlightBlock(self, text):
            for pattern, format in self.highlight_rules:
                expression = QRegularExpression(pattern)
                matches = expression.globalMatch(text)
                while matches.hasNext():
                    match = matches.next()
                    self.setFormat(match.capturedStart(), match.capturedLength(), format)

    def clear_console(self):
        """清除控制台内容"""
        self.console_text.clear()
        self.status_label.setText("控制台已清除")

    def copy_console(self):
        """复制控制台内容"""
        clipboard = QApplication.clipboard()
        clipboard.setText(self.console_text.toPlainText())
        self.status_label.setText("内容已复制到剪贴板")

    def save_console(self):
        """保存控制台内容到文件"""
        file_path, _ = QFileDialog.getSaveFileName(
            self.console_window, "保存日志", "", "文本文件 (*.txt);;所有文件 (*)"
        )
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.console_text.toPlainText())
                self.status_label.setText(f"日志已保存到: {file_path}")
            except Exception as e:
                self.status_label.setText(f"保存失败: {str(e)}")

    def write(self, text):
        """重写write方法以捕获所有输出"""
        try:
            # 尝试UTF-8解码
            decoded_text = text.encode('utf-8', errors='replace').decode('utf-8')
        except:
            # 如果UTF-8失败，尝试系统默认编码
            try:
                decoded_text = text.encode(sys.getdefaultencoding(), errors='replace').decode(sys.getdefaultencoding())
            except:
                # 最后尝试GBK
                decoded_text = text.encode('gbk', errors='replace').decode('gbk', errors='replace')

        self.console_text.moveCursor(QTextCursor.End)
        self.console_text.insertPlainText(decoded_text)
        # 确保立即更新显示
        QApplication.processEvents()

    def flush(self):
        """确保缓冲区被刷新"""
        pass

    def top_button_clicked(self, name):
        if name == "控制台":
            if self.console_window.isVisible():
                self.console_window.hide()
            else:
                self.console_window.show()
        elif name == "最小化":
            self.showMinimized()
            self.is_minimized = True  # 更新最小化状态
        elif name == "关闭":
            self.close()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # ==== 顶部灰色栏 ====
        self.top_bar = QWidget()
        self.top_bar.setFixedHeight(40)
        self.top_bar.setStyleSheet("background-color: #ebeaea;")
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(10, 0, 10, 0)

        # 主标题
        title_label = QLabel("JITIAN")
        title_label.setFont(build_ui_font(15, QFont.Bold))
        title_label.setStyleSheet("color: #8e98ac;")
        top_layout.addWidget(title_label)

        # 版本号标签
        version_label = QLabel(VERSION)

        # 加载自定义字体
        font_id = QFontDatabase.addApplicationFont(get_path("font/Aa棉花糖.ttf"))
        if font_id != -1:
            loaded_font_family = QFontDatabase.applicationFontFamilies(font_id)[0]
            version_label.setFont(QFont(loaded_font_family, 16))  # 版本号大小
            version_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)  # 先靠上
            version_label.setContentsMargins(0, 7, 0, 0)  #版本号字体上下参数调第二个 上边距增加 5 像素，让文字稍微往下一点

        else:
            version_label.setFont(build_ui_font(15))

        version_label.setStyleSheet("color: #8e98ac;")  # 与主标题颜色一致
        top_layout.addWidget(version_label)

        top_layout.addStretch()

        icon_paths = {
            "控制台": get_path("assets/logos/ui_search.png"),
            "最小化": get_path("assets/logos/ui_min.ico"),
            "关闭": get_path("assets/logos/ui_close.ico"),
        }

        for name, path in icon_paths.items():
            btn = QPushButton()
            btn.setIcon(QIcon(path))
            btn.setIconSize(QSize(20, 20))
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(name)
            btn.setStyleSheet("QPushButton { background-color: transparent; border: none; }")
            btn.clicked.connect(lambda _, b=name: self.top_button_clicked(b))
            top_layout.addWidget(btn)

        main_layout.addWidget(self.top_bar)

        # ==== 中间标题 ====
        title = QLabel("超级白工具箱")
        title.setFont(build_ui_font(17, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #222; padding: 8px; border-bottom: 1px solid #CCC;")  # 尺寸
        main_layout.addWidget(title)

        # ==== 主体区域 中下方整个背景 ====
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)  # 消除布局的外边距 中下方整个背景
        content_layout.setSpacing(2)

        # 左侧分类区
        self.category_list = QListWidget()
        self.category_list.setFixedWidth(80)
        self.category_list.setStyleSheet("""
            QListWidget {
                background-color: #F6F6F6;
                border: none;
                border-right: 1px solid #CCCCCC;
                outline: 0;
            }
            QListWidget::item {
                height: 40px;
                padding: 0px;
                color: #0096FF; 
                border-bottom: 1px solid #E0E0E0;
                text-align: center;
            }
            QListWidget::item:selected {
                background-color: #E6F0FF;
                color: #3F00FF;
                border-left: 4px solid #0078D7;
                border-radius: 3px;
            }
        """)
        for name in ["ADB功能", "FB功能", "面具/环境", "电脑脚本", '二进制', '其他', '图片']:
            item = QListWidgetItem(name)
            item.setTextAlignment(Qt.AlignCenter)
            self.category_list.addItem(item)
        self.category_list.currentRowChanged.connect(self.switch_page)

        # 功能区窗口
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setStyleSheet("background-color: #FFFFFF;")
        self.stacked_widget.setFixedWidth(250)

        # 功能区
        self.stacked_widget.addWidget(self.build_tool_page("ADB功能", [
            (" Scrcpy投屏", "#FF0000", get_path("assets/logos/scrcpy.ico"), self.open_scrcpy),
            (" 设备选择", "#FF0000", get_path("assets/logos/android2.png"), self.on_choose_devices_clicked),
            (" 打开ADB面板", "#FF0000", get_path("assets/logos/cmd.png"), self.open_adb),
            ("一键备份基带", "#FF0000", get_path("assets/logos/backup.png"), self.backup_IMG),
            ("一键还原基带", "#FF0000", get_path("assets/logos/restore.png"), self.restore_IMG),
            (" ADB重启设备", "#FF0000", get_path('assets/logos/reboot.png'), self.adb_reboot),
            (" ADB驱动安装", "#FF0000", get_path("assets/logos/android.png"), self.install_adb_driver),
            ("一加一键解锁BL", "#FF0000", get_path("assets/logos/android3.png"), self.oneplus_unblock_BL),
        ]))

        self.stacked_widget.addWidget(self.build_tool_page("FB功能", [
            ("[FB]一键刷入boot.img", "#e85239", get_path("assets/logos/cd.png"), self.flash_boot),
            ("[FB]重启设备", "#e85239", get_path('assets/logos/reboot.png'), self.fastboot_reboot),
        ]))

        self.stacked_widget.addWidget(self.build_tool_page("面具/检测", [
            ("自动安装环境检测软件", "#FF00FF", get_path("assets/logos/iconic_round.png"), self.install_environment_apks),
            ("一键Alpha完美环境", "#FF00FF", get_path("assets/logos/iconic_round.png"), self.install_alpha_apks),
            ("发送Alpha过环境文件", "#FF00FF", get_path("assets/logos/iconic_round.png"), self.send_al_environment_files),
            ("一键Sukisu完美环境", "#FF00FF", get_path("assets/logos/iconic_round.png"), self.install_sukisu_apks),
            ("发送Sukisu过环境文件", "#FF00FF", get_path("assets/logos/iconic_round.png"), self.send_su_environment_files),
            (" 常用APP", "#FF00FF", get_path("assets/logos/iconic_round.png"), self.install_root_apks),
        ]))

        self.stacked_widget.addWidget(self.build_tool_page("电脑脚本", [
            ("腾讯ACE一键根除", "#DE3163", get_path("assets/logos/Uninstall_ACE.png"), self.Uninstall_ACE),
            ("激活WIN10/WIN11正版", "#DE3163", get_path("assets/logos/win11.png"), self.windows_key),
            ("F1禁止跳Edge浏览器", "#DE3163", get_path("assets/logos/edge_fk.png"), self.prevent_F1),
            ("还原win10右键菜单", "#DE3163", get_path("assets/logos/win10_black.png"), self.win10_menu),
            ("还原win11右键菜单", "#DE3163", get_path("assets/logos/win11_black.png"), self.win11_menu),
            ("资源管理器精简六项隐藏", "#DE3163", get_path("assets/logos/explorer_hide"), self.six_class_hide),
            ("资源管理器精简六项恢复", "#DE3163", get_path("assets/logos/explorer_hide_cancel"),self.six_class_hide_cancel),
            ("资源管理器删除广告", "#DE3163", get_path("assets/logos/delete.png"), self.explorer_clean),
        ]))

        self.stacked_widget.addWidget(self.build_tool_page("二进制", [
            ("[工具]HiBitUninstaller", "#FF8800", get_path("assets/logos/others/HiBitUninstaller.png"),self.HiBitUninstaller),
            ("[工具]Geek卸载工具", "#FF8800", get_path("assets/logos/others/Geek.ico"), self.Geek),
            ("[工具]Everything", "#FF8800", get_path("assets/logos/others/Everything64.ico"), self.Everything64),
            ("[工具]Krokiet数据管理", "#FF8800", get_path("assets/logos/others/Krokiet.png"), self.Krokiet),
            ("[工具]磁盘空间分析器", "#FF8800", get_path("assets/logos/others/DiskCheck.png"), self.DiskCheck),
            ("[工具]Wiztree磁盘分析", "#FF8800", get_path("assets/logos/others/WizTree.png"), self.Wiztree),
            ("[工具]空文件删除", "#FF8800", get_path("assets/logos/others/EFN.png"), self.EFNdelete),
            ("[工具]RAMMap", "#FF8800", get_path("assets/logos/others/RAMMap.png"), self.RAMMap),
            ("[工具]Windows11轻松设置", "#FF8800", get_path("assets/logos/others/Windows11.ico"), self.win11_settings),
            ("[工具]360驱动大师纯净版", "#FF8800", get_path("assets/logos/others/360driver.ico"), self.driver360),
            ("[工具]驱动精灵标准版", "#FF8800", get_path("assets/logos/others/driverG.ico"), self.driverGenius),
            ("[工具]图标提取转换器", "#FF8800", get_path("assets/logos/others/getico.ico"), self.getico),
            ("[工具]Office激活工具", "#FF8800", get_path("assets/logos/others/Office激活工具.png"), self.OfficeTool),
            ("[静默安装]腾讯桌面管家", "#FF8800", get_path("assets/logos/others/TencentDesktop.ico"), self.TencentDesktop),
            ("[安装包]Steam正版", "#FF8800", get_path("assets/logos/others/steam.png"), self.SteamSetup),
            ("[安装包]python-3.13.4", "#FF8800", get_path("assets/logos/others/python.ico"), self.python3_13_4),
            ("[安装包]jdk-11", "#FF8800", get_path("assets/logos/others/jdk.png"), self.jdk11),
            ("[安装包]jdk-17", "#FF8800", get_path("assets/logos/others/jdk.png"), self.jdk17),
            ("[安装包]WPS无广告版", "#FF8800", get_path("assets/logos/others/wps2023.png"), self.wps2023),
            ("[安装包]Localsend", "#FF8800", get_path("assets/logos/others/LocalSend.ico"), self.localsendWin),
            ("[安装包]Radminlan", "#FF8800", get_path("assets/logos/others/Radminlan.ico"), self.Radminlan),
            ("[安装包]Pycharm可破解版", "#FF8800", get_path("assets/logos/others/pycharm.png"), self.Pycharm),
            ("[安装包]Foxit PDF Editor", "#FF8800", get_path("assets/logos/others/Foxit PDF Editor.png"), self.Foxit_PDF_Editor),
            ("[安装包]微软运行库", "#FF8800", get_path("assets/logos/others/微软常用运行库合集.png"),self.MicrosoftRunLibrary),
            ("[安装包]UU加速器", "#FF8800", get_path("assets/logos/others/UU加速器.png"), self.UU_VPN),
            ("[安装包]ToDesk", "#FF8800", get_path("assets/logos/others/ToDesk.png"), self.ToDesk),
            ("[安装包]JiJiDown", "#FF8800", get_path("assets/logos/others/JiJiDown.png"), self.JiJiDown),
        ]))

        self.stacked_widget.addWidget(self.build_tool_page("其他", [
            ("软件中心", "#FF00FF", get_path("assets/logos/boss.png"), self.SoftWareStore),
            ("清理本软件缓存", "#FF00FF", get_path("assets/logos/boss2.png"), self.del_cache),
            ("分券工具", "#FF00FF", get_path("assets/logos/boss3.png"), self.Open_FileMergeSplit),
            ('指定文件夹搜索文本',"#FF00FF", get_path("assets/logos/search.png"), self.open_file_searcher),
            ("Hash+MD5重复清理", "#FF00FF", get_path("assets/logos/garbage_truck_recycling.png"), self.open_hash_md5_tool),
            ("安装李跳跳并发送配置文件", "#FF00FF", get_path("assets/logos/Leetiaotiao.png"), self.Leetiaotiao),
        ]))

        self.stacked_widget.addWidget(self.build_tool_page("图片", [
            (" 台式CPU天梯图", "#8d39e8", get_path("assets/logos/cpu.png"), self.show_CPU),
            (" 台式显卡天梯图", "#8d39e8", get_path("assets/logos/gpu.png"), self.show_GPU),
            (" 笔记本CPU天梯图", "#8d39e8", get_path("assets/logos/cpu_m.png"), self.show_CPUm),
            (" 笔记本显卡天梯图", "#8d39e8", get_path("assets/logos/gpu_m.png"), self.show_GPUm),
        ]))

        content_layout.addWidget(self.category_list)
        content_layout.addWidget(self.stacked_widget)
        main_layout.addWidget(content)
        QTimer.singleShot(0, self._reset_current_page_scroll)

    def build_tool_page(self, title, tool_list):
        """
        创建一个工具页面，每项包含图标+文字按钮
        格式: (按钮文本, 字体颜色, 图标路径, 回调函数)
        """
        page = QWidget()
        main_layout = QVBoxLayout(page)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 创建滚动区域
        scroll = NoHorizontalScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # 禁用水平滚动条
        # 这里加滚动条策略
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        hbar = scroll.horizontalScrollBar()
        hbar.setEnabled(False)
        hbar.rangeChanged.connect(lambda _min, _max, bar=hbar: bar.setValue(0))
        hbar.valueChanged.connect(lambda value, bar=hbar: bar.setValue(0) if value != 0 else None)

        # 如果想限制宽度防止布局撑开
        scroll.setFixedWidth(250)  # 根据你的左侧菜单实际宽度调整
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: #F6F6F6;
                width: 8px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #CCCCCC;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: none;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
        """)

        # 创建内容容器
        content = QWidget()
        content.setLayoutDirection(Qt.LeftToRight)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 14, 12, 14)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        for text, color, icon_path, callback in tool_list:
            btn = QPushButton(text)
            btn.setIcon(QIcon(icon_path))
            btn.setIconSize(QSize(35, 35))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: #F0F0F0;
                    border: 1px solid #CCCCCC;
                    border-radius: 5px;
                    padding: 8px 12px;
                    text-align: left;
                    color: {color};
                }}
                QPushButton:hover {{
                    background-color: #E0E0E0;
                }}
            """)
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        layout.addStretch()

        # 设置滚动区域的内容
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        return page

    def switch_page(self, index):
        self.stacked_widget.setCurrentIndex(index)
        QTimer.singleShot(0, self._reset_current_page_scroll)

    def _reset_current_page_scroll(self):
        current_page = self.stacked_widget.currentWidget()
        if not current_page:
            return
        scroll = current_page.findChild(QScrollArea)
        if not scroll:
            return
        scroll.verticalScrollBar().setValue(0)
        scroll.horizontalScrollBar().setValue(0)

    def mousePressEvent(self, event: QMouseEvent):
        # 只有当窗口不是最小化状态时才允许拖动
        cursor_pos = event.position().toPoint()
        if not self.is_minimized and event.button() == Qt.LeftButton and cursor_pos.y() < 40:
            self.old_pos = event.globalPosition().toPoint()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        # 只有当窗口不是最小化状态时才允许拖动
        cursor_pos = event.position().toPoint()
        if not self.is_minimized and event.buttons() == Qt.LeftButton and cursor_pos.y() < 40:
            global_pos = event.globalPosition().toPoint()
            delta = global_pos - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = global_pos
            event.accept()

    def changeEvent(self, event):
        # 处理窗口状态变化事件
        if event.type() == QEvent.Type.WindowStateChange:
            self.is_minimized = self.isMinimized()
        super().changeEvent(event)



# ================== 导入模块（不使用 *） ==================
import libs.Android as android
import libs.Show_img as show_img
import libs.FileMergeSplit as fms
import libs.DeepSearch as ds
import libs.SoftWareStore as store
import libs.Cloud_Installation_Service as cloud
import libs.HashMD5Tool as hashmd5
import core_function as core
# ================== 统一绑定表 ==================

BINDINGS = {
    core: [
        'prevent_F1',
        'win10_menu',
        'win11_menu',
        'six_class_hide',
        'six_class_hide_cancel',
        'explorer_clean',
        'win11_settings',
        'del_cache',
        'oneplus_unblock_BL',
        'install_adb_driver',
        'driver360',
        'driverGenius',
        'Everything64',
        'Geek',
        'DiskCheck',
        'getico',
        'Wiztree',
        'SteamSetup',
        'windows_key',
        'EFNdelete',
        'python3_13_4',
        'Krokiet',
        'HiBitUninstaller',
        'OfficeTool',
        'RAMMap',
        'Uninstall_ACE'
    ],
    android:[
        'open_scrcpy',
        'open_adb',
        'backup_IMG',
        'restore_IMG',
        'flash_boot',
        'fastboot_reboot',
        'install_alpha_apks',
        'send_al_environment_files',
        'install_sukisu_apks',
        'send_su_environment_files',
        'install_root_apks',
        'install_environment_apks',
        'adb_reboot',
        'on_choose_devices_clicked',
        'Leetiaotiao'
    ],
    show_img: [
        'show_CPU',
        'show_GPU',
        'show_CPUm',
        'show_GPUm',
    ],
    fms: [
        'Open_FileMergeSplit',
    ],
    ds: [
        'open_file_searcher',
    ],
    hashmd5: [
        'open_hash_md5_tool',
    ],
    store: [
        'SoftWareStore',
    ],
    cloud: [
        'jdk11',
        'jdk17',
        'localsendWin',
        'Radminlan',
        'wps2023',
        'TencentDesktop',
        'Pycharm',
        'Foxit_PDF_Editor',
        'MicrosoftRunLibrary',
        'UU_VPN',
        'ToDesk',
        'JiJiDown',
    ],
}
# ================== 执行绑定 ==================
for module, names in BINDINGS.items():
    for name in names:
        if not hasattr(module, name):
            raise AttributeError(
                f'{module.__name__} 中不存在 {name}'
            )
        setattr(MainWindow, name, getattr(module, name))

# 程序启动
if __name__ == '__main__':
    # 检测版本更新
    lanzoui.version_detection("https://sharechain.qq.com/2d73cf70d30cc76567045bb9360d6e39", VERSION, VERSION_CODE())
    # 云控
    lanzoui.total_control()

    # Qt 6 on Windows is DPI-aware by default; keep the native PMv2 behavior.
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        f'®JT.jitian.{VERSION}'
    )
    app = QtWidgets.QApplication(sys.argv)
    app.setFont(build_ui_font())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
