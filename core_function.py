import ctypes
import os
import shutil
import subprocess
import sys
import winreg
from tkinter import messagebox
from PySide6.QtWidgets import (QMessageBox)

from core_lib import get_path

def windows_key(self):
    # 激活正版
    # subprocess.Popen(['cmd.exe', '/k', get_path("tools/一键激活win10和win11正版.bat")],creationflags=subprocess.CREATE_NEW_CONSOLE)
    print("正在开始 Windows 10-11 激活...")

    # 步骤 1：输入产品密钥
    print("步骤 1：输入产品密钥")
    os.system('slmgr /ipk W269N-WFGWX-YVC9B-4J6C9-T83GX')
    print("产品密钥已输入，等待弹出提示窗口...")

    # 步骤 2：设置 KMS 服务器
    print("步骤 2：设置 KMS 服务器")
    os.system('slmgr /skms kms.loli.best')
    print("KMS 服务器已设置，等待弹出提示窗口...")

    # 步骤 3：激活系统
    print("步骤 3：激活系统")
    os.system('slmgr /ato')
    print("激活完成，等待弹出提示窗口显示成功激活！")

    input("按任意键继续...")

def prevent_F1(self):
    # subprocess.Popen(['cmd.exe', '/k', get_path("tools/F1禁止跳Edge浏览器.bat")],creationflags=subprocess.CREATE_NEW_CONSOLE)
    helppane_path = r"C:\Windows\HelpPane.exe"
    if os.path.exists(helppane_path):
        print("Found HelpPane.exe, attempting to delete...")

        # 取得所有权
        subprocess.run(["takeown", "/f", helppane_path, "/a"], shell=True)

        # 修改权限（拒绝当前用户访问）
        username = os.getlogin()
        subprocess.run(["icacls", helppane_path, "/deny", f"{username}:F"], shell=True)

        # 强制删除
        try:
            os.remove(helppane_path)
        except PermissionError:
            # 如果直接删不掉，尝试用 del 命令
            subprocess.run(["del", "/f", "/q", helppane_path], shell=True)

        # 检查是否删除成功
        if not os.path.exists(helppane_path):
            print("HelpPane.exe has been deleted.")
        else:
            print("Failed to delete HelpPane.exe.")
    else:
        print("HelpPane.exe not found.")

def win10_menu(self):
    subprocess.Popen(['cmd.exe', '/k', get_path("tools/修改win10菜单.bat")],
                     creationflags=subprocess.CREATE_NEW_CONSOLE)
    print("正在恢复 Win10 右键菜单...")

    # 添加注册表项
    subprocess.run([
        "reg", "add",
        r"HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32",
        "/f", "/ve"
    ], shell=True)

    # 重启资源管理器
    subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], shell=True)
    os.startfile("explorer.exe")

    print("Win10 右键菜单恢复完成！")

def win11_menu(self):
    # subprocess.Popen(['cmd.exe', '/k', get_path("tools/还原win11右键菜单.bat")],creationflags=subprocess.CREATE_NEW_CONSOLE)
    print("正在恢复 Win11 右键菜单...")

    # 删除注册表项
    subprocess.run([
        "reg", "delete",
        r"HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32",
        "/va", "/f"
    ], shell=True)

    # 重启资源管理器
    subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], shell=True)
    os.startfile("explorer.exe")

    print("Win11 右键菜单恢复完成！")

def six_class_hide(self):
    # subprocess.Popen(['regedit.exe', '/s', get_path("tools/hide.reg")], creationflags=subprocess.CREATE_NEW_CONSOLE, shell=True)
    # 如果不是管理员，先提权
    if not ctypes.windll.shell32.IsUserAnAdmin():
        script = os.path.abspath(__file__)
        params = f'"{script}"'
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        sys.exit(0)  # 原进程退出，让提升后的进程执行

    # 到这里说明已经是管理员
    NAMESPACE_SUBKEYS = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace\{f86fa3ab-70d2-4fc7-9c99-fcbf05467f3a}",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace\{d3162b92-9365-467a-956b-92703aca08af}",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace\{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace\{3dfdf296-dbec-4fb4-81d1-6a3438bcf4de}",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace\{088e3905-0323-4b02-9826-5d99428e115f}",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace\{24ad3ad4-a569-4530-98e1-ab02f9417aa8}",
    ]

    for subkey in NAMESPACE_SUBKEYS:
        try:
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, subkey)
            print(f"已删除 {subkey}")
        except FileNotFoundError:
            print(f"键不存在，无需删除 {subkey}")
        except PermissionError:
            print(f"权限不足，无法删除 {subkey}（需要管理员权限）")
        except OSError as e:
            # 有些键下可能还有子键，需要用 DeleteKeyEx 或递归删除
            print(f"删除 {subkey} 失败：{e}")

    QMessageBox.information(None, "提示", "隐藏成功！")

def six_class_hide_cancel(self):
    # subprocess.Popen(['regedit.exe', '/s', get_path("tools/hide_cancel.reg")], creationflags=subprocess.CREATE_NEW_CONSOLE, shell=True)
    # 检查是否管理员
    if not ctypes.windll.shell32.IsUserAnAdmin():
        # 提权并重启自己
        script = os.path.abspath(__file__)
        params = f'"{script}"'
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
        sys.exit(0)  # 原进程退出，让提升后的进程执行
    # 到这里说明已经是管理员
    NAMESPACE_SUBKEYS = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace\{f86fa3ab-70d2-4fc7-9c99-fcbf05467f3a}",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace\{d3162b92-9365-467a-956b-92703aca08af}",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace\{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace\{3dfdf296-dbec-4fb4-81d1-6a3438bcf4de}",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace\{088e3905-0323-4b02-9826-5d99428e115f}",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace\{24ad3ad4-a569-4530-98e1-ab02f9417aa8}",
    ]
    for subkey in NAMESPACE_SUBKEYS:
        try:
            with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, subkey) as key:
                print(f"已恢复 {subkey}")
        except PermissionError:
            print(f"权限不足，无法恢复 {subkey}（需要管理员权限）")
        except Exception as e:
            print(f"恢复 {subkey} 失败：{e}")
    QMessageBox.information(None, "提示", "取消隐藏成功！")

def explorer_clean(self,namespace_subkey: str = r"Software\Microsoft\Windows\CurrentVersion\Explorer\MyComputer\NameSpace") -> int:
    """
    删除 HKCU\\...\\MyComputer\\NameSpace 下形如 {GUID} 的子键。
    如果命令行参数包含 --dry-run 或 -n，则进入模拟模式。
    :param namespace_subkey: 要清理的注册表路径。
    :return: 实际删除的项数（dry-run 时返回将被删除的数量）。
    """
    # 在函数内部自动解析命令行参数
    dry_run = ("--dry-run" in sys.argv) or ("-n" in sys.argv)

    print()
    print("正在运行：超级白工具箱 - 资源管理器删除广告")
    print("来源键：HKCU\\" + namespace_subkey)
    print("模式：", "DRY RUN (模拟)" if dry_run else "实际删除")
    print()

    deleted = 0
    to_delete = []

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, namespace_subkey, 0, winreg.KEY_READ) as parent:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(parent, i)
                    i += 1
                    if name.startswith("{") and name.endswith("}"):
                        to_delete.append(name)
                except OSError:
                    break
    except FileNotFoundError:
        print("未找到目标注册表路径，可能已经没有需要清理的项。")
        return 0

    if not to_delete:
        print("没有发现符合模式的 GUID 项，清理结束。")
        return 0

    for guid in to_delete:
        full = namespace_subkey + "\\" + guid
        if dry_run:
            print("[DRY RUN] 将删除：", full)
        else:
            print("正在删除：", full)
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, full)
                deleted += 1
            except Exception as e:
                print("  -> 删除失败：", e)

    if dry_run:
        print(f"\nDRY RUN 完成。共计 {len(to_delete)} 项将被删除。")
        return len(to_delete)
    else:
        print(f"\n清理完成。成功删除 {deleted} 项（共尝试 {len(to_delete)} 项）。")
        return deleted

def install_adb_driver(self):
    subprocess.Popen(get_path('tools/adb-fastboot/adb驱动.exe'), shell=True)

def oneplus_unblock_BL(self):
    subprocess.Popen(get_path('tools/adb-fastboot/一加一键解锁bl.exe'), shell=True)

# 其他区
def win11_settings(self):
    subprocess.Popen(get_path('tools/bin/Windows11轻松设置/Windows11轻松设置.exe'), shell=True)

def driver360(self):
    subprocess.Popen(get_path('tools/bin/360驱动大师纯净版-2.0.0.1970-绿色单文件.exe'), shell=True)

def driverGenius(self):
    subprocess.Popen(get_path('tools/bin/驱动精灵标准版-9.70.0.104-纯净版绿色单文件.exe'), shell=True)

def Everything64(self):
    subprocess.Popen(get_path('tools/bin/Everything64.exe'), shell=True)

def Geek(self):
    subprocess.Popen(get_path('tools/bin/Geek.exe'), shell=True)

def DiskCheck(self):
    subprocess.Popen(get_path('tools/bin/磁盘空间分析器.exe'), shell=True)

def Wiztree(self):
    ctypes.windll.shell32.ShellExecuteW(None, "runas", get_path('tools/bin/Wiztree_4_28/WizTree.exe'), "", None, 1)

def getico(self):
    subprocess.Popen(get_path('tools/bin/图标提取转换器(Quick Any2Ico)3.5.0.0汉化版.exe'), shell=True)

def python3_13_4(self):
    subprocess.Popen(get_path('tools/bin/python-3.13.4-amd64.exe'), shell=True)

def EFNdelete(self):
    subprocess.Popen(get_path('tools/bin/EmptyFolderNuker.chs空文件删除.exe'), shell=True)

def SteamSetup(self):
    subprocess.Popen(get_path('tools/bin/SteamSetup.exe'), shell=True)

click_times = 0

def del_cache(self):
    global click_times
    click_times += 1
    if os.path.exists(os.path.join(os.path.expanduser('~'), "PyCache")):
        shutil.rmtree(os.path.join(os.path.expanduser('~'), "PyCache"))
        messagebox.showinfo('提示', '已清理完毕!')
    else:
        if click_times <= 3:
            messagebox.showinfo('别点了', '没了哥们儿 你刚清过啊')
        elif click_times <= 8:
            messagebox.showinfo('还点?', '没了啊,你听不懂吗')
        elif click_times <= 15:
            messagebox.showinfo('你点个鸡毛啊', '我*****你大爷!真没事干了你')
        elif click_times <= 20:
            messagebox.showinfo('那你继续', '你真无聊,不理你了')
        elif click_times <= 25:
            pass
        elif click_times >= 30 and click_times <= 35:
            messagebox.showinfo('转人工', '666 那我问你 你是人吗?')
        elif click_times <= 36:
            messagebox.showinfo('快点继续点', '很难想象你是个人类')
        elif click_times <= 50:
            messagebox.showinfo('你会放弃的', f'很难想象你是个人类+{click_times - 36}')
        elif click_times == 51:
            messagebox.showinfo('我认输', '你无敌了孩子 投了投了,下一把,别折磨我了求你了')

def Krokiet(self):
    subprocess.Popen(get_path('tools/bin/Krokiet10.0.exe'), shell=True)

def HiBitUninstaller(self):
    subprocess.Popen(get_path('tools/bin/HiBitUninstaller-v3.2.70-CN'), shell=True)

def OfficeTool(self):
    subprocess.Popen(get_path('tools/bin/Office激活工具_KMS_v42.3.0.exe'), shell=True)

def RAMMap(self):
    subprocess.Popen(get_path('tools/bin/RAMMap64.exe'), shell=True)

def fuckAce(self):
    path = get_path(r"tools/bin/ACE Kill 1.0.5/ACE kill启动.bat")
    ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",   # 请求管理员
        path,
        None,
        None,
        1
    )