import cv2
import sys
import time
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow


class CameraThread(QThread):
    # 定义信号：打开成功、打开失败、帧数据可用
    opened = pyqtSignal()
    failed = pyqtSignal()
    frame_ready = pyqtSignal(QImage)

    def __init__(self, video_source, parent=None):
        super().__init__(parent)
        self.video_source = video_source
        self.cap = None
        self.running = True

    def run(self):
        # 尝试打开摄像头
        self.cap = cv2.VideoCapture(self.video_source)

        if not self.cap.isOpened():
            self.failed.emit()
            return

        # 打开成功，发出信号
        self.opened.emit()

        # 循环读取视频帧
        while self.running:
            ret, frame = self.cap.read()
            if not ret:
                break

            # 将OpenCV图像转换为Qt图像
            rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)

            # 发出帧就绪信号
            self.frame_ready.emit(qt_image)

            # 避免占用太多CPU资源
            time.sleep(0.03)

    def stop(self):
        self.running = False
        self.wait(1000)  # 等待线程结束，最多1秒
        if self.cap and self.cap.isOpened():
            self.cap.release()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # 设置窗口
        self.setWindowTitle("Camera Viewer")
        self.setGeometry(100, 100, 800, 600)

        # 创建显示标签
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(self.label)
        self.label.setText("正在尝试连接摄像头...")

        # 摄像头源
        self.video_source = "rtsp://192.168.1.168:554/ch01.264"

        # 创建并启动摄像头线程
        self.camera_thread = CameraThread(self.video_source)
        self.camera_thread.opened.connect(self.on_camera_opened)
        self.camera_thread.failed.connect(self.on_camera_failed)
        self.camera_thread.frame_ready.connect(self.update_frame)

        # 设置超时定时器
        self.timeout_timer = QTimer(self)
        self.timeout_timer.setSingleShot(True)
        self.timeout_timer.timeout.connect(self.on_timeout)
        self.timeout_timer.start(5000)  # 5秒超时

        # 启动摄像头线程
        self.camera_thread.start()

    def on_camera_opened(self):
        """摄像头成功打开"""
        self.timeout_timer.stop()  # 停止超时计时器
        print("摄像头打开成功！")

    def on_camera_failed(self):
        """摄像头打开失败"""
        self.timeout_timer.stop()
        self.label.setText("摄像头打开失败！")
        print("摄像头打开失败！")

    def on_timeout(self):
        """5秒内未打开摄像头"""
        self.camera_thread.stop()
        self.label.setText("5秒内未连接成功！")
        print("5秒内未连接成功！")

    def update_frame(self, image):
        """更新显示帧"""
        pixmap = QPixmap.fromImage(image)
        self.label.setPixmap(pixmap.scaled(
            self.label.width(),
            self.label.height(),
            Qt.KeepAspectRatio
        ))

    def closeEvent(self, event):
        """窗口关闭时停止线程"""
        self.camera_thread.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())