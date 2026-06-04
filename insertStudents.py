import argparse
import os
import sqlite3


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
DB_PATH = os.path.join(BASE_DIR, "attendance.db")


def parse_args():
    parser = argparse.ArgumentParser(description="Import students from dataset folders.")
    parser.add_argument("--program", default="UG")
    parser.add_argument("--department", default="ECE")
    parser.add_argument("--year", default="1")
    parser.add_argument("--section", default="A")
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.isdir(DATASET_DIR):
        print("Dataset folder not found")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    inserted = 0

    for folder in sorted(os.listdir(DATASET_DIR)):
        folder_path = os.path.join(DATASET_DIR, folder)

        if not os.path.isdir(folder_path) or "_" not in folder:
            continue

        reg, name = folder.split("_", 1)
        name = name.replace("_", " ").strip()

        cursor.execute("SELECT 1 FROM students WHERE register_number = ?", (reg,))

        if cursor.fetchone():
            print(f"Already exists: {name}")
            continue

        cursor.execute("""
            INSERT INTO students (name, register_number, program, department, year, section)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, reg, args.program, args.department, args.year, args.section))

        inserted += 1
        print(f"Inserted: {name}")

    conn.commit()
    conn.close()

    print(f"Student import completed. Inserted {inserted} student(s).")


if __name__ == "__main__":
    main()
