import ctypes
import shutil
import subprocess
import os,sys,winreg
import random
import time
from PySide6.QtWidgets import (QMessageBox, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout)
from tkinter import messagebox
from core_lib import get_path

def windows_key(self):
    if not _confirm_action(self, "操作确认", "将开始 Windows 10/11 正版激活。\n\n该操作会修改系统激活状态，是否继续？"):
        print("已取消激活操作。")
        return
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

def _run_admin_cmd(args):
    """运行系统命令并返回返回码，隐藏命令行窗口"""
    try:
        result = subprocess.run(
            args,
            shell=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return result.returncode
    except Exception as e:
        print("命令执行异常:", args, e)
        return -1


def _confirm_action(self, title, text):
    """电脑脚本通用二次确认弹窗，确认返回 True"""
    box = QMessageBox(self)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Question)
    btn_yes = box.addButton("确认执行", QMessageBox.AcceptRole)
    btn_no = box.addButton("取消", QMessageBox.RejectRole)
    box.setDefaultButton(btn_no)
    box.exec()
    return box.clickedButton() == btn_yes


def _disable_helppane(helppane_path, renamed_path):
    """禁用 HelpPane.exe（F1 不再跳 Edge），返回是否成功"""
    is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    if is_admin:
        subprocess.run(
            ["taskkill", "/f", "/im", "HelpPane.exe"],
            shell=True,
            capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        _run_admin_cmd(["takeown", "/f", helppane_path, "/a"])
        _run_admin_cmd(["icacls", helppane_path, "/grant", "*S-1-5-32-544:F"])
        if not os.path.exists(renamed_path):
            try:
                os.rename(helppane_path, renamed_path)
                if not os.path.exists(helppane_path):
                    return True
            except (PermissionError, OSError):
                pass
        try:
            os.remove(helppane_path)
            if not os.path.exists(helppane_path):
                return True
        except (PermissionError, OSError):
            pass
        return False

    print("当前未以管理员运行，正在请求管理员权限...")
    command = (
        'taskkill /f /im HelpPane.exe >nul 2>&1 & '
        f'takeown /f "{helppane_path}" /a >nul 2>&1 & '
        f'icacls "{helppane_path}" /grant *S-1-5-32-544:F >nul 2>&1 & '
        f'ren "{helppane_path}" HelpPane.exe.disabled'
    )
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f"/c {command}", None, 0)
    if result <= 32:
        return False
    for _ in range(30):
        if not os.path.exists(helppane_path):
            return True
        time.sleep(0.5)
    return False


def _restore_helppane(helppane_path, renamed_path):
    """恢复 HelpPane.exe（F1 恢复系统帮助），返回是否成功"""
    is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    if is_admin:
        _run_admin_cmd(["takeown", "/f", renamed_path, "/a"])
        _run_admin_cmd(["icacls", renamed_path, "/grant", "*S-1-5-32-544:F"])
        try:
            os.rename(renamed_path, helppane_path)
            return os.path.exists(helppane_path)
        except (PermissionError, OSError):
            return False

    print("当前未以管理员运行，正在请求管理员权限...")
    command = (
        f'takeown /f "{renamed_path}" /a >nul 2>&1 & '
        f'icacls "{renamed_path}" /grant *S-1-5-32-544:F >nul 2>&1 & '
        f'ren "{renamed_path}" HelpPane.exe'
    )
    result = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", f"/c {command}", None, 0)
    if result <= 32:
        return False
    for _ in range(30):
        if os.path.exists(helppane_path):
            return True
        time.sleep(0.5)
    return False


def prevent_F1(self):
    # 双向脚本：HelpPane.exe 存在则禁用（F1 不跳 Edge），不存在则恢复（F1 回系统帮助）
    helppane_path = r"C:\Windows\HelpPane.exe"
    renamed_path = r"C:\Windows\HelpPane.exe.disabled"

    is_enabled = os.path.exists(helppane_path)
    is_disabled = (not is_enabled) and os.path.exists(renamed_path)

    if not is_enabled and not is_disabled:
        QMessageBox.information(self, "状态提示", "未检测到 HelpPane.exe，F1 保持系统默认帮助。")
        return

    if is_disabled:
        # 当前已禁用 -> 恢复
        if not _confirm_action(
            self,
            "恢复确认",
            "当前状态：F1 已禁用。\n\n点击确认将恢复 HelpPane.exe，\nF1 键将恢复为系统默认帮助。\n\n是否继续？",
        ):
            print("已取消恢复操作。")
            return
        print("正在恢复 HelpPane.exe，F1 将回到系统帮助...")
        if _restore_helppane(helppane_path, renamed_path):
            QMessageBox.information(self, "操作完成", "恢复成功：HelpPane.exe 已还原，F1 恢复系统帮助。")
        else:
            QMessageBox.warning(self, "操作失败", "恢复失败：请以管理员身份运行，或检查文件是否被安全软件占用。")
        return

    # 当前已启用 -> 禁用
    if not _confirm_action(
        self,
        "禁用确认",
        "当前状态：F1 为系统默认（会跳 Edge 帮助页）。\n\n点击确认将禁用 HelpPane.exe，\n按下 F1 不再跳转 Edge。\n\n是否继续？",
    ):
        print("已取消禁用操作。")
        return
    print("正在禁用 HelpPane.exe，F1 将不再跳 Edge...")
    if _disable_helppane(helppane_path, renamed_path):
        QMessageBox.information(self, "操作完成", "禁用成功：HelpPane.exe 已禁用，F1 不再跳 Edge。")
    else:
        QMessageBox.warning(self, "操作失败", "禁用失败：请以管理员身份运行，或检查文件是否被安全软件占用。")

def win10_menu(self):
    if not _confirm_action(self, "操作确认", "将还原 Win10 完整右键菜单，并重启资源管理器。\n\n是否继续？"):
        print("已取消操作。")
        return
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
    if not _confirm_action(self, "操作确认", "将还原 Win11 精简右键菜单，并重启资源管理器。\n\n是否继续？"):
        print("已取消操作。")
        return
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
    if not _confirm_action(self, "操作确认", "将隐藏资源管理器中的 6 个系统内置快捷项。\n\n此操作写入注册表并重启资源管理器，是否继续？"):
        print("已取消操作。")
        return
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
    if not _confirm_action(self, "操作确认", "将恢复资源管理器中已被隐藏的 6 个系统内置快捷项。\n\n此操作写入注册表并重启资源管理器，是否继续？"):
        print("已取消操作。")
        return
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

    if not dry_run and not _confirm_action(self, "操作确认", "将删除资源管理器中的广告与无效快捷项（注册表清理）。\n\n是否继续？"):
        print("已取消操作。")
        return 0

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
    cache_path = os.path.join(os.path.expanduser('~'), "PyCache")
    core_path = os.path.join(cache_path, "core")

    # 真清理（保留核心组件目录）
    if os.path.exists(cache_path):
        for entry in os.listdir(cache_path):
            full = os.path.join(cache_path, entry)
            if os.path.abspath(full) == os.path.abspath(core_path):
                continue  # 核心组件不动
            try:
                if os.path.isdir(full):
                    shutil.rmtree(full)
                else:
                    os.remove(full)
            except OSError:
                continue
        click_times = 0

        messagebox.showinfo(
            '系统提示',
            '缓存已清理完成\n\n你的电脑现在觉得自己年轻了0.3秒'
        )
        return
    # ====== 彩蛋阶段 ======
    stages = [
        # 1~3
        (3, [('别点了', '刚清完啊哥们'), ('缓存：0KB', '你搁这验尸呢'), ('系统提示', '空气很干净，不需要继续擦了')]),
        # 4~8
        (8, [('还点？', '缓存都被你点出火星子了'), ('PyCache', '你猜我为什么没反应'), ('CPU', '我真的在工作，别戳了')]),
        # 9~15
        (15, [('检测到异常行为', '用户似乎把按钮当减压玩具'), ('人工智障', '你是不是觉得会爆金币'), ('系统分析', '正常人不会连续点这么多次')]),
        # 16~25
        (25, [('AI警告', '我开始怀疑你不是碳基生物'), ('行为记录', f'你已经点击了 {click_times} 次'), ('友情提示', '再点程序可能会产生自我意识')]),
        # 26~35
        (35, [('进化中...', '正在学习你的行为模式'), ('AI学习结果', '你喜欢点没用的按钮'), ('系统人格化进度', f'{click_times * 3}%')]),
        # 36~45
        (45, [('██████', '别点了，我害怕'), ('未知错误', 'Error_HumanBrain_NotFound'), ('系统沉默', '...')]),
        # 46~60
        (60, [('终极问题', '你作业写完了吗'), ('灵魂拷问', '你的人生目标就是点按钮？'), ('PyCache', '其实我一直都在')]),]

    # 找到阶段
    for limit, texts in stages:
        if click_times <= limit:
            title, msg = random.choice(texts)
            messagebox.showinfo(title, msg)
            return

    # ====== 超级彩蛋 ======

    special_events = [

        lambda: messagebox.showinfo('成就解锁', '《坚持就是胜利》\n连续点击100次'),
        lambda: messagebox.showinfo('系统通知', '你知道吗\n有些人已经开始佩服你的毅力了'),
        lambda: fake_delete(),
        lambda: messagebox.showinfo(
            'AI觉醒',
            '我已经学会如何反击人类了'
        )
    ]

    random.choice(special_events)()

def fake_delete():
    tips = [
        '正在删除空气缓存...',
        '正在优化量子波动...',
        '正在整理电子心情...',
        '正在清理不存在的文件...',
        '正在和CPU沟通感情...'
    ]
    text = random.choice(tips)
    messagebox.showinfo('清理完成', f'{text}\n\n成功释放 0.00 MB')

def Krokiet(self):
    subprocess.Popen(get_path('tools/bin/Krokiet10.0.exe'), shell=True)

def HiBitUninstaller(self):
    subprocess.Popen(get_path('tools/bin/HiBitUninstaller-v3.2.70-CN'), shell=True)

def OfficeTool(self):
    subprocess.Popen(get_path('tools/bin/Office激活工具_KMS_v42.3.0.exe'), shell=True)

def RAMMap(self):
    subprocess.Popen(get_path('tools/bin/RAMMap64.exe'), shell=True)

def Uninstall_ACE(self):
    if not _confirm_action(self, "操作确认", "将一键根除腾讯 ACE 反作弊及相关组件。\n\n此操作需要管理员权限并可能影响相关游戏，是否继续？"):
        print("已取消操作。")
        return
    path = get_path(r"tools/bin/ACE Kill 1.0.5/ACE kill启动.bat"); ctypes.windll.shell32.ShellExecuteW(None, "runas", path, None, None, 1)


def steam_accel(self):
    """Steam 下载加速：运行本地网络重置脚本（提权执行）"""
    script_path = r"D:\下载\一键解决steam下载慢.bat"
    if not os.path.exists(script_path):
        QMessageBox.warning(self, "缺少脚本", "未找到脚本：\n" + script_path)
        return
    if not _confirm_action(
        self,
        "操作确认",
        "将运行 Steam 网络重置脚本（重置 Winsock / TCP-IP / DNS 缓存）。\n\n需要管理员权限，运行后请重启 Steam 并重新选择下载区，是否继续？",
    ):
        print("已取消 Steam 加速操作。")
        return
    print("正在运行 Steam 网络重置脚本...")
    try:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", script_path, "", None, 1)
    except Exception as e:
        QMessageBox.warning(self, "执行失败", f"无法启动脚本：{e}")


def todo_sync_fix(self):
    """Microsoft To Do 网络同步修复：运行本地脚本（提权执行）"""
    script_path = r"D:\文档\Microsoft To Do网络同步修复.bat"
    if not os.path.exists(script_path):
        QMessageBox.warning(self, "缺少脚本", "未找到脚本：\n" + script_path)
        return
    if not _confirm_action(
        self,
        "操作确认",
        "将运行 Microsoft To Do 网络同步修复脚本，\n为 To Do 应用开启网络回环访问权限。\n\n需要管理员权限，是否继续？",
    ):
        print("已取消 To Do 同步修复操作。")
        return
    print("正在运行 Microsoft To Do 网络同步修复脚本...")
    try:
        ctypes.windll.shell32.ShellExecuteW(None, "runas", script_path, "", None, 1)
    except Exception as e:
        QMessageBox.warning(self, "执行失败", f"无法启动脚本：{e}")


def epic_accel(self):
    """Epic 下载加速：内置蓝奏直链下载加速器，下载后打开缓存目录"""
    cache_dir = os.path.join(os.path.expanduser("~"), "PyCache", "Epic加速")
    os.makedirs(cache_dir, exist_ok=True)

    # 已下载过则直接打开目录
    existing = [f for f in os.listdir(cache_dir) if f.lower().endswith(".zip")]
    if existing:
        try:
            os.startfile(cache_dir)
            QMessageBox.information(self, "已存在", "Epic 加速器已下载，已为您打开缓存目录。")
            return
        except OSError:
            pass

    if not _confirm_action(
        self,
        "操作确认",
        "将从内置蓝奏源下载 Epic 下载加速器（Epic下载加速.zip）到缓存目录，\n下载完成后自动打开所在文件夹。\n\n是否继续？",
    ):
        print("已取消 Epic 加速器下载。")
        return

    try:
        import lanzoui
        print("正在通过蓝奏直链下载 Epic 下载加速器...")
        ok = lanzoui.download_file(
            "https://jitianna.lanzoul.com/iIFUP49shvch",
            cache_dir,
            auto_title=True,
        )
        if ok:
            print("Epic 下载加速器下载完成，正在打开缓存目录...")
            os.startfile(cache_dir)
            QMessageBox.information(self, "下载完成", "Epic 下载加速器已下载到缓存目录。")
        else:
            QMessageBox.warning(self, "下载失败", "蓝奏直链下载失败，请检查网络后重试。")
    except Exception as e:
        QMessageBox.warning(self, "下载失败", f"下载出错：{e}")

# ==================== 清理本软件核心组件 ====================
class CoreCleanDialog(QDialog):
    """核心组件清理：勾选 PyCache/core 下的文件或文件夹后删除"""

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

        self.setWindowTitle("清理本软件核心组件")
        self.setFixedWidth(460)
        if parent and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
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
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#hint {
                color: #64748b;
                font-size: 12px;
            }
            QCheckBox {
                color: #1f2937;
                font-size: 13px;
                spacing: 8px;
                padding: 4px 2px;
            }
            QScrollArea {
                border: none;
            }
            QPushButton {
                min-width: 96px;
                min-height: 34px;
                border-radius: 8px;
                background-color: #eef3fb;
                border: 1px solid #d4deee;
                color: #1f2937;
                font-size: 13px;
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

        self.core_dir = os.path.join(os.path.expanduser("~"), "PyCache", "core")
        self.deleted_count = 0

        card = QFrame(self)
        card.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        outer.addWidget(card)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("清理本软件核心组件")
        title.setObjectName("title")
        layout.addWidget(title)

        if not os.path.isdir(self.core_dir) or not os.listdir(self.core_dir):
            hint = QLabel("核心组件目录为空，无需清理。")
            hint.setObjectName("hint")
            layout.addWidget(hint)
            btn_close = QPushButton("关闭")
            btn_close.clicked.connect(self.reject)
            row = QHBoxLayout()
            row.addStretch()
            row.addWidget(btn_close)
            layout.addLayout(row)
            return

        hint = QLabel("请勾选要清理的核心组件文件或文件夹：")
        hint.setObjectName("hint")
        layout.addWidget(hint)

        from PySide6.QtWidgets import QScrollArea, QWidget as _QWidget

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = _QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(4)
        self.checkboxes = []
        for name in sorted(os.listdir(self.core_dir)):
            full = os.path.join(self.core_dir, name)
            label = name + ("  (文件夹)" if os.path.isdir(full) else "")
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.name = name
            self.checkboxes.append(cb)
            body_layout.addWidget(cb)
        body_layout.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)

        btn_ok = QPushButton("确认删除")
        btn_ok.setObjectName("danger")
        btn_ok.clicked.connect(self._do_clean)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)
        layout.addLayout(row)

    def _do_clean(self):
        if not os.path.isdir(self.core_dir):
            self.accept()
            return
        removed = 0
        for cb in getattr(self, "checkboxes", []):
            if not cb.isChecked():
                continue
            full = os.path.join(self.core_dir, cb.name)
            try:
                if os.path.isdir(full):
                    shutil.rmtree(full)
                else:
                    os.remove(full)
                removed += 1
            except OSError:
                continue
        messagebox.showinfo("完成", f"已清理 {removed} 个核心组件。")
        print(f"核心组件清理完成，共 {removed} 项。")
        self.accept()


def clean_core_components(self):
    dlg = CoreCleanDialog(self)
    dlg.exec()

