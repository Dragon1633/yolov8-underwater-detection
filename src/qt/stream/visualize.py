import cv2
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QImage
from PyQt5.uic.properties import QtCore

from src.data_type.video_buffer import FrameBuffer
import cv2 as cv
import numpy as np
from src.utils.visualize import draw_results
from src.utils.general import get_param
import copy


class VideoVisualizationThread(QThread):
    send_thread_start_stop_flag = pyqtSignal(str)
    send_displayable_frame = pyqtSignal(np.ndarray)
    # send_original_frame = pyqtSignal(np.ndarray)
    # send_displayable_frame = pyqtSignal(QImage)
    send_ai_output = pyqtSignal(list)
    def __init__(self):
        super(VideoVisualizationThread, self).__init__()
        self.thread_name = "VideoVisualizationThread"
        self.threadFlag = False
        self.frame_buffer = FrameBuffer(10)  # 表示该帧缓存可以存储10个帧。
        self.scale = get_param("scale")
    
    def set_start_config(self, screen_size):
        self.threadFlag = True
        self.ai_output = []
        self.get_screen_size(screen_size)
    
    def get_fresh_frame(self, frame_list):
        self.frame_buffer.put(frame=copy.deepcopy(frame_list[1]), frame_id=frame_list[0], realtime=True)

    def get_ai_output(self, ai_output):
        self.ai_output = ai_output

    def get_screen_size(self, screen_size):
        self.iw, self.ih = screen_size
    
    def stop_display(self):
        self.threadFlag = False
        self.frame_buffer.clear_buffer()

    def run(self):
        self.send_thread_start_stop_flag.emit("processing_on_camera")
        while self.threadFlag:
            frame_id, frame = self.frame_buffer.get()
            # print(frame_id)
            if frame_id is not None:
                # self.send_original_frame.emit(frame)
                frame = draw_results(frame, self.ai_output, self.scale)
                # show_image = self.cvToQImage(self.showPicture(frame, self.ih, self.iw))
                self.send_displayable_frame.emit(frame)
                self.send_ai_output.emit(self.ai_output)
            else:
                # self.send_ai_output.emit([])
                cv2.waitKey(50)
                continue
                # break

    def cvToQImage(self, image):
        """将OpenCV图像 转换为QImage图像"""
        h, w, pix = image.shape[0], image.shape[1], image.strides[0]
        channels = 1 if len(image.shape) == 2 else image.shape[2]
        if channels == 3:  # CV_8UC3
            qImg = QImage(image.data, w, h, pix, QImage.Format.Format_RGB888)  # 通过访问img.data，你可以直接操作图像的二进制数据
            return qImg.rgbSwapped()
        elif channels == 1:
            qImg = QImage(image.data, w, h, pix, QImage.Format.Format_Indexed8)
            return qImg
        else:
            QtCore.qDebug("错误: numpy.ndarray无法转换为QImage格式. Channels = %d" % image.shape[2])
            return QImage()

    def showPicture(self, img, h, w):
        """ 输入np图像，将图像按显示框大小自动缩放,h、w分别为需要展示的label区域的高和宽 """
        height = img.shape[0]
        weight = img.shape[1]
        if height / weight > h / w:
            k = h / height
            resize_img = cv2.resize(img, None, None, k, k)
            num = abs(int((w - resize_img.shape[1]) / 2))
            n = (w - resize_img.shape[1]) % 2
            re_img = cv2.copyMakeBorder(resize_img, 0, 0, num + n, num, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        else:
            k = w / weight
            resize_img = cv2.resize(img, None, None, k, k)
            num = abs(int((h - resize_img.shape[0]) / 2))
            n = (h - resize_img.shape[0]) % 2
            re_img = cv2.copyMakeBorder(resize_img, num + n, num, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        return re_img


    # def showPicture(self, image, screen_height, screen_width):
    #     h, w, _ = image.shape
    #     scale = min(screen_width / w, screen_height / h)
    #     nw, nh = int(scale * w), int(scale * h)
    #     image_resized = cv.resize(image, (nw, nh))
    #     image_paded = np.full(shape=[screen_height, screen_width, 3], fill_value=0)
    #     dw, dh = (screen_width - nw) // 2, (screen_height - nh) // 2
    #     image_paded[dh:nh + dh, dw:nw + dw, :] = image_resized
    #     image_paded = image_paded.astype('uint8')
    #     return image_paded

    
