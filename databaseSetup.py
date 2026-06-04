import sqlite3

conn = sqlite3.connect("attendance.db")
cursor = conn.cursor()

# 🔥 Students Table (FINAL VERSION)
cursor.execute("""
CREATE TABLE students (
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

# 🔥 Attendance Table (FINAL VERSION)
cursor.execute("""
CREATE TABLE attendance (
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

print("✅ Database created successfully!")