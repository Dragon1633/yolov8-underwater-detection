import sys
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel
from PyQt5.QtGui import QPixmap, QPainter, QColor, QImage
from PyQt5.QtCore import Qt

class ImageWithRectangles(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        # 设置窗口标题
        self.setWindowTitle('绘制透明彩色正方形')

        # 创建一个标签用于显示图片
        self.image_label = QLabel(self)

        # 加载图片
        self.original_image = QPixmap('test.jpg')
        self.image_label.setPixmap(self.original_image)

        # 创建一个按钮
        self.draw_button = QPushButton('绘制正方形', self)
        self.draw_button.clicked.connect(self.draw_rectangles)

        # 创建一个垂直布局
        layout = QVBoxLayout()
        layout.addWidget(self.image_label)
        layout.addWidget(self.draw_button)

        # 设置窗口的布局
        self.setLayout(layout)

    def draw_rectangles(self):
        # 创建一个新的 QPixmap 对象，用于绘制
        new_pixmap = QPixmap(self.original_image.size())
        new_pixmap.fill(Qt.transparent)

        # 创建 QPainter 对象
        painter = QPainter(new_pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # 设置第一个正方形的颜色和透明度
        color1 = QColor(255, 0, 0, 128)  # 红色，透明度 50%
        painter.setBrush(color1)
        painter.setPen(Qt.NoPen)
        painter.drawRect(50, 50, 100, 100)  # 左上角 (50, 50)，宽度 100，高度 100

        # 设置第二个正方形的颜色和透明度
        color2 = QColor(0, 255, 0, 128)  # 绿色，透明度 50%
        painter.setBrush(color2)
        painter.setPen(Qt.NoPen)
        painter.drawRect(200, 200, 100, 100)  # 左上角 (200, 200)，宽度 100，高度 100

        # 结束绘制
        painter.end()

        # 将绘制结果叠加到原图上
        painter = QPainter(self.original_image)
        painter.drawPixmap(0, 0, new_pixmap)
        painter.end()

        # 更新标签显示新的图片
        self.image_label.setPixmap(self.original_image)

        # 保存新的图片
        # self.original_image.save('output_image.jpg')


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ImageWithRectangles()
    window.show()
    sys.exit(app.exec_())
