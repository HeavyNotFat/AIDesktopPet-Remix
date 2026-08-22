import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QDesktopWidget
from PyQt5.QtGui import QPainter, QPen, QColor, QPixmap
from PyQt5.QtCore import Qt, QPoint, QRect, QThread, pyqtSignal


class BrightnessAdjuster(QThread):
    finished = pyqtSignal(QPixmap)

    def __init__(self, pixmap, adjustment):
        super().__init__()
        self.pixmap = pixmap
        self.adjustment = adjustment

    def run(self):
        adjusted_pixmap = self.adjust_brightness(self.pixmap, self.adjustment)
        self.finished.emit(adjusted_pixmap)

    @staticmethod
    def adjust_brightness(pixmap, adjustment):
        image = pixmap.toImage()
        width = image.width()
        height = image.height()

        for y in range(height):
            for x in range(width):
                pixel = image.pixel(x, y)
                r, g, b, a = QColor(pixel).getRgb()
                new_r = max(0, min(255, r + adjustment))
                new_g = max(0, min(255, g + adjustment))
                new_b = max(0, min(255, b + adjustment))
                new_pixel = QColor(new_r, new_g, new_b, a).rgb()
                image.setPixel(x, y, new_pixel)

        return QPixmap.fromImage(image)


class ScreenshotTool(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Capture Screen by area - AgenticAI@Official")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setGeometry(100, 100, 210, 60)

        screen = QDesktopWidget().screenGeometry()
        self.pixmap = self.label = None
        self.drawing = self.is_finished = False
        self.screen_width = screen.width()
        self.screen_height = screen.height()

        screen = QApplication.primaryScreen()
        self.original_pixmap = screen.grabWindow(0)

        self.loading_label = QLabel("正在加载组件...\nLoading components...", self)
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 20px;")
        self.loading_label.setGeometry(0, 0, self.width(), self.height())

        self.brightness_thread = BrightnessAdjuster(self.original_pixmap, 40)
        self.brightness_thread.finished.connect(self.on_brightness_adjusted)
        self.brightness_thread.start()

        self.start_point = QPoint()
        self.end_point = QPoint()

    def on_brightness_adjusted(self, adjusted_pixmap):
        self.setGeometry(0, 0, self.screen_width, self.screen_height)

        self.is_finished = True

        self.loading_label.hide()
        self.pixmap = adjusted_pixmap
        self.label = QLabel(self)
        self.label.setPixmap(self.pixmap)
        self.label.setGeometry(0, 0, self.width(), self.height())

    def mousePressEvent(self, event):
        if not self.is_finished:
            return
        if event.button() == Qt.LeftButton:
            self.drawing = True
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if not self.is_finished:
            return
        if self.drawing:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if not self.is_finished:
            return
        if event.button() == Qt.LeftButton and self.drawing:
            self.drawing = False
            self.save_screenshot()
            self.close()

    def paintEvent(self, event):
        if not self.is_finished:
            return
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.pixmap)

        if self.drawing:
            rect = QRect(self.start_point, self.end_point).normalized()
            pen = QPen(QColor(255, 0, 0), 2, Qt.DashLine)
            painter.setPen(pen)
            painter.drawRect(rect)

            original_rect = QRect(self.start_point, self.end_point).normalized()
            painter.drawPixmap(original_rect, self.original_pixmap, original_rect)

    def save_screenshot(self):
        rect = QRect(self.start_point, self.end_point).normalized()
        clipboard = QApplication.clipboard()
        cropped_pixmap = self.pixmap.copy(rect)
        clipboard.setPixmap(cropped_pixmap)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ScreenshotTool()
    window.show()
    sys.exit(app.exec_())
