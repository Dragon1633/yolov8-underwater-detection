import json
import os
from pathlib import Path
import numpy as np
import ntpath


FILE = Path(__file__).resolve()
ROOT = FILE.parents[2]


def path_leaf(path):
    head, tail = ntpath.split(path)
    return tail or ntpath.basename(head)

# def get_classes(class_txt_file):
#     with open(class_txt_file, 'r') as f:
#         class_names = f.readlines()
#     class_names = [c.strip() for c in class_names]
#     print(class_names)
#     print(type(class_names))
#     return class_names


def get_param(para_name):
    # 获取json文件参数
    filename = "./params.json"
    if os.path.exists(filename):
        if para_name in ["classes", "detected object", "detected task", "model path", "model name", "whether save video", "save video path",
                         "save error path", "save picture interval", "save picture path", "no object time", "exist object time",
                         "waitkey time", "confidence", "iou", "focus", "scale", "modbus_ip", "modbus_port"]:
            with open(filename, encoding='utf-8') as f:
                content = f.read()
                param = json.loads(content)[para_name]
                if isinstance(param, (int, float)):
                    return param
                elif ',' in param:
                    return [p.strip() for p in param.split(",") if p.strip() != ""]
                elif '\\' in param:
                    return param.replace('\\', '/')
                else:
                    return param
        else:
            raise "你想要获取的参数名称输入错误，请修改"


def add_image_id(model_outputs, image_id):
    model_outputs_updated = []
    if model_outputs != []:
        for output in model_outputs:
            output["image_id"] = image_id
            model_outputs_updated.append(output.copy())
    return model_outputs_updated


def sigmoid(x):
    return 1 / (1 + np.exp(-x))

