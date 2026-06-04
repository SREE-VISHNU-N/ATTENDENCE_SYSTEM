import cv2
import face_recognition
import os
import numpy as np
import datetime
import sqlite3

dataset_path = "dataset"

known_encodings = []
known_names = []

print("Loading dataset...")

# Load dataset
for folder in os.listdir(dataset_path):
    folder_path = os.path.join(dataset_path, folder)

    if not os.path.isdir(folder_path):
        continue

    for image_name in os.listdir(folder_path):
        image_path = os.path.join(folder_path, image_name)

        image = face_recognition.load_image_file(image_path)
        encodings = face_recognition.face_encodings(image)

        if len(encodings) > 0:
            known_encodings.append(encodings[0])
            known_names.append(folder)

print("Encoding completed")

# Connect DB
conn = sqlite3.connect("attendance.db")
cursor = conn.cursor()

marked_students = set()
name_counter = {}

cap = cv2.VideoCapture(2)

cv2.namedWindow("Attendance System", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Attendance System", 700, 500)

process_frame = True
face_locations = []
face_encodings = []

print("Press 'q' to exit")

while True:
    ret, frame = cap.read()
    if not ret:
        break

    small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    rgb_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

    if process_frame:
        face_locations = face_recognition.face_locations(rgb_small, model="hog")
        face_encodings = face_recognition.face_encodings(rgb_small, face_locations)

    process_frame = not process_frame

    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):

        top *= 2
        right *= 2
        bottom *= 2
        left *= 2

        face_distances = face_recognition.face_distance(known_encodings, face_encoding)

        name = "Unknown"

        if len(face_distances) > 0:
            best_match_index = np.argmin(face_distances)

            if face_distances[best_match_index] < 0.55:
                name = known_names[best_match_index]

        cv2.rectangle(frame, (left, top), (right, bottom), (0, 255, 0), 2)
        cv2.putText(frame, name, (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        if name != "Unknown":

            name_counter[name] = name_counter.get(name, 0) + 1

            if name_counter[name] >= 5 and name not in marked_students:

                reg_no, student_name = name.split("_", 1)

                # Get student_id
                cursor.execute("""
                SELECT student_id FROM students WHERE register_number = ?
                """, (reg_no,))
                result = cursor.fetchone()

                if result:
                    student_id = result[0]

                    now = datetime.datetime.now()
                    date = now.strftime("%Y-%m-%d")
                    time = now.strftime("%H:%M:%S")

                    # Insert attendance
                    # ✅ NEW INSERT
                    cursor.execute("""
                    INSERT INTO attendance (student_id, name, register_number, date, time, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (student_id, student_name, reg_no, date, time, "Present"))

                    conn.commit()

                    marked_students.add(name)
                    print(f"{student_name} marked present in DB")

    cv2.imshow("Attendance System", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
conn.close()
cv2.destroyAllWindows()