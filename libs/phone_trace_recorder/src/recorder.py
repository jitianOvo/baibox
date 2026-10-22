"""录制引擎:adb getevent 流式读取触摸事件,还原「点击 / 长按 / 滑动」与原始时间间隔。

工作原理
--------
- 监听手机**全部输入设备**(`adb shell getevent -t`),任何设备节点上出现的
  触摸事件(BTN_TOUCH / ABS_MT_POSITION_X/Y)都会被还原 —— 既覆盖实体触摸屏,
  也覆盖 pc-uinput 之类的虚拟触摸设备(电脑端控制工具注入的触控);
- 事件时间戳取自设备侧(getevent -t),动作之间的间隔不受 USB 传输延迟影响,
  做到「原封不动」;
- BTN_TOUCH 按下/抬起划分一次手势,ABS_MT_POSITION_X/Y 记录轨迹起止;
- 手势分类:位移 <= 判定阈值 → 点击(时长 < 500ms)/ 长按,否则滑动;
- 原始事件流同时被完整保存(root 增强导出使用)。

兼容性
------
- 行格式兼容:带/不带 [时间戳]、带/不带 /dev/input/eventX: 路径前缀;
- 每个设备节点按各自在 `getevent -pl` 中上报的 ABS_MT 量程换算坐标;
- shell 无权限读取 /dev/input 时自动改用 `su -c`(需 root,手机会弹授权)。
"""
from __future__ import annotations

import re
import subprocess
import threading
import time
import uuid

from . import adb_utils

# getevent 输出行,兼容三种形态:
#   [  10243.123456] 0003 0035 000002bc                      (旧版,无路径前缀)
#   [  10243.123456] /dev/input/event4: 0003 0035 000002bc   (新版,带路径前缀)
#   /dev/input/event4: 0003 0035 000002bc                    (无时间戳)
LINE_RE = re.compile(
    r"^\s*(?:\[\s*(\d+(?:\.\d+)?)\s*\]\s*)?"
    r"(?:/dev/input/(\S+?):\s*)?"
    r"([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{8})\s*$"
)

EV_SYN = 0x0000
EV_KEY = 0x0001
EV_ABS = 0x0003
SYN_REPORT = 0x0000
SYN_MT_REPORT = 0x0002
ABS_MT_SLOT = 0x002F
ABS_MT_POSITION_X = 0x0035
ABS_MT_POSITION_Y = 0x0036
ABS_MT_TRACKING_ID = 0x0039
BTN_TOUCH = 0x014A

_MT_CODES = (ABS_MT_SLOT, ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID)

LONG_PRESS_MS = 500      # 按住超过该时长视为长按
TAP_SLOP_RATIO = 0.015   # 屏幕宽度的 1.5% 内的位移视为「没有移动」

# getevent 启动时打印的设备清单行(不是事件),监听全部设备时会出现
_HEADER_WHOLE = ("add device",)
_HEADER_INDENT = ("name:", "events:", "input props:", "values:", "test:")


class GestureParser:
    """把 getevent 事件行流解析为手势序列(纯逻辑,可离线单测)。

    坐标说明:触摸屏原始坐标永远对应显示器的「自然(竖屏)方向」,
    与当前横竖屏无关,因此解析结果就是自然方向坐标;录制时的旋转
    方向通过 rot_fn 在每次手指按下时查询,作为变量附加到每个手势。
    """

    MAX_RAW = 200_000  # 原始事件保存上限,防极端长录制撑爆内存

    def __init__(self, node, max_x, max_y, screen_w, screen_h, rot_fn=None):
        self.node = node
        self.max_x = max_x
        self.max_y = max_y
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.rot_fn = rot_fn     # 手指按下时查询当前旋转 0/90/180/270
        # 触摸原始量程 → 屏幕坐标 的换算系数(量程通常 = 分辨率-1,
        # 部分机型是分辨率的整数倍,如 10 倍,该系数都能正确换算)
        self.kx = screen_w / (max_x + 1) if max_x > 0 else 1.0
        self.ky = screen_h / (max_y + 1) if max_y > 0 else 1.0

        self.raw_events = []   # [(相对首事件的毫秒, type, code, value)]
        self.gestures = []

        self._t0_dev = None                 # 首个带时间戳事件(设备时钟)
        self._t0_local = None               # 首个事件(本地时钟)
        self._t_start_local = time.time()   # 录制开始,用于首动作间隔
        self._down = False
        self._cur_rot = 0
        self._x_raw = self._y_raw = None
        self._x0_raw = self._y0_raw = None
        self._frame_locked = False
        self._t_down_dev = None
        self._t_down_local = None
        self._t_up_dev_prev = None
        self._t_up_local_prev = None

    def feed_line(self, line, local_t=None):
        """喂入一行 getevent 输出;一次手势结束时返回该手势 dict,否则返回 None。"""
        local_t = time.time() if local_t is None else local_t
        m = LINE_RE.match(line.strip())
        if not m:
            return None
        ts, _node, etype_s, code_s, value_s = m.groups()
        t = float(ts) if ts is not None else None
        etype = int(etype_s, 16)
        code = int(code_s, 16)
        value = int(value_s, 16)

        if self._t0_local is None:
            self._t0_local = local_t
        if t is not None and self._t0_dev is None:
            self._t0_dev = t
        if t is not None and self._t0_dev is not None:
            rel = round((t - self._t0_dev) * 1000, 1)
        else:
            rel = round((local_t - self._t0_local) * 1000, 1)
        if len(self.raw_events) < self.MAX_RAW:
            self.raw_events.append((rel, etype, code, value))

        if etype == EV_KEY and code == BTN_TOUCH:
            if value == 1 and not self._down:      # 手指按下
                self._down = True
                self._cur_rot = self._safe_rot()   # 记录本步操作时的横竖屏
                # 先锁存当前坐标;真实设备上坐标可能与 BTN_TOUCH 同帧,
                # 首帧 SYN 提交前到达的坐标事件会覆盖此值
                self._x0_raw = self._x_raw
                self._y0_raw = self._y_raw
                self._frame_locked = False
                self._t_down_dev = t
                self._t_down_local = local_t
            elif value == 0 and self._down:        # 手指抬起
                self._down = False
                return self._finish(t, local_t)
        elif etype == EV_ABS:
            if code == ABS_MT_POSITION_X:
                self._x_raw = value
                if self._down and (not self._frame_locked or self._x0_raw is None):
                    self._x0_raw = value
            elif code == ABS_MT_POSITION_Y:
                self._y_raw = value
                if self._down and (not self._frame_locked or self._y0_raw is None):
                    self._y0_raw = value
        elif etype == EV_SYN and code in (SYN_REPORT, SYN_MT_REPORT):
            if self._down:
                self._frame_locked = True   # 起点已在首帧定型,之后的坐标属于轨迹
        return None

    def _finish(self, t_up_dev, t_up_local):
        if self._x0_raw is None or self._y0_raw is None:
            return None  # 没拿到坐标(极短促的异常事件),丢弃

        # 时长:优先使用设备时间戳
        if self._t_down_dev is not None and t_up_dev is not None:
            dur = (t_up_dev - self._t_down_dev) * 1000.0
        else:
            dur = (t_up_local - self._t_down_local) * 1000.0
        dur = max(1, int(round(dur)))

        # 与上一次动作的间隔:同样优先设备时间戳,时钟异常时退回本地时钟
        delay = None
        if (self._t_down_dev is not None and self._t_up_dev_prev is not None
                and t_up_dev is not None):
            d = (self._t_down_dev - self._t_up_dev_prev) * 1000.0
            if d >= 0:
                delay = d
        if delay is None:
            base = self._t_up_local_prev or self._t_start_local
            delay = max(0.0, (self._t_down_local - base) * 1000.0)
        delay = int(round(delay))

        x0 = self._clamp_x(self._x0_raw)
        y0 = self._clamp_y(self._y0_raw)
        x1 = self._clamp_x(self._x_raw if self._x_raw is not None else self._x0_raw)
        y1 = self._clamp_y(self._y_raw if self._y_raw is not None else self._y0_raw)

        dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        slop = max(16, int(round(self.screen_w * TAP_SLOP_RATIO)))
        if dist <= slop:
            g = {"type": "long_press" if dur >= LONG_PRESS_MS else "tap",
                 "x": x0, "y": y0, "duration_ms": dur, "delay_ms": delay}
        else:
            g = {"type": "swipe", "x1": x0, "y1": y0, "x2": x1, "y2": y1,
                 "duration_ms": dur, "delay_ms": delay}
        g["rot"] = self._cur_rot
        g["ori"] = "landscape" if self._cur_rot in (90, 270) else "portrait"
        self.gestures.append(g)

        self._t_up_dev_prev = t_up_dev
        self._t_up_local_prev = t_up_local
        self._x0_raw = self._y0_raw = None
        return g

    def _clamp_x(self, raw):
        v = int(round(raw * self.kx))
        return max(0, min(self.screen_w - 1, v))

    def _clamp_y(self, raw):
        v = int(round(raw * self.ky))
        return max(0, min(self.screen_h - 1, v))

    def _safe_rot(self):
        """查询当前旋转;任何异常都退回 0(自然方向)。"""
        if self.rot_fn is None:
            return 0
        try:
            r = int(self.rot_fn())
        except Exception:
            return 0
        return r if r in (0, 90, 180, 270) else 0


class Recorder:
    """一次完整的录制会话(探测与读取都在后台线程完成)。

    UI 只需:
        r = Recorder(serial, on_status=..., on_finished=...)
        r.start()
        ...
        r.stop()
    回调运行在后台线程,UI 侧请用 after() 等方式切回主线程。
    """

    def __init__(self, serial=None, on_status=None, on_finished=None):
        self.serial = serial                      # None = 自动选择设备
        self.on_status = on_status or (lambda s: None)
        self.on_finished = on_finished or (lambda rec, err: None)
        self.parser = None
        self.touch = None
        self.result = None
        self._meta = {}
        self.ranges = {}                # 设备节点 -> (max_x, max_y)
        self._running = False
        self._finalized = False
        self._stop = threading.Event()
        self._proc = None
        self._thread = None
        self._raw_samples = []
        self._sent_statuses = set()
        self._awaiting_su = False

    @property
    def running(self):
        return self._running

    def start(self):
        if self._running:
            raise RuntimeError("录制已在进行中")
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """停止录制并等待收尾(最多 ~4s),返回记录 dict(可能为 None)。"""
        if not self._running:
            return self.result
        self._stop.set()
        self._kill_proc()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4)
        return self.result

    # -- 内部实现 ---------------------------------------------------------

    def _run(self):
        rec, err = None, None
        try:
            serial = self._resolve_serial()
            self.serial = serial
            self._status("正在探测触摸设备…")
            devs = adb_utils.find_touch_devices(serial)
            if not devs:
                raise adb_utils.AdbError("未找到触摸屏输入设备(无 ABS_MT_POSITION_X)")
            self.touch = devs[0]
            self.ranges = {d.path: (d.max_x, d.max_y) for d in devs}
            w, h = adb_utils.screen_size(serial)
            self.parser = GestureParser(self.touch.path, self.touch.max_x,
                                        self.touch.max_y, w, h,
                                        rot_fn=lambda: adb_utils.get_rotation(self.serial))
            self._meta = {"serial": serial, "model": adb_utils.device_model(serial),
                          "resolution": [w, h], "touch_device": self.touch.path,
                          "max_x": self.touch.max_x, "max_y": self.touch.max_y}
            self._status("监听 %d 个输入设备中 · 请在手机上操作…(实体触摸或电脑控制均可)"
                         % len(self.ranges))
            got = False
            reason = None
            seen_any = matched_any = 0
            for use_su in (False, True):
                if self._stop.is_set():
                    break
                if reason is not None:
                    self._status("改用 %s 方式读取…" % ("root(su)" if use_su else "直连"))
                self._spawn(use_su)
                got, lines, matched, reason = self._stream_once()
                seen_any += lines
                matched_any += matched
                if got:
                    break
            if not got and not self._stop.is_set():
                sample = (";样例行:" + " | ".join(self._raw_samples[:3])) if self._raw_samples else ""
                raise adb_utils.AdbError(
                    "读取触摸事件流失败(共收到 %d 行事件,识别 %d 行)%s"
                    % (seen_any, matched_any, sample))
        except Exception as e:
            err = str(e)
            self._status("✗ %s" % err)
        finally:
            self._running = False
            if not self._finalized:
                self._finalized = True
                rec = self._build_result() if self.parser is not None else None
                self.result = rec
                # 先回调(UI 立即保存/恢复按钮),再做手机侧收尾
                self.on_finished(rec, err)
            self._cleanup_remote()

    def _resolve_serial(self):
        if self.serial:
            return self.serial
        devs = [d for d in adb_utils.devices_detailed() if d[1] == "device"]
        if not devs:
            raise adb_utils.AdbError("未检测到已连接的 Android 设备")
        if len(devs) > 1:
            self._status("检测到多台设备,默认使用第一台:%s" % devs[0][0])
        return devs[0][0]

    def _spawn(self, use_su):
        remote = "getevent -t"
        if use_su:
            remote = "su -c 'getevent -t'"
            self._awaiting_su = True
            t = threading.Timer(2.5, self._su_grant_hint)
            t.daemon = True
            t.start()
        cmd = adb_utils.shell_cmd(self.serial, remote)
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT,
                                      text=True, encoding="utf-8",
                                      errors="replace", bufsize=1)

    def _su_grant_hint(self):
        if self._awaiting_su and self._running and not self._stop.is_set():
            self._status("等待 root 授权…(若手机弹出授权请求,请点「允许」)")

    def _stream_once(self):
        """读取事件流,直到停止/流结束。

        返回 (got, lines, matched, reason):
        got=True 表示捕捉到了触摸事件;reason ∈ stop / perm / eof。
        """
        got = False
        lines = matched = 0
        perm_seen = False
        proc = self._proc
        try:
            for line in proc.stdout:
                if self._stop.is_set():
                    return got, lines, matched, "stop"
                line = line.strip()
                if not line:
                    continue
                low = line.lower()
                if "permission denied" in low or "operation not permitted" in low:
                    perm_seen = True
                    if not got:
                        self._status_once(
                            "部分输入设备无权限读取,若录不到操作会自动改用 root 方式…")
                    continue
                if line.startswith(_HEADER_WHOLE) or line.lstrip().startswith(_HEADER_INDENT):
                    continue  # 启动时的设备清单行,不是事件
                lines += 1
                if len(self._raw_samples) < 3:
                    self._raw_samples.append(line[:160])
                m = LINE_RE.match(line)
                if not m:
                    continue
                matched += 1
                ty = int(m.group(3), 16)
                code = int(m.group(4), 16)
                if not got:
                    # 只把触摸类事件视为「事件流可用」;音量键/传感器等直接忽略
                    if ((ty == EV_KEY and code == BTN_TOUCH)
                            or (ty == EV_ABS and code in _MT_CODES)):
                        got = True
                    else:
                        continue
                node = m.group(2)
                if (node and not self.parser.gestures
                        and node != self.parser.node and node in self.ranges):
                    self._retarget(node)   # 触摸事件实际来自另一块设备(如虚拟触摸)
                g = self.parser.feed_line(line)
                if g:
                    self._status("已捕捉 %d 个动作…" % len(self.parser.gestures))
            return got, lines, matched, ("perm" if perm_seen else "eof")
        except (ValueError, OSError):
            return got, lines, matched, "eof"
        finally:
            self._awaiting_su = False
            self._kill_proc()

    def _retarget(self, node):
        """触摸事件实际来自另一块设备节点:按其量程重建解析器。

        仅在手势尚未开始时切换;原始事件流随之清零,保证 root 导出的
        sendevent 序列始终对应单一设备节点。
        """
        mx, my = self.ranges[node]
        w, h = self._meta["resolution"]
        self.parser = GestureParser(node, mx, my, w, h)
        self.touch = adb_utils.TouchDevice(node, node, mx, my, True)
        self._meta["touch_device"] = node
        self._meta["max_x"], self._meta["max_y"] = mx, my
        self._status("触摸事件来自 %s,已按其量程换算坐标" % node)

    def _kill_proc(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
                self._proc.wait(timeout=3)
            except Exception:
                pass
        self._proc = None

    def _cleanup_remote(self):
        """收尾:确保手机侧残留的 getevent 进程退出(best-effort)。"""
        if not self.touch:
            return
        try:
            cmd = adb_utils.shell_cmd(self.serial, "kill $(pidof getevent) >/dev/null 2>&1")
            subprocess.run(cmd, capture_output=True, timeout=3)
        except Exception:
            pass

    def _build_result(self):
        p = self.parser
        if p is None:
            return None
        lt = time.localtime(p._t_start_local)
        total = sum(g["delay_ms"] + g["duration_ms"] for g in p.gestures)
        return {
            "version": 1,
            "id": uuid.uuid4().hex[:8],
            "name": "录制_" + time.strftime("%Y%m%d_%H%M%S", lt),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S", lt),
            "duration_ms": total,
            "device": dict(self._meta),
            "gestures": list(p.gestures),
            "raw_events": [list(e) for e in p.raw_events],
        }

    def _status(self, s):
        try:
            self.on_status(s)
        except Exception:
            pass

    def _status_once(self, s):
        if s not in self._sent_statuses:
            self._sent_statuses.add(s)
            self._status(s)
