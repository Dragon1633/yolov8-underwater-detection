import numpy as np

def process_image(image, additional_data):
    # 假设 image 是一个 numpy 数组
    # additional_data 是其他数据
    result_list = [image, additional_data]
    return result_list

# 测试代码
image = np.zeros((100, 100, 3), dtype=np.uint8)  # 创建一个空白图像
additional_data = "Some additional data"

result = process_image(image, additional_data)
print(result)
