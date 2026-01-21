import copy
import cv2
from PyQt5.QtCore import QThread, pyqtSignal
from src.models.detection.yolov8_detector_onnx import YoloDetector
from src.models.tracking.deep_sort.deep_sort import DeepSort
from src.models.tracking.byte_track.byte_tracker import BYTETracker

from src.data_type.video_buffer import LatestFrame
from src.utils.general import ROOT, add_image_id, get_param
import os
import time


class AiWorkerThread(QThread):
    send_ai_output = pyqtSignal(list)
    def __init__(self):
        super(AiWorkerThread, self).__init__()
        self.thread_name = "AiWorkerThread"
        self.threadFlag = False
        self.ignore_area_list = []
        self.ignore_area_size = 50
    
    def set_start_config(self, ai_task, model_name="yolov8n", confidence_threshold=0.35, iou_threshold=0.45, tracker_name="deepsort"):
        self.threadFlag = True
        self.ai_task = ai_task
        self.latest_frame = LatestFrame()
        self.confi_thr = confidence_threshold
        self.iou_thr = iou_threshold
        self.model_name = model_name
        self.tracker_name = tracker_name
        self._init_yolo()
        self._init_tracker()
        print(self.model_name)
        self.tem = self.ai_task

    def set_iou_threshold(self, iou_threshold):
        self.iou_thr = iou_threshold
    
    def set_confidence_threshold(self, confidence_threshold):
        self.confi_thr = confidence_threshold
    
    def set_model_name(self, model_name):
        self.model_name = model_name

    def _init_yolo(self):
        model_path = get_param("model path")
        if self.ai_task == "object_detection" or self.ai_task == "both":
            self.detector = YoloDetector()
            self.detector.init(
                # model_path=os.path.join("./", f"weights/detection/{self.model_name}.onnx"),
                # class_txt_path=os.path.join("./", "weights/classes.txt"),
                model_path=model_path + f"/{self.model_name}.onnx",
                confidence_threshold=self.confi_thr,
                iou_threshold=self.iou_thr)

    def _init_tracker(self):
        if self.tracker_name == "deepsort":
            self.tracker = DeepSort(
                model_path="weights/ckpt.t7")
                # model_path=os.path.join(ROOT, f"weights/ckpt.t7"))
        elif self.tracker_name == "bytetrack":
            self.tracker = BYTETracker(
                track_high_thresh=0.5,
                track_low_thresh=0.1,
                new_track_thresh=0.6,
                match_thresh=0.8,
                track_buffer=30,
                frame_rate=30)
    
    def get_frame(self, frame_list):
        self.latest_frame.put(frame=frame_list[1], frame_id=frame_list[0], realtime=True)

    def get_ignore_area_list(self, ignore_area_list):
        self.ignore_area_list = ignore_area_list

    def pause_continue_process(self):
        if self.ai_task == "pause":
            self.ai_task = self.tem
        else:
            self.tem = self.ai_task
            self.ai_task = "pause"
    
    def stop_process(self):
        self.threadFlag = False

    def determine_whether_ignore(self, ai_output):
        """判断ai输出是否需要忽略，如果是则删除某个输出"""
        if ai_output and self.ignore_area_list:
            new_ai_output = []
            for output in ai_output:
                box = output["bbox"]  # ai检测的值
                cls = output["class"]
                center = [int((box[0] + box[2]) / 2), int((box[1] + box[3]) / 2)]
                should_ignore = False
                for area in self.ignore_area_list:
                    if cls == area["class"]:  # 忽略的值
                        area_c = area["center"]
                        # 如果检测框的中心点在忽略区域内，则标记为忽略
                        if (area_c[0] - self.ignore_area_size < center[0] < area_c[0] + self.ignore_area_size and
                                area_c[1] - self.ignore_area_size < center[1] < area_c[1] + self.ignore_area_size):
                            should_ignore = True
                            break
                if not should_ignore:
                    new_ai_output.append(output)
            return new_ai_output
        return ai_output

    def run(self):
        time0 = time.time()
        id = 0
        while self.threadFlag:
            frame_id, frame = self.latest_frame.get()

            if time.time() - time0 >= 1:
                time0 = time.time()
                # print("时间经过1s！！！！！！！")
                # print("1s检测的帧为：", id)
                id = 0
            if frame_id is None:
                break
            model_output = []
            if self.ai_task == "object_detection" or self.ai_task == "both":
                model_output = self.detector.inference(frame, self.confi_thr, self.iou_thr)
                id += 1
                # print("ai处理结果：", model_output)
                model_output = self.tracker.update(detection_results=model_output, ori_img=frame)
            model_output = self.determine_whether_ignore(model_output)
            self.model_output = add_image_id(model_output, frame_id)
            self.send_ai_output.emit(model_output)
            cv2.waitKey(get_param("waitkey time"))     # 等待50ms，限制每s处理的帧数，避免占用过多cpu资源
