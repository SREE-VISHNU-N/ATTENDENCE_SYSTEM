import cv2
import os

# Ask student details
student_id = input("Enter Student ID: ")
name = input("Enter Name: ")

# Create dataset folder if not exists
dataset_path = "dataset"
os.makedirs(dataset_path, exist_ok=True)

# Create folder for this student
student_folder = os.path.join(dataset_path, f"{student_id}_{name}")
os.makedirs(student_folder, exist_ok=True)

# Load face detector
face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')

# Check if cascade loaded
if face_cascade.empty():
    print("Error loading cascade file")
    exit()

cap = cv2.VideoCapture(2)

# Window settings (not full screen)
cv2.namedWindow("Capturing Faces", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Capturing Faces", 600, 400)

count = 0

print("Press 'q' to stop capturing...")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Camera error")
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    faces = face_cascade.detectMultiScale(gray, 1.3, 5)

    for (x, y, w, h) in faces:
        count += 1

        face = gray[y:y+h, x:x+w]

        file_name = os.path.join(student_folder, f"{count}.jpg")
        cv2.imwrite(file_name, face)

        # Draw rectangle
        cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)

        # Show count
        cv2.putText(frame, f"Images: {count}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    cv2.imshow("Capturing Faces", frame)

    key = cv2.waitKey(1) & 0xFF

    # Press 'q' to quit OR auto stop at 50 images
    if key == ord('q') or count >= 50:
        break

cap.release()
cv2.destroyAllWindows()

print("Face data collected successfully!")