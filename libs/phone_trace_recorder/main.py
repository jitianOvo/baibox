"""手机轨迹录制器 —— 启动入口。

双击 启动.bat(自动装依赖)或命令行 `python main.py`。
单实例:重复启动时自动把已运行的窗口拉到前台,本次启动退出。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src import theme
from src.singleinstance import acquire_or_front


def main():
    if not acquire_or_front(theme.APP_TITLE):
        return 0    # 已有实例在运行,旧窗口已被拉到前台
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        print("[缺少依赖] 请先安装界面依赖:")
        print("    pip install customtkinter")
        try:
            input("按回车键退出...")
        except EOFError:
            pass
        return 1
    from src.ui_main import App
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
