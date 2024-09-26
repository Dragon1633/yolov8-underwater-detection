import os

import cv2
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5 import QtWidgets
import cv2 as cv
import datetime
import time
import threading

from src.utils.general import get_param


class CameraCaptureThread(QThread):
    send_video_info = pyqtSignal(dict)
    send_frame = pyqtSignal(list)       # 发送帧信号
    send_cameraIsOpen = pyqtSignal()    # 当摄像头断开时发送信号

    def __init__(self):
        super(CameraCaptureThread, self).__init__()
        self.thread_name = "CameraCaptureThread"
        self.threadFlag = False
        self.save_flag = not (get_param("whether save video") == 0)      # 是否启用保存标志位,当为0时不启用保存
        self.save_vedio = False     # 函数值判断是否保存视频

        self.video_info = []
        self.VM = cv.VideoWriter()          # 创建一个视频写入对象
        self.frame = np.zeros((1, 1, 3), dtype=np.uint8)

        self.focus = -1
        self.time0 = -1
        self.time1 = -1

    def set_start_config(self, ai_task, video_source=-1):
        self.threadFlag = True
        if video_source != -1:
            self.get_video_source(video_source)
        self.ai_task = ai_task
        self.detected_object = get_param("detected object")
        self.video_path = get_param("save video path")         # 发现异常保存视频路径
        self.picture_path = get_param("save picture path")     # 启用每3s保存一张图片的路径
        self.save_picture_interval = get_param("save picture interval")
        mkdir(self.video_path)
        mkdir(self.picture_path)
        # 每3s保存一张图片
        if self.ai_task in ["both", "save_picture"]:
            timer = threading.Timer(self.save_picture_interval, self.save_picture)
            timer.start()

    def get_video_source(self, video_source):
        self.video_source = video_source

    def get_video_focus(self, focus):
        self.focus = focus
        try:
            if self.cap.isOpened():
                self.cap.set(cv.CAP_PROP_FOCUS, focus)
        except:
            print("更改焦距失败，无法读取到摄像头！")

    def get_video_info(self, video_cap):
        video_info = {}
        video_info["FPS"] = video_cap.get(cv.CAP_PROP_FPS)
        video_info["length"] = int(video_cap.get(cv.CAP_PROP_FRAME_COUNT))
        video_info["size"] = (int(video_cap.get(cv.CAP_PROP_FRAME_WIDTH)), int(video_cap.get(cv.CAP_PROP_FRAME_HEIGHT)))
        return video_info

    def start_save_video(self, ai_output):
        contains_person = any(item.get('class') in self.detected_object for item in ai_output)
        if not contains_person:     # 检测到目标持续1s开始保存视频
            self.time1 = -1
            if self.time0 == -1:
                self.time0 = time.time()
            elif time.time() - self.time0 > get_param("exist object time") and self.save_vedio is False:
                self.save_vedio = True
        else:                   # 未检测到目标持续3s停止保存视频
            if self.time1 == -1:
                self.time1 = time.time()
            elif time.time() - self.time1 > get_param("no object time"):
                self.save_vedio = False
                self.time0 = -1
        # 创建视频
        if self.save_vedio and self.save_flag and self.VM.isOpened() is False and self.ai_task in ["both", "object_detection"]:
            fourcc = cv.VideoWriter_fourcc(*"mp4v")  # 保存的格式
            temp = self.video_path.split("/")
            real_path = ""
            for i in range(0, len(temp)):
                real_path += temp[i]
                if i != len(temp) - 1:
                    real_path += "\\"
            FName = fr"video{time.strftime('%Y-%m-%d_%H_%M_%S', time.localtime())}"
            print("视频创建！", FName)
            # 第一个参数是文件保存的名字，第二个参数是文件名称，第三个参数是帧率，第四个参数是文件的尺寸大小
            self.VM = cv.VideoWriter(real_path + "\\{}.mp4".format(FName), fourcc, 24,
                                     self.video_info["size"])
        elif not self.save_vedio:
            if self.VM:
                self.VM.release()

    def stop_capture(self):
        self.threadFlag = False

    def run(self):
        try:
            self.cap = cv.VideoCapture(self.video_source, cv.CAP_DSHOW)
        except:
            QtWidgets.QMessageBox.warning(None, "提示", "摄像头读取失败！")

        self.video_info = self.get_video_info(self.cap)
        self.send_video_info.emit(self.video_info)

        idx_frame = 0
        # id = 0
        # time0 = time.time()
        while self.threadFlag:
            ret, self.frame = self.cap.read()
            if ret is False:
                print("相机线程无法获得图片-摄像头断开连接！")
                self.send_cameraIsOpen.emit()
                # QtWidgets.QMessageBox.warning(None, "提示", "摄像头断开连接！", QtWidgets.QMessageBox.Ok)
                break
                # continue
            # if time.time() - time0 >= 1:
            #     print("1s输出的帧为：",id)
            #     id = 0
            #     time0 = time.time()
            # id += 1
            # 视频保存
            if self.ai_task in ["both", "object_detection"] and self.save_vedio:
                self.VM.write(self.frame)
                cv.waitKey(1)
            # 发送帧索引号和当前帧
            self.send_frame.emit(list([idx_frame, self.frame]))
            # print(idx_frame)
            idx_frame += 1

        self.send_frame.emit(list([None, None]))
        self.cap.release()
        if self.VM:
            self.VM.release()
        print("视频保存结束")

    def save_picture(self):
        now = time.strftime("%Y-%m-%d_%H_%M_%S", time.localtime())  # 2024-07-12 11:04:06
        now_date = now[0:10]    # 2024-07-12
        now_h = now[11:13]      # 11
        # now_min = now[14:16]    # 04
        now_name = now   # 11:04:06
        data_dir = self.picture_path + "/" + now_date
        mkdir(data_dir)
        h_dir = data_dir + "/" + now_h
        mkdir(h_dir)
        # if int(now_min) < 15:
        #     moment_dir = h_dir + "/" + "{}_00-{}_15".format(now_h, now_h)
        # elif int(now_min) < 30:
        #     moment_dir = h_dir + "/" + "{}_15-{}_30".format(now_h, now_h)
        # elif int(now_min) < 45:
        #     moment_dir = h_dir + "/" + "{}_30-{}_45".format(now_h, now_h)
        # else:
        #     moment_dir = h_dir + "/" + "{}_45-{}_00".format(now_h, int(now_h)+1)
        # mkdir(moment_dir)

        cv.imwrite(h_dir + "/" + "Picture-{}.jpg".format(now_name), self.frame)


def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)
