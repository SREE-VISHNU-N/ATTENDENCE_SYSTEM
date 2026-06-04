import cv2

face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')

cap = cv2.VideoCapture(2)

cv2.namedWindow("Face Detection", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Face Detection", 600, 400)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    for (x, y, w, h) in faces:
        cv2.rectangle(frame, (x, y), (x+w, y+h), (255, 0, 0), 2)

    cv2.imshow("Face Detection", frame)

    key = cv2.waitKey(1) & 0xFF

    # Press 'q' to quit OR auto stop at 50 images
    if key == ord('q') or count >= 50:
        break

cap.release()
cv2.destroyAllWindows()