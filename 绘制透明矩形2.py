import cv2
import numpy as np

# 读取原始图像
image = cv2.imread('test.jpg')

# 定义正方形的起始点和边长
squares = [
    ((100, 100), 50),  # (左上角坐标, 边长)
    ((200, 200), 80),
    ((300, 300), 100)
]

# 透明度
alpha = 0.5

# 复制原图用于绘制
output = image.copy()

# 在指定区域绘制带有透明度的正方形
for (top_left, size) in squares:
    bottom_right = (top_left[0] + size, top_left[1] + size)

    # 只绘制正方形区域，不影响其他区域
    roi = output[top_left[1]:bottom_right[1], top_left[0]:bottom_right[0]]

    # 创建一个与正方形区域相同大小的矩形并设置颜色
    square = np.zeros_like(roi, dtype=np.uint8)
    color = (0, 255, 0)  # 绿色
    cv2.rectangle(square, (0, 0), (size, size), color, -1)

    # 将正方形与该区域进行透明混合
    cv2.addWeighted(square, alpha, roi, 1 - alpha, 0, roi)

# 保存并显示结果
# cv2.imwrite('output_image.jpg', output)
cv2.imshow('Output', output)
cv2.waitKey(0)
cv2.destroyAllWindows()
