"""ADB 工具封装:设备列表、屏幕信息、触摸输入设备探测。

- adb 默认从系统环境变量 PATH 查找,也可用环境变量 ADB 指定完整路径;
- 所有命令带超时,设备掉线时不会卡死界面;
- 输出统一按 utf-8 容错解码,兼容中文与厂商魔改输出。
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess


class AdbError(Exception):
    """adb 调用失败。"""


def adb_exe():
    """返回可用的 adb 可执行文件路径;找不到时返回空串。"""
    exe = os.environ.get("ADB", "adb")
    found = shutil.which(exe)
    if found:
        return found
    return exe if os.path.isfile(exe) else ""


def adb_ready():
    return bool(adb_exe())


def _base(serial=None):
    exe = adb_exe()
    if not exe:
        raise AdbError("未找到 adb,请先安装并加入系统环境变量 PATH"
                       "(或设置环境变量 ADB 指向 adb.exe)")
    cmd = [exe]
    if serial:
        cmd += ["-s", serial]
    return cmd


def shell_cmd(serial, remote_cmd):
    """构造 `adb [-s 序列号] shell <远程命令>` 的完整命令行列表。"""
    return _base(serial) + ["shell", remote_cmd]


def run(args, serial=None, timeout=10):
    """执行一条 adb 命令,返回 stdout 文本;失败抛 AdbError。"""
    cmd = _base(serial) + list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except FileNotFoundError:
        raise AdbError("adb 进程启动失败")
    except subprocess.TimeoutExpired:
        raise AdbError("adb 命令超时:%s" % " ".join(args))
    out = p.stdout.decode("utf-8", "replace")
    err = p.stderr.decode("utf-8", "replace")
    if p.returncode != 0:
        msg = (err.strip() or out.strip()) or ("exit=%d" % p.returncode)
        raise AdbError("adb %s 失败:%s" % (" ".join(args), msg))
    return out


def screencap(serial):
    """截取手机屏幕,返回 PNG 字节(供画面预览);失败抛 AdbError。"""
    cmd = _base(serial) + ["exec-out", "screencap", "-p"]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=15)
    except subprocess.TimeoutExpired:
        raise AdbError("screencap 超时")
    if p.returncode != 0 or not p.stdout:
        raise AdbError("截屏失败:" + p.stderr.decode("utf-8", "replace")[:80])
    return p.stdout


def devices_detailed():
    """返回 [(serial, state, model)],state ∈ device / offline / unauthorized…"""
    out = run(["devices", "-l"], timeout=8)
    res = []
    for ln in out.splitlines()[1:]:
        ln = ln.strip()
        if not ln or ln.startswith("List of") or ln.startswith("*"):
            continue
        parts = ln.split()
        if len(parts) < 2:
            continue
        model = ""
        for tk in parts[2:]:
            if tk.startswith("model:"):
                model = tk.split(":", 1)[1].replace("_", " ").strip()
        res.append((parts[0], parts[1], model))
    return res


def device_model(serial):
    try:
        return run(["shell", "getprop", "ro.product.model"], serial, timeout=6).strip() or "未知机型"
    except AdbError:
        return "未知机型"


def screen_size(serial):
    """返回自然(竖屏)方向的 (宽, 高);Override 分辨率优先于 Physical。

    wm size 报告的是显示器的物理自然尺寸,不随当前横竖屏旋转变化。
    """
    out = run(["shell", "wm", "size"], serial, timeout=6)
    phys = over = None
    for ln in out.splitlines():
        if "Physical size" in ln and not phys:
            phys = re.search(r"(\d+)x(\d+)", ln)
        elif "Override size" in ln and not over:
            over = re.search(r"(\d+)x(\d+)", ln)
    m = over or phys
    if not m:
        raise AdbError("无法获取屏幕分辨率(wm size 输出异常)")
    return int(m.group(1)), int(m.group(2))


def rotation_from_window(text):
    """从 dumpsys window 文本解析屏幕旋转;失败返回 None。

    只认 DisplayRotation 段的 mRotation=N(屏幕真实旋转;兼容
    mRotation=ROTATION_N 写法),排除含 snapshot 的噪音行。
    刻意不使用 mCurrentRotation —— 它属于 WindowOrientationListener,
    反映的是传感器感知的物理手持方向(平放/倒持时会与屏幕旋转不符,
    真机横屏实证:屏幕 ROTATION_270 时它报 ROTATION_2)。
    """
    if not text:
        return None
    for ln in text.splitlines():
        if "snapshot" in ln.lower():
            continue
        m = re.search(r"\bmRotation\s*=\s*(?:ROTATION_)?([0-3])\b", ln)
        if m:
            return int(m.group(1)) * 90
    return None


def rotation_from_input(text):
    """从 dumpsys input 文本解析旋转;失败返回 None。

    每个输入设备各上报一个 Orientation: RotationN,感知方向的设备跟随
    当前旋转、不感知的恒为 0,因此取最大值。
    """
    if not text:
        return None
    vals = re.findall(r"Orientation:\s*Rotation([0-3])", text)
    return max(int(v) for v in vals) * 90 if vals else None


def get_rotation(serial):
    """查询当前屏幕旋转,返回 0 / 90 / 180 / 270;识别失败返回 None。

    优先设备端 grep 精确取行首的 mRotation=(快照噪音行以 snapshot= 开头,
    天然不匹配,且 grep -m1 可让 dumpsys 提前退出,耗时更低);取不到时
    退回整包 dumpsys window 逐行解析,再退回 dumpsys input 取最大值。
    """
    attempts = (
        ("dumpsys window | grep -m1 '^ *mRotation='", rotation_from_window),
        ("dumpsys window", rotation_from_window),
        ("dumpsys input", rotation_from_input),
    )
    for cmd, fn in attempts:
        try:
            out = run(["shell", cmd], serial, timeout=8)
        except AdbError:
            continue
        r = fn(out)
        if r is not None:
            return r
    return None


class TouchDevice:
    """一个具备多点触摸坐标能力的输入设备。"""

    def __init__(self, path, name, max_x, max_y, has_btn_touch):
        self.path = path
        self.name = name
        self.max_x = max_x
        self.max_y = max_y
        self.has_btn_touch = has_btn_touch

    def __repr__(self):
        return "<TouchDevice %s %s max=%dx%d>" % (self.path, self.name, self.max_x, self.max_y)


def find_touch_devices(serial):
    """探测触摸屏输入设备,按可能性降序排列(第一个通常就是主触摸屏)。

    依据 `getevent -pl` 输出:同时具备 ABS_MT_POSITION_X/Y 量程的设备才算,
    BTN_TOUCH 与名字含 touch 的加分。
    """
    out = run(["shell", "getevent", "-pl"], serial, timeout=10)
    blocks = re.split(r"add device \d+:\s*", out)[1:]
    found = []
    for b in blocks:
        pm = re.match(r"(/dev/input/\S+)", b)
        if not pm:
            continue
        nm = re.search(r'name:\s*"([^"]*)"', b)
        max_x = max_y = None
        btn_touch = False
        for ln in b.splitlines():
            if "ABS_MT_POSITION_X" in ln:
                mm = re.search(r"max\s+(\d+)", ln)
                if mm:
                    max_x = int(mm.group(1))
            elif "ABS_MT_POSITION_Y" in ln:
                mm = re.search(r"max\s+(\d+)", ln)
                if mm:
                    max_y = int(mm.group(1))
            if "BTN_TOUCH" in ln:
                btn_touch = True
        if max_x is None or max_y is None or max_x <= 0 or max_y <= 0:
            continue
        found.append(TouchDevice(pm.group(1), nm.group(1) if nm else "",
                                 max_x, max_y, btn_touch))

    def score(d):
        s = 0
        if d.has_btn_touch:
            s += 4
        n = d.name.lower()
        if "touch" in n:
            s += 3
        return s

    found.sort(key=score, reverse=True)
    return found
