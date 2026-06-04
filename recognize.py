import cv2
import face_recognition
import os
import pickle
import sqlite3
from datetime import datetime

# ---------------- LOAD MODEL ----------------
with open("encodings.pkl", "rb") as f:
    data = pickle.load(f)

print("✅ Model Loaded")

# ---------------- CAMERA ----------------
camera_index = int(os.environ.get("CAMERA_INDEX", "0"))
video = cv2.VideoCapture(camera_index)

marked_today = set()  # avoid duplicate attendance in same run

# ---------------- LOOP ----------------
while True:
    ret, frame = video.read()
    if not ret:
        print("❌ Camera not working")
        break

    # Convert to RGB
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Detect faces
    face_locations = face_recognition.face_locations(rgb)
    face_encodings = face_recognition.face_encodings(rgb, face_locations)

    # ---------------- PROCESS EACH FACE ----------------
    for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):

        matches = face_recognition.compare_faces(data["encodings"], face_encoding)
        name = "Unknown"

        if True in matches:
            matched_idx = matches.index(True)
            name = data["names"][matched_idx]

            reg, student_name = name.split("_", 1)

            # Prevent duplicate marking
            if reg not in marked_today:
                marked_today.add(reg)

                now = datetime.now()
                date = now.strftime("%Y-%m-%d")
                time = now.strftime("%H:%M:%S")

                # ---------------- DATABASE ----------------
                conn = sqlite3.connect("attendance.db")
                cursor = conn.cursor()

                # Get student full details
                cursor.execute("""
                    SELECT student_id, program, department, year, section
                    FROM students
                    WHERE register_number = ?
                """, (reg,))

                student = cursor.fetchone()

                if student:
                    student_id, program, dept, year, section = student

                    cursor.execute("""
                        SELECT attendance_id FROM attendance
                        WHERE register_number = ? AND date = ? AND status = 'Present'
                    """, (reg, date))

                    already_marked = cursor.fetchone()

                    if already_marked:
                        print(f"Already marked today: {student_name}")
                    else:
                        cursor.execute("""
                            INSERT INTO attendance (
                                student_id, name, register_number,
                                program, department, year, section,
                                date, time, status
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            student_id,
                            student_name,
                            reg,
                            program,
                            dept,
                            year,
                            section,
                            date,
                            time,
                            "Present"
                        ))

                        conn.commit()
                        print(f"Attendance marked: {student_name}")

                else:
                    print("⚠️ Student not found in DB")

                conn.close()

        # ---------------- DRAW UI ----------------
        color = (0, 255, 0) if name != "Unknown" else (0, 0, 255)

        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.putText(frame, name, (left, top - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # Show window
    cv2.imshow("Attendance System", frame)

    # Press Q to exit
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# ---------------- CLEANUP ----------------
video.release()
cv2.destroyAllWindows()
