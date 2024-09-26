import cv2
from PyQt5.QtCore import QThread
import time
import modbus_tk.modbus_tcp as mt
import modbus_tk.defines as cst
from src.utils.general import get_param


class ModbusThread(QThread):
    def __init__(self):
        super(ModbusThread, self).__init__()
        self.master = mt.TcpMaster('192.168.1.30', 502)
        self.master.set_timeout(5)
        self.output_state = "waiting"      # OK,Waiting,NG,Buzzer分别对应绿灯、黄灯、红灯、蜂鸣器,对应的输出端口分别对应108,109,110,111
        self.time0 = -1
        self.time = -1
        self.detected_object = get_param('detected object')
        self.ai_output = []
        self.threadFlag = True
        self.ai_task = "none"

    def set_start_config(self, ai_task):
        self.threadFlag = True
        self.ai_task = ai_task

    # def get_ai_output(self, ai_output):
    #     self.ai_output = ai_output
    #     self.threadFlag = True
    #
    # def change_to_waiting_state(self):
    #     self.output_state = "waiting"

    def get_state(self, state):
        state = state.lower()
        if state in ["ok", "ng", "waiting"]:
            self.output_state = state
            # print("modbus的状态", state)

    def change_output_state(self, output_state):
        if output_state == "":
            return
        elif output_state == "ok":  # 绿灯
            try:
                self.master.execute(slave=1, function_code=cst.WRITE_MULTIPLE_COILS, starting_address=108,
                                    quantity_of_x=4, output_value=[1, 0, 0, 0])  # 写多个线圈分别对应绿灯、黄灯、红灯、蜂鸣器
            except Exception as e:
                print('error_ok: %s' % e)
        elif output_state == "ng":  # 红灯+蜂鸣器
            try:
                self.master.execute(slave=1, function_code=cst.WRITE_MULTIPLE_COILS, starting_address=108,
                                    quantity_of_x=4, output_value=[0, 0, 1, 1])  # 写多个线圈
            except Exception as e:
                print('error_ng: %s' % e)
        elif output_state == "waiting":     # 黄灯
            try:
                self.master.execute(slave=1, function_code=cst.WRITE_MULTIPLE_COILS, starting_address=108,
                                    quantity_of_x=4, output_value=[0, 1, 0, 0])  # 写多个线圈
            except Exception as e:
                print('error_waiting: %s' % e)

    def monitor_input(self):
        try:
            coils_value = self.master.execute(slave=1, function_code=cst.READ_COILS, starting_address=100,
                                     quantity_of_x=1)  # 读线圈状态
            # print("获取输入口1的状态", coils_value)
            if coils_value[0] == 1:
                self.output_state = "waiting"
            else:
                self.output_state = ""
        except Exception as e:
            print('error_input: %s' % e)

    def stop_output_state(self):
        if self.output_state != "":
            try:
                self.master.execute(slave=1, function_code=cst.WRITE_MULTIPLE_COILS, starting_address=108,
                                                      quantity_of_x=4, output_value=[0, 0, 0, 0])  # 写多个线圈
            except Exception as e:
                print('error_stop: %s' % e)
        self.threadFlag = False

    def run(self):
        if self.ai_task == "object_detection" or self.ai_task == "both":
            tem_state = self.output_state
            while self.threadFlag:
                if tem_state != self.output_state:
                    self.change_output_state(self.output_state)
                    tem_state = self.output_state
                cv2.waitKey(50)
        else:
            self.change_output_state(self.output_state)


