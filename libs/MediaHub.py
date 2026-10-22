from PySide6.QtWidgets import QMessageBox


def open_media_hub(self):
    try:
        from libs.media_hub.ui import MediaHubDialog
        if not getattr(self, "_media_hub_dialog", None):
            self._media_hub_dialog = MediaHubDialog(self)
        self._media_hub_dialog.show()
        self._media_hub_dialog.raise_()
        self._media_hub_dialog.activateWindow()
    except Exception as exc:
        QMessageBox.warning(self, "听读看", "打开失败：" + str(exc))
