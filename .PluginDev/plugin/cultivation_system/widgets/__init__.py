from PyQt5.Qt import Qt
from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import IconWidget, ImageLabel, CaptionLabel, ElevatedCardWidget


class ShopCard(ElevatedCardWidget):
    def __init__(self, icon, name: str, price: str, parent=None):
        super().__init__(parent)
        if isinstance(icon, str):
            self.iconWidget = ImageLabel(icon, self)
        else:
            self.iconWidget = IconWidget(icon)
        self.name_label = CaptionLabel(name, self)
        self.price_label = CaptionLabel(price, self)

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.addWidget(self.name_label, 0, Qt.AlignHCenter | Qt.AlignBottom)
        self.vBoxLayout.addStretch(1)
        self.vBoxLayout.setAlignment(Qt.AlignCenter)
        self.vBoxLayout.addStretch(1)
        self.vBoxLayout.addWidget(self.iconWidget, 0, Qt.AlignCenter)
        self.vBoxLayout.addStretch(1)
        self.vBoxLayout.addWidget(self.price_label, 0, Qt.AlignHCenter | Qt.AlignBottom)

        self.setFixedSize(90, 90)
        self.iconWidget.setFixedSize(30, 30)