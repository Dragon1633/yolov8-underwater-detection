import sys
import cv2
import math
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget
from PyQt5.QtGui import QPixmap, QImage, QPainter, QPen, QColor
from PyQt5.QtCore import Qt, QPoint, QTimer


class ImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.pixmap_loaded = False
        self.points = []  # Stores the points clicked by the user
        self.temp_point = None  # Temporary point for drawing the arrow (mouse move)
        self.original_pixmap = None  # To store the original pixmap
        self.video_source = None
        self.setMouseTracking(True)

    def start_video(self, video_source=0):
        """Starts capturing video from the given video source."""
        self.video_source = cv2.VideoCapture(video_source)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(30)  # Update frame every 30ms

    def update_frame(self):
        """Read a frame from the video source and display it."""
        ret, frame = self.video_source.read()
        if ret:
            # Convert the frame from BGR (OpenCV format) to RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            # Get the frame height, width, and channel
            height, width, channel = frame.shape
            # Convert to QImage
            qimg = QImage(frame.data, width, height, 3 * width, QImage.Format_RGB888)
            # Set the QImage as QPixmap
            self.setPixmap(QPixmap.fromImage(qimg))
        else:
            self.timer.stop()  # Stop the timer if there's an issue with the video source

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            # Right-click clears the points
            self.points.clear()
            self.temp_point = None
            self.update()
        elif event.button() == Qt.LeftButton:
            # Left-click to select points
            if len(self.points) < 2:
                self.points.append(event.pos())
                self.temp_point = None
            if len(self.points) == 2:
                self.update()

    def mouseMoveEvent(self, event):
        if len(self.points) == 1:
            # Draw an arrow to the current mouse position
            self.temp_point = event.pos()
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if len(self.points) == 1 and self.temp_point:
            # Draw arrow from p1 to p2
            p1 = self.points[0]
            p2 = self.temp_point

            painter = QPainter(self)
            pen = QPen(QColor(0, 0, 255), 3)
            painter.setPen(pen)
            painter.drawLine(p1, p2)
            self.draw_arrowhead(painter, p1, p2)
            painter.end()

        if len(self.points) == 2:
            p1 = self.points[0]
            p2 = self.points[1]
            painter = QPainter(self)
            pen = QPen(QColor(255, 0, 0), 3)
            painter.setPen(pen)
            radius = int(math.sqrt((p2.x() - p1.x()) ** 2 + (p2.y() - p1.y()) ** 2) / 2)
            center = QPoint(int((p1.x() + p2.x()) / 2), int((p1.y() + p2.y()) / 2))
            painter.drawEllipse(center, radius, radius)
            painter.end()

    def draw_arrowhead(self, painter, p1, p2):
        angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
        arrow_size = 10
        p1_arrow = QPoint(
            p2.x() - arrow_size * math.cos(angle - math.pi / 6),
            p2.y() - arrow_size * math.sin(angle - math.pi / 6)
        )
        p2_arrow = QPoint(
            p2.x() - arrow_size * math.cos(angle + math.pi / 6),
            p2.y() - arrow_size * math.sin(angle + math.pi / 6)
        )
        painter.drawLine(p2, p1_arrow)
        painter.drawLine(p2, p2_arrow)

    def closeEvent(self, event):
        """Clean up when closing the application."""
        if self.video_source is not None:
            self.video_source.release()
        super().closeEvent(event)


class VideoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Video Display with Circle Drawing')
        self.setGeometry(100, 100, 800, 600)

        self.image_label = ImageLabel(self)
        self.setCentralWidget(self.image_label)

        # Start video capture (default webcam, or provide path to a video file)
        self.image_label.start_video(0)  # Use 0 for webcam, or provide a video path


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = VideoApp()
    window.show()
    sys.exit(app.exec_())
