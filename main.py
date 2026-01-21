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

video_source = 0
cap = cv2.VideoCapture(video_source)
ret, _ = cap.read()
if not ret:
    video_source = "rtsp://192.168.1.168:554/ch01.264"
del cap, ret
# video_source = "rtsp://192.168.1.168:554/ch01.264"


def get_ipv4_addresses():
    """获取本机IPv4地址列表，适用于Windows系统。目的：自动配置modbus的IP地址"""
    try:
        # 执行ipconfig命令并捕获输出
        result = subprocess.check_output(
            'ipconfig',
            shell=True,
            stderr=subprocess.STDOUT,
            text=True,  # Python 3.7+可用
            encoding='cp936'  # Windows中文系统编码
        )

        # 提取所有IPv4地址
        ip_addresses = []
        for line in result.splitlines():
            if "IPv4" in line and "地址" in line:  # 适配中文系统
                # 提取冒号后的IP地址部分
                ip = line.split(':')[-1].strip()
                if ip:  # 确保不是空字符串
                    ip_addresses.append(ip)

        return ip_addresses

    except subprocess.CalledProcessError as e:
        print(f"命令执行失败: {e.output}")
        return []
    except FileNotFoundError:
        print("未找到ipconfig命令，请确保在Windows系统中运行")
        return []


def get_modbus_ip():
    """电脑上只有两个IP地址：水下相机和modbus通讯，自动返回modbus的IP地址"""
    ip_list = get_ipv4_addresses()
    with open('log_ip.txt', 'a') as file:
        file.write(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) + '\t' + "获取到的IP地址：" + str(ip_list) + '\n')
    if isinstance(video_source, int):
        return "0"
    cam_ip = video_source[7:17]     # 192.168.1.  水下相机的IP地址前三位
    for ip in ip_list:
        if cam_ip in ip:
            ip_list.remove(ip)  # 删除水下相机的IP地址

    if len(ip_list) == 1:
        with open('log_ip.txt', 'a') as file:
            file.write(time.strftime("唯一的modbus IP地址：" + str(ip_list[0]) + '\n'))
        return str(ip_list[0])  # 返回唯一的modbus IP地址
    return "0"


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    send_ignore_area_list = pyqtSignal(list)
    send_whether_save_video = pyqtSignal(bool)
    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.ai_thread = AiWorkerThread()                   # 目标检测线程
        self.camera_thread = CameraCaptureThread()          # 摄像头捕获线程
        self.display_thread = VideoVisualizationThread()
        self.modbus_thread = ModbusThread()                 # modbus通讯线程
        self.cleanup_thread = CleanupThread("./save_picture")               # 清理线程
        self.showMaximized()

        self.time_ok = -1           # 记录没有检测到缺陷ok的时间，对应exist_object_time实现计时器效果
        self.time_ng = -1           # 对应exist_object_time
        self.time_interval = -1     # 对应object_interval_time
        self.time_ok_flag = False   # 记录self.time_ok是否被初始化
        self.state = "waiting"                      # 三种状态：waiting,ng,ok
        self.start_waiting = 0                      # 不为0时一直处于waiting状态
        self.image = np.zeros((1, 1, 3), dtype=np.uint8)    # 用来存放ai检测后的图像
        self.temp_image = np.zeros((1, 1, 3), dtype=np.uint8)
        self.index = 1                              # 记录发生缺陷的索引数
        self.ignore_index = 1                       # 忽略的缺陷索引
        self.existing_id = []
        self.existing_class = []
        self.error_picture_list = []                # 存放错误图片名称的列表
        self.start_time = time.strftime("%Y-%m-%d_%H_%M_%S", time.localtime())
        self.ignore_area_list = []           # 存放忽略区域列表，存放字典示例{"class":"vortex","center":[20,20]},忽略的类型和中心点
        self.video_source = video_source    # 采用rtsp推流地址
        self.ai_output = []             # 存放ai输出结果，当忽略时使用
        self.timer = QTimer()           # 定时器，用于摄像头打开超时

        self.get_para()                         # 获取json文件参数
        self.init_slots()

        self.cam_whe_useful_thread = CameraThread(self.video_source)  # 判断相机是否可以打开线程
        self.process_camera()                   # 打开摄像头
        # 创建一个log.txt文件记录软件正常打开和关闭
        now = time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())
        with open('log.txt', 'a') as file:
            file.write(now + '\t' + "软件打开" + '\n')

    def init_slots(self):
        self.pushButton_stopWarning.clicked.connect(self.stop_warning)          # 停止报警按钮，报警时点击按钮可以停止报警，正常后会自动恢复检测状态
        self.pushButton_stopWarning_2.clicked.connect(self.set_waiting_state)   # 挂起按钮，点击后设置为waiting状态,报警器一直处于黄灯，再次点击按钮可以恢复检测状态
        self.pushButton_outputExcel.clicked.connect(self.output_excel)
        self.pushButton_clear.clicked.connect(self.clear_ignore_area_list)
        self.menu_setting.triggered.connect(self.open_setting)
        self.menu_sizeCalibration.triggered.connect(self.open_size_calibration)
        # 信号的绑定
        self.camera_thread.send_frame.connect(self.display_thread.get_fresh_frame)
        self.camera_thread.send_frame.connect(self.ai_thread.get_frame)
        self.camera_thread.send_cameraIsOpen.connect(self.reopen_camera)
        self.ai_thread.send_ai_output.connect(self.display_thread.get_ai_output)
        # self.ai_thread.send_ai_output.connect(self.camera_thread.start_save_video)  # 保存视频
        # self.ai_thread.send_ai_output.connect(self.modbus_thread.get_ai_output)  # 通讯获取ai输出
        self.send_ignore_area_list.connect(self.ai_thread.get_ignore_area_list)
        self.send_whether_save_video.connect(self.camera_thread.change_save_state)

        self.display_thread.send_displayable_frame.connect(self.update_display_frame)
        self.display_thread.send_ai_output.connect(self.update_statistic_table)
        # 点击标签打开对应的缺陷图片
        self.tableWidget_results.cellClicked.connect(self.open_table_picture)
        # 清理线程启动
        self.cleanup_thread.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.screen_size = (self.label_display.width(), self.label_display.height())
        self.display_thread.get_screen_size(self.screen_size)

    def closeEvent(self, event):
        if self.camera_thread.isRunning():
            self.display_thread.stop_display()
            self.ai_thread.stop_process()
            self.camera_thread.stop_capture()
            self.cleanup_thread.stop()
            if self.modbus_whether_on:
                self.modbus_thread.stop_output_state()
        now = time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())
        with open('log.txt', 'a') as file:
            file.write(now + '\t' + "软件关闭" + '\n')

    def get_para(self):
        """获取json文件参数"""
        p = para.load()
        self.detected_object = p["detected object"]  # 检测的目标名称
        self.warning_object = p["warning object"]   # 报警的目标名称,目的是检测记录但不报警-旋涡情况太多
        self.conf_thr = p["confidence"]  # 置信度阈值
        self.iou_thr = p["iou"]  # IOU
        self.focus = p["focus"]  # 焦距
        self.model_name = p["model name"]  # 模型名称
        self.modbus_whether_on = not (p["modbus"] == 0)  # 是否启用modbus模块进行报警
        self.ai_task = self.get_ai_task()  # 任务：四种类型object_detection,save_picture,both,none
        self.save_error_path = p["save error path"].replace(" ", "")  # 保存错误图片的路径
        self.exist_object_time = p["exist object time"]  # 检测到缺陷后持续几秒开始报警
        self.no_object_time = p["no object time"]  # 未检测缺陷后持续几秒后结束报警
        self.object_interval_time = p["object interval time"]  # 检测到某种缺陷，几秒后再次出现同类型缺陷，归为同一个缺陷，只记录一次
        self.scale = p["scale"]
        self.vortex_min_size = p["vortex min size"]
        self.save_flag = not (p["whether save video"] == 0)     # 是否保存视频
        self.save_video_object = p["save video object"]         # 检测到指定类型的缺陷时保存视频
        self.ignore_area_size = p["ignore size"]    # 控制忽略区域大小，正方形的边长的一半
        self.auto_modbus_ip = p["auto_modbus_ip"]   #是否自动配置modbus的ip
        if self.auto_modbus_ip:
            self.init_ip()
        # 更改ai线程的部分参数
        if self.ai_thread.isRunning():
            self.ai_thread.set_confidence_threshold(self.conf_thr)
            self.ai_thread.set_iou_threshold(self.iou_thr)
        # 读取参数，更改modbus线程的状态
        if self.modbus_thread.isRunning():
            if not self.modbus_whether_on:
                self.modbus_thread.stop_output_state()
                print("停止modbus线程成功")
        else:
            if self.modbus_whether_on:
                self.modbus_thread.set_start_config(self.ai_task)
                self.modbus_thread.start()
                print("启动modbus线程成功")
        mkdir(self.save_error_path)

    def init_ip(self):
        self.ip = get_modbus_ip()
        if self.ip == "0":
            QMessageBox.warning(self, "警告", "检测到多个ip地址，请手动设置modbus的IP地址！(或者采用网络摄像头请忽视)", QMessageBox.Ok)
        if self.ip.startswith("192.168."):      #再次验证
            para.set_param({"modbus_ip": self.ip})
            with open('log_ip.txt', 'a') as file:
                file.write("ip更改成功")
            return

        with open('log_ip.txt', 'a') as file:
            file.write("未更改ip")

    def open_setting(self):
        """打开设置窗口"""
        set_menu = SettingsWindow()
        set_menu.signal.connect(self.get_para)          # 重新加载参数
        set_menu.show()

    def open_size_calibration(self):
        """打开菜单1"""
        # self.ai_thread.stop_process()
        # self.display_thread.stop_display()
        # if self.modbus_whether_on:
        #     self.modbus_thread.stop_output_state()
        # 清理旧资源
        if hasattr(self, 'menu1'):
            self.menu1.close()  # 确保释放资源
            del self.menu1
        self.menu1 = Menu1(self.image)

        self.camera_thread.send_frame.connect(self.menu1.get_ori_frame)
        self.camera_thread.send_frame.connect(self.menu1.ai_find_circle.get_frame)  # ai检测用
        # 暂停主线程的检测，减少内存占用
        if self.ai_thread.isRunning():
            self.ai_thread.pause_continue_process()
            self.menu1.signal.connect(self.ai_thread.pause_continue_process)
        self.menu1.show()

    def restart_thread(self):
        pass

    def process_camera(self):
        """ 判断摄像头是否可用，是则启动拍摄检测线程 """
        print("SOURCE", self.video_source)
        self.label_display.setText('<font color="white">正在尝试连接摄像头...</font>')
        self.label_display.setAlignment(Qt.AlignCenter)
        if self.timer.isActive():
            pass
        else:
            # 创建并启动摄像头线程
            self.cam_whe_useful_thread.opened.connect(self.start_thread)
            # 超时定时器
            self.timer.setSingleShot(True)
            self.timer.timeout.connect(self.on_timeout)
            self.timer.start(5000)  # 5秒超时
            self.cam_whe_useful_thread.start()

    def start_thread(self):
        self.timer.stop()
        # if video_source is not None and video_source != '':
        # if cv2.VideoCapture(self.video_source).isOpened():
        self.ai_thread.set_start_config(ai_task=self.ai_task, model_name=self.model_name,
                                        confidence_threshold=self.conf_thr, iou_threshold=self.iou_thr)
        self.camera_thread.set_start_config(video_source=self.video_source, ai_task=self.ai_task)
        self.display_thread.set_start_config([self.label_display.width(), self.label_display.height()])
        if not self.ai_thread.isRunning():
            self.ai_thread.start()
            self.display_thread.start()
            self.camera_thread.start()
            # 是否启用modbus模块
            if self.modbus_whether_on:
                self.modbus_thread.set_start_config(self.ai_task)
                self.modbus_thread.start()

    def on_timeout(self):
        self.timer.stop()
        print("摄像头打开失败，5秒内未响应！")
        self.label_display.setText('<font color="white">连接摄像头失败，请检查接线并重启软件...</font>')
        QMessageBox.warning(self, "警告", "摄像头未连接或无法打开")

    def reopen_camera(self):
        """ 重新打开摄像头 """
        self.process_camera()
        # for i in range(5):      # 等待两秒，尝试五次识别摄像头
        #     cv2.waitKey(1000)
        #     print("摄像头识别中...")
        #     if cv2.VideoCapture(self.video_source).isOpened():
        #         ret, frame = cv2.VideoCapture(self.video_source).read()
        #         if ret:
        #             self.process_camera()
        #             return
        # QMessageBox.warning(self, "提示", "摄像头断开连接！", QMessageBox.Ok)

    def update_parameter(self, x, flag):  # 滑块和计数器联动
        if flag == 'SpinBox_focus':
            self.horizontalSlider_focus.setValue(x)
            self.focus = x
        elif flag == 'horizontalSlider_focus':
            self.spinBox_focus.setValue(x)
            self.focus = x
        self.camera_thread.get_video_focus(self.focus)

    def get_ai_task(self):
        task = para.load()["detected task"]
        task = task.lower().replace(" ", "")     # 小写，去除空格
        if task in ["detection", "object_detection", "detect", "d"]:
            return "object_detection"
        elif task in ["save_picture", "savepicture", "save", "s"]:
            return "save_picture"
        elif task in ["both", "all", "b"]:
            return "both"
        elif task in ["none", "nothing", "n", ""]:
            return "none"

    def stop_warning(self):
        if self.state == "ng":
            reply = QMessageBox.question(self, "提示", "检测到异常，是否选择忽略该区域继续执行检测？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.add_ignore_area()
            else:
                self.label.setStyleSheet("background-color: rgb(40, 90, 255);")
                self.label.setText("等待中...")
                self.state = "waiting"
                if self.modbus_whether_on:
                    self.modbus_thread.get_state("waiting")

    def set_waiting_state(self):
        self.label.setStyleSheet("background-color: rgb(40, 90, 255);")
        self.label.setText("等待中...")
        self.state = "waiting"
        if self.modbus_whether_on:
            self.modbus_thread.get_state("waiting")
        if self.start_waiting == 0:
            self.start_waiting = 1
            self.pushButton_stopWarning_2.setText("恢复")
        else:
            self.start_waiting = 0
            self.pushButton_stopWarning_2.setText("挂起")

    def output_excel(self):
        import time
        end_time = time.strftime("%Y-%m-%d_%H_%M_%S", time.localtime())
        save_xlsx_name = self.start_time + "——" + end_time + "缺陷数据"
        xlsx_path, tmp = QFileDialog.getSaveFileName(self, "保存文件", save_xlsx_name, "*.xlsx")
        if xlsx_path == "":
            return
        # 获取行和列的数量
        row_count = self.tableWidget_results.rowCount()
        # col_count = self.tableWidget_results.columnCount()
        series = {}     # 创建存放写入xlsx的字典
        num = []
        cla = []
        conf = []
        time = []
        # 逐行逐列地读取数据并填充 DataFrame
        for row in range(row_count):
            num.append(self.tableWidget_results.item(row, 0).text())
            cla.append(self.class_to_chinese(self.tableWidget_results.item(row, 1).text()))
            conf.append(self.tableWidget_results.item(row, 2).text())
            time.append(self.tableWidget_results.item(row, 3).text())

        series["序号"] = num
        series["类别"] = cla
        series["置信度"] = conf
        series["时间"] = time
        df = pd.DataFrame(series)

        # 将 DataFrame 写入 Excel 文件
        df.to_excel(xlsx_path, index=False)
        QMessageBox.information(self, "提示", "输出xlsx成功")
        self.index = 1
        self.clean_table()
        self.start_time = end_time

    def add_ignore_area(self):
        """将ai输出的结果中的类别的框的中心点加入到忽略区域中"""
        for output in self.ai_output:
            box = output["bbox"]
            center = [int((box[0] + box[2]) / 2), int((box[1] + box[3]) / 2)]
            self.ignore_area_list.append({"class": output["class"], "center": center})
            self.update_ignore_table(output["class"], center)
        self.send_ignore_area_list.emit(self.ignore_area_list)

    def draw_transparency_square(self, image):
        """在图片上指定区域绘制半透明的正方形区域，用于表示忽略的区域"""
        if self.ignore_area_list:
            alpha = 0.4
            for area in self.ignore_area_list:
                top_left = (area["center"][0] - self.ignore_area_size, area["center"][1] - self.ignore_area_size)
                bottom_right = (area["center"][0] + self.ignore_area_size, area["center"][1] + self.ignore_area_size)
                # 只绘制正方形区域，不影响其他区域
                roi = image[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]]
                # 创建一个与正方形区域相同大小的矩形并设置颜色
                square = np.zeros_like(roi, dtype=np.uint8)
                color = (0, 255, 0)  # 绿色
                cv2.rectangle(square, (0, 0), (self.ignore_area_size*2, self.ignore_area_size*2), color, -1)

                # 将正方形与该区域进行透明混合
                cv2.addWeighted(square, alpha, roi, 1 - alpha, 0, roi)
        return image

    def clear_ignore_area_list(self):
        """清空忽略区域"""
        self.ignore_area_list = []
        self.send_ignore_area_list.emit(self.ignore_area_list)
        while self.tableWidget_ignore.rowCount() > 0:
            self.tableWidget_ignore.removeRow(0)

    def update_display_frame(self, image):
        """ 更新显示的图像"""
        self.image = image.copy()
        image = self.draw_transparency_square(image)    # 绘制忽略区域
        showImage = self.cvToQImage(self.showPicture(image, self.label_display.height(), self.label_display.width()))
        self.label_display.setPixmap(QtGui.QPixmap.fromImage(showImage))

    def clean_table(self):
        """清空表格"""
        while self.tableWidget_results.rowCount() > 0:
            self.tableWidget_results.removeRow(0)

    def class_to_chinese(self, name):
        """ 将类别名转换为中文 """
        if name in "vortex":
            class_name = "旋涡"
        elif name == "abnormal":
            class_name = "异常出丝"
        elif name == "oil":
            class_name = "油污"
        elif name == "person":
            class_name = "人"
        else:
            class_name = str(name)
        return class_name

    def update_statistic_table(self, ai_output):
        """ 更新统计表格，显示检测信息 """
        # ai_output内容"bbox"格式[x1,y1,x2,y2]左上右下角坐标,"class","confidence","id"...
        self.ai_output = ai_output
        tem = 0
        if self.start_waiting == 0:     # 是否挂起
            contain_object = any(item.get('class') in self.detected_object for item in ai_output)
            # NG的实现
            if contain_object and self.state != "waiting":  # NG状态
                self.time_ok = -1
                self.time_ok_flag = False
                if self.time_ng == -1:
                    self.time_ng = time.time()
                elif time.time() - self.time_ng > self.exist_object_time:           # 缺陷出现的实际时间大于指定的时间，提示报错
                    # 输出检测结果信息
                    current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    for box in ai_output:
                        # 优先过滤掉不在检测列表中的目标
                        if box["class"] not in self.detected_object:
                            continue
                        box = self.filter_vortex(box)
                        if box != []:
                            class_name = self.class_to_chinese(box["class"])
                            each_item = [str(self.index), class_name, "{:.1f}%".format(box["confidence"] * 100),
                                         str(current_time)]
                            if box["class"] not in self.existing_class:     # 判断是否是第一次出现，避免重复输出
                                self.time_interval = -1
                                # if tem == 0:
                                self.index += 1
                                tem = 1
                                row = self.tableWidget_results.rowCount()
                                self.tableWidget_results.insertRow(row)  # 插入一行
                                # self.existing_id.append(box["id"])
                                self.existing_class.append(box["class"])
                                for j in range(len(each_item)):
                                    item = QtWidgets.QTableWidgetItem(str(each_item[j]))
                                    item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
                                    self.tableWidget_results.setItem(row, j, item)
                    # QTableWidget滚动条默认滚动到最下方
                    self.tableWidget_results.verticalScrollBar().setValue(self.tableWidget_results.verticalScrollBar().maximum())

                    # 在右侧框显示NG图片
                    if self.image.shape[0] != 1:
                        showImage = self.cvToQImage(
                            self.showPicture(self.image, self.label_display_2.height(), self.label_display_2.width()))
                        self.label_display_2.setPixmap(QtGui.QPixmap.fromImage(showImage))

                    if tem == 1:
                        self.process_ng(ai_output)  # 处理NG状态
                        if self.save_error_path != "":  # 不为空时保存NG图片
                            picture_name = "ERROR" + current_time.replace(" ", "_").replace(":", "_") + ".jpg"
                            self.error_picture_list.append(picture_name)
                            save_error_path = os.path.join(self.save_error_path, picture_name)
                            cv2.imwrite(save_error_path, self.image)
            # OK的实现
            else:
                if self.time_interval == -1:
                    self.time_interval = time.time()
                elif self.existing_class != [] and time.time() - self.time_interval > self.object_interval_time:
                    # self.existing_id = []
                    self.existing_class = []
                # print("当前的状态", self.state)
                self.time_ng = -1
                if self.time_ok == -1 and not contain_object:
                    self.time_ok = time.time()
                    self.time_ok_flag = True
                elif self.time_ok_flag and time.time() - self.time_ok > self.no_object_time:
                    self.label.setStyleSheet("background-color: rgb(0, 255, 0);")
                    self.label.setText("正常")
                    self.state = "ok"
                    if self.modbus_whether_on:
                        self.modbus_thread.get_state("ok")
                    self.send_whether_save_video.emit(False)

    def process_ng(self, ai_output):
        for box in ai_output:
            if box["class"] in self.warning_object:     #只针对报警的目标进行报警处理
                self.label.setStyleSheet("background-color: rgb(255, 0, 0);")
                self.label.setText("报错")
                self.state = "ng"
                if self.modbus_whether_on:
                    self.modbus_thread.get_state("ng")  # 传递modbus状态
        whether_save_video = any(item.get('class') in self.save_video_object for item in ai_output)
        if self.save_flag and whether_save_video:
            self.send_whether_save_video.emit(True)
        else:
            self.send_whether_save_video.emit(False)

    def update_ignore_table(self, class_name, center):
        """ 更新忽略区域表格 """
        current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        each_item = [str(self.ignore_index), class_name, str(center), current_time]
        self.ignore_index += 1
        row = self.tableWidget_ignore.rowCount()
        self.tableWidget_ignore.insertRow(row)
        for j in range(len(each_item)):
            item = QtWidgets.QTableWidgetItem(str(each_item[j]))
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            self.tableWidget_ignore.setItem(row, j, item)
        # QTableWidget滚动条默认滚动到最下方
        self.tableWidget_ignore.verticalScrollBar().setValue(
            self.tableWidget_ignore.verticalScrollBar().maximum())

    def open_table_picture(self, row):
        """ 打开表格中选中的图片 """
        # print("选中的列为：", row)
        if self.save_error_path != "":
            if row < len(self.error_picture_list):
                try:
                    image = cv2.imread(os.path.join(self.save_error_path, self.error_picture_list[row]))
                    showImage = self.cvToQImage(
                        self.showPicture(image, self.label_display_2.height(), self.label_display_2.width()))
                    self.label_display_2.setPixmap(QtGui.QPixmap.fromImage(showImage))
                except:
                    print("图片打开失败")

    def filter_vortex(self, box):
        """过滤较小的漩涡"""
        if box["class"] != "vortex":
            return box
        dx = box["bbox"][2] - box["bbox"][0]
        dy = box["bbox"][3] - box["bbox"][1]
        pixel_size = int(max(dx, dy))
        if pixel_size * self.scale >= self.vortex_min_size:
            return box
        else:
            return []

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

    def save_picture(self, path, picture):
        """按照 日-小时 文件夹格式来保存图片"""
        now = time.strftime("%Y-%m-%d_%H_%M_%S", time.localtime())  # 2024-07-12 11:04:06
        now_date = now[0:10]    # 2024-07-12
        now_h = now[11:13]      # 11
        now_name = now   # 11:04:06
        data_dir = path + "/" + now_date
        mkdir(data_dir)
        h_dir = data_dir + "/" + now_h
        mkdir(h_dir)

        cv2.imwrite(h_dir + "/" + "Picture-{}.jpg".format(now_name), picture)


class SettingsWindow(QDialog, Ui_Dialog):
    signal = pyqtSignal()
    """设置窗口"""
    def __init__(self):
        super().__init__()
        self.setupUi(self)  # 初始化窗口界面
        self.get_parameter()
        self.init_slots()

    def closeEvent(self, event):
        self.signal.emit()
        super().closeEvent(event)

    def get_parameter(self):
        """ 获取json文件的参数 """
        parameters = para.param_kw
        self.warning_object = parameters["warning object"]  # 报警的目标名称
        self.detected_task = parameters["detected task"]
        self.whether_save_video = parameters["whether save video"]          # 是否保存视频
        self.save_video_object = parameters["save video object"]            # 什么缺陷出来时保存视频
        self.save_picture_inteval = parameters["save picture interval"]     # 保存图片间隔
        self.exist_object_time = parameters["exist object time"]
        self.no_object_time = parameters["no object time"]
        self.object_interval_time = parameters["object interval time"]  # 检测到某种缺陷，几秒后再次出现同类型缺陷，归为同一个缺陷，只记录一次
        self.vortex_min_size = parameters["vortex min size"]
        self.confidence = parameters["confidence"]
        self.iou = parameters["iou"]
        self.waitkey_time = parameters["waitkey time"]      # 检测时间间隔，影响帧率，越大帧率越低，但CPU使用率越低
        self.modbus = parameters["modbus"]                  # 是否启用报警

        self.set_parameters()

    def init_slots(self):
        # 按钮绑定
        self.pushButton_setPara.clicked.connect(lambda x: self.set_parameters(save=True))
        self.pushButton_setDefault.clicked.connect(self.set_default)
        # 功能设置
        self.radioButton_startWarning.clicked.connect(lambda x: self.set_function("warning"))
        self.radioButton_startSavePicture.clicked.connect(lambda x: self.set_function("save_video"))
        self.radioButton_abnormal.clicked.connect(lambda x: self.set_function("abnormal"))
        self.radioButton_vortex.clicked.connect(lambda x: self.set_function("vortex"))
        self.radioButton_oil.clicked.connect(lambda x: self.set_function("oil"))
        self.radioButton_abnormal_warning.clicked.connect(lambda x: self.set_function("abnormal_warning"))
        self.radioButton_vortex_warning.clicked.connect(lambda x: self.set_function("vortex_warning"))
        self.radioButton_oil_warning.clicked.connect(lambda x: self.set_function("oil_warning"))
        # 模式选择
        self.comboBox.currentIndexChanged.connect(lambda x: self.set_function("mode"))
        # 滑块和计数器联动
        self.doubleSpinBox_conf.valueChanged.connect(lambda x: self.update_parameter(x, 'doubleSpinBox_conf'))
        self.spinBox_interval.valueChanged.connect(lambda x: self.update_parameter(x, 'doubleSpinBox_interval'))
        self.doubleSpinBox_iou.valueChanged.connect(lambda x: self.update_parameter(x, 'doubleSpinBox_iou'))
        self.horizontalSlider_conf.valueChanged.connect(lambda x: self.update_parameter(x, 'horizontalSlider_conf'))
        self.horizontalSlider_interval.valueChanged.connect(lambda x: self.update_parameter(x, 'horizontalSlider_interval'))
        self.horizontalSlider_iou.valueChanged.connect(lambda x: self.update_parameter(x, 'horizontalSlider_iou'))
        # 更新值
        self.spinBox_timeForStartWarning.valueChanged.connect(lambda x: self.update_parameter(x, 'spinBox_timeForStartWarning'))
        self.spinBox_timeForStopWarning.valueChanged.connect(lambda x: self.update_parameter(x, 'spinBox_timeForStopWarning'))
        self.spinBox_savePictureInterval.valueChanged.connect(lambda x: self.update_parameter(x, 'spinBox_savePictureInterval'))
        self.spinBox_timeForObjectIntervalTime.valueChanged.connect(lambda x: self.update_parameter(x, 'spinBox_timeForObjectIntervalTime'))
        self.doubleSpinBox_vortexMinSize.valueChanged.connect(lambda x: self.update_parameter(x, 'doubleSpinBox_vortexMinSize'))

    def update_parameter(self, x, flag):
        # 滑块和计数器联动
        if flag == 'doubleSpinBox_conf':
            self.horizontalSlider_conf.setValue(int(x*100))
            self.confidence = float(x)
        elif flag == 'doubleSpinBox_interval':
            self.horizontalSlider_interval.setValue(int(x))
            self.waitkey_time = int(x)
        elif flag == 'doubleSpinBox_iou':
            self.horizontalSlider_iou.setValue(int(x*100))
            self.iou = float(x)
        elif flag == 'horizontalSlider_conf':
            self.doubleSpinBox_conf.setValue(x/100)
            self.confidence = float(x/100)
        elif flag == 'horizontalSlider_interval':
            self.spinBox_interval.setValue(x)
            self.waitkey_time = int(x)
        elif flag == 'horizontalSlider_iou':
            self.doubleSpinBox_iou.setValue(x/100)
            self.iou = float(x/100)
        # 及时获取更新参数
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
        """设置参数，选择是否保存"""
        self.get_ai_task(self.detected_task)
        self.radioButton_startSavePicture.setChecked(not (self.whether_save_video == 0))
        self.radioButton_startWarning.setChecked(not (self.modbus == 0))
        self.spinBox_timeForStartWarning.setValue(self.exist_object_time)
        self.spinBox_timeForStopWarning.setValue(self.no_object_time)
        self.spinBox_timeForObjectIntervalTime.setValue(self.object_interval_time)
        self.spinBox_savePictureInterval.setValue(self.save_picture_inteval)
        self.doubleSpinBox_vortexMinSize.setValue(self.vortex_min_size)
        self.doubleSpinBox_conf.setValue(self.confidence)
        self.horizontalSlider_conf.setValue(int(self.confidence*100))
        self.doubleSpinBox_iou.setValue(self.iou)
        self.horizontalSlider_iou.setValue(int(self.iou*100))
        self.spinBox_interval.setValue(self.waitkey_time)
        self.horizontalSlider_interval.setValue(self.waitkey_time)

        self.radioButton_abnormal.setChecked("abnormal" in self.save_video_object)
        self.radioButton_vortex.setChecked("vortex" in self.save_video_object)
        self.radioButton_oil.setChecked("oil" in self.save_video_object)
        self.radioButton_abnormal_warning.setChecked("abnormal" in self.warning_object)
        self.radioButton_vortex_warning.setChecked("vortex" in self.warning_object)
        self.radioButton_oil_warning.setChecked("oil" in self.warning_object)
        # 保存参数
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
        """恢复默认参数"""
        p = para.original_para
        default_para = {        # 读取默认参数
            "detected task":        p["detected task"],
            "whether save video":   p["whether save video"],
            "save picture interval": p["save picture interval"],
            "exist object time":    p["exist object time"],
            "no object time":       p["no object time"],
            "object interval time": p["object interval time"],
            "vortex min size":      p["vortex min size"],
            "confidence":           p["confidence"],
            "iou":                  p["iou"],
            "waitkey time":         p["waitkey time"],
            "modbus":               p["modbus"]
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
        # 以下三个为保存缺陷的用户勾选的缺陷类型
        if flag == "abnormal":
            if self.radioButton_abnormal.isChecked():
                if "abnormal" not in self.save_video_object:
                    self.save_video_object += "abnormal"
            else:
                if "abnormal" in self.save_video_object:
                    self.save_video_object = self.save_video_object.replace("abnormal", "")
        if flag == "vortex":
            if self.radioButton_vortex.isChecked():
                if "vortex" not in self.save_video_object:
                    self.save_video_object += "vortex"
            else:
                if "vortex" in self.save_video_object:
                    self.save_video_object = self.save_video_object.replace("vortex", "")
        if flag == "oil":
            if self.radioButton_oil.isChecked():
                if "oil" not in self.save_video_object:
                    self.save_video_object += "oil"
            else:
                if "oil" in self.save_video_object:
                    self.save_video_object = self.save_video_object.replace("oil", "")
        if flag == "abnormal_warning":
            if self.radioButton_abnormal_warning.isChecked():
                if "abnormal" not in self.warning_object:
                    self.warning_object += "abnormal"
            else:
                if "abnormal" in self.warning_object:
                    self.warning_object = self.warning_object.replace("abnormal", "")
        if flag == "vortex_warning":
            if self.radioButton_vortex_warning.isChecked():
                if "vortex" not in self.warning_object:
                    self.warning_object += "vortex"
            else:
                if "vortex" in self.warning_object:
                    self.warning_object = self.warning_object.replace("vortex", "")
        if flag == "oil_warning":
            if self.radioButton_oil_warning.isChecked():
                if "oil" not in self.warning_object:
                    self.warning_object += "oil"
            else:
                if "oil" in self.warning_object:
                    self.warning_object = self.warning_object.replace("oil", "")

    def get_ai_task(self, task):
        task = task.lower().replace(" ", "")
        # print(task)
        if task in ["detection", "object_detection", "detect", "d"]:
            self.comboBox.setCurrentIndex(1)
        elif task in ["save_picture", "savepicture", "save", "s"]:
            self.comboBox.setCurrentIndex(0)
        elif task in ["both", "all", "b"]:
            self.comboBox.setCurrentIndex(2)
        elif task in ["none", "nothing", "n", ""]:
            self.comboBox.setCurrentIndex(3)


class Menu1(QDialog, Ui_Menu1):
    """ 标定菜单 """
    signal = pyqtSignal(float)

    def __init__(self, image):
        super().__init__()
        self.setupUi(self)  # 初始化窗口界面
        self.show()
        self.img = image
        self.scale = para.load()["scale"]
        self.threadFlag = True
        self.r = 0
        self.model_name = "yolov8n_circle"
        self.idx_frame = 0
        self.mode = "auto"      # auto,manual
        self.ai_find_circle = AiWorkerThread2()

        # 保存原来的 label_showPicture 控件
        self.original_label_showPicture = self.findChild(QLabel, "label_showPicture")
        # 创建自定义的 ImageLabel 控件
        self.manual_label_showPicture = self.ImageLabel(self)        # 用来人工标注圆时的自定义的label，用来显示图像
        # 将自定义控件设置为与原来 label_showPicture 相同的位置和大小
        self.manual_label_showPicture.setGeometry(self.original_label_showPicture.geometry())
        self.manual_label_showPicture.setVisible(False)

        self.init_slots()
        self.k = self.get_k()       # 比例尺，k=图片像素距离/展示label中的距离，实际的像素尺寸=检测出来尺寸*k
        print(self.k)

        self.setWindowFlags(QtCore.Qt.WindowType.WindowStaysOnTopHint)

    def closeEvent(self, event):
        """ 重写关闭事件函数 """
        self.threadFlag = False
        para.save()
        self.signal.emit(self.scale)
        super().closeEvent(event)  # 调用基类的 closeEvent 方法完成窗口关闭的

    def init_slots(self):
        # self.pushButton_loadPicture.clicked.connect(self.loadPicture)
        self.pushButton_calibration.clicked.connect(self.calibration)
        self.pushButton_changemode.clicked.connect(self.change_mode)
        self.ai_find_circle.send_ai_output.connect(self.get_results)
        self.manual_label_showPicture.send_r.connect(self.change_det_r)
        # self.camera.send_frame.connect(self.get_results)
        self.label_scale.setText(str(self.scale))
        # 展示主窗口传递过来的图片
        # if self.img.shape[0] != 1:
        #     if not cv2.VideoCapture(0).isOpened():
        #         print("展示图片1——传递", self.img.shape)
                # self.ai_find_circle.get_model_output(self.img)
        # 初始化ai检测圆的线程并启动
        self.ai_find_circle.set_start_config(model_name=self.model_name)
        if cv2.VideoCapture(video_source).isOpened():
            self.ai_find_circle.start()
            print("Menu1圆检测线程启动")

    def get_k(self):
        """计算比例尺"""
        height, width = self.img.shape[:2]
        if height != 1:
            w = self.label_showPicture.width()
            h = self.label_showPicture.height()
            if height / width > h / w:
                return height / h       # 展示label的宽/图片高度
            else:
                return width / w

    def change_det_r(self, r):
        """ 更新检测到的圆的半径 """
        self.r = r
        if self.r != 0:
            self.label_lengthPixel.setText(str(round(self.r * self.k*2, 1)))

    def get_results(self, result):
        """ 获取并显示ai处理后的图片 """
        print("ai自动检测获得图片")
        if self.threadFlag:
            img = result[1]
            self.change_det_r(result[0])
            qImg = self.cvToQImage(self.showPicture(img, self.label_showPicture.height(),
                                                    self.label_showPicture.width()))  # np转为QImage图像格式
            # self.label_showPicture.setScaledContents(True)
            # self.label_showPicture.setPixmap(QPixmap.fromImage(qImg))
            self.original_label_showPicture.setScaledContents(True)
            self.original_label_showPicture.setPixmap(QPixmap.fromImage(qImg))
            print("显示图片完毕！！！！！！")

    def get_ori_frame(self, frame):
        """ 获取原始图片 """
        if self.mode == "auto":
            # self.idx_frame += 1
            # self.ai_find_circle.get_frame(list([(self.idx_frame, frame)]))
            pass
            # if self.ai_find_circle.isRunning():
            #     self.ai_find_circle.get_results(frame)
                # self.ai_find_circle.send_ai_output.connect(self.get_results)
        else:
            self.manual_label_showPicture.set_image(frame[1])

    def change_mode(self):
        """切换模式"""
        if self.mode == "auto":     # 自动检测切换人工
            self.mode = "manual"
            if self.ai_find_circle.isRunning():
                self.ai_find_circle.stop_process()
            self.manual_draw_circle()
            self.label_mode.setText("手动")
        else:                       # 手动标注切换自动
            self.mode = "auto"
            self.restore_original_label()
            self.ai_find_circle.set_start_config(model_name=self.model_name)
            if cv2.VideoCapture(video_source).isOpened():
                self.ai_find_circle.start()
            self.label_mode.setText("自动")

    def manual_draw_circle(self):
        """切换到手动标注圆模式"""
        # 使用布局替换原来的控件
        self.layout().replaceWidget(self.original_label_showPicture, self.manual_label_showPicture)
        # 删除原来的 label_showPicture 控件
        # original_label.deleteLater()  # 释放原来的 QLabel 控件
        self.original_label_showPicture.setVisible(False)
        self.manual_label_showPicture.setVisible(True)

    def restore_original_label(self):
        """恢复原来的 label_showPicture 控件"""
        # 使用布局替换自定义控件，恢复原来的 label_showPicture
        self.layout().replaceWidget(self.manual_label_showPicture, self.original_label_showPicture)
        # 显示原来的控件
        self.original_label_showPicture.setVisible(True)
        # 隐藏或删除自定义控件
        self.manual_label_showPicture.setVisible(False)
        # 如果你不再需要自定义控件，也可以删除它
        # self.manual_label_showPicture.deleteLater()

    class ImageLabel(QLabel):
        send_r = pyqtSignal(int)
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAlignment(Qt.AlignCenter)
            self.pixmap_loaded = False
            self.points = []  # Stores the points clicked by the user
            self.temp_point = None  # Temporary point for drawing the arrow (mouse move)
            self.original_pixmap = None  # To store the original pixmap

            self.setMouseTracking(True)

        def set_image(self, image):
            if image is not None:
                # image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                # height, width, channel = image.shape
                # Convert to QImage
                # qimg = QImage(image, width, height, 3 * width, QImage.Format_RGB888)
                # pixmap = QPixmap(qimg)
                self.original_pixmap = image  # Store the original pixmap
                self.resize_image()  # Resize the image to fit the label
                self.pixmap_loaded = True

        def resize_image(self):
            # if self.original_pixmap:
                # Resize the image to fit the label size while keeping aspect ratio
                # scaled_pixmap = self.original_pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if self.original_pixmap is not None:
                scaled_pixmap = self.cvToQImage(self.showPicture(self.original_pixmap, self.height(), self.width()))
                self.setPixmap(QPixmap.fromImage(scaled_pixmap))

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
                # print(self.temp_point)
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
                self.send_r.emit(radius)

                # Draw the circle
                painter.drawEllipse(center, radius, radius)
                painter.end()

        def draw_arrowhead(self, painter, p1, p2):
            """绘制一个从 p1 到 p2 的箭头。"""
            angle = math.atan2(p2.y() - p1.y(), p2.x() - p1.x())
            arrow_size = 10

            # Calculate the points of the arrowhead
            p1_arrow = QPoint(
                int(p2.x() - arrow_size * math.cos(angle - math.pi / 6)),
                int(p2.y() - arrow_size * math.sin(angle - math.pi / 6))
            )
            p2_arrow = QPoint(
                int(p2.x() - arrow_size * math.cos(angle + math.pi / 6)),
                int(p2.y() - arrow_size * math.sin(angle + math.pi / 6))
            )

            # Draw the arrowhead
            painter.drawLine(p2, p1_arrow)
            painter.drawLine(p2, p2_arrow)

        def resizeEvent(self, event):
            # When the label is resized, adjust the image size as well
            self.resize_image()
            super().resizeEvent(event)

        def cvToQImage(self, image):
            """将OpenCV图像 转换为 PyQt图像"""
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
            """ 将图片缩放、补齐到跟显示框相同大小，h、w分别为需要展示的label区域的高和宽 """
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
        """ 根据用户输入获取到实际的长度 """
        unit = self.comboBox.currentIndex()
        if unit == 0:  # mm
            actual_length = self.doubleSpinBox.value()
        elif unit == 1:  # cm
            actual_length = self.doubleSpinBox.value() * 10
        else:  # m
            actual_length = self.doubleSpinBox.value() * 1000
        return actual_length

    def loadPicture(self):
        """ 加载图片按钮操作 """
        filename, _ = QFileDialog.getOpenFileName(self, "Open Image", "./picture/", "*.png *.jpg")
        if len(filename) != 0:
            # self.img = cv2.imread(filename)
            self.img = cv2.imdecode(np.fromfile(filename, dtype=np.uint8), cv2.IMREAD_COLOR)
            print("加载图片1——加载", self.img.shape)
            # self.findOneCircle(self.img.copy())
            [self.r, frame] = self.ai_find_circle.get_model_output(self.img, False)
            if self.r != 0:
                self.label_lengthPixel.setText(str(self.r))
            self.label_showPicture.setScaledContents(True)
            qImg = self.cvToQImage(self.showPicture(frame, self.label_showPicture.height(),
                                                    self.label_showPicture.width()))  # np转为QImage图像格式
            self.label_showPicture.setPixmap(QPixmap.fromImage(qImg))

    def calibration(self):
        """ 标定按钮操作 """
        actual_length = self.getActualLength()
        pixel_length = self.r
        if pixel_length != 0:
            self.scale = round(actual_length / pixel_length, 5)     # 实际除以像素长度，得到标定比例
            print("标定比例：", actual_length / pixel_length)
            self.label_scale.setText(str(self.scale))
            para.set_param({"scale": self.scale})

    def cvToQImage(self, image):
        """将OpenCV图像 转换为 PyQt图像"""
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
        """ 将图片缩放、补齐到跟显示框相同大小，h、w分别为需要展示的label区域的高和宽 """
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
    """ 管理json文件的读取 """
    """加载：    para.load()["scale"]
       保存：    para.save()
       设置/更改：para.set_param({"scale": 1})"""
    def __init__(self):
        self.file_name = "./params.json"    # 读取json文件的路径
        self.original_para = {"classes": "",                       # 检测的类别
                           "detected object": "",                   # 检测的目标
                           "warning object":"",                   # 警报的目标
                           "detected task": "s",                     # 检测的任务
                           "model path": "./weights/detection",
                           "model name": "YOLOv8n",
                           "whether save video": 0,                 # 是否保存视频，0不保存
                           "save video object": "abnormal",
                           "save video path": "./save_video",       # 存放检测到缺陷时保存视频的目录
                           "save error path": "./error_picture",    # 存放检测到缺陷时保存的图片目录
                           "save picture interval": 3,
                           "save picture path": "./save_picture",
                           "exist object time": 1,      # 检测到目标持续一秒时，认为检测到目标，警报并且保存视频
                           "no object time": 3,         # 目标消失持续三秒时，关闭警报，停止保存视频
                           "object interval time": 20,
                           "waitkey time": 50,          # 检测图片时等待时间，影响一秒检测的帧率
                           "confidence": 0.35,
                           "iou": 0.45,
                           "focus": -1,             # 焦距
                           "modbus": 0,             # 是否启动modbus线程,0不启用
                           "scale":1,               # 比例尺,实际/像素长度
                           "vortex min size":0,     # vortex最小尺寸，mm
                           "ignore size": 30,
                           "modbus_ip": "192.168.1.30",
                           "modbus_port": 502,
                           "auto_modbus_ip":1,        # 是否自动配置modbus的ip地址，0不自动
                           "save picture days": 90  # 保存图片的天数，超过天数自动删除
                           }
        # 不存在json文件自动创建并初始化
        if not os.path.exists(self.file_name):
            with open(self.file_name, 'w', encoding="utf-8") as file_obj:
                json.dump(self.original_para, file_obj, indent=4)
        # 加载参数,如果不存在则采用默认参数并保存
        self.parameters = list(self.original_para.keys())
        user_dict = self.load()
        self.param_kw = {}
        for p in self.parameters:
            if p in user_dict:
                self.param_kw[p] = user_dict[p]
            else:
                self.param_kw[p] = self.original_para[p]
                self.save()

    # 从文件加载 参数
    def load(self):
        if os.path.exists(self.file_name):
            f = open(self.file_name, encoding='utf-8')
            content = f.read()
            user_dic = json.loads(content)
            # print("文件加载后:", user_dic)
            return user_dic

    # 保存参数 到文件
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
