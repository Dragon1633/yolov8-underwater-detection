import cv2


video_source = "rtsp://192.168.1.168:554/ch01.264"


cap = cv2.VideoCapture(video_source)
ret,frame = cap.read()
while ret:
    ret,frame = cap.read()
    cv2.imshow("frame",frame)
    if cv2.waitKey(25) & 0xFF == ord('q'):
        break
cv2.destroyAllWindows()
cap.release()