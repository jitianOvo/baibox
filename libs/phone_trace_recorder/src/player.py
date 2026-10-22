"""应用内回放:把记录生成标准脚本后,用本机 Python 子进程执行。

这样做与「导出的 .py」行为完全一致 —— 回放测试同时就是对导出产物的预检。
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

from . import exporter, storage


class ReplayHandle:
    """回放句柄:持有一个子进程,可随时 stop()。"""

    def __init__(self):
        self.proc = None

    def stop(self):
        p = self.proc
        if p and p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass


def _child_env():
    """子进程强制 utf-8 输出,避免中文日志在管道里变乱码。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def start(rec, serial=None, speed=1.0, loop=1, on_line=None, on_done=None):
    """新起后台线程回放记录(loop=循环遍数),返回可 stop() 的句柄。

    on_line(str) / on_done(int) 都在后台线程触发,UI 侧请自行切回主线程。
    """
    on_line = on_line or (lambda s: None)
    on_done = on_done or (lambda code: None)
    h = ReplayHandle()

    def worker():
        storage.ensure_dirs()
        path = storage.TEMP_DIR / ("replay_%s_%d.py"
                                   % (time.strftime("%H%M%S"), time.time() * 1000 % 1000))
        code = 0
        try:
            path.write_text(exporter.build_standard(rec), encoding="utf-8")
            cmd = [sys.executable, str(path), "--speed", str(speed), "--no-pause"]
            loop_int = int(loop)
            if loop_int == 0:
                cmd += ["--loop", "0"]          # 0 表示无限循环
            elif loop_int > 1:
                cmd += ["--loop", str(loop_int)]
            if serial:
                cmd += ["--serial", serial]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT,
                                    text=True, encoding="utf-8", errors="replace",
                                    cwd=str(storage.TEMP_DIR),
                                    env=_child_env())
            h.proc = proc
            for ln in proc.stdout:
                on_line(ln.rstrip("\r\n"))
            code = proc.wait()
        except Exception as e:
            on_line("[错误] %s" % e)
            code = -1
        finally:
            try:
                path.unlink()
            except OSError:
                pass
        on_done(code)

    threading.Thread(target=worker, daemon=True).start()
    return h
