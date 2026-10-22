"""可拖拽的视频文件列表控件。"""

from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
)

from ..constants import VIDEO_EXTENSIONS


class VideoDropList(QListWidget):
    """支持拖入视频文件的列表。多选 + 拖拽。"""

    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.viewport().installEventFilter(self)
        self.setSelectionMode(QListWidget.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setDefaultDropAction(Qt.CopyAction)

    # -----------------------------------------------------------------
    def _video_paths_from_event(self, event):
        if not event.mimeData().hasUrls():
            return []
        paths = []
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                paths.append(path)
        return paths

    def dragEnterEvent(self, event):
        if self._video_paths_from_event(event):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._video_paths_from_event(event):
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = self._video_paths_from_event(event)
        if paths:
            self.filesDropped.emit(paths)
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def eventFilter(self, obj, event):
        # 部分主题下 viewport 不直接转发，主动拦截一次
        if obj is self.viewport():
            if event.type() == QEvent.DragEnter:
                self.dragEnterEvent(event)
                return event.isAccepted()
            if event.type() == QEvent.DragMove:
                self.dragMoveEvent(event)
                return event.isAccepted()
            if event.type() == QEvent.Drop:
                self.dropEvent(event)
                return event.isAccepted()
        return super().eventFilter(obj, event)
