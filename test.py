import time

import cv2
import json
import numpy as np


def get_classes(class_json_file):
    with open(class_json_file, encoding='utf-8') as f:
        content = f.read()
        class_names = json.loads(content)["classes"]
        class_names = [i for i in class_names.split(",") if i != ""]
    return class_names


def save_picture(picture=1):
    now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    print("保存图片：", now)
    now_date = now[0:10]
    now_h = now[11:13]
    now_min = now[14:16]
    now_name = now[11:19]
    print(now_date)
    print(now_h)
    print(now_min)
    print(now_name)

def find_circle(img):
    img1 = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, black_white = cv2.threshold(img1, 50, 255, cv2.THRESH_BINARY)
    contours, hierarchy = cv2.findContours(black_white, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(img, contours, -1, (0, 255, 0), 3)
    cv2.imshow("img", img)
    cv2.waitKey(0)

picture_path = "C:\\Users\\16339\\Desktop\\水下检测\\Picture-2024-07-11_17_45_41.jpg"
img = cv2.imdecode(np.fromfile(picture_path, dtype=np.uint8), cv2.IMREAD_COLOR)
# img = cv2.imread(picture_path)
# find_circle(img)

# 使用Canny边缘检测
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
edges = cv2.Canny(gray, 50, 150)

# 使用Hough Circle变换检测圆形
circles = cv2.HoughCircles(edges, cv2.HOUGH_GRADIENT, 1, minDist=150, param1=250, param2=80, minRadius=100, maxRadius=0)

# 如果检测到至少一个圆，则提取它
# if circles is not None:
#     circles = np.round(circles[0, :]).astype("int")
circles = np.round(circles[0,:]).astype("int")
circles = circles[np.argmax(circles[:,2])]

# 提取圆形区域
(x, y, r) = circles
# 检查圆形是否在图像范围内
center_circle = img
# 可视化结果
cv2.circle(img, (x, y), r, (0, 255, 0), 2)



# 显示原图上的标记
cv2.imshow("Detected Circles", img)
cv2.waitKey(0)
cv2.destroyAllWindows()



