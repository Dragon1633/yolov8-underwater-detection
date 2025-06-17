# import cv2
#
# # 设置 RTSP 流地址
# rtsp_url = "rtsp://192.168.1.168:554/ch01.264"
#
# # 使用 OpenCV 打开 RTSP 流
# cap = cv2.VideoCapture(rtsp_url)
#
# if not cap.isOpened():
#     print("无法连接到 RTSP 流")
# else:
#     print("连接到 RTSP 流成功")
#
#     while True:
#         # 捕获每一帧画面
#         ret, frame = cap.read()
#
#         if not ret:
#             print("无法获取视频帧")
#             break
#
#         # 显示视频帧
#         cv2.imshow("Video", frame)
#
#         # 如果按下 'q' 键退出
#         if cv2.waitKey(1) & 0xFF == ord('q'):
#             break
#
#     # 释放资源
#     cap.release()
#     cv2.destroyAllWindows()


import cv2

# 配置参数
rtsp_url = "rtsp://192.168.1.168:554/ch01.264?stimeout=5000000"  # 5秒超时
# rtsp_url = 0  # 5秒超时
max_init_retry = 3  # 初始化最大重试次数
max_errors = 15  # 连续读取失败最大容忍次数


def check_stream_alive(cap):
    """验证流是否真实有效（尝试读取首帧）"""
    for _ in range(max_init_retry):
        if cap.read()[0]:
            return True
    return False


# 初始化视频流
cap = cv2.VideoCapture(rtsp_url)

# 第一阶段检查：基础连接状态
if not cap.isOpened():
    print("[错误] 无法建立RTSP基础连接")
    exit()

# 第二阶段检查：验证流数据是否可达
print("已建立基础连接，正在验证数据流...")
if not check_stream_alive(cap):
    print("[错误] 流数据不可达，可能设备离线或地址错误")
    cap.release()
    exit()

# 进入正常播放流程
print("RTSP流验证通过，开始播放")
error_count = 0

while True:
    ret, frame = cap.read()

    if not ret:
        error_count += 1
        print(f"视频流异常（{error_count}/{max_errors}）")

        if error_count >= max_errors:
            print("连续多次读取失败，判定为断流")
            break
        continue

    error_count = 0  # 重置计数器

    cv2.imshow('监控画面', frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# 资源清理
cap.release()
cv2.destroyAllWindows()
print("播放器已正常退出")