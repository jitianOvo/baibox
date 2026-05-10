import os
import subprocess
from core_lib import get_path
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import (
    QLabel, QMessageBox, QListWidget, QListWidgetItem, QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QCheckBox, QPushButton, QScrollArea
)
from PySide6 import QtWidgets, QtGui, QtCore
# 窗口类

# 镜像选择窗口
class CheckListDialog(QDialog):
    def __init__(self, parent=None, data_list=None, title="请选择镜像文件", font_size=9):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(500, 400)

        # 自动继承父窗口图标
        if parent and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())

        self.data_list = data_list or []
        self.vars_list = []
        self.columns = 4  # 固定4列
        self.choose = []  # 勾选结果
        self.result = False  # 返回 True/False

        main_layout = QVBoxLayout(self)

        # 显示总条目数量
        self.label_count = QLabel(f"总条目: {len(self.data_list)}")
        main_layout.addWidget(self.label_count)

        # 字体设置
        self.font = QFont()
        self.font.setPointSize(font_size)

        # 顶部快捷按钮
        btn_layout = QHBoxLayout()
        btn_select_all = QPushButton("全选")
        btn_select_all.setFont(self.font)
        btn_select_all.setMinimumHeight(25)
        btn_select_all.clicked.connect(self.select_all)

        btn_invert = QPushButton("反选")
        btn_invert.setFont(self.font)
        btn_invert.setMinimumHeight(25)
        btn_invert.clicked.connect(self.invert_selection)

        btn_clear = QPushButton("全取消")
        btn_clear.setFont(self.font)
        btn_clear.setMinimumHeight(25)
        btn_clear.clicked.connect(self.clear_all)

        btn_layout.addWidget(btn_select_all)
        btn_layout.addWidget(btn_invert)
        btn_layout.addWidget(btn_clear)
        main_layout.addLayout(btn_layout)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QGridLayout(scroll_content)
        scroll_layout.setSpacing(4)  # 间距小
        scroll_layout.setContentsMargins(4, 4, 4, 4)

        # 添加checkbox到网格布局
        for index, item in enumerate(self.data_list):
            chk = QCheckBox(item)
            chk.setFont(self.font)
            chk.setStyleSheet("QCheckBox::indicator { width: 16px; height: 16px; }")  # 勾选框稍小
            chk.setChecked(True)
            row = index // self.columns
            col = index % self.columns
            scroll_layout.addWidget(chk, row, col)
            self.vars_list.append((chk, item))

        scroll_content.setLayout(scroll_layout)
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # 确认和取消按钮
        btn_confirm = QPushButton("确认")
        btn_confirm.setFont(self.font)
        btn_confirm.setMinimumHeight(30)
        btn_confirm.clicked.connect(self.confirm)

        btn_cancel = QPushButton("取消")
        btn_cancel.setFont(self.font)
        btn_cancel.setMinimumHeight(30)
        btn_cancel.clicked.connect(self.cancel)

        btn_bottom_layout = QHBoxLayout()
        btn_bottom_layout.addWidget(btn_confirm)
        btn_bottom_layout.addWidget(btn_cancel)
        main_layout.addLayout(btn_bottom_layout)

        # 弹窗阻塞
        self.exec()

    # 确认
    def confirm(self):
        self.choose = [item for chk, item in self.vars_list if chk.isChecked()]
        self.result = True
        self.accept()

    # 取消
    def cancel(self):
        self.choose = []
        self.result = False
        self.reject()

    # 快捷功能
    def select_all(self):
        for chk, _ in self.vars_list:
            chk.setChecked(True)

    def invert_selection(self):
        for chk, _ in self.vars_list:
            chk.setChecked(not chk.isChecked())

    def clear_all(self):
        for chk, _ in self.vars_list:
            chk.setChecked(False)
# 安装apk窗口
class ApkInstallWindow(QDialog):
        def __init__(self, apk_dir, adb_path, preselected=None):
            super().__init__()
            self.setWindowTitle("安装 APK")
            self.resize(350, 420)
            self.apk_dir = apk_dir
            self.adb_path = adb_path
            self.preselected = set(os.path.abspath(p) for p in (preselected or []))
            self.setWindowIcon(QIcon(get_path('assets/logos/iconic.ico')))
            self.apk_files = self.get_all_apk_files()
            self.layout = QVBoxLayout()
            self.list_widget = QListWidget()
            self.checkbox_map = {}

            for apk_path in self.apk_files:
                rel_path = os.path.relpath(apk_path, self.apk_dir)
                item = QListWidgetItem()
                checkbox = QCheckBox(rel_path)
                if os.path.abspath(apk_path) in self.preselected:
                    checkbox.setChecked(True)
                item.setSizeHint(checkbox.sizeHint())
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, checkbox)
                self.checkbox_map[apk_path] = checkbox

            self.layout.addWidget(QLabel("请选择要安装的 APK 文件："))
            self.layout.addWidget(self.list_widget)

            btn_layout = QHBoxLayout()
            self.install_btn = QPushButton("安装选中 APK")
            self.install_btn.clicked.connect(self.install_selected_apks)
            btn_layout.addWidget(self.install_btn)

            self.layout.addLayout(btn_layout)
            self.setLayout(self.layout)

        def get_all_apk_files(self):
            apk_list = []
            for root, _, files in os.walk(self.apk_dir):
                for f in files:
                    if f.endswith(".apk"):
                        apk_list.append(os.path.join(root, f))
            return apk_list

        def install_selected_apks(self):
            selected_apks = [path for path, checkbox in self.checkbox_map.items() if checkbox.isChecked()]
            if not selected_apks:
                print("未选择任何 APK。")
                return
            for apk in selected_apks:
                print(f"安装中: {apk}")
                subprocess.run([self.adb_path, "install", "-r", apk], shell=True)
            self.close()
# 发送文件窗口
class FileSendWindow(QDialog):
        def __init__(self, file_dir, adb_path, preselected=None):
            super().__init__()
            self.setWindowTitle("发送文件到手机 Download 文件夹")
            self.resize(350, 420)
            self.file_dir = file_dir
            self.adb_path = adb_path
            self.preselected = set(os.path.abspath(p) for p in (preselected or []))
            self.setWindowIcon(QIcon(get_path('assets/logos/iconic.ico')))
            self.file_list = self.get_all_target_files()
            self.layout = QVBoxLayout()
            self.list_widget = QListWidget()
            self.checkbox_map = {}

            for file_path in self.file_list:
                rel_path = os.path.relpath(file_path, self.file_dir)
                item = QListWidgetItem()
                checkbox = QCheckBox(rel_path)
                if os.path.abspath(file_path) in self.preselected:
                    checkbox.setChecked(True)
                item.setSizeHint(checkbox.sizeHint())
                self.list_widget.addItem(item)
                self.list_widget.setItemWidget(item, checkbox)
                self.checkbox_map[file_path] = checkbox

            self.layout.addWidget(QLabel("请选择要发送的文件："))
            self.layout.addWidget(self.list_widget)

            btn_layout = QHBoxLayout()
            self.send_btn = QPushButton("发送选中文件")
            self.send_btn.clicked.connect(self.send_selected_files)
            btn_layout.addWidget(self.send_btn)

            self.layout.addLayout(btn_layout)
            self.setLayout(self.layout)

        def get_all_target_files(self):
            """扫描目录，获取指定类型文件"""
            allowed_exts = (".zip", ".sh", ".txt", ".json", ".png", ".jpg")
            target_list = []
            for root, _, files in os.walk(self.file_dir):
                for f in files:
                    if f.lower().endswith(allowed_exts):
                        target_list.append(os.path.join(root, f))
            return target_list

        def send_selected_files(self):
            selected_files = [path for path, checkbox in self.checkbox_map.items() if checkbox.isChecked()]
            if not selected_files:
                print("未选择任何文件。")
                return
            for file_path in selected_files:
                remote_path = f"/sdcard/Download/{os.path.basename(file_path)}"
                print(f"发送中: {file_path} -> {remote_path}")
                subprocess.run(f'"{self.adb_path}" push "{file_path}" "{remote_path}"', shell=True)
            QMessageBox.information(self, "完成", "选中文件已发送到手机 Download 文件夹。")
            self.close()
# 二次确认窗口
class ConfirmDialog(QtWidgets.QMessageBox):
    def __init__(self, parent=None, title="确认", text="是否继续？"):
        super().__init__(parent)

        # 启用高DPI缩放和平滑图标
        set_qt_application_attribute("AA_EnableHighDpiScaling")
        set_qt_application_attribute("AA_UseHighDpiPixmaps")

        self.setWindowTitle(title)
        self.setText(text)
        self.setIcon(QtWidgets.QMessageBox.Question)

        # 设置字体
        font = QtGui.QFont("微软雅黑", 11)
        self.setFont(font)

        # 自定义按钮
        self.btn_yes = self.addButton("是", QtWidgets.QMessageBox.AcceptRole)
        self.btn_cancel = self.addButton("取消", QtWidgets.QMessageBox.RejectRole)

        # 美化按钮
        self._style_buttons()

        # 设置圆角和阴影
        self.setStyleSheet("""
            QMessageBox {
                border-radius: 12px;
            }
            QLabel {
                padding: 10px;
            }
        """)

    def _style_buttons(self):
        # 设置按钮样式
        for btn in [self.btn_yes, self.btn_cancel]:
            btn.setStyleSheet("""
                QPushButton {
                    min-width: 80px;
                    min-height: 32px;
                    border-radius: 6px;
                    padding: 5px 15px;
                    background-color: #4CAF50;
                    color: white;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #45a049;
                }
                QPushButton:pressed {
                    background-color: #3e8e41;
                }
            """)

        # 取消按钮颜色区分
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                min-width: 80px;
                min-height: 32px;
                border-radius: 6px;
                padding: 5px 15px;
                background-color: #f44336;
                color: white;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #e53935;
            }
            QPushButton:pressed {
                background-color: #d32f2f;
            }
        """)

    def exec_confirm(self):
        self.exec()
        return self.clickedButton() == self.btn_yes



def open_scrcpy(self):
    dialog = QDialog(self)
    dialog.setWindowTitle("投屏方式选择")

    if self and not self.windowIcon().isNull():
        dialog.setWindowIcon(self.windowIcon())

    screen = dialog.screen() or QtWidgets.QApplication.primaryScreen()
    if screen:
        available = screen.availableGeometry()
        scale = min(max(available.height() / 1080, 0.85), 1.05)
        dialog_width = max(320, min(420, available.width() - 120))
        dialog_height = max(220, min(280, available.height() - 140))
    else:
        scale = 1.0
        dialog_width, dialog_height = 360, 240

    dialog.resize(dialog_width, dialog_height)
    dialog.setMinimumSize(320, 220)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)

    title = QLabel("请选择投屏方式:")
    title.setFont(QFont("Microsoft YaHei UI", max(13, int(round(15 * scale))), QFont.Bold))
    title.setWordWrap(True)
    title.setStyleSheet("margin-bottom: 6px;")
    layout.addWidget(title)

    button_font = QFont("Microsoft YaHei UI", max(11, int(round(13 * scale))))
    button_min_height = max(48, int(round(54 * scale)))
    button_style = """
    QPushButton {
        background-color: #4CAF50;
        border: none;
        color: white;
        padding: 8px 18px;
        margin: 4px 0px;
        border-radius: 8px;
    }
    QPushButton:hover {
        background-color: #45a049;
    }
    """

    def run_scrcpy(extra_args=None):
        base_dir = os.getcwd()
        devices_path = os.path.join(base_dir, "data", "cache", "my_devices.txt")

        cmd = [get_path("tools/bin/scrcpy-win64-v3.3.4/scrcpy.exe")]

        if os.path.exists(devices_path):
            with open(devices_path, "r", encoding="utf-8") as f:
                my_device = f.read().strip()
                cmd += ["-s", my_device]

        if extra_args:
            cmd += extra_args

        subprocess.Popen(cmd)

    # 按钮1
    button1 = QPushButton("有线投屏（带音频）")
    button1.setFont(button_font)
    button1.setMinimumHeight(button_min_height)
    button1.setCursor(Qt.PointingHandCursor)
    button1.setStyleSheet(button_style)
    button1.clicked.connect(lambda: run_scrcpy())
    layout.addWidget(button1)

    # 按钮2
    button2 = QPushButton("有线投屏（不投音频）")
    button2.setFont(button_font)
    button2.setMinimumHeight(button_min_height)
    button2.setCursor(Qt.PointingHandCursor)
    button2.setStyleSheet(button_style)
    button2.clicked.connect(lambda: run_scrcpy(["--no-audio"]))
    layout.addWidget(button2)

    layout.addStretch()

    dialog.exec()

def on_choose_devices_clicked(self):
    adb_get_devices()  # 每次点击按钮时动态刷新

    base_dir = os.getcwd()
    data_dir = os.path.join(base_dir, "data")
    devices_path = os.path.join(data_dir, "cache", "devices.txt")
    my_devices_path = os.path.join(data_dir, "cache", "my_devices.txt")

    # ===== 读取 devices.txt =====
    if not os.path.exists(devices_path):
        choice = dialog = ConfirmDialog(self, "错误", "吊毛，我没检测到你插手机了，快检查一下~").exec_confirm()
        if choice:
            import requests
            headers = {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "DNT": "1",
                "Pragma": "no-cache",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0",
                "sec-ch-ua": "\"Microsoft Edge\";v=\"143\", \"Chromium\";v=\"143\", \"Not A(Brand\";v=\"24\"",
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": "\"Windows\""
            }
            cookies = {
                "user_locale": "zh-CN",
                "oschina_new_user": "false",
                "Hm_lvt_24f17767262929947cc3631f99bfd274": "1763381080",
                "yp_riddler_id": "4d463928-9cb1-4f32-b531-babcfad7966e",
                "remove_bulletin": "gitee-maintain-1762842849",
                "remote_way": "http",
                "abymg_id": "1_2A3C5E6E3DA15CD3087155164604DC6CC6754C3C55963892C9EC260AC783EA08",
                "BEC": "4431548549a19240b277aa1ec69b0837",
                "sl-session": "AkFfQaceYWl6X4OOcvk+Wg==",
                "sl-challenge-server": "cloud",
                "user_return_to_0": "%2F",
                "tz": "Asia%2FShanghai",
                "remember_user_token": "BAhbCFsGaQPYc%2FpJIiIkMmEkMTAkbFkvLlU4ZDhKNXZ0SmpYOWdRWkk5LgY6BkVUSSIXMTc2Nzg4NjEzMC42MTMzNjExBjsARg%3D%3D--fd016cfd0f5aeb634aa84889139b3d976fe8eb6c",
                "gitee_user": "true",
                "csrf_token": "zQ%2FgBvbzoX9GNWFjVTIg1FDgqh777XMdlksvY%2FRrmsdPvrcAbwPCLbQScJ5DSS%2BbqX5Jtp5KJ6Xi%2FnQV%2FUXedg%3D%3D",
                "gitee-session-n": "RFpuZ3FieEpnRmNXVm9VWUV3UDM1bzJwc1U5YW1EMEdOTitwR1N6QWQrZDIzbm0xa21tbGo4M2ttMHRtYkltblV3eklLM3Q1RU9mRW1xc2o3Q2ZxRk03dmZJM0s2RlkyUEFyVERUVXd5TlNZNVN3NGJJN1JXZ1BnQ3JMWCs2bkdoSUdSemt4NmlsOGk1QzNJL280cktGdUI1K25YMDQ2MUY2QVpwYzYyeXE1ejhqdFdFcUV6dkdSSnJPb0ZLSzNQRGtMUTZSdCt4WkhQSDJZNU83QWVQSE9FRSsxRlNXVVBXcUZYOExQV3A3OTJrY201dm9nd2R5ODdlbGg1eVZRZ0pQUDNTbHR3cTM0L0N3Vjd2NkFrNXNobWZxVVRMYlRJY05GTnJJeVFiR1NTNDljY0tHTUhQazJkT2pyMjlKeFhoejcrU0RSeXJ2WmtMU3lXNjIxSVFFUUhOaUlTZFpHNzV1ZFYrRTZSVkw0Nm5JNTF2Qlpqa2NxbjJKS2pGRzEzUmtVMUp1TmNXNGtJeGJCL3FKZTlyZ1lPRk9jUzdBZ0JpdkhQbVJJdzVnaEY0c0Z4ek5jYy8yZk15TStHeStONDlmK1JIWlVKVm5YSXlyRjdZcy95aHdRUUxra3FGUU9MZVQwdndUelNTL1NINDQ1KytVQnUxbENNMkVPZElZcys3U0lLNnppeHRzZkJzMGxJazhNYjU0R1R6YVRpWHp5ZUJ6NW14V3JRTzdGN2hQWEYrRXh2MzNsVnQ1YThVVHlKTnBUQjVWVzk2d0Vnd2l4MUF3Z2RoZUYxZkxCQkJOcTdEZ0Q2dGpSUW41Nzk4VVluOHJTcml0Q3dCUW9INHM3Uy0ta0gzbUlQQVJPTDZ3ZDBaZ2pWNjdHdz09--45c70173bd7ed17421ff42d008bf578d60811dc7"
            }
            url = "https://gitee.com/jitianovo/my-server-rp/raw/master/%E6%89%93%E5%BC%80usb%E6%95%99%E5%AD%A6QQ%E5%BD%95%E5%B1%8F20260108230948%20.mp4"

            save_path = os.path.join(os.path.expanduser("~"),'PyCache',"usb.mp4")
            fail_txt = os.path.join(os.path.expanduser("~"),'PyCache',"read.txt")

            # ---------- 情况 1：文件已存在 ----------
            if os.path.exists(save_path):
                print("文件已存在，直接打开视频")
                os.startfile(save_path)
                return

            print("文件不存在，开始下载...")
            try:
                response = requests.get(url, headers=headers, cookies=cookies)
                downloaded = 0
                total = int(response.headers.get("Content-Length", 0))
                with open(save_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if not chunk:
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            print(f"下载中: {downloaded / 1024 / 1024:.2f} MB / {total / 1024 / 1024:.2f} MB", end="\r")

                print("\n下载完成，打开视频")

                os.startfile(save_path)


            # ---------- 情况 3：下载失败 ----------
            except Exception as e:
                print("下载失败:", e)
                print("生成 read.txt")
                with open(fail_txt, "w", encoding="utf-8") as f:
                    f.write(
                        "如何打开USB调试 使用超级白工具箱的投屏或者ADB相关功能\n\n"
                        "第一步：打开【开发者选项】\n\n"
                        "打开 设置\n"
                        "找到 关于手机 / 关于设备\n"
                        "找到 版本号\n"
                        "连续点 7 次版本号\n"
                        "提示：\n"
                        "“您已处于开发者模式”\n\n"
                        "如果要输入锁屏密码，输就是了，别慌。\n\n"
                        "第二步：打开【USB 调试】\n\n"
                        "返回 设置首页\n"
                        "找到 开发者选项\n"
                        "（有的在：设置 → 更多设置 → 开发者选项）\n"
                        "打开 USB 调试\n"
                        "弹窗提示 → 点 确定\n\n"
                        "第三步\n"
                        "用数据线插电脑\n"
                        "下拉手机状态栏，找到 USB 选项\n"
                        "选择 文件传输 / 传输文件 / MTP\n"
                        "手机弹窗询问是否允许 USB 调试 → 勾选 始终允许 → 确定\n\n"
                        "小贴士（避免新手翻车）\n\n"
                        "数据线必须是 支持数据传输 的，不是充电线\n"
                        "USB 模式没切到“传输文件”，电脑可能识别不到\n"
                        "USB 调试没开，电脑无法操作手机文件\n"
                    )
                # 用记事本打开
                os.system(f'notepad "{fail_txt}"')
            return
        else:
            print('取消操作')
            return


    with open(devices_path, "r", encoding="utf-8") as f:
        devices = [line.strip() for line in f if line.strip()]

    if not devices:
        QMessageBox.information(self, "提示", "devices.txt 中没有任何设备")
        return

    # ===== 设备选择对话框 =====
    dialog = QDialog(self)
    dialog.setWindowTitle("选择设备")
    dialog.setFixedSize(360, 300)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(12)

    title = QLabel("请选择要使用的设备：")
    title.setAlignment(Qt.AlignCenter)
    title.setStyleSheet("font-size:16px;font-weight:bold;")
    layout.addWidget(title)

    def choose_device(dev):
        os.makedirs(data_dir, exist_ok=True)
        with open(my_devices_path, "w", encoding="utf-8") as f:
            f.write(dev)
        print(f"[Debug] 当前设备: {dev}")
        QMessageBox.information(self, "完成", f"已选择设备：{dev}")
        dialog.accept()

    # ===== 动态生成按钮 =====
    for dev in devices:
        btn = QPushButton(dev)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                padding: 10px;
                border-radius: 6px;
                background: #F0F0F0;
                border: 1px solid #CCC;
                text-align: center;
            }
            QPushButton:hover {
                background: #E6F0FF;
            }
        """)
        btn.clicked.connect(lambda _, d=dev: choose_device(d))
        layout.addWidget(btn)

    dialog.exec()

def open_adb(self):
    subprocess.Popen(['cmd.exe', '/k', get_path("tools/adb-fastboot/打开CMD命令行.bat")],
                     creationflags=subprocess.CREATE_NEW_CONSOLE)

def backup_IMG(self):
    box = QMessageBox(self)
    box.setWindowTitle("高危功能提示 - 基带备份")
    box.setText("""
    <b>请确认以下事项：</b><br><br>
    • 手机已通过 <b>USB</b> 连接电脑<br>
    • 备份镜像将保存至 <b>D:/backup</b><br><br>
    <b>请选择备份模式：</b><br>
     ①防格机镜像备份（完整）<br>
     ②面具修补还原镜像（部分）
    """)

    box.setStyleSheet("""
    QMessageBox {
        font-family: "Microsoft YaHei UI";
        font-size: 13px;
    }
    QPushButton {
        font-size: 12px;
        padding: 6px 16px;
    }
    """)
    btn_full = box.addButton("防格机备份", QMessageBox.AcceptRole)
    btn_patch = box.addButton("面具修补备份", QMessageBox.ActionRole)
    btn_cancel = box.addButton("取消", QMessageBox.RejectRole)
    box.exec()
    clicked = box.clickedButton()

    #使用此函数先进行设备有无连接的判断
    info = adb_get_devices()
    if info == None and not clicked == btn_cancel: # 当点击A/B时出现，C不出现
        dialog = ConfirmDialog(self,'错误提示','获取设备失败')
        dialog.exec_confirm()
        return -1

    # 路径
    backup_dir = "D:/backup"
    os.makedirs(backup_dir, exist_ok=True)
    #兼容联发科骁龙双cpu
    cpu = adb_commander(['shell', 'su -c', '"cd /dev/block/bootdevice/by-name && ls -1"'])
    if not cpu == None:
        byname = 'bootdevice/by-name'
    else:
        byname = 'by-name'

    if clicked == btn_full: # 基带1
        result = adb_commander(['shell', 'su -c', f'"cd /dev/block/{byname} && ls -1"'])  # 得到基带目录名
        result = result.strip().splitlines()
        # 要删除的元素
        to_remove = ['bootloader1','bootloader2','userdata','sda','sdb','sdc']
        # 删除操作
        result = [x for x in result if x not in to_remove]


        # 弹出子窗口选择
        windows = CheckListDialog(self, result)  # 自动继承父窗口图标
        if windows.result:
            result = windows.choose
            print("已选择刷入镜像", result)
            # 创建临时目录
            adb_commander(["shell", "su -c 'mkdir -p /sdcard/tmp'"])
            for file_name in result:
                # dd 备份到手机临时目录
                res = adb_commander([
                    "shell",
                    f"su -c 'dd if=/dev/block/{byname}/{file_name} of=/sdcard/tmp/{file_name}.img && echo get_done'"
                ])
                print(f"dd {file_name}:", res)

                # pull 到电脑
                res2 = adb_commander([
                    "pull",
                    f"/sdcard/tmp/{file_name}.img",
                    "D:/backup"
                ])
                print(f"pull {file_name}:", res2)

                # 删除手机临时文件
                res3 = adb_commander([
                    "shell",
                    f"su -c 'rm /sdcard/tmp/{file_name}.img && echo removed_done'"
                ])
                print(f"rm {file_name}:", res3)
            dlg = ConfirmDialog(self, "确认", "备份完毕，请确认！")
            dlg.exec_confirm()



    elif clicked == btn_patch: # 基带2
        files_name = [
            'init_boot_b',
            'boot_b',
            'vendor_boot_b',
            'dtbo_b',
            'vbmeta_system_b',
            'vbmeta_b',
            'vbmeta_vendor_b'
        ]

        # 创建临时目录
        adb_commander(["shell", "su -c 'mkdir -p /sdcard/tmp'"])

        # 循环备份
        for file_name in files_name:
            # dd 备份到手机临时目录
            res = adb_commander([
                "shell",
                f"su -c 'dd if=/dev/block/{byname}/{file_name} of=/sdcard/tmp/{file_name}.img && echo get_done'"
            ])
            print(f"dd {file_name}:", res)

            # pull 到电脑
            res2 = adb_commander([
                "pull",
                f"/sdcard/tmp/{file_name}.img",
                "D:/backup"
            ])
            print(f"pull {file_name}:", res2)

            # 删除手机临时文件
            res3 = adb_commander([
                "shell",
                f"su -c 'rm /sdcard/tmp/{file_name}.img && echo removed_done'"
            ])
            print(f"rm {file_name}:", res3)
        dialog = ConfirmDialog(self, "确认", "面具原镜像备份成功，请确认！").exec_confirm()
        print("面具原镜像备份成功")
    elif clicked == btn_cancel:
        print("已取消操作")


def restore_IMG(self):
    os.makedirs('D:/backup', exist_ok=True)
    img = os.listdir('D:/backup')
    if not img:
        info = ConfirmDialog(self,'错误提示','请把镜像文件放入\nD:/backup')
        info.exec_confirm()
        return
    windows = CheckListDialog(self, img)  # 自动继承父窗口图标
    img = windows.choose
    for i in img:
        name = i.split('.')[0]
        fastboot_commander(f'flash {name} D:/{name}.img')
        print(f"刷入成功{name}") if result else print(f'刷入失败{name}')


def flash_boot(self):
    box = QMessageBox(self)
    box.setWindowTitle("【高危操作】⚠若操作不当将会变砖哦~")
    box.setText(
        "请确保手机处于fastboot模式下\n将镜像文件放入D:/backup\n文件名是init_boot_a/b.img\n请选择刷入分区\n您可以选择init_boot_a或init_boot_b分区\n手动刷入时\n请把有且一个镜像文件放入D:/backup\n文件名就是刷入分区名")
    font = QFont("Microsoft YaHei UI", 12)  # 字体"微软雅黑"，字号12，可改大
    box.setFont(font)
    btn_boot_A = box.addButton("刷入init_boot_a", QMessageBox.ActionRole)
    btn_boot_B = box.addButton("刷入init_boot_b", QMessageBox.ActionRole)
    btn_boot_C = box.addButton("手动刷入", QMessageBox.ActionRole)
    btn_cancel = box.addButton("取消", QMessageBox.RejectRole)
    box.exec()
    clicked = box.clickedButton()
    if clicked == btn_boot_A:
        result = fastboot_commander('flash init_boot_a D:/init_boot_a.img')
        print("刷入成功A") if result else print('刷入失败')
    elif clicked == btn_boot_B:
        result = fastboot_commander('flash init_boot_b D:/init_boot_b.img')
        print("刷入成功B") if result else print('刷入失败')
    elif clicked == btn_boot_C:
        os.makedirs('D:/backup', exist_ok=True)
        path = os.listdir('D:/backup')
        if not path:
            dialog = ConfirmDialog(self,'错误','D:/backup 目录下未发现镜像文件')
            result = dialog.exec_confirm()
            return result
        elif 'img' in path[0] and len(path) == 1:
            name = path[0].split('.')[0]
        else:
            print('D:/img img文件只能为1个')
        result = fastboot_commander(f'flash {name} D:/{name}.img')
        print(f"刷入成功{name}") if result else print(f'刷入失败{name}')
    elif clicked == btn_cancel:
        print("已取消操作")


###################安装apk↓#######################

def install_apks(preselect_list=None):
    dlg = ApkInstallWindow(get_path("tools/android"), get_path("tools/adb-fastboot/adb.exe"), preselect_list)
    dlg.exec()


def install_environment_apks(self):
    install_apks([get_path('tools/android/环境检测/牛头30.apk'),
                  get_path('tools/android/环境检测/橘子检测.apk'),
                  get_path('tools/android/环境检测/Ruru_1.1.1.apk'),
                  get_path('tools/android/环境检测/Momo_4.4.1.apk'),
                  get_path('tools/android/环境检测/Luna_1.4.2.7.apk'),
                  get_path('tools/android/环境检测/Hunter_6.42.apk'),
                  get_path('tools/android/环境检测/放大镜2.1.apk'),
                  get_path('tools/android/环境检测/春秋检测.apk'),
                  get_path('tools/android/环境检测/Applist Detector_2.4.apk')])


def install_alpha_apks(self):
    install_apks([get_path('tools/android/阿尔法环境/Alpha30400.apk'),
                  get_path('tools/android/阿尔法环境/隐藏BL列表.apk'),
                  get_path('tools/android/阿尔法环境/密钥认证修改版.apk'),
                  get_path('tools/android/阿尔法环境/超级用户列表.apk'),
                  get_path('tools/android/阿尔法环境/隐藏应用列表改包名版.apk'),
                  get_path('tools/android/阿尔法环境/MT管理器_2.19.3-clone.apk')])


def install_sukisu_apks(self):
    install_apks([get_path('tools/android/Sukisu环境/Kernel Flasher_1.0.0-alpha21.apk')])


def install_root_apks(self):
    install_apks()


def Leetiaotiao(self):
    install_apks([get_path('tools/android/李跳跳2.2正式版.apk')])


###################发送文件↓#######################
def send_files(preselect_list=None):

    dlg = FileSendWindow(get_path("tools/android"), get_path("tools/adb-fastboot/adb.exe"), preselect_list)
    dlg.exec()


def send_al_environment_files(self):
    send_files([
        get_path('tools/android/过环境文件/Keybox.xml一键更新(1218).sh'),
        get_path('tools/android/过环境文件/隐藏应用列表jitian_11.19.json'),
        get_path('tools/android/过环境文件/阿尔法一键隐藏v5.0(1228).zip')
    ])


def send_su_environment_files(self):
    send_files([
        get_path('tools/android/Sukisu环境/Tricky Store-v1.4.0.zip'),
        get_path('tools/android/Sukisu环境/Tricky Addon - Update Target List-v4.1.zip'),
        get_path('tools/android/Sukisu环境/SUSFS-FOR-KERNELSU-v1.5.2-R23.zip')
    ])


def send_litiaotiao(self):
    send_files([
        get_path('tools/android/李跳跳规则/【推荐】B站热心站友冇名之辈分享的去重规则(890条).txt'),
        get_path('tools/android/李跳跳规则/【精简】常用软件精简规则.txt'),
        get_path('tools/android/李跳跳规则/【更新】Github更新规则，比较多但是可能有重复的.txt')
    ])


####adb-fastboot#########

def adb_get_devices():
    """
    返回devices列表
    把结果写入硬盘，作为选择设备的前置函数
    也可在任意需要使用adb命令前进行设备判断
    """
    listDevices = []

    base_dir = os.getcwd()
    # print('[Debug]',base_dir)
    if "libs" in base_dir:  # 消除路径中的/libs
        base_dir = os.path.dirname(os.getcwd())

    data_dir = os.path.join(base_dir, "data")
    adb_path = os.path.join(base_dir, "tools", "adb-fastboot", 'adb.exe')

    result = subprocess.run(fr"{adb_path} devices", shell=True, encoding='gbk', capture_output=True)
    for line in result.stdout.splitlines()[1:]:  # 处理原始返回结果
        if 'device' in line:
            listDevices.append(line.split('	device')[0])
        if len(listDevices) == 0:  # 如果没有设备
            import shutil  # 初始化检测，如果没有设备把上次的设备文件全部删除
            if os.path.exists(os.path.join(data_dir, "cache")):
                shutil.rmtree(os.path.join(data_dir, "cache"))  # 删除整个文件夹及内容
            return None
    if not os.path.exists(os.path.join(data_dir, "cache")):
        os.mkdir(os.path.join(data_dir, "cache"))
    with open(os.path.join(data_dir, "cache", 'devices.txt'), 'w+', encoding='utf-8') as f:  # 初始化写入本地
        for device in listDevices:
            f.write(device + '\n')
    return listDevices


"""def adb_commander(args):
    if type(args) is not list: # 处理单命令情况
        args = [args]

    base_dir = os.getcwd()
    if "libs" in base_dir:
        base_dir = os.path.dirname(base_dir)

    adb_path = os.path.join(base_dir, "tools", "adb-fastboot", "adb.exe")

    result = subprocess.run(
        [adb_path] + args,
        capture_output=True,
        encoding="gbk"
    )
    return result.stdout if result.stdout else None"""

def adb_commander(args):
    if type(args) is not list:
        args = [args]

    base_dir = os.getcwd()
    if "libs" in base_dir:
        base_dir = os.path.dirname(base_dir)

    adb_path = os.path.join(base_dir, "tools", "adb-fastboot", "adb.exe")

    try:
        result = subprocess.run(
            [adb_path] + args,
            capture_output=True,
            encoding="utf-8",
            errors="ignore"
        )
        return result.stdout
    except Exception as e:
        print("adb_commander 调用失败:", e)
        return subprocess.CompletedProcess([adb_path] + args, returncode=1, stdout="", stderr=str(e))



def fastboot_commander(command):
    base_dir = os.getcwd()
    if "libs" in base_dir:
        base_dir = os.path.dirname(base_dir)

    fastboot_path = os.path.join(
        base_dir, "tools", "adb-fastboot", "fastboot.exe"
    )

    try:
        result = subprocess.run(
            [fastboot_path, command],
            shell=False,
            timeout=0.3,
            capture_output=True,
            encoding="gbk"
        )
        return result.stdout.strip() if result.stdout else None

    except subprocess.TimeoutExpired:
        print("未检测到 fastboot 设备")
        return None


def adb_reboot(self):
    dlg = ConfirmDialog(self, "确认", "是否继续？")
    result = dlg.exec_confirm()
    if result:
        adb_commander('reboot')

def fastboot_reboot(self):
    dlg = ConfirmDialog(self, "确认", "是否继续？")
    result = dlg.exec_confirm()
    if result:
        fastboot_commander('reboot')


def clean_file_dir(dir_path):
    """删除指定目录下的所有文件夹"""
    dirs = adb_commander(["shell", "find", dir_path, "-maxdepth", "1", "-type", "d"]).strip().splitlines()
    for d in dirs:
        if d != dir_path:  # 避免删除根目录
            adb_commander(["shell", "rm", "-rf", f'"{d}"'])
            print(f"已删除目录: {d}")


# ------------------ 主程序 ------------------
if __name__ == "__main__":
    adb_commander(["shell", "find", "/sdcard/", "-maxdepth", "1", "-type", "d"])
    # 示例调用
    #delete_dirs_with_confirmation("/sdcard")

    #print(adb_commander(["shell", "find /sdcard/", "-maxdepth 1", "-type d"]))
