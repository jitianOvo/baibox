from core_lib import get_path

def show_image_dialog(parent, image_path, title="图片查看器"):
    from PyQt5.QtWidgets import QDialog, QLabel, QApplication, QHBoxLayout, QPushButton, QWidget
    from PyQt5.QtGui import QPixmap
    from PyQt5.QtCore import Qt, QPoint

    class ImageViewer(QDialog):
        def __init__(self, parent, path, title):
            super().__init__(parent)
            self.setWindowTitle(title)
            self.resize(1600, 900)
            self.setStyleSheet("""
                QDialog {
                    background-color: white;
                }
                QPushButton {
                    background-color: rgba(255, 255, 255, 150);
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    padding: 2px 8px;
                    margin: 2px;
                }
                QPushButton:hover {
                    background-color: rgba(255, 255, 255, 200);
                }
            """)

            # 设置窗口标志，添加最大化和最小化按钮
            self.setWindowFlags(
                Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)

            # 移除窗口大小限制
            self.setMinimumSize(100, 100)

            # 原图
            self.orig_pix = QPixmap(path)
            if self.orig_pix.isNull():
                print(f"无法加载图片: {path}")
                return

            self.scale = 1.0
            self.drag_start = QPoint()
            self.image_pos = QPoint(0, 0)
            self.is_dragging = False
            self.drag_button = None

            # 创建控制按钮
            self.create_control_buttons()

            # QLabel 显示图片
            self.label = QLabel(self)
            self.label.setPixmap(self.orig_pix)
            self.label.resize(self.orig_pix.size())
            self.label.move(0, 0)

            # 设置鼠标跟踪
            self.setMouseTracking(True)
            self.label.setMouseTracking(True)

            # 初始居中显示
            self.center_image()

        def create_control_buttons(self):
            """创建控制按钮"""
            self.control_widget = QWidget(self)
            self.control_widget.setStyleSheet("background-color: rgba(255, 255, 255, 150); border-radius: 5px;")
            self.control_widget.resize(160, 60)

            layout = QHBoxLayout(self.control_widget)
            layout.setSpacing(5)
            layout.setContentsMargins(5, 5, 5, 5)

            # 重置按钮
            self.reset_btn = QPushButton("重置", self.control_widget)
            self.reset_btn.clicked.connect(self.reset_view)
            self.reset_btn.setToolTip("重置视图 (R)")

            # 适应窗口按钮
            self.fit_btn = QPushButton("适应", self.control_widget)
            self.fit_btn.clicked.connect(self.fit_to_window)
            self.fit_btn.setToolTip("适应窗口大小 (F)")

            # 原始大小按钮
            self.original_btn = QPushButton("一半", self.control_widget)
            self.original_btn.clicked.connect(self.half_size)
            self.original_btn.setToolTip("一半大小 (O)")

            layout.addWidget(self.reset_btn)
            layout.addWidget(self.fit_btn)
            layout.addWidget(self.original_btn)

            self.control_widget.move(10, 10)
            self.control_widget.raise_()  # 确保按钮在最上层

        def reset_view(self):
            """重置视图"""
            self.scale = 1.0
            self.label.setPixmap(self.orig_pix)
            self.label.resize(self.orig_pix.size())
            self.center_image()

        def fit_to_window(self):
            """适应窗口大小"""
            if self.orig_pix.isNull():
                return

            # 计算适应窗口的缩放比例
            window_size = self.size()
            pix_size = self.orig_pix.size()

            scale_x = window_size.width() / pix_size.width()
            scale_y = window_size.height() / pix_size.height()
            self.scale = min(scale_x, scale_y) * 0.9  # 留一些边距

            # 缩放图片
            new_pix = self.orig_pix.scaled(
                int(pix_size.width() * self.scale),
                int(pix_size.height() * self.scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.label.setPixmap(new_pix)
            self.label.resize(new_pix.size())
            self.center_image()

        def half_size(self):
            """一半大小"""
            self.scale = 0.5
            self.label.setPixmap(self.orig_pix)
            self.label.resize(self.orig_pix.size())
            self.center_image()

        def wheelEvent(self, event):
            # 获取鼠标在图片上的相对位置，用于缩放中心点
            old_pos = self.label.mapFrom(self, event.pos())

            # 计算缩放因子
            factor = 1.2 if event.angleDelta().y() > 0 else 0.8
            new_scale = self.scale * factor

            # 设置缩放限制
            if new_scale < 0.1:
                new_scale = 0.1
            if new_scale > 10.0:
                new_scale = 10.0

            # 计算缩放前后位置的比例
            scale_ratio = new_scale / self.scale

            # 更新缩放比例
            self.scale = new_scale

            # 缩放图片
            new_pix = self.orig_pix.scaled(
                int(self.orig_pix.width() * self.scale),
                int(self.orig_pix.height() * self.scale),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.label.setPixmap(new_pix)
            self.label.resize(new_pix.size())

            # 调整位置，使缩放以鼠标位置为中心
            new_x = int(self.image_pos.x() * scale_ratio + (1 - scale_ratio) * old_pos.x())
            new_y = int(self.image_pos.y() * scale_ratio + (1 - scale_ratio) * old_pos.y())

            self.image_pos = QPoint(new_x, new_y)
            self.label.move(self.image_pos)

            # 确保图片不会完全移出视图
            self.ensure_image_visible()

        def mousePressEvent(self, event):
            # 支持左键和右键拖动
            if event.button() in (Qt.LeftButton, Qt.RightButton):
                self.drag_start = event.pos()
                self.is_dragging = True
                self.drag_button = event.button()
                QApplication.setOverrideCursor(Qt.ClosedHandCursor)

        def mouseMoveEvent(self, event):
            if self.is_dragging and event.buttons() & (Qt.LeftButton | Qt.RightButton):
                delta = event.pos() - self.drag_start
                self.drag_start = event.pos()

                # 更新图片位置
                self.image_pos += delta
                self.label.move(self.image_pos)

                # 确保图片不会完全移出视图
                self.ensure_image_visible()

        def mouseReleaseEvent(self, event):
            if event.button() in (Qt.LeftButton, Qt.RightButton) and event.button() == self.drag_button:
                self.is_dragging = False
                self.drag_button = None
                QApplication.restoreOverrideCursor()

        def contextMenuEvent(self, event):
            """重写右键菜单事件，避免弹出默认菜单"""
            event.accept()

        def ensure_image_visible(self):
            """确保图片至少有一部分在视图内"""
            label_rect = self.label.geometry()
            view_rect = self.rect()

            # 如果图片比视图小，则居中显示
            if label_rect.width() <= view_rect.width():
                new_x = (view_rect.width() - label_rect.width()) // 2
            else:
                # 限制图片不会完全移出视图
                new_x = min(max(label_rect.x(), view_rect.width() - label_rect.width()), 0)

            if label_rect.height() <= view_rect.height():
                new_y = (view_rect.height() - label_rect.height()) // 2
            else:
                new_y = min(max(label_rect.y(), view_rect.height() - label_rect.height()), 0)

            self.image_pos = QPoint(new_x, new_y)
            self.label.move(self.image_pos)

        def center_image(self):
            """居中显示图片"""
            view_rect = self.rect()
            label_rect = self.label.geometry()

            new_x = (view_rect.width() - label_rect.width()) // 2
            new_y = (view_rect.height() - label_rect.height()) // 2

            self.image_pos = QPoint(new_x, new_y)
            self.label.move(self.image_pos)

        def resizeEvent(self, event):
            """窗口大小改变时重新调整图片位置和按钮位置"""
            super().resizeEvent(event)
            # 调整控制按钮位置，保持在右上角
            self.control_widget.move(self.width() - self.control_widget.width() - 10, 10)

            # 只在图片比窗口小时居中，大图片保持当前位置
            if self.label.width() <= self.width() and self.label.height() <= self.height():
                self.center_image()
            else:
                self.ensure_image_visible()

        def keyPressEvent(self, event):
            """键盘控制"""
            if event.key() == Qt.Key_R:
                self.reset_view()
            elif event.key() == Qt.Key_F:
                self.fit_to_window()
            elif event.key() == Qt.Key_O:
                self.half_size()
            elif event.key() == Qt.Key_Escape:
                self.close()
            super().keyPressEvent(event)

    dlg = ImageViewer(parent, image_path, title)
    dlg.exec_()

def show_CPU(self):
    show_image_dialog(self, get_path('assets/res/台式CPU.jpg'), "台式CPU查看")

def show_GPU(self):
    show_image_dialog(self, get_path('assets/res/台式GPU.jpg'), "台式本GPU查看")

def show_CPUm(self):
    show_image_dialog(self, get_path('assets/res/笔记本CPU.jpg'), "笔记本CPU查看")

def show_GPUm(self):
    show_image_dialog(self, get_path('assets/res/笔记本GPU.jpg'), "笔记本GPU查看")

