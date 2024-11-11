import sys
import math

import cv2
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor
from PyQt5.QtCore import Qt, QPoint


class ImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.pixmap_loaded = False
        self.points = []  # Stores the points clicked by the user
        self.temp_point = None  # Temporary point for drawing the arrow (mouse move)
        self.original_pixmap = None  # To store the original pixmap

        self.setMouseTracking(True)


    def set_image(self, image_path):
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            self.original_pixmap = pixmap  # Store the original pixmap
            self.resize_image()  # Resize the image to fit the label
            self.pixmap_loaded = True

    def resize_image(self):
        if self.original_pixmap:
            # Resize the image to fit the label size while keeping aspect ratio
            scaled_pixmap = self.original_pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.setPixmap(scaled_pixmap)

    def mousePressEvent(self, event):
        if self.pixmap_loaded:
            if event.button() == Qt.RightButton:
                # Right-click clears the points
                self.points.clear()
                self.temp_point = None
                self.update()
            elif event.button() == Qt.LeftButton:
                # Left-click to select points
                if len(self.points) < 2:
                    # Record the clicked position
                    self.points.append(event.pos())
                    self.temp_point = None  # Clear the temp point
                if len(self.points) == 2:
                    # If two points are selected, trigger a repaint
                    self.update()

    def mouseMoveEvent(self, event):
        # print("函数被触发")
        # cv2.waitKey(10)
        if self.pixmap_loaded and len(self.points) == 1:
            # If one point is selected, draw an arrow to the current mouse position
            self.temp_point = event.pos()
            print(self.temp_point)
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        if len(self.points) == 1 and self.temp_point:
            # If one point is selected, draw an arrow to the mouse position
            p1 = self.points[0]
            p2 = self.temp_point

            painter = QPainter(self)
            pen = QPen(QColor(0, 0, 255), 3)
            painter.setPen(pen)

            # Draw arrow from p1 to p2
            painter.drawLine(p1, p2)

            # Calculate arrowhead
            self.draw_arrowhead(painter, p1, p2)

            painter.end()

        if len(self.points) == 2:
            # Draw a line between the two selected points
            p1 = self.points[0]
            p2 = self.points[1]

            painter = QPainter(self)
            pen = QPen(QColor(255, 0, 0), 3)
            painter.setPen(pen)

            # Calculate the center and radius of the circle
            radius = int(math.sqrt((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) / 2)
            center = QPoint(int((p1.x() + p2.x()) / 2), int((p1.y() + p2.y()) / 2))

            # Draw the circle
            painter.drawEllipse(center, radius, radius)
            painter.end()


    def draw_arrowhead(self, painter, p1, p2):
        """Draw an arrowhead pointing from p1 to p2."""
        angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
        arrow_size = 10

        # Calculate the points of the arrowhead
        p1_arrow = QPoint(
            p2.x() - arrow_size * math.cos(angle - math.pi / 6),
            p2.y() - arrow_size * math.sin(angle - math.pi / 6)
        )
        p2_arrow = QPoint(
            p2.x() - arrow_size * math.cos(angle + math.pi / 6),
            p2.y() - arrow_size * math.sin(angle + math.pi / 6)
        )

        # Draw the arrowhead
        painter.drawLine(p2, p1_arrow)
        painter.drawLine(p2, p2_arrow)

    def resizeEvent(self, event):
        # When the label is resized, adjust the image size as well
        self.resize_image()
        super().resizeEvent(event)


class ImageCircleDrawer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Circle Drawer with Arrow')
        self.setGeometry(100, 100, 800, 600)

        # Create an ImageLabel to display the image
        self.image_label = ImageLabel(self)

        # Load and display the image
        self.image_label.set_image("test.jpg")

        # Layout setup
        layout = QVBoxLayout()
        layout.addWidget(self.image_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ImageCircleDrawer()
    window.show()
    sys.exit(app.exec_())
