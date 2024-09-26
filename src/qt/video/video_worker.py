import cv2
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.uic.properties import QtCore

from src.models.detection.yolov8_detector_onnx import YoloDetector
# from src.models.pose.yolov8_pose_onnx import PoseDetector
# from src.models.segmentation.yolov8_seg_onnx import YOLOSeg
from src.utils.general import ROOT, add_image_id, get_param
from src.utils.visualize import draw_results
import os
import cv2 as cv
import numpy as np
from PyQt5.QtGui import QImage
import time


class FileProcessThread(QThread):
    send_thread_start_finish_flag = pyqtSignal(str)     # 线程开始结束信号
    send_video_info = pyqtSignal(dict)                  # 视频信息信号
    send_ai_output = pyqtSignal(list)                   # AI结果输出信号
    send_display_frame = pyqtSignal(QImage)             # 显示帧信号
    send_play_progress = pyqtSignal(int)                # 播放进度信号
    def __init__(self):
        super(FileProcessThread, self).__init__()
        self.thread_name = "FileProcessThread"
        self.threadFlag = False
    
    def set_start_config(self, video_path, ai_task, screen_size, model_name="yolov8n", confidence_threshold=0.35, iou_threshold=0.45, frame_interval=0):
        self.threadFlag = True
        self.video_path = video_path
        self.ai_task = ai_task
        self.pause_process = False      # 控制暂停播放
        self.confi_thr = confidence_threshold
        self.iou_thr = iou_threshold
        self.model_name = model_name
        self.frame_interval = frame_interval    # 设置帧间隔，为0时不跳帧
        self.get_screen_size(screen_size)
        self._init_yolo()       # 初始化模型

    def set_iou_threshold(self, iou_threshold):
        self.iou_thr = iou_threshold
    
    def set_confidence_threshold(self, confidence_threshold):
        self.confi_thr = confidence_threshold
    
    def set_model_name(self, model_name):
        self.model_name = model_name
    
    def set_frame_interval(self, frame_interval):
        self.frame_interval = frame_interval
    
    def get_screen_size(self, screen_size):
        self.iw, self.ih = screen_size

    def _init_yolo(self):
        model_path = get_param("model path") + f"/{self.model_name}.onnx"
        if self.ai_task == "object_detection":
            self.detector = YoloDetector()
            self.detector.init(
                model_path=os.path.join(ROOT, model_path),
                # model_path=os.path.join(model_path, f"/{self.model_name}.onnx"),
                # class_txt_path=os.path.join(ROOT, "weights/classes.txt"),
                confidence_threshold=self.confi_thr,
                iou_threshold=self.iou_thr)
    
    def stop_process(self):
        self.threadFlag = False
    
    def toggle_play_pause(self):    # 切换播放暂停
        self.pause_process = not self.pause_process
        
    def run(self):
        self.send_thread_start_finish_flag.emit("processing_on_file")
        # media_fmt = self.check_image_or_video(self.video_path)      # 判断是视频还是图片
        cap = cv.VideoCapture(self.video_path)
        if not cap.isOpened():
            raise IOError("Couldn't open webcam or video")
        video_info = self.get_video_info(cap)
        self.send_video_info.emit(video_info)

        model_output = []
        frame_id = 1            # 记录帧id
        while self.threadFlag:
            if self.pause_process:
                continue
            ret, frame = cap.read()     # 读取一帧，如果读取成功，ret为True，frame为当前帧即图片
            if ret is False:
                break

            if frame_id % int(self.frame_interval+1) == 0:      # 是否跳帧读取
                model_output = []
                if self.ai_task == "object_detection":
                    model_output = self.detector.inference(frame, self.confi_thr, self.iou_thr)
                    # pass

            model_output = add_image_id(model_output, frame_id) # 在结果中增加一个帧id属性
            frame = draw_results(frame, model_output)
            # display_frame = self.convert_cv_qt(frame, self.ih, self.iw)
            display_frame = self.cvToQImage(self.showPicture(frame, self.ih, self.iw))     # 转换图片类型和调整大小

            self.send_display_frame.emit(display_frame)     # 发送显示的一帧帧图片
            self.send_play_progress.emit(int(frame_id/video_info["length"]*1000))
            self.send_ai_output.emit(model_output)
            frame_id += 1
        cap.release()

        self.send_thread_start_finish_flag.emit("waiting_for_setting")
    
    def get_video_info(self, video_cap):
        video_info = {}
        video_info["FPS"] = video_cap.get(cv.CAP_PROP_FPS)
        video_info["length"] = int(video_cap.get(cv.CAP_PROP_FRAME_COUNT))
        video_info["size"] = (int(video_cap.get(cv.CAP_PROP_FRAME_WIDTH)),int(video_cap.get(cv.CAP_PROP_FRAME_HEIGHT)))
        return video_info

    def check_image_or_video(self, media_path):
        img_fm = (".tif", ".tiff", ".jpg", ".jpeg", ".gif", ".png", ".eps", ".raw", ".cr2", ".nef", ".orf", ".sr2", ".bmp", ".ppm", ".heif")
        vid_fm = (".flv", ".avi", ".mp4", ".3gp", ".mov", ".webm", ".ogg", ".qt", ".avchd")
        media_fms = {"image": img_fm, "video": vid_fm}
        if any(media_path.lower().endswith(media_fms["image"]) for ext in media_fms["image"]):
            return "image"
        elif any(media_path.lower().endswith(media_fms["video"]) for ext in media_fms["video"]):
            return "video"
        else:
            raise TypeError("Please select an image or video")

    def cvToQImage(self, image):
        """将OpenCV图像转换为QImage"""
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