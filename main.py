import math
import os
import threading
import time
import cv2
import sys
import json
import numpy as np
import pandas as pd
import subprocess

from src.qt.stream.video_capture import CameraCaptureThread
from src.qt.stream.video_capture import CameraThread
from src.qt.stream.visualize import VideoVisualizationThread
from src.qt.stream.ai_worker import AiWorkerThread
from src.qt.stream.ai_find_circle import AiWorkerThread2
from src.qt.stream.modbus import ModbusThread
from src.qt.stream.floder_clean_up import CleanupThread

from src.ui.main_window_end import Ui_MainWindow
from src.ui.menu_setting import Ui_Dialog
from src.ui.menu1 import Ui_Menu1
from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtWidgets import QDialog, QMessageBox, QFileDialog, QLabel
from PyQt5.QtGui import QImage, QPixmap, QPen, QColor, QPainter
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QTimer

# 设置两个视频源，如果是本地摄像头通常是 0 和 1。如果是RTSP请分别填入对应的推流地址。
video_source_1 = 0
video_source_2 = 1

# 现场使用的水下相机是rtsp推流的，需要替换video_source
# cap = cv2.VideoCapture(video_source_1)
# ret, _ = cap.read()
# if not ret:
#     video_source_1 = "rtsp://192.168.1.168:554/ch01.264"
# del cap, ret
#

# cap2 = cv2.VideoCapture(video_source_2)
# ret2, _ = cap2.read()
# if not ret2:
#     video_source_2 = "rtsp://192.168.1.169:554/ch01.264"  # 示例备用地址
# del cap2, ret2


def get_ipv4_addresses():
    """获取本机IPv4地址列表，适用于Windows系统。目的：自动配置modbus的IP地址"""
    try:
        result = subprocess.check_output(
            'ipconfig',
            shell=True,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='cp936'
        )
        ip_addresses = []
        for line in result.splitlines():
            if "IPv4" in line and "地址" in line:
                ip = line.split(':')[-1].strip()
                if ip:
                    ip_addresses.append(ip)
        return ip_addresses
    except subprocess.CalledProcessError as e:
        print(f"命令执行失败: {e.output}")
        return []
    except FileNotFoundError:
        print("未找到ipconfig命令，请确保在Windows系统中运行")
        return []


def get_modbus_ip():
    """自动返回modbus的IP地址"""
    ip_list = get_ipv4_addresses()
    with open('log_ip.txt', 'a') as file:
        file.write(
            time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) + '\t' + "获取到的IP地址：" + str(ip_list) + '\n')

    # 针对双相机，取第一个相机的IP作为过滤基准即可，或者都过滤
    if isinstance(video_source_1, int):
        return "0"
    cam_ip = video_source_1[7:17]
    for ip in ip_list:
        if cam_ip in ip:
            ip_list.remove(ip)

    if len(ip_list) == 1:
        with open('log_ip.txt', 'a') as file:
            file.write(time.strftime("唯一的modbus IP地址：" + str(ip_list[0]) + '\n'))
        return str(ip_list[0])
    return "0"


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    send_ignore_area_list_1 = pyqtSignal(list)
    send_ignore_area_list_2 = pyqtSignal(list)
    send_whether_save_video_1 = pyqtSignal(bool)
    send_whether_save_video_2 = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        # 双份线程实例化
        self.ai_thread_1 = AiWorkerThread()
        self.ai_thread_2 = AiWorkerThread()
        self.camera_thread_1 = CameraCaptureThread()
        self.camera_thread_2 = CameraCaptureThread()
        self.display_thread_1 = VideoVisualizationThread()
        self.display_thread_2 = VideoVisualizationThread()

        self.modbus_thread = ModbusThread()
        self.cleanup_thread = CleanupThread("./save_picture")

        # 状态变量字典化，支持两个相机独立状态追踪
        self.time_ok = {1: -1, 2: -1}
        self.time_ng = {1: -1, 2: -1}
        self.time_interval = {1: -1, 2: -1}
        self.time_ok_flag = {1: False, 2: False}
        self.state = {1: "waiting", 2: "waiting"}
        self.start_waiting = 0
        self.image = {1: np.zeros((1, 1, 3), dtype=np.uint8), 2: np.zeros((1, 1, 3), dtype=np.uint8)}
        self.temp_image = np.zeros((1, 1, 3), dtype=np.uint8)
        self.index = {1: 1, 2: 1}
        self.ignore_index = 1
        self.existing_class = {1: [], 2: []}
        self.error_picture_list = {1: [], 2: []}
        self.start_time = time.strftime("%Y-%m-%d_%H_%M_%S", time.localtime())
        self.ignore_area_list = {1: [], 2: []}

        self.video_source_1 = video_source_1
        self.video_source_2 = video_source_2
        self.ai_output = {1: [], 2: []}

        self.timer_1 = QTimer()
        self.timer_2 = QTimer()

        self.get_para()
        self.init_slots()
        self.showMaximized()

        self.cam_whe_useful_thread_1 = CameraThread(self.video_source_1)
        self.cam_whe_useful_thread_2 = CameraThread(self.video_source_2)
        self.process_camera()

        now = time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())
        with open('log.txt', 'a') as file:
            file.write(now + '\t' + "软件打开" + '\n')

    def init_slots(self):
        self.pushButton_stopWarning.clicked.connect(self.stop_warning)
        self.pushButton_stopWarning_2.clicked.connect(self.set_waiting_state)
        self.pushButton_outputExcel.clicked.connect(self.output_excel)
        self.pushButton_clear.clicked.connect(self.clear_ignore_area_list)
        self.menu_setting.triggered.connect(self.open_setting)
        self.menu_sizeCalibration.triggered.connect(self.open_size_calibration)

        # 信号的绑定 - 相机 1
        self.camera_thread_1.send_frame.connect(self.display_thread_1.get_fresh_frame)
        self.camera_thread_1.send_frame.connect(self.ai_thread_1.get_frame)
        self.camera_thread_1.send_cameraIsOpen.connect(lambda: self.reopen_camera(1))
        self.ai_thread_1.send_ai_output.connect(self.display_thread_1.get_ai_output)
        self.send_ignore_area_list_1.connect(self.ai_thread_1.get_ignore_area_list)
        self.send_whether_save_video_1.connect(self.camera_thread_1.change_save_state)
        self.display_thread_1.send_displayable_frame.connect(self.update_display_frame_1)
        self.display_thread_1.send_ai_output.connect(self.update_statistic_table_1)
        self.tableWidget_results.cellClicked.connect(self.open_table_picture_1)

        # 信号的绑定 - 相机 2
        self.camera_thread_2.send_frame.connect(self.display_thread_2.get_fresh_frame)
        self.camera_thread_2.send_frame.connect(self.ai_thread_2.get_frame)
        self.camera_thread_2.send_cameraIsOpen.connect(lambda: self.reopen_camera(2))
        self.ai_thread_2.send_ai_output.connect(self.display_thread_2.get_ai_output)
        self.send_ignore_area_list_2.connect(self.ai_thread_2.get_ignore_area_list)
        self.send_whether_save_video_2.connect(self.camera_thread_2.change_save_state)
        self.display_thread_2.send_displayable_frame.connect(self.update_display_frame_2)
        self.display_thread_2.send_ai_output.connect(self.update_statistic_table_2)
        self.tableWidget_results_2.cellClicked.connect(self.open_table_picture_2)

        self.cleanup_thread.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.screen_size_1 = (self.label_display.width(), self.label_display.height())
        self.screen_size_2 = (self.label_display_2.width(), self.label_display_2.height())
        self.display_thread_1.get_screen_size(self.screen_size_1)
        self.display_thread_2.get_screen_size(self.screen_size_2)

    def closeEvent(self, event):
        # 1. 第一时间隐藏窗口，给用户“秒关”的体验
        self.hide()

        # 2. 刷新 GUI 事件循环，确保窗口立刻消失
        QtWidgets.QApplication.processEvents()
        # 3. 记录日志
        now = time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())
        with open('log.txt', 'a') as file:
            file.write(now + '\t' + "软件关闭" + '\n')
        # 4. 释放各个后台资源
        try:
            if self.camera_thread_1.isRunning():
                self.display_thread_1.stop_display()
                self.ai_thread_1.stop_process()
                self.camera_thread_1.stop_capture()
                # 可以在这里增加一点微小的延时或不再强求 wait()，防止底层 C++ 卡死
            if self.camera_thread_2.isRunning():
                self.display_thread_2.stop_display()
                self.ai_thread_2.stop_process()
                self.camera_thread_2.stop_capture()
            self.cleanup_thread.stop()

            if self.modbus_whether_on:
                self.modbus_thread.stop_output_state()
        except Exception as e:
            print(f"关闭线程时发生异常: {e}")
        with open('log.txt', 'a') as file:
            file.write(now + '\t' + "软件彻底关闭" + '\n')
        # 5. 接受关闭事件，正式退出进程
        event.accept()

    def get_para(self):
        p = para.load()
        self.detected_object = p["detected object"]
        self.warning_object = p["warning object"]
        self.conf_thr = p["confidence"]
        self.iou_thr = p["iou"]
        self.focus = p["focus"]
        self.model_name = p["model name"]
        self.modbus_whether_on = not (p["modbus"] == 0)
        self.ai_task = self.get_ai_task()
        self.save_error_path = p["save error path"].replace(" ", "")
        self.exist_object_time = p["exist object time"]
        self.no_object_time = p["no object time"]
        self.object_interval_time = p["object interval time"]
        self.scale = p["scale"]
        self.vortex_min_size = p["vortex min size"]
        self.save_flag = not (p["whether save video"] == 0)
        self.save_video_object = p["save video object"]
        self.ignore_area_size = p["ignore size"]
        self.auto_modbus_ip = p["auto_modbus_ip"]
        if self.auto_modbus_ip:
            self.init_ip()

        if self.ai_thread_1.isRunning():
            self.ai_thread_1.set_confidence_threshold(self.conf_thr)
            self.ai_thread_1.set_iou_threshold(self.iou_thr)
        if self.ai_thread_2.isRunning():
            self.ai_thread_2.set_confidence_threshold(self.conf_thr)
            self.ai_thread_2.set_iou_threshold(self.iou_thr)

        if self.modbus_thread.isRunning():
            if not self.modbus_whether_on:
                self.modbus_thread.stop_output_state()
        else:
            if self.modbus_whether_on:
                self.modbus_thread.set_start_config(self.ai_task)
                self.modbus_thread.start()
        mkdir(self.save_error_path)

    def init_ip(self):
        self.ip = get_modbus_ip()
        if self.ip == "0":
            QMessageBox.warning(self, "警告", "检测到多个ip地址，请手动设置modbus的IP地址！(或者采用网络摄像头请忽视)",
                                QMessageBox.Ok)
        if self.ip.startswith("192.168."):
            para.set_param({"modbus_ip": self.ip})
            with open('log_ip.txt', 'a') as file:
                file.write("ip更改成功")
            return
        with open('log_ip.txt', 'a') as file:
            file.write("未更改ip")

    def open_setting(self):
        set_menu = SettingsWindow()
        set_menu.signal.connect(self.get_para)
        set_menu.show()

    def open_size_calibration(self):
        if hasattr(self, 'menu1'):
            self.menu1.close()
            del self.menu1
        self.menu1 = Menu1(self.image[1])  # 默认传相机1的图像进行标定

        self.camera_thread_1.send_frame.connect(self.menu1.get_ori_frame)
        self.camera_thread_1.send_frame.connect(self.menu1.ai_find_circle.get_frame)

        if self.ai_thread_1.isRunning():
            self.ai_thread_1.pause_continue_process()
            self.menu1.signal.connect(self.ai_thread_1.pause_continue_process)
        self.menu1.show()

    def process_camera(self):
        """ 判断摄像头是否可用，是则启动拍摄检测线程 """
        self.label_display.setText('<font color="white">正在尝试连接摄像头 1...</font>')
        self.label_display.setAlignment(Qt.AlignCenter)
        self.label_display_2.setText('<font color="white">正在尝试连接摄像头 2...</font>')
        self.label_display_2.setAlignment(Qt.AlignCenter)

        if not self.timer_1.isActive():
            self.cam_whe_useful_thread_1.opened.connect(lambda: self.start_thread(1))
            self.timer_1.setSingleShot(True)
            self.timer_1.timeout.connect(lambda: self.on_timeout(1))
            self.timer_1.start(5000)
            self.cam_whe_useful_thread_1.start()

        if not self.timer_2.isActive():
            self.cam_whe_useful_thread_2.opened.connect(lambda: self.start_thread(2))
            self.timer_2.setSingleShot(True)
            self.timer_2.timeout.connect(lambda: self.on_timeout(2))
            self.timer_2.start(5000)
            self.cam_whe_useful_thread_2.start()

    def start_thread(self, cam_id):
        if cam_id == 1:
            self.timer_1.stop()
            self.ai_thread_1.set_start_config(ai_task=self.ai_task, model_name=self.model_name,
                                              confidence_threshold=self.conf_thr, iou_threshold=self.iou_thr)
            self.camera_thread_1.set_start_config(video_source=self.video_source_1, ai_task=self.ai_task)
            self.display_thread_1.set_start_config([self.label_display.width(), self.label_display.height()])
            if not self.ai_thread_1.isRunning():
                self.ai_thread_1.start()
                self.display_thread_1.start()
                self.camera_thread_1.start()
        elif cam_id == 2:
            self.timer_2.stop()
            self.ai_thread_2.set_start_config(ai_task=self.ai_task, model_name=self.model_name,
                                              confidence_threshold=self.conf_thr, iou_threshold=self.iou_thr)
            self.camera_thread_2.set_start_config(video_source=self.video_source_2, ai_task=self.ai_task)
            self.display_thread_2.set_start_config([self.label_display_2.width(), self.label_display_2.height()])
            if not self.ai_thread_2.isRunning():
                self.ai_thread_2.start()
                self.display_thread_2.start()
                self.camera_thread_2.start()

        if self.modbus_whether_on and not self.modbus_thread.isRunning():
            self.modbus_thread.set_start_config(self.ai_task)
            self.modbus_thread.start()

    def on_timeout(self, cam_id):
        if cam_id == 1:
            self.timer_1.stop()
            self.label_display.setText('<font color="white">连接摄像头 1 失败，请检查接线...</font>')
        else:
            self.timer_2.stop()
            self.label_display_2.setText('<font color="white">连接摄像头 2 失败，请检查接线...</font>')
        # QMessageBox.warning(self, "警告", f"摄像头 {cam_id} 未连接或无法打开")

    def reopen_camera(self, cam_id):
        if cam_id == 1:
            self.cam_whe_useful_thread_1.start()
        else:
            self.cam_whe_useful_thread_2.start()

    def update_parameter(self, x, flag):
        if flag == 'SpinBox_focus':
            self.horizontalSlider_focus.setValue(x)
            self.focus = x
        elif flag == 'horizontalSlider_focus':
            self.spinBox_focus.setValue(x)
            self.focus = x
        self.camera_thread_1.get_video_focus(self.focus)
        self.camera_thread_2.get_video_focus(self.focus)

    def get_ai_task(self):
        task = para.load()["detected task"].lower().replace(" ", "")
        if task in ["detection", "object_detection", "detect", "d"]:
            return "object_detection"
        elif task in ["save_picture", "savepicture", "save", "s"]:
            return "save_picture"
        elif task in ["both", "all", "b"]:
            return "both"
        elif task in ["none", "nothing", "n", ""]:
            return "none"

    def stop_warning(self):
        """ 忽略异常按钮逻辑 """
        if self.state[1] == "ng" or self.state[2] == "ng":
            reply = QMessageBox.question(self, "提示", "检测到异常，是否选择忽略该区域继续执行检测？",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                if self.state[1] == "ng": self.add_ignore_area(1)
                if self.state[2] == "ng": self.add_ignore_area(2)

                # 【核心修复】：忽略后，强制重置出错相机的状态，并清空缓存，以便立刻检测画面中的其他区域
                if self.state[1] == "ng": self.state[1] = "ok"
                if self.state[2] == "ng": self.state[2] = "ok"
                self.existing_class = {1: [], 2: []}
                self.update_global_state()
            else:
                self.set_waiting_state()

    def set_waiting_state(self):
        """ 挂起 / 恢复 按钮逻辑 """
        if self.start_waiting == 0:
            # 触发【挂起】操作
            self.start_waiting = 1
            self.pushButton_stopWarning_2.setText("恢复")
            # 将两个相机状态全部强置为 waiting
            self.state[1] = "waiting"
            self.state[2] = "waiting"
            self.update_global_state()  # 这里会把右上角图标变成蓝色 "等待中..."
        else:
            # 触发【恢复】操作
            self.start_waiting = 0
            self.pushButton_stopWarning_2.setText("挂起")

            # 【核心修复】：恢复时，强制把状态切回 ok，并彻底清空历史计时和缺陷列表
            # 这样就算画面里还存在缺陷，代码也会把它当做“新缺陷”立刻触发红色报警
            self.state[1] = "ok"
            self.state[2] = "ok"
            self.existing_class = {1: [], 2: []}
            self.time_ng = {1: -1, 2: -1}
            self.time_ok = {1: -1, 2: -1}
            self.update_global_state()  # 先恢复绿色，如果下半秒立刻检测到缺陷会自动切成红色

    def output_excel(self):
        end_time = time.strftime("%Y-%m-%d_%H_%M_%S", time.localtime())
        save_xlsx_name = self.start_time + "——" + end_time + "缺陷数据"
        xlsx_path, tmp = QFileDialog.getSaveFileName(self, "保存文件", save_xlsx_name, "*.xlsx")
        if xlsx_path == "":
            return

        num, cla, conf, dt, cam = [], [], [], [], []

        # 提取表 1 数据
        row_count_1 = self.tableWidget_results.rowCount()
        for row in range(row_count_1):
            num.append(self.tableWidget_results.item(row, 0).text())
            cla.append(self.class_to_chinese(self.tableWidget_results.item(row, 1).text()))
            conf.append(self.tableWidget_results.item(row, 2).text())
            dt.append(self.tableWidget_results.item(row, 3).text())
            cam.append("相机1")

        # 提取表 2 数据
        row_count_2 = self.tableWidget_results_2.rowCount()
        for row in range(row_count_2):
            num.append(self.tableWidget_results_2.item(row, 0).text())
            cla.append(self.class_to_chinese(self.tableWidget_results_2.item(row, 1).text()))
            conf.append(self.tableWidget_results_2.item(row, 2).text())
            dt.append(self.tableWidget_results_2.item(row, 3).text())
            cam.append("相机2")

        series = {
            "序号": num,
            "类别": cla,
            "置信度": conf,
            "时间": dt,
            "来源": cam
        }
        df = pd.DataFrame(series)
        df.to_excel(xlsx_path, index=False)
        QMessageBox.information(self, "提示", "输出xlsx成功")

        self.index = {1: 1, 2: 1}
        self.clean_table()
        self.start_time = end_time

    def add_ignore_area(self, cam_id):
        for output in self.ai_output[cam_id]:
            box = output["bbox"]
            center = [int((box[0] + box[2]) / 2), int((box[1] + box[3]) / 2)]
            self.ignore_area_list[cam_id].append({"class": output["class"], "center": center})
            self.update_ignore_table(f"{output['class']}(Cam {cam_id})", center)

        if cam_id == 1:
            self.send_ignore_area_list_1.emit(self.ignore_area_list[1])
        else:
            self.send_ignore_area_list_2.emit(self.ignore_area_list[2])

    def draw_transparency_square(self, image, cam_id):
        if self.ignore_area_list[cam_id]:
            alpha = 0.4
            for area in self.ignore_area_list[cam_id]:
                top_left = (area["center"][0] - self.ignore_area_size, area["center"][1] - self.ignore_area_size)
                bottom_right = (area["center"][0] + self.ignore_area_size, area["center"][1] + self.ignore_area_size)

                # 边界保护
                h, w = image.shape[:2]
                x1, y1 = max(0, top_left[0]), max(0, top_left[1])
                x2, y2 = min(w, bottom_right[0]), min(h, bottom_right[1])

                roi = image[y1:y2, x1:x2]
                if roi.size == 0: continue

                square = np.zeros_like(roi, dtype=np.uint8)
                color = (0, 255, 0)
                cv2.rectangle(square, (0, 0), (x2 - x1, y2 - y1), color, -1)
                cv2.addWeighted(square, alpha, roi, 1 - alpha, 0, roi)
        return image

    def clear_ignore_area_list(self):
        self.ignore_area_list = {1: [], 2: []}
        self.send_ignore_area_list_1.emit([])
        self.send_ignore_area_list_2.emit([])
        while self.tableWidget_ignore.rowCount() > 0:
            self.tableWidget_ignore.removeRow(0)

    def update_display_frame_1(self, image):
        self.image[1] = image.copy()
        image = self.draw_transparency_square(image, 1)
        showImage = self.cvToQImage(self.showPicture(image, self.label_display.height(), self.label_display.width()))
        self.label_display.setPixmap(QtGui.QPixmap.fromImage(showImage))

    def update_display_frame_2(self, image):
        self.image[2] = image.copy()
        image = self.draw_transparency_square(image, 2)
        showImage = self.cvToQImage(
            self.showPicture(image, self.label_display_2.height(), self.label_display_2.width()))
        self.label_display_2.setPixmap(QtGui.QPixmap.fromImage(showImage))

    def clean_table(self):
        while self.tableWidget_results.rowCount() > 0:
            self.tableWidget_results.removeRow(0)
        while self.tableWidget_results_2.rowCount() > 0:
            self.tableWidget_results_2.removeRow(0)

    def class_to_chinese(self, name):
        if name in "vortex":
            return "旋涡"
        elif name == "abnormal":
            return "异常出丝"
        elif name == "oil":
            return "油污"
        elif name == "person":
            return "人"
        else:
            return str(name)

    def update_statistic_table_1(self, ai_output):
        self._process_statistic_table(ai_output, 1)

    def update_statistic_table_2(self, ai_output):
        self._process_statistic_table(ai_output, 2)

    def _process_statistic_table(self, ai_output, cam_id):
        self.ai_output[cam_id] = ai_output
        tem = 0

        table = self.tableWidget_results if cam_id == 1 else self.tableWidget_results_2
        label_err = self.label_display_error if cam_id == 1 else self.label_display_error_2

        if self.start_waiting == 0:
            contain_object = any(item.get('class') in self.detected_object for item in ai_output)
            if contain_object and self.state[cam_id] != "waiting":
                self.time_ok[cam_id] = -1
                self.time_ok_flag[cam_id] = False
                if self.time_ng[cam_id] == -1:
                    self.time_ng[cam_id] = time.time()
                elif time.time() - self.time_ng[cam_id] > self.exist_object_time:
                    current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    for box in ai_output:
                        if box["class"] not in self.detected_object: continue
                        box = self.filter_vortex(box)
                        if box != []:
                            class_name = self.class_to_chinese(box["class"])
                            each_item = [class_name, "{:.1f}%".format(box["confidence"] * 100),
                                         str(current_time)]
                            if box["class"] not in self.existing_class[cam_id]:
                                self.time_interval[cam_id] = -1
                                self.index[cam_id] += 1
                                tem = 1
                                row = table.rowCount()
                                table.insertRow(row)
                                self.existing_class[cam_id].append(box["class"])
                                for j in range(len(each_item)):
                                    item = QtWidgets.QTableWidgetItem(str(each_item[j]))
                                    item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
                                    table.setItem(row, j, item)

                    table.verticalScrollBar().setValue(table.verticalScrollBar().maximum())

                    if self.image[cam_id].shape[0] != 1:
                        showImage = self.cvToQImage(
                            self.showPicture(self.image[cam_id], label_err.height(), label_err.width()))
                        label_err.setPixmap(QtGui.QPixmap.fromImage(showImage))

                    if tem == 1:
                        self.process_ng(ai_output, cam_id)
                        if self.save_error_path != "":
                            picture_name = f"ERROR_C{cam_id}_" + current_time.replace(" ", "_").replace(":",
                                                                                                        "_") + ".jpg"
                            self.error_picture_list[cam_id].append(picture_name)
                            save_error_path = os.path.join(self.save_error_path, picture_name)
                            cv2.imwrite(save_error_path, self.image[cam_id])
            else:
                if self.time_interval[cam_id] == -1:
                    self.time_interval[cam_id] = time.time()
                elif self.existing_class[cam_id] != [] and time.time() - self.time_interval[
                    cam_id] > self.object_interval_time:
                    self.existing_class[cam_id] = []
                self.time_ng[cam_id] = -1
                if self.time_ok[cam_id] == -1 and not contain_object:
                    self.time_ok[cam_id] = time.time()
                    self.time_ok_flag[cam_id] = True
                elif self.time_ok_flag[cam_id] and time.time() - self.time_ok[cam_id] > self.no_object_time:
                    self.state[cam_id] = "ok"
                    self.update_global_state()
                    if cam_id == 1:
                        self.send_whether_save_video_1.emit(False)
                    else:
                        self.send_whether_save_video_2.emit(False)

    def update_global_state(self):
        """ 综合评估两台相机的状态来更新总状态标签及Modbus """
        if self.state[1] == "ng" or self.state[2] == "ng":
            self.label.setStyleSheet("background-color: rgb(255, 0, 0);")
            self.label.setText("报错")
            if self.modbus_whether_on:
                self.modbus_thread.get_state("ng")
        elif self.state[1] == "waiting" and self.state[2] == "waiting":
            self.label.setStyleSheet("background-color: rgb(40, 90, 255);")
            self.label.setText("等待中...")
            if self.modbus_whether_on:
                self.modbus_thread.get_state("waiting")
        else:
            self.label.setStyleSheet("background-color: rgb(0, 255, 0);")
            self.label.setText("正常")
            if self.modbus_whether_on:
                self.modbus_thread.get_state("ok")

    def process_ng(self, ai_output, cam_id):
        for box in ai_output:
            if box["class"] in self.warning_object:
                self.state[cam_id] = "ng"
                self.update_global_state()

        whether_save_video = any(item.get('class') in self.save_video_object for item in ai_output)
        if self.save_flag and whether_save_video:
            if cam_id == 1:
                self.send_whether_save_video_1.emit(True)
            else:
                self.send_whether_save_video_2.emit(True)
        else:
            if cam_id == 1:
                self.send_whether_save_video_1.emit(False)
            else:
                self.send_whether_save_video_2.emit(False)

    def update_ignore_table(self, class_name, center):
        current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        each_item = [str(self.ignore_index), class_name, str(center), current_time]
        self.ignore_index += 1
        row = self.tableWidget_ignore.rowCount()
        self.tableWidget_ignore.insertRow(row)
        for j in range(len(each_item)):
            item = QtWidgets.QTableWidgetItem(str(each_item[j]))
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            self.tableWidget_ignore.setItem(row, j, item)
        self.tableWidget_ignore.verticalScrollBar().setValue(self.tableWidget_ignore.verticalScrollBar().maximum())

    def open_table_picture_1(self, row):
        self._open_table_picture(row, 1)

    def open_table_picture_2(self, row):
        self._open_table_picture(row, 2)

    def _open_table_picture(self, row, cam_id):
        label_err = self.label_display_error if cam_id == 1 else self.label_display_error_2
        if self.save_error_path != "":
            if row < len(self.error_picture_list[cam_id]):
                try:
                    image = cv2.imread(os.path.join(self.save_error_path, self.error_picture_list[cam_id][row]))
                    showImage = self.cvToQImage(self.showPicture(image, label_err.height(), label_err.width()))
                    label_err.setPixmap(QtGui.QPixmap.fromImage(showImage))
                except:
                    print(f"图片 {cam_id} 打开失败")

    def filter_vortex(self, box):
        if box["class"] != "vortex": return box
        dx = box["bbox"][2] - box["bbox"][0]
        dy = box["bbox"][3] - box["bbox"][1]
        pixel_size = int(max(dx, dy))
        if pixel_size * self.scale >= self.vortex_min_size:
            return box
        else:
            return []

    def cvToQImage(self, image):
        h, w, pix = image.shape[0], image.shape[1], image.strides[0]
        channels = 1 if len(image.shape) == 2 else image.shape[2]
        if channels == 3:
            qImg = QImage(image.data, w, h, pix, QImage.Format.Format_RGB888)
            return qImg.rgbSwapped()
        elif channels == 1:
            qImg = QImage(image.data, w, h, pix, QImage.Format.Format_Indexed8)
            return qImg
        else:
            QtCore.qDebug("错误: numpy.ndarray无法转换为QImage格式. Channels = %d" % image.shape[2])
            return QImage()

    def showPicture(self, img, h, w):
        height = img.shape[0]
        width = img.shape[1]
        if height / width > h / w:
            k = h / height
            resize_img = cv2.resize(img, None, None, k, k)
            num = abs(int((w - resize_img.shape[1]) / 2))
            n = (w - resize_img.shape[1]) % 2
            re_img = cv2.copyMakeBorder(resize_img, 0, 0, num + n, num, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        else:
            k = w / width
            resize_img = cv2.resize(img, None, None, k, k)
            num = abs(int((h - resize_img.shape[0]) / 2))
            n = (h - resize_img.shape[0]) % 2
            re_img = cv2.copyMakeBorder(resize_img, num + n, num, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        return re_img

    def save_picture(self, path, picture):
        now = time.strftime("%Y-%m-%d_%H_%M_%S", time.localtime())
        now_date = now[0:10]
        now_h = now[11:13]
        now_name = now
        data_dir = path + "/" + now_date
        mkdir(data_dir)
        h_dir = data_dir + "/" + now_h
        mkdir(h_dir)
        cv2.imwrite(h_dir + "/" + "Picture-{}.jpg".format(now_name), picture)


# ==========================================
# 下面保留原有的 SettingsWindow, Menu1, ParamSave, mkdir
# 由于这部分主要是参数读写和标定UI功能，未强制依赖相机双通道，无需改动即可完美适配。
# ==========================================

class SettingsWindow(QDialog, Ui_Dialog):
    signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setupUi(self)
        self.get_parameter()
        self.init_slots()

    def closeEvent(self, event):
        self.signal.emit()
        super().closeEvent(event)

    def get_parameter(self):
        parameters = para.param_kw
        self.warning_object = parameters["warning object"]
        self.detected_task = parameters["detected task"]
        self.whether_save_video = parameters["whether save video"]
        self.save_video_object = parameters["save video object"]
        self.save_picture_inteval = parameters["save picture interval"]
        self.exist_object_time = parameters["exist object time"]
        self.no_object_time = parameters["no object time"]
        self.object_interval_time = parameters["object interval time"]
        self.vortex_min_size = parameters["vortex min size"]
        self.confidence = parameters["confidence"]
        self.iou = parameters["iou"]
        self.waitkey_time = parameters["waitkey time"]
        self.modbus = parameters["modbus"]
        self.set_parameters()

    def init_slots(self):
        self.pushButton_setPara.clicked.connect(lambda x: self.set_parameters(save=True))
        self.pushButton_setDefault.clicked.connect(self.set_default)
        self.radioButton_startWarning.clicked.connect(lambda x: self.set_function("warning"))
        self.radioButton_startSavePicture.clicked.connect(lambda x: self.set_function("save_video"))
        self.radioButton_abnormal.clicked.connect(lambda x: self.set_function("abnormal"))
        self.radioButton_vortex.clicked.connect(lambda x: self.set_function("vortex"))
        self.radioButton_oil.clicked.connect(lambda x: self.set_function("oil"))
        self.radioButton_abnormal_warning.clicked.connect(lambda x: self.set_function("abnormal_warning"))
        self.radioButton_vortex_warning.clicked.connect(lambda x: self.set_function("vortex_warning"))
        self.radioButton_oil_warning.clicked.connect(lambda x: self.set_function("oil_warning"))
        self.comboBox.currentIndexChanged.connect(lambda x: self.set_function("mode"))
        self.doubleSpinBox_conf.valueChanged.connect(lambda x: self.update_parameter(x, 'doubleSpinBox_conf'))
        self.spinBox_interval.valueChanged.connect(lambda x: self.update_parameter(x, 'doubleSpinBox_interval'))
        self.doubleSpinBox_iou.valueChanged.connect(lambda x: self.update_parameter(x, 'doubleSpinBox_iou'))
        self.horizontalSlider_conf.valueChanged.connect(lambda x: self.update_parameter(x, 'horizontalSlider_conf'))
        self.horizontalSlider_interval.valueChanged.connect(
            lambda x: self.update_parameter(x, 'horizontalSlider_interval'))
        self.horizontalSlider_iou.valueChanged.connect(lambda x: self.update_parameter(x, 'horizontalSlider_iou'))
        self.spinBox_timeForStartWarning.valueChanged.connect(
            lambda x: self.update_parameter(x, 'spinBox_timeForStartWarning'))
        self.spinBox_timeForStopWarning.valueChanged.connect(
            lambda x: self.update_parameter(x, 'spinBox_timeForStopWarning'))
        self.spinBox_savePictureInterval.valueChanged.connect(
            lambda x: self.update_parameter(x, 'spinBox_savePictureInterval'))
        self.spinBox_timeForObjectIntervalTime.valueChanged.connect(
            lambda x: self.update_parameter(x, 'spinBox_timeForObjectIntervalTime'))
        self.doubleSpinBox_vortexMinSize.valueChanged.connect(
            lambda x: self.update_parameter(x, 'doubleSpinBox_vortexMinSize'))

    def update_parameter(self, x, flag):
        if flag == 'doubleSpinBox_conf':
            self.horizontalSlider_conf.setValue(int(x * 100))
            self.confidence = float(x)
        elif flag == 'doubleSpinBox_interval':
            self.horizontalSlider_interval.setValue(int(x))
            self.waitkey_time = int(x)
        elif flag == 'doubleSpinBox_iou':
            self.horizontalSlider_iou.setValue(int(x * 100))
            self.iou = float(x)
        elif flag == 'horizontalSlider_conf':
            self.doubleSpinBox_conf.setValue(x / 100)
            self.confidence = float(x / 100)
        elif flag == 'horizontalSlider_interval':
            self.spinBox_interval.setValue(x)
            self.waitkey_time = int(x)
        elif flag == 'horizontalSlider_iou':
            self.doubleSpinBox_iou.setValue(x / 100)
            self.iou = float(x / 100)
        elif flag == 'spinBox_timeForStartWarning':
            self.exist_object_time = x
        elif flag == 'spinBox_timeForStopWarning':
            self.no_object_time = x
        elif flag == 'spinBox_savePictureInterval':
            self.save_picture_inteval = x
        elif flag == 'spinBox_timeForObjectIntervalTime':
            self.object_interval_time = x
        elif flag == 'doubleSpinBox_vortexMinSize':
            self.vortex_min_size = x

    def set_parameters(self, save=False):
        self.get_ai_task(self.detected_task)
        self.radioButton_startSavePicture.setChecked(not (self.whether_save_video == 0))
        self.radioButton_startWarning.setChecked(not (self.modbus == 0))
        self.spinBox_timeForStartWarning.setValue(self.exist_object_time)
        self.spinBox_timeForStopWarning.setValue(self.no_object_time)
        self.spinBox_timeForObjectIntervalTime.setValue(self.object_interval_time)
        self.spinBox_savePictureInterval.setValue(self.save_picture_inteval)
        self.doubleSpinBox_vortexMinSize.setValue(self.vortex_min_size)
        self.doubleSpinBox_conf.setValue(self.confidence)
        self.horizontalSlider_conf.setValue(int(self.confidence * 100))
        self.doubleSpinBox_iou.setValue(self.iou)
        self.horizontalSlider_iou.setValue(int(self.iou * 100))
        self.spinBox_interval.setValue(self.waitkey_time)
        self.horizontalSlider_interval.setValue(self.waitkey_time)

        self.radioButton_abnormal.setChecked("abnormal" in self.save_video_object)
        self.radioButton_vortex.setChecked("vortex" in self.save_video_object)
        self.radioButton_oil.setChecked("oil" in self.save_video_object)
        self.radioButton_abnormal_warning.setChecked("abnormal" in self.warning_object)
        self.radioButton_vortex_warning.setChecked("vortex" in self.warning_object)
        self.radioButton_oil_warning.setChecked("oil" in self.warning_object)
        if save:
            para.set_param({
                "warning object": self.warning_object,
                "detected task": self.detected_task,
                "whether save video": self.whether_save_video,
                "save video object": self.save_video_object,
                "save picture interval": self.save_picture_inteval,
                "exist object time": self.exist_object_time,
                "no object time": self.no_object_time,
                "object interval time": self.object_interval_time,
                "vortex min size": self.vortex_min_size,
                "confidence": self.confidence,
                "iou": self.iou,
                "waitkey time": self.waitkey_time,
                "modbus": self.modbus
            })
            para.save()
            QMessageBox.information(self, "提示", "参数更改成功！", QMessageBox.StandardButton.Ok)

    def set_default(self):
        p = para.original_para
        default_para = {
            "detected task": p["detected task"],
            "whether save video": p["whether save video"],
            "save picture interval": p["save picture interval"],
            "exist object time": p["exist object time"],
            "no object time": p["no object time"],
            "object interval time": p["object interval time"],
            "vortex min size": p["vortex min size"],
            "confidence": p["confidence"],
            "iou": p["iou"],
            "waitkey time": p["waitkey time"],
            "modbus": p["modbus"]
        }
        for key, value in default_para.items():
            para.set_param({key: value})
        para.save()
        self.get_parameter()
        QMessageBox.information(self, "提示", "已恢复默认设置参数！", QMessageBox.StandardButton.Ok)

    def set_function(self, flag):
        if flag == "warning":
            self.modbus = 1 if self.radioButton_startWarning.isChecked() else 0
        if flag == "save_video":
            self.whether_save_video = 1 if self.radioButton_startSavePicture.isChecked() else 0
        if flag == "mode":
            index = self.comboBox.currentIndex()
            if index == 0:
                self.detected_task = "save_picture"
            elif index == 1:
                self.detected_task = "detection"
            elif index == 2:
                self.detected_task = "both"
            elif index == 3:
                self.detected_task = "none"
        if flag == "abnormal":
            if self.radioButton_abnormal.isChecked():
                if "abnormal" not in self.save_video_object: self.save_video_object += "abnormal"
            else:
                if "abnormal" in self.save_video_object: self.save_video_object = self.save_video_object.replace(
                    "abnormal", "")
        if flag == "vortex":
            if self.radioButton_vortex.isChecked():
                if "vortex" not in self.save_video_object: self.save_video_object += "vortex"
            else:
                if "vortex" in self.save_video_object: self.save_video_object = self.save_video_object.replace("vortex",
                                                                                                               "")
        if flag == "oil":
            if self.radioButton_oil.isChecked():
                if "oil" not in self.save_video_object: self.save_video_object += "oil"
            else:
                if "oil" in self.save_video_object: self.save_video_object = self.save_video_object.replace("oil", "")
        if flag == "abnormal_warning":
            if self.radioButton_abnormal_warning.isChecked():
                if "abnormal" not in self.warning_object: self.warning_object += "abnormal"
            else:
                if "abnormal" in self.warning_object: self.warning_object = self.warning_object.replace("abnormal", "")
        if flag == "vortex_warning":
            if self.radioButton_vortex_warning.isChecked():
                if "vortex" not in self.warning_object: self.warning_object += "vortex"
            else:
                if "vortex" in self.warning_object: self.warning_object = self.warning_object.replace("vortex", "")
        if flag == "oil_warning":
            if self.radioButton_oil_warning.isChecked():
                if "oil" not in self.warning_object: self.warning_object += "oil"
            else:
                if "oil" in self.warning_object: self.warning_object = self.warning_object.replace("oil", "")

    def get_ai_task(self, task):
        task = task.lower().replace(" ", "")
        if task in ["detection", "object_detection", "detect", "d"]:
            self.comboBox.setCurrentIndex(1)
        elif task in ["save_picture", "savepicture", "save", "s"]:
            self.comboBox.setCurrentIndex(0)
        elif task in ["both", "all", "b"]:
            self.comboBox.setCurrentIndex(2)
        elif task in ["none", "nothing", "n", ""]:
            self.comboBox.setCurrentIndex(3)


class Menu1(QDialog, Ui_Menu1):
    signal = pyqtSignal(float)

    def __init__(self, image):
        super().__init__()
        self.setupUi(self)
        self.show()
        self.img = image
        self.scale = para.load()["scale"]
        self.threadFlag = True
        self.r = 0
        self.model_name = "yolov8n_circle"
        self.idx_frame = 0
        self.mode = "auto"
        self.ai_find_circle = AiWorkerThread2()
        self.original_label_showPicture = self.findChild(QLabel, "label_showPicture")
        self.manual_label_showPicture = self.ImageLabel(self)
        self.manual_label_showPicture.setGeometry(self.original_label_showPicture.geometry())
        self.manual_label_showPicture.setVisible(False)
        self.init_slots()
        self.k = self.get_k()
        self.setWindowFlags(QtCore.Qt.WindowType.WindowStaysOnTopHint)

    def closeEvent(self, event):
        self.threadFlag = False
        para.save()
        self.signal.emit(self.scale)
        super().closeEvent(event)

    def init_slots(self):
        self.pushButton_calibration.clicked.connect(self.calibration)
        self.pushButton_changemode.clicked.connect(self.change_mode)
        self.ai_find_circle.send_ai_output.connect(self.get_results)
        self.manual_label_showPicture.send_r.connect(self.change_det_r)
        self.label_scale.setText(str(self.scale))
        self.ai_find_circle.set_start_config(model_name=self.model_name)
        if cv2.VideoCapture(video_source_1).isOpened():
            self.ai_find_circle.start()

    def get_k(self):
        height, width = self.img.shape[:2]
        if height != 1:
            w = self.label_showPicture.width()
            h = self.label_showPicture.height()
            if height / width > h / w:
                return height / h
            else:
                return width / w

    def change_det_r(self, r):
        self.r = r
        if self.r != 0:
            self.label_lengthPixel.setText(str(round(self.r * self.k * 2, 1)))

    def get_results(self, result):
        if self.threadFlag:
            img = result[1]
            self.change_det_r(result[0])
            qImg = self.cvToQImage(
                self.showPicture(img, self.label_showPicture.height(), self.label_showPicture.width()))
            self.original_label_showPicture.setScaledContents(True)
            self.original_label_showPicture.setPixmap(QPixmap.fromImage(qImg))

    def get_ori_frame(self, frame):
        if self.mode == "auto":
            pass
        else:
            self.manual_label_showPicture.set_image(frame[1])

    def change_mode(self):
        if self.mode == "auto":
            self.mode = "manual"
            if self.ai_find_circle.isRunning():
                self.ai_find_circle.stop_process()
            self.manual_draw_circle()
            self.label_mode.setText("手动")
        else:
            self.mode = "auto"
            self.restore_original_label()
            self.ai_find_circle.set_start_config(model_name=self.model_name)
            if cv2.VideoCapture(video_source_1).isOpened():
                self.ai_find_circle.start()
            self.label_mode.setText("自动")

    def manual_draw_circle(self):
        self.layout().replaceWidget(self.original_label_showPicture, self.manual_label_showPicture)
        self.original_label_showPicture.setVisible(False)
        self.manual_label_showPicture.setVisible(True)

    def restore_original_label(self):
        self.layout().replaceWidget(self.manual_label_showPicture, self.original_label_showPicture)
        self.original_label_showPicture.setVisible(True)
        self.manual_label_showPicture.setVisible(False)

    class ImageLabel(QLabel):
        send_r = pyqtSignal(int)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAlignment(Qt.AlignCenter)
            self.pixmap_loaded = False
            self.points = []
            self.temp_point = None
            self.original_pixmap = None
            self.setMouseTracking(True)

        def set_image(self, image):
            if image is not None:
                self.original_pixmap = image
                self.resize_image()
                self.pixmap_loaded = True

        def resize_image(self):
            if self.original_pixmap is not None:
                scaled_pixmap = self.cvToQImage(self.showPicture(self.original_pixmap, self.height(), self.width()))
                self.setPixmap(QPixmap.fromImage(scaled_pixmap))

        def mousePressEvent(self, event):
            if self.pixmap_loaded:
                if event.button() == Qt.RightButton:
                    self.points.clear()
                    self.temp_point = None
                    self.update()
                elif event.button() == Qt.LeftButton:
                    if len(self.points) < 2:
                        self.points.append(event.pos())
                        self.temp_point = None
                    if len(self.points) == 2:
                        self.update()

        def mouseMoveEvent(self, event):
            if self.pixmap_loaded and len(self.points) == 1:
                self.temp_point = event.pos()
                self.update()

        def paintEvent(self, event):
            super().paintEvent(event)
            if len(self.points) == 1 and self.temp_point:
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
                self.send_r.emit(radius)
                painter.drawEllipse(center, radius, radius)
                painter.end()

        def draw_arrowhead(self, painter, p1, p2):
            angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
            arrow_size = 10
            p1_arrow = QPoint(
                int(p2.x() - arrow_size * math.cos(angle - math.pi / 6)),
                int(p2.y() - arrow_size * math.sin(angle - math.pi / 6))
            )
            p2_arrow = QPoint(
                int(p2.x() - arrow_size * math.cos(angle + math.pi / 6)),
                int(p2.y() - arrow_size * math.sin(angle + math.pi / 6))
            )
            painter.drawLine(p2, p1_arrow)
            painter.drawLine(p2, p2_arrow)

        def resizeEvent(self, event):
            self.resize_image()
            super().resizeEvent(event)

        def cvToQImage(self, image):
            h, w, pix = image.shape[0], image.shape[1], image.strides[0]
            channels = 1 if len(image.shape) == 2 else image.shape[2]
            if channels == 3:
                qImg = QImage(image.data, w, h, pix, QImage.Format.Format_RGB888)
                return qImg.rgbSwapped()
            elif channels == 1:
                qImg = QImage(image.data, w, h, pix, QImage.Format.Format_Indexed8)
                return qImg
            else:
                return QImage()

        def showPicture(self, img, h, w):
            height = img.shape[0]
            width = img.shape[1]
            if height / width > h / w:
                k = h / height
                resize_img = cv2.resize(img, None, None, k, k)
                num = abs(int((w - resize_img.shape[1]) / 2))
                n = (w - resize_img.shape[1]) % 2
                re_img = cv2.copyMakeBorder(resize_img, 0, 0, num + n, num, cv2.BORDER_CONSTANT, value=(0, 0, 0))
            else:
                k = w / width
                resize_img = cv2.resize(img, None, None, k, k)
                num = abs(int((h - resize_img.shape[0]) / 2))
                n = (h - resize_img.shape[0]) % 2
                re_img = cv2.copyMakeBorder(resize_img, num + n, num, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
            return re_img

    def getActualLength(self):
        unit = self.comboBox.currentIndex()
        if unit == 0:
            actual_length = self.doubleSpinBox.value()
        elif unit == 1:
            actual_length = self.doubleSpinBox.value() * 10
        else:
            actual_length = self.doubleSpinBox.value() * 1000
        return actual_length

    def loadPicture(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open Image", "./picture/", "*.png *.jpg")
        if len(filename) != 0:
            self.img = cv2.imdecode(np.fromfile(filename, dtype=np.uint8), cv2.IMREAD_COLOR)
            [self.r, frame] = self.ai_find_circle.get_model_output(self.img, False)
            if self.r != 0:
                self.label_lengthPixel.setText(str(self.r))
            self.label_showPicture.setScaledContents(True)
            qImg = self.cvToQImage(
                self.showPicture(frame, self.label_showPicture.height(), self.label_showPicture.width()))
            self.label_showPicture.setPixmap(QPixmap.fromImage(qImg))

    def calibration(self):
        actual_length = self.getActualLength()
        pixel_length = self.r
        if pixel_length != 0:
            self.scale = round(actual_length / pixel_length, 5)
            self.label_scale.setText(str(self.scale))
            para.set_param({"scale": self.scale})

    def cvToQImage(self, image):
        h, w, pix = image.shape[0], image.shape[1], image.strides[0]
        channels = 1 if len(image.shape) == 2 else image.shape[2]
        if channels == 3:
            qImg = QImage(image.data, w, h, pix, QImage.Format.Format_RGB888)
            return qImg.rgbSwapped()
        elif channels == 1:
            qImg = QImage(image.data, w, h, pix, QImage.Format.Format_Indexed8)
            return qImg
        else:
            return QImage()

    def showPicture(self, img, h, w):
        height = img.shape[0]
        width = img.shape[1]
        if height / width > h / w:
            k = h / height
            resize_img = cv2.resize(img, None, None, k, k)
            num = abs(int((w - resize_img.shape[1]) / 2))
            n = (w - resize_img.shape[1]) % 2
            re_img = cv2.copyMakeBorder(resize_img, 0, 0, num + n, num, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        else:
            k = w / width
            resize_img = cv2.resize(img, None, None, k, k)
            num = abs(int((h - resize_img.shape[0]) / 2))
            n = (h - resize_img.shape[0]) % 2
            re_img = cv2.copyMakeBorder(resize_img, num + n, num, 0, 0, cv2.BORDER_CONSTANT, value=(0, 0, 0))
        return re_img


class ParamSave(object):
    def __init__(self):
        self.file_name = "./params.json"
        self.original_para = {
            "classes": "",
            "detected object": "",
            "warning object": "",
            "detected task": "s",
            "model path": "./weights/detection",
            "model name": "YOLOv8n",
            "whether save video": 0,
            "save video object": "abnormal",
            "save video path": "./save_video",
            "save error path": "./error_picture",
            "save picture interval": 3,
            "save picture path": "./save_picture",
            "exist object time": 1,
            "no object time": 3,
            "object interval time": 20,
            "waitkey time": 50,
            "confidence": 0.35,
            "iou": 0.45,
            "focus": -1,
            "modbus": 0,
            "scale": 1,
            "vortex min size": 0,
            "ignore size": 30,
            "modbus_ip": "192.168.1.30",
            "modbus_port": 502,
            "auto_modbus_ip": 1,
            "save picture days": 90
        }
        if not os.path.exists(self.file_name):
            with open(self.file_name, 'w', encoding="utf-8") as file_obj:
                json.dump(self.original_para, file_obj, indent=4)
        self.parameters = list(self.original_para.keys())
        user_dict = self.load()
        self.param_kw = {}
        for p in self.parameters:
            if p in user_dict:
                self.param_kw[p] = user_dict[p]
            else:
                self.param_kw[p] = self.original_para[p]
                self.save()

    def load(self):
        if os.path.exists(self.file_name):
            f = open(self.file_name, encoding='utf-8')
            content = f.read()
            user_dic = json.loads(content)
            return user_dic

    def save(self):
        with open(self.file_name, 'w', encoding="utf-8") as file_obj:
            json.dump(self.param_kw, file_obj, indent=4)

    def set_param(self, set_dict):
        for k, v in self.param_kw.items():
            if k in set_dict.keys():
                self.param_kw[k] = set_dict[k]


def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)


if __name__ == '__main__':
    para = ParamSave()
    if para.load() is None:
        para.save()

    app = QtWidgets.QApplication(sys.argv)
    mainWindow = MainWindow()
    mainWindow.show()
    sys.exit(app.exec_())