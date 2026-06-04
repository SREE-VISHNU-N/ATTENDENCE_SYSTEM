import sqlite3
import os

dataset_path = "dataset"

conn = sqlite3.connect("attendance.db")
cursor = conn.cursor()

for folder in os.listdir(dataset_path):

    # Skip invalid folders
    if "_" not in folder:
        continue

    try:
        reg, name = folder.split("_", 1)

    

        # 🔥 Check duplicate
        cursor.execute("SELECT * FROM students WHERE register_number = ?", (reg,))
        exists = cursor.fetchone()

        if exists:
            print(f"Already exists: {name}")
            continue

        # 🔥 Insert student
        cursor.execute("""
            INSERT INTO students (name, register_number, program, department, year, section)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, reg, program, department, year, section))

        print(f"Inserted: {name}")

    except Exception as e:
        print(f"Error with folder {folder}: {e}")

conn.commit()
conn.close()

print("✅ All students processed!")