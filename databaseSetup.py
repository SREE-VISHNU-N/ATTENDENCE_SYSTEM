import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "attendance.db")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Students Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    register_number TEXT UNIQUE,
    program TEXT,
    department TEXT,
    year TEXT,
    section TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# Attendance Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    name TEXT,
    register_number TEXT,
    program TEXT,
    department TEXT,
    year TEXT,
    section TEXT,
    date TEXT,
    time TEXT,
    status TEXT
)
""")

conn.commit()
conn.close()

print("Database setup completed successfully!")
