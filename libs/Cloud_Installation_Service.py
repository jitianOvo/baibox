# ==== 标准库 ====
import os,shutil,subprocess
# ==== 第三方库 ====
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar,
)

# ==== 本地模块 ====
import lanzoui
import core_lib
from assets.aira2c.aria2c_api import aria2_download
###################云安装↓#######################
class DownloadThread(QThread):
    progress = Signal(int)  # 百分比
    error = Signal(str)
    finished = Signal()

    def __init__(self, name, exe_name, urls):
        super().__init__()
        self.name = name
        self.exe_name = exe_name
        self.urls = urls

    def run(self):
        try:
            username = os.path.expanduser('~')
            target_dir = os.path.join(username, "PyCache", self.name)
            final_exe_path = os.path.join(username, "PyCache", self.exe_name)

            os.makedirs(target_dir, exist_ok=True)

            total_files = len(self.urls)

            # 真实进度：每个分片用 aria2 的百分比回调，再换算成整体进度
            def make_progress_callback(index):
                def _cb(data):
                    file_percent = data.get("percent", 0) / 100.0
                    overall = int((index + file_percent) / total_files * 100)
                    self.progress.emit(max(0, min(99, overall)))
                return _cb

            for idx, url in enumerate(self.urls):
                direct = lanzoui.get_direct_link(url)
                if not direct:
                    raise RuntimeError(f"蓝奏直链解析失败：{url}")
                aria2_download(
                    url=direct,
                    threads=16,
                    path=target_dir,
                    min_split_size="1M",
                    on_progress=make_progress_callback(idx),
                )

            # 如果只有一个文件，直接重命名，不执行合并
            if total_files == 1:
                # 获取下载的文件（目录中应该只有一个文件）
                files = os.listdir(target_dir)
                if files:
                    downloaded_file = os.path.join(target_dir, files[0])
                    # 确保目标目录存在
                    os.makedirs(os.path.dirname(final_exe_path), exist_ok=True)
                    # 移动文件到最终位置
                    if os.path.exists(final_exe_path):
                        os.remove(final_exe_path)
                    shutil.move(downloaded_file, final_exe_path)
                    print(f"单个文件已移动: {downloaded_file} -> {final_exe_path}")
            else:
                # 多个文件才执行合并
                core_lib.merge_file(target_dir, os.path.join(username, "PyCache"))
                print(f"多个文件已合并到: {final_exe_path}")

            self.progress.emit(100)

            # 删除缓存目录
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
                print(f"缓存目录已删除: {target_dir}")

            # 运行最终文件
            if os.path.exists(final_exe_path):
                try:
                    subprocess.Popen(final_exe_path, shell=True)
                    print(f"程序已启动: {final_exe_path}")
                except Exception as e:
                    print(f"启动程序失败: {e}")
            else:
                print(f"错误：最终文件不存在: {final_exe_path}")

            self.finished.emit()
        except Exception as exc:
            self.error.emit(str(exc))

class InstallDialog(QDialog):
    def __init__(self, name, exe_name, urls, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"安装 {name}")
        self.setFixedSize(450, 150)

        layout = QVBoxLayout(self)
        self.label = QLabel(f"正在安装 {name} ...")
        self.label.setAlignment(Qt.AlignCenter)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)

        # 启动下载线程
        self.thread = DownloadThread(name, exe_name, urls)
        self.thread.progress.connect(self.progress_bar.setValue)
        self.thread.error.connect(self.on_error)
        self.thread.finished.connect(self.on_finished)
        self.thread.start()

    def on_finished(self):
        self.label.setText("安装完成！")
        # 自动关闭窗口
        self.close()

    def on_error(self, msg):
        from PySide6.QtWidgets import QMessageBox
        self.label.setText("安装失败")
        QMessageBox.critical(self, "安装失败", f"下载失败：{msg}")
        self.close()

def install_package(parent, name, exe_name, urls):
    """
    安装统一入口函数：
    parent: 主窗口实例
    name: 软件名称
    exe_name: 最终exe文件名
    urls: 分片下载链接列表
    """
    username = os.path.expanduser('~')
    final_exe_path = os.path.join(username, "PyCache", exe_name)

    # 文件已存在 → 直接运行
    if os.path.exists(final_exe_path):
        subprocess.Popen(final_exe_path, shell=True)
        return

    # 弹出安装进度窗口
    dialog = InstallDialog(name, exe_name, urls, parent=parent)
    dialog.exec()

def jdk11(self):
    install_package(
        self,
        "jdk11",
        "jdk-11.0.15_windows-x64_bin.exe",
        ['https://jitianna.lanzoul.com/iwt9y3421vgd',
         'https://jitianna.lanzoul.com/iHVhb3421zhi']
    )

def jdk17(self):
    install_package(
        self,
        "jdk17",
        "jdk-17.0.2_windows-x64_bin.exe",
        ['https://jitianna.lanzoul.com/ixjtZ341g41a',
         'https://jitianna.lanzoul.com/iXFcN341g6de']
    )

def wps2023(self):
    install_package(
        self,
        "wps2023",
        "【2023版本】WPSOffice无广告自制版.exe",
        ['https://jitianna.lanzoul.com/iDWFV3425ydc',
         'https://jitianna.lanzoul.com/if0Us34261na',
         'https://jitianna.lanzoul.com/iqZiH34264qb',
         'https://jitianna.lanzoul.com/iKqRG34267ib']
    )

def TencentDesktop(self):
    install_package(
        self,
        "腾讯桌面管家",
        "腾讯桌面管家.exe",
        ['https://jitianna.lanzoul.com/ivirZ35dcv2h'])

def localsendWin(self):
    install_package(
        self,
        "localsendWin",
        "LocalSend-1.17.0.exe",
        ['https://jitianna.lanzoul.com/iDM7J35dcw7i'])

def Radminlan(self):
    install_package(
        self,
        "Radminlan",
        "Radmin_LAN.exe",
        ['https://jitianna.lanzoul.com/iTgUC35dcvte'])

def Pycharm(self):
    install_package(
        self,
        "Pycharm",
        "pycharm-community-2023.1.4.exe",
        ['https://jitianna.lanzoul.com/ioBx33g1x6ni',
         'https://jitianna.lanzoul.com/ix8ns3g1xc7i',
         'https://jitianna.lanzoul.com/ig0Re3g1wj3a',
         'https://jitianna.lanzoul.com/ij73k3g1wtmj',
         'https://jitianna.lanzoul.com/iCrkG3g1x24f',
         'https://jitianna.lanzoul.com/ibvja3g1xoad',
         'https://jitianna.lanzoul.com/iZvoU3g1w49g',
         'https://jitianna.lanzoul.com/ijqQN3g1w5zi'
         ])

def Foxit_PDF_Editor(self):
    install_package(
        self,
        "Foxit_PDF_Editor",
        "FoxitPDFEditor_Setup.exe",
        ['https://jitianna.lanzoul.com/iQDDD3g1xukj',
         'https://jitianna.lanzoul.com/iJ80q3g1xzuj',
         'https://jitianna.lanzoul.com/ibMRo3g1y7qd',
         'https://jitianna.lanzoul.com/iylqV3g1yhtg',
         'https://jitianna.lanzoul.com/iw5s73g1wvdc',
         'https://jitianna.lanzoul.com/irCGY3g1x3he',
         'https://jitianna.lanzoul.com/iv2Yq3g1x7xe',
         'https://jitianna.lanzoul.com/iV0MG3g1xdli',
         'https://jitianna.lanzoul.com/i8cEj3g1xjxg',
         'https://jitianna.lanzoul.com/isS573g1xpla',
         'https://jitianna.lanzoul.com/ihFJO3g1w9re',
         'https://jitianna.lanzoul.com/ifWxZ3g1wnta',
         ])

def MicrosoftRunLibrary(self):
    install_package(
        self,
        "MicrosoftRunLibrary",
        "微软常用运行库合集 2025.11.24.exe",
        ['https://jitianna.lanzoul.com/imHS83g26lqf']
    )

def UU_VPN(self):
    install_package(
        self,
        "UU加速器",
        "UU加速器.exe",
        ['https://jitianna.lanzoul.com/ixrlM3g1ylab']
    )



def JiJiDown(self):
    install_package(
        self,
        "JiJiDown",
        "JiJiDown_Setup.exe",
        ['https://jitianna.lanzoul.com/iHn4J3g26sab']
    )

def ToDesk(self):
    install_package(
        self,
        "ToDesk",
        "ToDesk_Setup.exe",
        ['https://jitianna.lanzoul.com/i9YS73g26vhg']
    )
