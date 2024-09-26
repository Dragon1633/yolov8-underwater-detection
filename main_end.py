import os
import time
import cv2
import sys
import json
import numpy as np
import pandas as pd

from src.qt.stream.video_capture import CameraCaptureThread
from src.qt.stream.visualize import VideoVisualizationThread
from src.qt.stream.ai_worker import AiWorkerThread
from src.qt.stream.ai_find_circle import AiWorkerThread2
from src.qt.stream.modbus import ModbusThread
# from src.qt.video.video_worker import FileProcessThread

from src.ui.main_window_end import Ui_MainWindow
from src.ui.menu_setting import Ui_Dialog
from src.ui.menu1 import Ui_Menu1
from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.QtWidgets import QDialog, QMessageBox, QFileDialog
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, pyqtSignal


class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):

    def __init__(self):
        super().__init__()
        self.setupUi(self)

        self.ai_thread = AiWorkerThread()                   # 目标检测线程
        self.camera_thread = CameraCaptureThread()          # 摄像头捕获线程
        self.display_thread = VideoVisualizationThread()
        self.modbus_thread = ModbusThread()                 # modbus通讯线程
        self.showMaximized()

        self.time_ok = -1           # 记录没有检测到缺陷ok的时间，对应exist_object_time实现计时器效果
        self.time_ng = -1           # 对应exist_object_time
        self.time_interval = -1     # 对应object_interval_time
        self.state = "waiting"                      # 三种状态：waiting,ng,ok
        self.start_waiting = 0                      # 不为0时一直处于waiting状态
        self.image = np.zeros((1, 1, 3), dtype=np.uint8)    # 用来存放ai检测后的图像
        self.index = 1                              # 记录发生缺陷的索引数
        self.existing_id = []
        self.existing_class = []
        self.error_picture_list = []                # 存放错误图片名称的列表
        self.start_time = time.strftime("%Y-%m-%d_%H_%M_%S", time.localtime())

        self.get_para()                         # 获取json文件参数
        self.init_slots()
        self.process_camera()                   # 打开摄像头
        # 创建一个log.txt文件记录软件正常打开和关闭
        now = time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())
        with open('log.txt', 'a') as file:
            file.write(now +'\t' + "软件打开" +'\n')

    def init_slots(self):
        self.pushButton_cam.clicked.connect(self.process_camera)
        self.pushButton_stopWarning.clicked.connect(self.stop_warning)          # 停止报警按钮，报警时点击按钮可以停止报警，正常后会自动恢复检测状态
        self.pushButton_stopWarning_2.clicked.connect(self.set_waiting_state)   # 挂起按钮，点击后设置为waiting状态,报警器一直处于黄灯，再次点击按钮可以恢复检测状态
        self.pushButton_outputExcel.clicked.connect(self.output_excel)
        self.pushButton_setting.clicked.connect(self.open_setting)
        self.menu_sizeCalibration.triggered.connect(self.open_menu1)
        # 信号的绑定
        self.camera_thread.send_frame.connect(self.display_thread.get_fresh_frame)
        self.camera_thread.send_frame.connect(self.ai_thread.get_frame)
        self.camera_thread.send_cameraIsOpen.connect(self.reopen_camera)
        self.ai_thread.send_ai_output.connect(self.display_thread.get_ai_output)
        self.ai_thread.send_ai_output.connect(self.camera_thread.start_save_video)  # 保存视频
        # self.ai_thread.send_ai_output.connect(self.modbus_thread.get_ai_output)  # 通讯获取ai输出

        self.display_thread.send_displayable_frame.connect(self.update_display_frame)
        self.display_thread.send_ai_output.connect(self.update_statistic_table)
        # 滑块和计数器联动
        self.spinBox_focus.valueChanged.connect(lambda x: self.update_parameter(x, 'SpinBox_focus'))
        self.horizontalSlider_focus.valueChanged.connect(lambda x: self.update_parameter(x, 'horizontalSlider_focus'))
        # 点击标签打开对应的缺陷图片
        self.tableWidget_results.cellClicked.connect(self.open_table_picture)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.screen_size = (self.label_display.width(), self.label_display.height())
        self.display_thread.get_screen_size(self.screen_size)

    def closeEvent(self, event):
        if self.camera_thread.isRunning():
            self.display_thread.stop_display()
            self.ai_thread.stop_process()
            self.camera_thread.stop_capture()
            if self.modbus_whether_on:
                self.modbus_thread.stop_output_state()
        now = time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())
        with open('log.txt', 'a') as file:
            file.write(now +'\t' + "软件关闭" +'\n')

    def get_para(self):
        """获取json文件参数"""
        p = para.load()
        self.detected_object = p["detected object"]  # 检测的目标名称
        self.conf_thr = p["confidence"]  # 置信度阈值
        self.iou_thr = p["iou"]  # IOU
        self.focus = p["focus"]  # 焦距
        self.model_name = p["model name"]  # 模型名称
        self.modbus_whether_on = p["modbus"]  # 是否启用modbus模块进行报警
        self.ai_task = self.get_ai_task()  # 任务：四种类型object_detection,save_picture,both,none
        self.save_error_path = p["save error path"].replace(" ", "")  # 保存错误图片的路径
        self.exist_object_time = p["exist object time"]  # 检测到缺陷后持续几秒开始报警
        self.no_object_time = p["no object time"]  # 未检测缺陷后持续几秒后结束报警
        self.object_interval_time = p["object interval time"]  # 检测到某种缺陷，几秒后再次出现同类型缺陷，归为同一个缺陷，只记录一次
        self.scale = p["scale"]
        self.vortex_min_size = p["vortex min size"]
        if self.ai_thread.isRunning():
            self.ai_thread.set_confidence_threshold(self.conf_thr)
            self.ai_thread.set_iou_threshold(self.iou_thr)

    def open_setting(self):
        """打开设置窗口"""
        set_menu = SettingsWindow()
        set_menu.signal.connect(self.get_para)          # 重新加载参数
        set_menu.show()

    def open_menu1(self):
        """打开菜单1"""
        self.menu1 = Menu1(self.image)
        self.camera_thread.send_frame.connect(self.menu1.ai_find_circle.get_frame)
        # 暂停主线程的检测，减少内存占用
        if self.ai_thread.isRunning():
            self.ai_thread.pause_continue_process()
            self.menu1.signal.connect(self.ai_thread.pause_continue_process)
        self.menu1.show()

    def process_camera(self):
        """ 判断摄像头是否可用，是则启动拍摄检测线程 """
        video_source = 0
        print("SOURCE", video_source)
        # if video_source is not None and video_source != '':
        if cv2.VideoCapture(video_source).isOpened():
            self.buttons_states("camera_on")
            self.ai_thread.set_start_config(ai_task=self.ai_task, model_name=self.model_name,
                                            confidence_threshold=self.conf_thr, iou_threshold=self.iou_thr)
            self.camera_thread.set_start_config(video_source=video_source, ai_task=self.ai_task)
            self.display_thread.set_start_config([self.label_display.width(), self.label_display.height()])
            if not self.ai_thread.isRunning():
                self.ai_thread.start()
                self.display_thread.start()
                self.camera_thread.start()
                # 是否启用mudbus模块
                if self.modbus_whether_on:
                    self.modbus_thread.set_start_config(self.ai_task)
                    self.modbus_thread.start()
        else:
            QMessageBox.warning(self, "警告", "摄像头未连接或无法打开")

    def reopen_camera(self):
        """ 重新打开摄像头 """
        for i in range(5):      # 等待两秒，尝试五次识别摄像头
            cv2.waitKey(1000)
            print("摄像头识别中...")
            if cv2.VideoCapture(0).isOpened():
                ret, frame = cv2.VideoCapture(0).read()
                if ret:
                    self.process_camera()
                    return
        # QMessageBox.warning(self, "提示", "摄像头断开连接！", QMessageBox.Ok)
        self.buttons_states("camera_off")

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

    def buttons_states(self, work_state):       # 根据工作状况 设置按钮状态
        if work_state == "camera_on":
            self.pushButton_cam.setDisabled(True)
            self.horizontalSlider_focus.setDisabled(False)
            self.spinBox_focus.setDisabled(False)
        elif work_state == "camera_off":
            self.pushButton_cam.setDisabled(False)
            self.horizontalSlider_focus.setDisabled(True)
            self.spinBox_focus.setDisabled(True)

    def stop_warning(self):
        if self.state == "ng":
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

    def update_display_frame(self, image, is_original=False):
        if is_original:
            self.ori_image = image
        else:
            self.image = image
        showImage = self.cvToQImage(self.showPicture(image, self.label_display.height(), self.label_display.width()))
        self.label_display.setPixmap(QtGui.QPixmap.fromImage(showImage))

    def clean_table(self):
        while self.tableWidget_results.rowCount() > 0:
            self.tableWidget_results.removeRow(0)

    def class_to_chinese(self, name):
        """ 将类别名转换为中文 """
        if name == "vortex":
            class_name = "旋涡"
        elif name == "abnormal":
            class_name = "异常出丝"
        elif name == "oil":
            class_name = "油污"
        else:
            class_name = str(name)
        return class_name

    def update_statistic_table(self, ai_output):
        """ 更新统计表格，显示检测信息 """
        tem = 0
        if self.start_waiting == 0:
            contain_object = any(item.get('class') in self.detected_object for item in ai_output)
            # NG的实现
            if contain_object and self.state != "waiting":  # NG状态
                self.time_ok = -1
                if self.time_ng == -1:
                    self.time_ng = time.time()
                elif time.time() - self.time_ng > self.exist_object_time:           # 缺陷出现的实际时间大于指定的时间，提示报错
                    self.label.setStyleSheet("background-color: rgb(255, 0, 0);")
                    self.label.setText("报错")
                    self.state = "ng"
                    if self.modbus_whether_on:
                        self.modbus_thread.get_state("ng")      # 传递modbus状态
                    # 输出检测结果信息
                    current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
                    for box in ai_output:
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
                self.time_ng = -1
                if self.time_ok == -1:
                    self.time_ok = time.time()
                elif time.time() - self.time_ok > self.no_object_time:
                    self.label.setStyleSheet("background-color: rgb(0, 255, 0);")
                    self.label.setText("正常")
                    self.state = "ok"
                    if self.modbus_whether_on:
                        self.modbus_thread.get_state("ok")

    def open_table_picture(self, row):
        # print("选中的列为：", row)
        if self.save_error_path != "":
            if row < len(self.error_picture_list):
                image = cv2.imread(os.path.join(self.save_error_path, self.error_picture_list[row]))
                showImage = self.cvToQImage(
                    self.showPicture(image, self.label_display_2.height(), self.label_display_2.width()))
                self.label_display_2.setPixmap(QtGui.QPixmap.fromImage(showImage))

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
        self.detected_task = parameters["detected task"]
        self.whether_save_video = parameters["whether save video"]          # 是否保存视频
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
        self.spinBox_vortexMinSize.valueChanged.connect(lambda x: self.update_parameter(x, 'spinBox_vortexMinSize'))

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
        elif flag == 'spinBox_vortexMinSize':
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
        self.spinBox_vortexMinSize.setValue(self.vortex_min_size)
        self.doubleSpinBox_conf.setValue(self.confidence)
        self.horizontalSlider_conf.setValue(int(self.confidence*100))
        self.doubleSpinBox_iou.setValue(self.iou)
        self.horizontalSlider_iou.setValue(int(self.iou*100))
        self.spinBox_interval.setValue(self.waitkey_time)
        self.horizontalSlider_interval.setValue(self.waitkey_time)
        if save:
            para.set_param({
                "detected task": self.detected_task,
                "whether save video": self.whether_save_video,
                "save picture interval": self.save_picture_inteval,
                "exist object time": self.exist_object_time,
                "no object time": self.no_object_time,
                "object interval time": self.object_interval_time,
                "vortex min size": self.vortex_min_size,
                "confidence": self.confidence,
                "iou": self.iou,
                "waitkey time":self.waitkey_time,
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
        # self.show()
        self.img = image
        self.scale = para.load()["scale"]
        self.threadFlag = True
        self.r = 0
        self.model_name = "yolov8n_circle"
        self.ai_find_circle = AiWorkerThread2()

        self.init_slots()
        self.setWindowFlags(QtCore.Qt.WindowType.WindowStaysOnTopHint)

    def closeEvent(self, event):
        """ 重写关闭事件函数 """
        self.threadFlag = False
        para.save()
        self.signal.emit(self.scale)
        super().closeEvent(event)  # 调用基类的 closeEvent 方法完成窗口关闭的

    def init_slots(self):
        self.pushButton_loadPicture.clicked.connect(self.loadPicture)
        self.pushButton_calibration.clicked.connect(self.calibration)
        self.ai_find_circle.send_ai_output.connect(self.get_frame)
        # self.camera.send_frame.connect(self.get_frame)
        self.label_scale.setText(str(self.scale))
        # 展示主窗口传递过来的图片
        if self.img.shape[0] != 1:
            if not cv2.VideoCapture(0).isOpened():
                print("展示图片1——传递", self.img.shape)
                # self.ai_find_circle.get_model_output(self.img)
        # 初始化ai检测圆的线程并启动
        self.ai_find_circle.set_start_config(model_name=self.model_name)
        if cv2.VideoCapture(0).isOpened():
            self.ai_find_circle.start()
            print("Menu1圆检测线程启动")

    def get_frame(self, result):
        """ 获取图片 """
        if self.threadFlag:
            img = result[1]
            self.r = result[0]
            if self.r != 0:
                self.label_lengthPixel.setText(str(self.r))
            # self.findOneCircle(self.img)
            self.label_showPicture.setScaledContents(True)
            qImg = self.cvToQImage(self.showPicture(img, self.label_showPicture.height(),
                                                    self.label_showPicture.width()))  # np转为QImage图像格式
            self.label_showPicture.setPixmap(QPixmap.fromImage(qImg))

    def findOneCircle(self, img):
        """输入一张图片，返回一个圆(x,y,r)，未找到则返回None"""
        copy_img = img.copy()
        # 使用Canny边缘检测
        gray = cv2.cvtColor(copy_img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)

        # 使用Hough Circle变换检测圆形
        circles = cv2.HoughCircles(edges, cv2.HOUGH_GRADIENT, 1, minDist=100, param1=250, param2=80, minRadius=100,
                                   maxRadius=0)

        if circles is None:
            return None
        circles = np.round(circles[0, :]).astype("int")
        print(circles)
        if len(circles) == 0:
            return None
        elif len(circles) > 1:
            # 存在多个圆选择半径最大的圆
            circles = circles[np.argmax(circles[:, 2])]
        else:
            circles = circles[0]
        x, y, r = circles
        cv2.circle(img, (x, y), r, (0, 255, 0), 4)
        print("识别出圆的半径为：", r)
        # cv2.imshow("Detected Circles", img)
        # cv2.waitKey(0)

        self.label_showPicture.setScaledContents(True)
        qImg = self.cvToQImage(self.showPicture(img, self.label_showPicture.height(), self.label_showPicture.width()))  # np转为QImage图像格式
        self.label_showPicture.setPixmap(QPixmap.fromImage(qImg))
        return circles

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
                           "detected task": "s",                     # 检测的任务
                           "model path": "./weights/detection",
                           "model name": "YOLOv8n",
                           "whether save video": 0,                 # 是否保存视频，0不保存
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
                           "Format example": "person,bicycle,car,motorcycle,#此行是格式模版，请按照对应的格式填写"}
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
