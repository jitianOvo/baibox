"""把录制记录导出为可独立双击运行的 Python 回放脚本。

两种模式:
- standard(默认):adb `input tap / swipe` 注入,无需 root,兼容性最好;
  脚本把 adb 当作系统环境变量直接调用,双击即按录制节奏原样回放一遍。
- root(实验性):把录制的原始事件流还原为 sendevent 脚本推送到手机,
  经 su 以内核事件方式回放,与真实硬件事件一致(适合对 input 注入
  不敏感的应用/游戏);要求手机已 root。

横竖屏自适应:
- 坐标一律以「自然(竖屏)方向」存储 —— 触摸屏原始坐标系与自然方向一致,
  不随当前横竖屏变化;
- 回放时每一步实时识别手机当前旋转(0/90/180/270°),把自然坐标换算为
  当前显示坐标再注入 —— 横竖屏与录制时不一致、流程中途发生旋转切换,
  都能点准;
- root 模式回放原始内核事件,系统会像对待真实手指一样自动应用旋转,
  天然支持任意方向。

导出的脚本只依赖 Python 标准库,不依赖本软件。
"""
from __future__ import annotations

from . import storage

# ----------------------------- 模板(头部) -----------------------------
_HEADER = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《__NAME__》—— 由「手机轨迹录制器」导出的自动回放脚本__MODE_NOTE__
================================================================
录制时间 : __CREATED__
来源设备 : __DEVICE__(自然分辨率 __RES__,即竖屏方向的宽x高)
动作数量 : __COUNT__ 个(点击 __TAP__ · 长按 __LONG__ · 滑动 __SWIPE__)
预计时长 : 约 __DUR__ 秒(1.0x 原速)

▶ 双击本文件(或命令行 python 本文件.py)即可按录制时的节奏原样回放一遍。
  前提:电脑装有 Python 3;adb 已加入系统环境变量;手机已开启 USB 调试并连接。

横竖屏自适应:
  脚本内的坐标一律是自然(竖屏)方向的坐标;回放时每一步实时识别手机当前
  旋转(0/90/180/270°)并自动换算 —— 无论当前横屏还是竖屏,也无论流程中途
  是否发生旋转切换,点击位置都与录制时一致。
  ORIENTS 列表记录每步动作「录制时」的旋转方向(0=竖屏,90/270=横屏)。

可选参数:
  --speed 1.5         回放倍速(默认 1.0 原速,2 即两倍速)
  --loop 3            连续回放 3 遍(默认 1;root 模式暂不支持,按单遍执行)
  --serial 序列号      指定手机(连接多台设备时;默认自动选择)
  --rotation 90       强制指定旋转(0/90/180/270),跳过自动识别
  --no-rotcheck       只在开始时识别一次旋转,之后逐步不再检测(更快)
  --dry               预览模式:只打印将要执行的动作,不真机操作
  --pause/--no-pause  强制/禁止结束后等待回车(双击运行默认自动等待)

供 AI / 其他程序调用:
__CALL_NOTE__
  也可直接用 subprocess 执行本文件,退出码 0=成功。
"""
import os
import re
import subprocess
import sys
import time

ADB = os.environ.get("ADB", "adb")   # 默认把 adb 当作系统环境变量直接调用
SERIAL = ""                           # 留空 = 自动选择设备
DRY_RUN = False                       # True = 只打印不执行
ROT_CHECK = True                      # 每步动作前实时识别横竖屏
FORCED_ROT = None                     # 强制旋转(0/90/180/270),非 None 时优先
_LAST_ROT = 0                         # 最近一次成功识别的旋转
'''

# ----------------------------- 模板(标准模式) -----------------------------
_STD_BODY = '''

W_NAT = __WNAT__   # 自然(竖屏)分辨率宽
H_NAT = __HNAT__   # 自然(竖屏)分辨率高

# ============ 动作序列(与录制时完全一致) ============
# (执行前等待秒数, 类型, 参数)  tap=(x,y)  long_press=(x,y,ms)  swipe=(x1,y1,x2,y2,ms)
# 坐标为自然(竖屏)方向;回放时按当前旋转自动换算
ACTIONS = [
__ACTIONS__
]

# 每步动作录制时的屏幕旋转(0=竖屏,90/270=横屏;仅作记录与 AI 参考,
# 不影响回放准确性 —— 回放按实时识别的旋转换算)
ORIENTS = [
__ORIENTS__
]


def _clamp(v, hi):
    return max(0, min(hi - 1, int(v)))


def to_display(x, y, rot):
    """自然(竖屏)坐标 → 当前旋转 rot 下的显示坐标(input 命令需要的坐标)。"""
    if rot == 90:
        return _clamp(y, H_NAT), _clamp(W_NAT - 1 - x, W_NAT)
    if rot == 180:
        return _clamp(W_NAT - 1 - x, W_NAT), _clamp(H_NAT - 1 - y, H_NAT)
    if rot == 270:
        return _clamp(H_NAT - 1 - y, H_NAT), _clamp(x, W_NAT)
    return _clamp(x, W_NAT), _clamp(y, H_NAT)


def get_rotation():
    """实时识别当前屏幕旋转,返回 0/90/180/270;识别失败返回 None。

    只认 dumpsys window 里 DisplayRotation 段的 mRotation=N(屏幕真实
    旋转;刻意不用 mCurrentRotation,它是传感器的物理手持方向,横屏时
    可能误报,真机实证过)。优先设备端 grep 取行首 mRotation=(快照
    噪音行天然不匹配,更快);退回整包解析;再退回 dumpsys input 取最大。
    """
    pat = r"\\bmRotation\\s*=\\s*(?:ROTATION_)?([0-3])\\b"
    for cmd, parser in (
        ("dumpsys window | grep -m1 '^ *mRotation='", "grep"),
        ("dumpsys window", "full"),
        ("dumpsys input", "input"),
    ):
        try:
            out = _adb("shell", cmd, timeout=12)
        except Exception:
            continue
        if parser == "input":
            vals = [int(v) for v in re.findall(r"Orientation:\\s*Rotation([0-3])", out)]
            if vals:
                return max(vals) * 90
            continue
        if parser == "grep":
            m = re.search(pat, out)
            if m:
                return int(m.group(1)) * 90
            continue
        for ln in out.splitlines():          # full:整包逐行,排除快照行
            if "snapshot" in ln.lower():
                continue
            m = re.search(pat, ln)
            if m:
                return int(m.group(1)) * 90
    return None


def _current_rot():
    """当前旋转:强制指定 > 实时检测 > 最近一次成功值。"""
    global _LAST_ROT
    if FORCED_ROT is not None:
        return FORCED_ROT
    r = get_rotation() if ROT_CHECK else None
    if r is None:
        return _LAST_ROT
    _LAST_ROT = r
    return r


def _ori_label(rot):
    return "横屏" if rot in (90, 270) else "竖屏"


def _describe(kind, p):
    if kind == "tap":
        return "点击 (%d, %d)" % (p[0], p[1])
    if kind == "long_press":
        return "长按 (%d, %d) %dms" % (p[0], p[1], p[2])
    return "滑动 (%d,%d)→(%d,%d) %dms" % (p[0], p[1], p[2], p[3], p[4])


def run(speed=1.0, loop=1):
    """按录制节奏回放,loop>1 时连续回放多遍(loop=0 表示无限循环),返回累计执行的动作数。"""
    global _LAST_ROT
    loop = max(0, int(loop))
    infinite = (loop == 0)
    if not DRY_RUN:
        _resolve_serial()
        r0 = get_rotation()
        if r0 is None:
            print("[警告] 无法识别当前屏幕旋转,按竖屏(0°)处理;可用 --rotation 90 强制指定")
        else:
            _LAST_ROT = r0
            print("[环境] 当前屏幕:%s(%d°)· 自然分辨率 %dx%d" % (_ori_label(r0), r0, W_NAT, H_NAT))
    n = len(ACTIONS)
    total = "∞" if infinite else str(loop)
    print("[开始] 共 %d 个动作 × %s 遍,倍速 %.2fx%s"
          % (n, total, speed, "(预览模式)" if DRY_RUN else ""))
    t0 = time.time()
    done = 0
    try:
        lap = 0
        while True:
            lap += 1
            if loop != 1 and not DRY_RUN:
                print("[第 %d/%d 遍]" % (lap, loop) if not infinite
                      else "[第 %d 遍]" % lap)
            for i, (delay, kind, p) in enumerate(ACTIONS, 1):
                if DRY_RUN:
                    rot = ORIENTS[i - 1] if ORIENTS and i - 1 < len(ORIENTS) else 0
                    print("  %02d/%02d  [录制时:%s %d°] %s"
                          % (i, n, _ori_label(rot), rot, _describe(kind, p)))
                    done += 1
                    continue
                ta = time.time()
                rot = _current_rot()   # 旋转检测耗时计入动作间隔,不额外拖慢节奏
                remain = delay / speed - (time.time() - ta)
                if remain > 0:
                    time.sleep(remain)
                if kind == "tap":
                    x, y = to_display(p[0], p[1], rot)
                    dp = (x, y)
                    _adb("shell", "input", "tap", str(x), str(y))
                elif kind == "long_press":
                    x, y = to_display(p[0], p[1], rot)
                    dp = (x, y, p[2])
                    _adb("shell", "input", "swipe", str(x), str(y), str(x), str(y), str(p[2]))
                elif kind == "swipe":
                    x1, y1 = to_display(p[0], p[1], rot)
                    x2, y2 = to_display(p[2], p[3], rot)
                    dp = (x1, y1, x2, y2, p[4])
                    _adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(p[4]))
                else:
                    raise RuntimeError("未知动作类型:" + kind)
                tag = "" if loop == 1 else ("[第 %d 遍] " % lap if infinite
                                            else "[第 %d/%d 遍] " % (lap, loop))
                print("  %s%02d/%02d  [%s %d°] %s"
                      % (tag, i, n, _ori_label(rot), rot, _describe(kind, dp)))
                done += 1
            if not infinite and lap >= loop:
                break
            if infinite and DRY_RUN:
                break                       # 预览模式只展示一遍
    except KeyboardInterrupt:
        print("\\n[中断] 已停止(累计 %d 个动作)" % done)
        raise
    print("[完成] 共 %d 个动作 × %s 遍,用时 %.1f 秒" % (n, total, time.time() - t0))
    return done
'''

# ----------------------------- 模板(root 模式) -----------------------------
_ROOT_BODY = '''

# ============ 原始触摸事件流(root 增强) ============
# 列:(相对首事件的毫秒, 事件类型, 事件代码, 值)—— 与内核 evdev 事件一一对应
# 注意:这是触摸屏的原始事件流,系统回放时会像对待真实手指一样自动应用
# 当前横竖屏旋转 —— 天然支持任意方向,无需坐标换算。
EVENTS = [
__EVENTS__
]
NODE = "__NODE__"
INIT_DELAY = __INIT_DELAY__   # 首个事件前的等待秒数(与录制一致)
SE_HEX = False                # sendevent 参数进制:False=十进制(现代 toybox,
                              # 真机 RMX3850 实证);旧版 toolbox 为十六进制,
                              # 命令行加 --sendevent-hex 切换


def _remote_script(speed):
    """把事件流还原为手机端 sh 脚本:sendevent + sleep 按原节奏排列。"""
    fmt = "%x %x %x" if SE_HEX else "%d %d %d"
    lines = ["E=%s" % NODE,
             "command -v sendevent >/dev/null 2>&1 || { echo NO_SENDEVENT; exit 3; }"]
    if INIT_DELAY > 0:
        lines.append("sleep %s" % ("%.3f" % (INIT_DELAY / speed)))
    prev = 0.0
    for t, ty, c, v in EVENTS:
        dt = (t - prev) / 1000.0 / speed
        if dt >= 0.003:
            lines.append("sleep %s" % ("%.3f" % dt))
        lines.append("sendevent $E %s" % (fmt % (ty, c, v)))
        prev = t
    return "\\n".join(lines) + "\\n"


def _check_root():
    out = _adb("shell", "su", "-c", "id", timeout=15)
    if "uid=0" not in out:
        raise RuntimeError("未获得 root(su 失败或手机未授权),root 增强模式无法使用\\n" + out.strip())


def run(speed=1.0, loop=1):
    """以 root 方式(sendevent)回放原始事件流,返回已执行的事件数。"""
    if int(loop) != 1:
        print("[提示] root 模式暂不支持 --loop(含无限/多遍),按单遍执行")
    if DRY_RUN:
        dur = (INIT_DELAY + (EVENTS[-1][0] if EVENTS else 0) / 1000.0) / speed
        print("[预览] 共 %d 个内核事件,设备节点 %s,预计 %.1f 秒" % (len(EVENTS), NODE, dur))
        return 0
    _resolve_serial()
    _check_root()
    if not EVENTS:
        raise RuntimeError("该记录未保存原始事件流,无法使用 root 模式")
    script = _remote_script(speed)
    remote = "/data/local/tmp/mtr_replay_%d.sh" % int(time.time() * 1000 % 100000000)
    p = subprocess.Popen([ADB] + (["-s", SERIAL] if SERIAL else []) + ["shell", "cat > " + remote],
                         stdin=subprocess.PIPE)
    p.communicate(script.encode("utf-8"))
    if p.returncode != 0:
        raise RuntimeError("回放脚本推送到手机失败")
    print("[执行] su -c sh %s(共 %d 个事件)" % (remote, len(EVENTS)))
    try:
        total_s = (INIT_DELAY + EVENTS[-1][0] / 1000.0) / speed
        out = _adb("shell", "su", "-c", "sh " + remote, timeout=int(total_s) + 120)
        if "NO_SENDEVENT" in out:
            raise RuntimeError("手机上没有 sendevent 工具,无法使用 root 模式")
    finally:
        try:
            _adb("shell", "rm", "-f", remote, timeout=15, check=False)
        except Exception:
            pass
    print("[完成] 原始事件回放结束")
    return len(EVENTS)
'''

# ----------------------------- 模板(公共尾部) -----------------------------
_TAIL = '''

def _adb(*args, timeout=30, check=True):
    cmd = [ADB]
    if SERIAL:
        cmd += ["-s", SERIAL]
    cmd += list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError("adb 命令失败:%s\\n%s" % (" ".join(cmd), (r.stderr or r.stdout).strip()))
    return r.stdout


def _resolve_serial():
    global SERIAL
    if SERIAL:
        return SERIAL
    if os.environ.get("ANDROID_SERIAL"):
        SERIAL = os.environ["ANDROID_SERIAL"]
        return SERIAL
    out = _adb("devices", timeout=10)
    devs = [ln.split()[0] for ln in out.splitlines()
            if len(ln.split()) >= 2 and ln.split()[1] == "device"]
    if not devs:
        raise RuntimeError("未检测到已连接的 Android 设备(请检查 USB 线与 USB 调试授权)")
    if len(devs) > 1:
        print("[提示] 连接了多台设备,默认使用第一台:%s(可用 --serial 指定)" % devs[0])
    SERIAL = devs[0]
    return SERIAL


def main(argv=None):
    global SERIAL, DRY_RUN, ROT_CHECK, FORCED_ROT, SE_HEX
    argv = list(sys.argv[1:] if argv is None else argv)
    speed, pause, loop = 1.0, None, 1
    i = 0
    try:
        while i < len(argv):
            a = argv[i]
            if a == "--speed":
                speed = float(argv[i + 1]); i += 2
            elif a == "--loop":
                try:
                    loop = int(argv[i + 1])
                    if loop < 0:
                        raise ValueError
                except (IndexError, ValueError):
                    print("--loop 需要非负整数(0 表示无限循环)")
                    return 2
                i += 2
            elif a == "--serial":
                SERIAL = argv[i + 1]; i += 2
            elif a == "--rotation":
                try:
                    FORCED_ROT = int(argv[i + 1])
                except (IndexError, ValueError):
                    print("--rotation 需要 0/90/180/270")
                    return 2
                if FORCED_ROT not in (0, 90, 180, 270):
                    print("--rotation 需要 0/90/180/270")
                    return 2
                ROT_CHECK = False
                i += 2
            elif a == "--no-rotcheck":
                ROT_CHECK = False; i += 1
            elif a == "--sendevent-hex":
                SE_HEX = True; i += 1
            elif a == "--dry":
                DRY_RUN = True; i += 1
            elif a == "--pause":
                pause = True; i += 1
            elif a == "--no-pause":
                pause = False; i += 1
            elif a in ("-h", "--help"):
                print(__doc__)
                return 0
            else:
                print("未知参数:%s(--help 查看用法)" % a)
                return 2
    except (IndexError, ValueError):
        print("参数用法错误(--help 查看用法)")
        return 2
    code = 0
    try:
        run(speed, loop)
    except KeyboardInterrupt:
        code = 130
    except Exception as e:
        print("[失败]", e)
        code = 1
    do_pause = pause if pause is not None else sys.stdout.isatty()
    if do_pause:
        try:
            input("\\n按回车键退出...")
        except (EOFError, KeyboardInterrupt):
            pass
    return code


if __name__ == "__main__":
    sys.exit(main())
'''


# ----------------------------- 生成逻辑 -----------------------------

def _ori_label(rot):
    return "横屏" if rot in (90, 270) else "竖屏"


def _fill_meta(text, rec, mode):
    s = storage.summarize(rec)
    dev = rec.get("device", {})
    res = dev.get("resolution") or [1080, 2400]
    if mode == "standard":
        note = ""
        call_note = ("  import 本模块后调用 run(speed=1.0, loop=1);动作数据保存在 ACTIONS 列表\\n"
                     "  (坐标为自然/竖屏方向),ORIENTS 为每步录制时的旋转;两者可自由\\n"
                     "  增删改,增删动作时请同步维护 ORIENTS(或整体置 None 忽略)。")
    else:
        note = "\\n模式:root 增强(sendevent 原始事件流,实验性;需要手机已 root)"
        call_note = ("  import 本模块后调用 run(speed=1.0);原始事件流保存在 EVENTS 列表\\n"
                     "  (触摸屏原始坐标系,系统回放时自动应用横竖屏旋转),可自由增删改。")
    text = text.replace("__MODE_NOTE__", note)
    text = text.replace("__CALL_NOTE__", call_note)
    text = text.replace("__NAME__", str(rec.get("name", "未命名")))
    text = text.replace("__CREATED__", str(rec.get("created_at", "")))
    text = text.replace("__DEVICE__", "%s(%s)" % (dev.get("model", "未知机型"),
                                                  dev.get("serial", "-")))
    text = text.replace("__RES__", "%dx%d" % (res[0], res[1]))
    text = text.replace("__WNAT__", str(res[0]))
    text = text.replace("__HNAT__", str(res[1]))
    text = text.replace("__COUNT__", str(s["count"]))
    text = text.replace("__TAP__", str(s["tap"]))
    text = text.replace("__LONG__", str(s["long_press"]))
    text = text.replace("__SWIPE__", str(s["swipe"]))
    text = text.replace("__DUR__", "%.1f" % (s["total_ms"] / 1000.0))
    return text


def _fmt_actions(rec):
    lines = []
    for i, g in enumerate(rec.get("gestures", []), 1):
        d = g.get("delay_ms", 0) / 1000.0
        rot = int(g.get("rot", 0) or 0)
        tag = "# 动作%d [%s %d°]:" % (i, _ori_label(rot), rot)
        if g["type"] == "tap":
            lines.append('    (%.3f, "tap", (%d, %d)),    %s 点击 (%d,%d) 按下%dms'
                         % (d, g["x"], g["y"], tag, g["x"], g["y"], g["duration_ms"]))
        elif g["type"] == "long_press":
            lines.append('    (%.3f, "long_press", (%d, %d, %d)),    %s 长按 (%d,%d) %dms'
                         % (d, g["x"], g["y"], g["duration_ms"], tag,
                            g["x"], g["y"], g["duration_ms"]))
        else:
            lines.append('    (%.3f, "swipe", (%d, %d, %d, %d, %d)),    %s 滑动 (%d,%d)→(%d,%d) %dms'
                         % (d, g["x1"], g["y1"], g["x2"], g["y2"], g["duration_ms"], tag,
                            g["x1"], g["y1"], g["x2"], g["y2"], g["duration_ms"]))
    return "\n".join(lines) if lines else "    # (无动作)"


def _fmt_orients(rec):
    gs = rec.get("gestures", [])
    if not gs:
        return "    # (无动作)"
    return "\n".join("    %d," % int(g.get("rot", 0) or 0) for g in gs)


def _fmt_events(rec):
    ev = rec.get("raw_events") or []
    if not ev:
        return "    # (无原始事件)"
    return "\n".join("    (%.1f, %d, %d, %d)," % (t, ty, c, v)
                     for t, ty, c, v in ev)


def build_standard(rec):
    """生成标准模式(adb input,无需 root)的回放脚本文本。"""
    text = _HEADER + _STD_BODY + _TAIL
    text = _fill_meta(text, rec, "standard")
    text = text.replace("__ACTIONS__", _fmt_actions(rec))
    return text.replace("__ORIENTS__", _fmt_orients(rec))


def build_root(rec):
    """生成 root 模式(sendevent 原始事件流)的回放脚本文本。"""
    if not rec.get("raw_events"):
        raise ValueError("该记录未保存原始事件流,无法导出 root 模式")
    text = _HEADER + _ROOT_BODY + _TAIL
    text = _fill_meta(text, rec, "root")
    node = rec.get("device", {}).get("touch_device", "/dev/input/event0")
    init = (rec.get("gestures") or [{}])[0].get("delay_ms", 0) / 1000.0
    text = text.replace("__NODE__", node)
    text = text.replace("__INIT_DELAY__", "%.3f" % init)
    return text.replace("__EVENTS__", _fmt_events(rec))


def export(rec, path, mode="standard"):
    """导出脚本到 path,返回 path。mode ∈ {standard, root}。"""
    text = build_root(rec) if mode == "root" else build_standard(rec)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path
