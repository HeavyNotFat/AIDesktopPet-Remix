import sys
import time
import os
import shutil
import tempfile

import numpy
from PIL import Image, ImageFilter

from PyQt5.Qt import QApplication, QIcon, QFileDialog, QRect, Qt, QPixmap
from PyQt5.QtWidgets import QWidget, QLabel, QScrollArea
from qfluentwidgets import FluentWindow, FluentIcon, BodyLabel, LineEdit, PrimaryToolButton, Slider, \
    RoundMenu, Action


class HomePage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("HomePage")


class MathExpression(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("MathExpression")

        # 展示数学算法
        BodyLabel("图片阶梯", self).setGeometry(QRect(20, 5, 100, 35))
        self.grad = BodyLabel(self)
        grad_pixmap = QPixmap("math_expr/grad.png")
        self.grad.setPixmap(grad_pixmap.scaled(500, 80))
        self.grad.setGeometry(QRect(20, 50, 500, 80))

        BodyLabel("图片单元张量", self).setGeometry(QRect(20, 130, 100, 35))
        self.unit_tensor = BodyLabel(self)
        unit_tensor_pixmap = QPixmap("math_expr/unit_tensors.png")
        self.unit_tensor.setPixmap(unit_tensor_pixmap.scaled(700, 70))
        self.unit_tensor.setGeometry(QRect(20, 170, 700, 70))

        BodyLabel("图片光照模型", self).setGeometry(QRect(20, 240, 100, 35))
        self.normalized = BodyLabel(self)
        normalized_pixmap = QPixmap("math_expr/normalized.png")
        self.normalized.setPixmap(normalized_pixmap.scaled(1000, 70))
        self.normalized.setGeometry(QRect(20, 260, 1000, 90))

        BodyLabel("图片归一光照", self).setGeometry(QRect(20, 320, 100, 35))
        self.clone_normalized = BodyLabel(self)
        clone_normalized_pixmap = QPixmap("math_expr/clone_normalized.png")
        self.clone_normalized.setPixmap(clone_normalized_pixmap.scaled(550, 40))
        self.clone_normalized.setGeometry(QRect(20, 360, 550, 40))


class PictureShow(QScrollArea):
    def __init__(self, parent, allocate):
        super().__init__(allocate)
        self.parent = parent
        self.setObjectName("PictureShow")
        self.zoom_factor = 1.0
        self.drag_start_position = self.original_pixmap = None
        self.drag_start_scroll_x = self.drag_start_scroll_y = None
        self.image_label = QLabel(self)
        self.setWidget(self.image_label)
        self.setWidgetResizable(True)

    def contextMenuEvent(self, a0):
        menu = RoundMenu("MENU", self)

        save = Action(FluentIcon.SAVE, "保存", self)
        save.triggered.connect(self.save)
        menu.addAction(save)

        save_as = Action(FluentIcon.SAVE_AS, "另存为", self)
        save_as.triggered.connect(self.save_as)
        menu.addAction(save_as)

        menu.exec(self.mapToGlobal(a0.pos()))

    def wheelEvent(self, event):
        angle_delta = event.angleDelta().y()
        if angle_delta > 0:
            self.zoom_factor *= 1.1
        else:
            self.zoom_factor /= 1.1

        mouse_pos = event.pos()
        if not self.image_label.pixmap():
            return
        old_size = self.image_label.pixmap().size()
        new_size = self.original_pixmap.size() * self.zoom_factor

        relative_mouse_pos_x = mouse_pos.x() / old_size.width() if old_size.width() != 0 else 0
        relative_mouse_pos_y = mouse_pos.y() / old_size.height() if old_size.height() != 0 else 0

        self.update_pixmap()

        new_mouse_pos_x = relative_mouse_pos_x * new_size.width()
        new_mouse_pos_y = relative_mouse_pos_y * new_size.height()
        scroll_x = new_mouse_pos_x - mouse_pos.x()
        scroll_y = new_mouse_pos_y - mouse_pos.y()
        self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + int(scroll_x))
        self.verticalScrollBar().setValue(self.verticalScrollBar().value() + int(scroll_y))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.pos()
            self.drag_start_scroll_x = self.horizontalScrollBar().value()
            self.drag_start_scroll_y = self.verticalScrollBar().value()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self.drag_start_position is not None:
            delta_x = event.pos().x() - self.drag_start_position.x()
            delta_y = event.pos().y() - self.drag_start_position.y()
            self.horizontalScrollBar().setValue(self.drag_start_scroll_x - delta_x)
            self.verticalScrollBar().setValue(self.drag_start_scroll_y - delta_y)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = None
            event.accept()

    def setPixmap(self, pixmap):
        self.original_pixmap = pixmap
        self.update_pixmap()

    def update_pixmap(self):
        if self.original_pixmap:
            scaled_pixmap = self.original_pixmap.scaled(
                int(self.original_pixmap.width() * self.zoom_factor),
                int(self.original_pixmap.height() * self.zoom_factor),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)

    def save_as(self):
        select_folder = QFileDialog.getExistingDirectory(self, "选择保存路径", "")
        if select_folder:
            shutil.move(self.parent.filename, f"{select_folder}/{time.strftime('%Y-%m-%d %H.%M.%S')}.png")

    def save(self):
        shutil.move(self.parent.filename, f"{time.strftime('%Y-%m-%d %H.%M.%S')}.png")


class Accord(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("图片临摹软件")
        self.setWindowIcon(QIcon("logo.ico"))
        self.setGeometry(QRect(self.x(), self.y(), 1100, 550))
        
        self.filename: str | None = None
        
        # 添加主页
        self.home_page = HomePage()
        self.addSubInterface(self.home_page, FluentIcon.HOME, "临摹")
        # 添加数学
        self.math_expression = MathExpression()
        self.addSubInterface(self.math_expression, FluentIcon.DEVELOPER_TOOLS, "数学")
        self.switchTo(self.home_page)

        BodyLabel("图片路径", self.home_page).setGeometry(QRect(20, 5, 100, 35))
        self.original_path = LineEdit(self.home_page)
        self.original_path.setClearButtonEnabled(True)
        self.original_path.setGeometry(QRect(90, 5, 900, 35))
        self.click_select_folder = PrimaryToolButton(FluentIcon.FOLDER, self.home_page)
        self.click_select_folder.clicked.connect(self.select_picture)
        self.click_select_folder.setGeometry(QRect(1000, 5, 35, 35))

        BodyLabel("临摹深度", self.home_page).setGeometry(QRect(20, 40, 100, 35))
        self.show_depth = BodyLabel("2.0", self.home_page)
        self.show_depth.setGeometry(QRect(1000, 40, 100, 35))
        self.scale_depth = Slider(Qt.Horizontal, self.home_page)
        self.scale_depth.setRange(0, 100)
        self.scale_depth.setValue(20)
        self.scale_depth.setGeometry(QRect(90, 50, 900, 35))
        self.scale_depth.valueChanged.connect(self.scaled)

        self.click_accord = PrimaryToolButton(FluentIcon.SEND_FILL, self.home_page)
        self.click_accord.clicked.connect(self.accord)
        self.click_accord.setGeometry(QRect(20, 80, 35, 35))

        self.picture_show = PictureShow(self, self.home_page)
        self.picture_show.setGeometry(QRect(55, 80, 865, 420))

    def scaled(self):
        self.show_depth.setText(str(self.scale_depth.value() / 10))
        self.scale_depth.setToolTip(str(self.scale_depth.value() / 10))

    def select_picture(self):
        file_path = QFileDialog.getOpenFileName(self, "选择图片", "", "图像 (*.jpg *.png *.jpeg)")[0]
        if file_path:
            self.original_path.setText(file_path)

    def accord(self):
        if not self.original_path.text():
            return
        self.filename = os.path.join(tempfile.gettempdir(), f"{time.time()}.png")

        image_object = Image.open(self.original_path.text())
        width, height = image_object.width, image_object.height
        # 锐化
        sharpened1 = image_object.filter(ImageFilter.SHARPEN)
        sharpened2 = sharpened1.filter(ImageFilter.SHARPEN)
        sharpened3 = sharpened2.filter(ImageFilter.SHARPEN)
        sharpened3.save(self.filename)
        # 图像阶梯
        picture_grad = numpy.gradient(numpy.asarray(Image.open(self.filename).convert('L')).astype('int'))
        grad_x, grad_y = picture_grad[0] * self.scale_depth.value() / 100, picture_grad[1] * self.scale_depth.value() / 100
        # x, y, z的向量光照模型发福利
        base = numpy.sqrt(grad_x ** 2 + grad_y ** 2 + 1)
        _x, _y, _z = grad_x / base, grad_y / base, 1 / base
        # 重设置光照模型的目标角度
        sce_z, sce_x = numpy.pi / 2.1, numpy.pi / 3
        dx, dy, dz = numpy.cos(sce_z) * numpy.cos(sce_x), numpy.cos(sce_z) * numpy.sin(sce_x), numpy.sin(sce_z)
        # 光照模型的像素值
        normalized = 255 * (dx * _x + dy * _y + dz * _z).clip(0, 255)
        im = Image.fromarray(normalized.astype('uint8'))
        im = im.resize((width, height), Image.Resampling.LANCZOS)
        os.remove(self.filename)

        im.save(self.filename)

        pixmap = QPixmap(self.filename).scaled(self.picture_show.width(),
                                               self.picture_show.height(),
                                               Qt.KeepAspectRatio)
        self.picture_show.setPixmap(pixmap)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = Accord()
    w.show()
    sys.exit(app.exec_())
