"""单实例守护:重复启动时把已运行的实例拉到前台(还原最小化),本次启动退出。

原理:系统级命名互斥体;二次启动检测到已存在 → FindWindow 找到主窗口 →
SW_RESTORE 还原 + SetForegroundWindow 置前。对 .py 直接运行与 exe 打包均有效
(互斥体属于系统,与进程形态无关)。
"""
from __future__ import annotations

MUTEX_NAME = "Zai.PhoneTraceRecorder.SingleInstance"
ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9

_mutex_handle = None   # 进程存活期间持有,防止句柄被回收


def acquire_or_front(title, mutex_name=MUTEX_NAME) -> bool:
    """首次启动返回 True(持有互斥体);检测到重复启动返回 False(旧窗口已置前)。

    非 Windows 平台或 API 异常时不阻止启动(返回 True)。
    """
    global _mutex_handle
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        u32 = ctypes.windll.user32
        _mutex_handle = k32.CreateMutexW(None, False, mutex_name)
        if k32.GetLastError() == ERROR_ALREADY_EXISTS:
            hwnd = u32.FindWindowW(None, str(title))
            if hwnd:
                u32.ShowWindow(hwnd, SW_RESTORE)
                u32.SetForegroundWindow(hwnd)
            return False
    except Exception:
        return True
    return True
