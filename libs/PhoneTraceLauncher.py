# -*- coding: utf-8 -*-
import os
import subprocess
import sys


def open_phone_trace_recorder(self):
    """启动手机轨迹录制器（独立 tkinter 窗口，避免与 PySide6 事件循环冲突）"""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "phone_trace_recorder", "main.py")
    if not os.path.exists(script):
        print("手机轨迹录制器入口不存在:", script)
        return
    try:
        subprocess.Popen(
            [sys.executable, script],
            cwd=os.path.dirname(script),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as e:
        print("启动手机轨迹录制器失败:", e)
