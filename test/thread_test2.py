import cv2
import threading
import time

video_source = "rtsp://192.168.1.168:554/ch01.264"
cap = None
open_success = False
stop_event = threading.Event()

# 线程函数：专门用来尝试打开摄像头
def open_camera():
    global cap, open_success
    # 创建本地VideoCapture对象
    local_cap = cv2.VideoCapture(video_source)
    # 检查是否打开成功
    open_success = local_cap.isOpened()
    if open_success:
        # 如果打开成功，才赋值给全局对象
        cap = local_cap
    else:
        # 没打开则释放本地对象
        local_cap.release()
    # 通知主线程已完成操作
    stop_event.set()

# 启动线程去尝试打开
thread = threading.Thread(target=open_camera)
thread.start()

# 主线程等待5秒或等待线程完成（以先到者为准）
stop_event.wait(timeout=5.0)

# 判断结果
if not open_success:
    print("5秒内没打开！强制返回！")
    # 确保线程已停止
    if thread.is_alive():
        # 虽然不能强制终止线程，但可以通过超时让它自然结束
        thread.join(timeout=1.0)
    if cap:
        cap.release()
else:
    # 打开成功，正常显示视频
    print("打开成功！")
    while True:
        ret, frame = cap.read()
        if not ret:
            print("视频流断了")
            break
        cv2.imshow("frame", frame)
        if cv2.waitKey(25) & 0xFF == ord('q'):
            break
    cv2.destroyAllWindows()
    cap.release()