"""大丸工具箱入口：启动 splash 后展示主窗口。"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from paths import assets_dir
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("大丸工具箱")

    # ===== Splash 启动画面 =====
    splash_path = assets_dir() / "splash.png"
    splash = None
    if splash_path.exists():
        pixmap = QPixmap(str(splash_path))
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                720, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            splash = QSplashScreen(pixmap, Qt.WindowStaysOnTopHint)
            splash.setEnabled(False)
            splash.show()
            app.processEvents()

    # ===== 创建主窗口（先不显示）=====
    main_window = MainWindow()

    def show_main():
        if splash:
            splash.close()
        main_window.show()

    # splash 至少展示 1.2s，避免一闪而过
    QTimer.singleShot(1200, show_main)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
