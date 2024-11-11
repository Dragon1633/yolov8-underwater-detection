import copy
import cv2
from PyQt5.QtCore import QThread, pyqtSignal
from src.models.detection.yolov8_detector_onnx_c import YoloDetector
from src.models.tracking.deep_sort.deep_sort import DeepSort
from src.models.tracking.byte_track.byte_tracker import BYTETracker

from src.data_type.video_buffer import LatestFrame
from src.utils.general import ROOT, add_image_id, get_param
from src.utils.visualize import draw_results_circle, draw_results
import os
import time


class AiWorkerThread2(QThread):
    send_ai_output = pyqtSignal(list)

    def __init__(self):
        super(AiWorkerThread2, self).__init__()
        self.thread_name = "AiWorkerThread"
        self.threadFlag = False

    def set_start_config(self, model_name="yolov8n_circle", confidence_threshold=0.35,
                         iou_threshold=0.45):
        self.threadFlag = True
        self.latest_frame = LatestFrame()
        self.confi_thr = confidence_threshold
        self.iou_thr = iou_threshold
        self.model_name = model_name
        self._init_yolo()
        # self._init_tracker()
        # print(self.model_name)

    def set_iou_threshold(self, iou_threshold):
        self.iou_thr = iou_threshold

    def set_confidence_threshold(self, confidence_threshold):
        self.confi_thr = confidence_threshold

    def set_model_name(self, model_name):
        self.model_name = model_name

    def _init_yolo(self):
        model_path = get_param("model path")
        self.detector = YoloDetector()
        self.detector.init(
            # model_path=os.path.join("./", f"weights/detection/{self.model_name}.onnx"),
            # class_txt_path=os.path.join("./", "weights/classes.txt"),
            model_path=model_path + f"/{self.model_name}.onnx",
            confidence_threshold=self.confi_thr,
            iou_threshold=self.iou_thr)

    # def _init_tracker(self):
    #     if self.tracker_name == "deepsort":
    #         self.tracker = DeepSort(
    #             model_path=os.path.join(ROOT, f"weights/ckpt.t7"))
    #     elif self.tracker_name == "bytetrack":
    #         self.tracker = BYTETracker(
    #             track_high_thresh=0.5,
    #             track_low_thresh=0.1,
    #             new_track_thresh=0.6,
    #             match_thresh=0.8,
    #             track_buffer=30,
    #             frame_rate=30)

    def get_frame(self, frame_list):
        self.latest_frame.put(frame=frame_list[1], frame_id=frame_list[0], realtime=True)

    def stop_process(self):
        self.threadFlag = False

    def run(self):
        time0 = time.time()
        id = 0
        while self.threadFlag:
            frame_id, frame = self.latest_frame.get()

            # if time.time() - time0 >= 1:
            #     time0 = time.time()
            #     # print("时间经过1s！！！！！！！")
            #     print("1s检测的帧为：", id)
            #     id = 0
            if frame_id is None:
                break
            id += 1
            result = self.get_model_output(frame)

            # self.model_output = add_image_id(model_output, frame_id)
            self.send_ai_output.emit(result)
            cv2.waitKey(get_param("waitkey time"))  # 等待50ms，限制每s处理的帧数，避免占用过多cpu资源

    def get_model_output(self, frame, use_tracker=True):
        model_output = self.detector.inference(frame, self.confi_thr, self.iou_thr)
        # if use_tracker:
        #     model_output = self.tracker.update(detection_results=model_output, ori_img=frame)
        result = draw_results_circle(frame, model_output)
        # result = draw_results(frame, model_output)
        return result
