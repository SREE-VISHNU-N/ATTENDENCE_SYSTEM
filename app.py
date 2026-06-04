from flask import Flask, render_template, request, jsonify, redirect, session, url_for, Response, send_from_directory, send_file
import sqlite3
import base64
import os
import datetime
import hmac
import json
import secrets
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "attendance.db")
DATASET_DIR = os.path.join(BASE_DIR, "dataset")
MODEL_PATH = os.path.join(BASE_DIR, "encodings.pkl")


def load_env_file(path=None):
    if path is None:
        path = os.path.join(BASE_DIR, ".env")

    if not os.path.exists(path):
        return

    with open(path) as env_file:
        for line in env_file:
            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


load_env_file()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-key")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
recognition_process = None


def get_db():
    return sqlite3.connect(DB_PATH)


def safe_dataset_folder_name(register_number, name):
    allowed = []

    for char in f"{register_number}_{name}":
        if char.isalnum() or char in ("-", "_"):
            allowed.append(char)
        elif char.isspace():
            allowed.append("_")

    folder_name = "".join(allowed).strip("_")
    return folder_name or str(register_number)


def find_student_folder(register_number):
    if not os.path.isdir(DATASET_DIR):
        return None

    for folder in os.listdir(DATASET_DIR):
        folder_path = os.path.join(DATASET_DIR, folder)

        if os.path.isdir(folder_path) and folder.startswith(f"{register_number}_"):
            return folder_path

    return None


def get_filters():
    return {
        "program": request.args.get("program", ""),
        "dept": request.args.get("dept", ""),
        "year": request.args.get("year", ""),
        "section": request.args.get("section", ""),
        "date_from": request.args.get("date_from", ""),
        "date_to": request.args.get("date_to", "")
    }


def apply_class_filters(query, params, filters, table_type="attendance"):
    dept_column = "department"

    if filters.get("program"):
        query += " AND program = ?"
        params.append(filters["program"])

    if filters.get("dept"):
        query += f" AND {dept_column} = ?"
        params.append(filters["dept"])

    if filters.get("year"):
        query += " AND year = ?"
        params.append(filters["year"])

    if filters.get("section"):
        query += " AND section = ?"
        params.append(filters["section"])

    if table_type == "attendance":
        if filters.get("date_from"):
            query += " AND date >= ?"
            params.append(filters["date_from"])

        if filters.get("date_to"):
            query += " AND date <= ?"
            params.append(filters["date_to"])

    return query, params


def approved_google_email(email):
    allowed = os.environ.get("ALLOWED_GOOGLE_EMAILS", "").strip()
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()

    if not email:
        return False

    email = email.lower()

    if email == admin_email:
        return True

    if not allowed:
        return email == admin_email

    allowed_emails = [item.strip().lower() for item in allowed.split(",") if item.strip()]
    return email in allowed_emails


def current_user_role():
    user = session.get("user", {})
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()

    if user.get("email", "").lower() == admin_email:
        return "admin"

    return user.get("role", "staff")


def admin_required():
    return current_user_role() == "admin"


def update_env_value(key, value, path=".env"):
    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)

    lines = []
    found = False

    if os.path.exists(path):
        with open(path) as env_file:
            lines = env_file.readlines()

    with open(path, "w") as env_file:
        for line in lines:
            if line.startswith(f"{key}="):
                env_file.write(f"{key}={value}\n")
                found = True
            else:
                env_file.write(line)

        if not found:
            env_file.write(f"{key}={value}\n")

    os.environ[key] = value


def month_bounds(month_value):
    if month_value:
        start = datetime.datetime.strptime(month_value, "%Y-%m").date()
    else:
        today = datetime.date.today()
        start = today.replace(day=1)

    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)

    end = next_month - datetime.timedelta(days=1)
    return start, end


@app.before_request
def require_login():
    public_routes = {"login", "password_login", "google_login", "google_callback", "forgot_password", "static"}

    if request.endpoint in public_routes:
        return

    if "user" not in session:
        return redirect(url_for("login"))

    admin_routes = {
        "register", "save_face", "students", "edit_student",
        "delete_student", "train_model", "start_recognition", "stop_recognition",
        "backup_db"
    }

    if request.endpoint in admin_routes and not admin_required():
        return redirect(url_for("index"))


@app.route('/login')
def login():
    toast = session.pop("login_toast", None)

    return render_template(
        "login.html",
        google_ready=bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        toast_message=toast["message"] if toast else None,
        toast_type=toast["type"] if toast else None
    )


@app.route('/login', methods=['POST'])
def password_login():
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "").strip()

    valid_email = hmac.compare_digest(email, admin_email)
    valid_password = hmac.compare_digest(password, admin_password)

    if admin_email and admin_password and valid_email and valid_password:
        session["user"] = {
            "name": email.split("@")[0],
            "email": email,
            "picture": None,
            "role": "admin"
        }
        if not wants_json:
            return redirect(url_for("index"))

        return jsonify({
            "success": True,
            "message": "Login successful",
            "redirect": url_for("index")
        })

    if not wants_json:
        session["login_toast"] = {
            "message": "Invalid email or password",
            "type": "error"
        }

        return redirect(url_for("login"))

    return jsonify({
        "success": False,
        "message": "Invalid email or password"
    }), 401


@app.route('/login/google')
def google_login():
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return redirect(url_for("login"))

    state = secrets.token_urlsafe(24)
    session["oauth_state"] = state

    redirect_uri = os.environ.get(
        "GOOGLE_REDIRECT_URI",
        url_for("google_callback", _external=True)
    )

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
        "prompt": "select_account"
    }

    return redirect(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")


@app.route('/auth/google/callback')
def google_callback():
    if request.args.get("state") != session.get("oauth_state"):
        return redirect(url_for("login"))

    code = request.args.get("code")

    if not code:
        return redirect(url_for("login"))

    redirect_uri = os.environ.get(
        "GOOGLE_REDIRECT_URI",
        url_for("google_callback", _external=True)
    )

    token_data = urllib.parse.urlencode({
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }).encode()

    token_request = urllib.request.Request(
        GOOGLE_TOKEN_URL,
        data=token_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )

    try:
        with urllib.request.urlopen(token_request) as response:
            token_response = json.loads(response.read().decode())

        access_token = token_response.get("access_token")

        if not access_token:
            return redirect(url_for("login"))

        user_request = urllib.request.Request(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"}
        )

        with urllib.request.urlopen(user_request) as response:
            user_info = json.loads(response.read().decode())

    except Exception:
        return redirect(url_for("login"))

    session["user"] = {
        "name": user_info.get("name"),
        "email": user_info.get("email"),
        "picture": user_info.get("picture"),
        "role": "admin" if user_info.get("email", "").lower() == os.environ.get("ADMIN_EMAIL", "").strip().lower() else "staff"
    }

    if not approved_google_email(session["user"]["email"]):
        session.clear()
        session["login_toast"] = {
            "message": "This Google account is not approved",
            "type": "error"
        }
        return redirect(url_for("login"))

    session.pop("oauth_state", None)

    return redirect(url_for("index"))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route('/forgot_password')
def forgot_password():
    return render_template("forgot_password.html")

# -------------------- HOME --------------------
@app.route('/')
def index():
    filters = get_filters()

    conn = get_db()
    cursor = conn.cursor()

    today = datetime.datetime.now().strftime("%Y-%m-%d")

    student_query = "SELECT COUNT(*) FROM students WHERE 1=1"
    student_params = []

    student_query, student_params = apply_class_filters(
        student_query, student_params, filters, table_type="students"
    )

    attendance_where = ""
    attendance_params = []
    attendance_filter_query, attendance_params = apply_class_filters(
        "SELECT 1 FROM attendance WHERE 1=1", attendance_params, filters, table_type="attendance"
    )
    attendance_where = attendance_filter_query.replace("SELECT 1 FROM attendance WHERE 1=1", "")

    cursor.execute(student_query, student_params)
    total_students = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT COUNT(DISTINCT register_number)
        FROM attendance
        WHERE date = ? AND status = 'Present' {attendance_where}
    """, [today] + attendance_params)
    today_attendance = cursor.fetchone()[0]

    absentees = max(total_students - today_attendance, 0)

    cursor.execute(f"""
        SELECT date, COUNT(DISTINCT register_number)
        FROM attendance
        WHERE status = 'Present' {attendance_where}
        GROUP BY date
        ORDER BY date DESC
        LIMIT 5
    """, attendance_params)
    chart_rows = cursor.fetchall()

    absentees_query = """
        SELECT name, register_number, program, department, year, section
        FROM students
        WHERE 1=1
    """
    absentees_params = []
    absentees_query, absentees_params = apply_class_filters(
        absentees_query, absentees_params, filters, table_type="students"
    )
    absentees_query += """
        AND register_number NOT IN (
            SELECT register_number FROM attendance
            WHERE date = ? AND status = 'Present'
        )
        ORDER BY name
    """
    cursor.execute(absentees_query, absentees_params + [today])
    absentees_list = cursor.fetchall()

    month_start, month_end = month_bounds(datetime.date.today().strftime("%Y-%m"))
    cursor.execute("""
        SELECT name, register_number
        FROM students
        ORDER BY name
    """)
    all_students_for_warning = cursor.fetchall()
    low_threshold = int(os.environ.get("LOW_ATTENDANCE_PERCENT", "75"))
    total_month_days = (month_end - month_start).days + 1
    low_attendance_list = []

    for student_name, reg_no in all_students_for_warning:
        cursor.execute("""
            SELECT COUNT(DISTINCT date)
            FROM attendance
            WHERE register_number = ? AND status = 'Present' AND date BETWEEN ? AND ?
        """, (reg_no, month_start.strftime("%Y-%m-%d"), month_end.strftime("%Y-%m-%d")))
        present_days = cursor.fetchone()[0]
        percentage = round((present_days / total_month_days) * 100, 1) if total_month_days else 0

        if percentage < low_threshold:
            low_attendance_list.append((student_name, reg_no, percentage))

    conn.close()

    chart_rows.reverse()
    chart_labels = [row[0] for row in chart_rows]
    chart_values = [row[1] for row in chart_rows]

    return render_template(
        'index.html',
        total_students=total_students,
        today_attendance=today_attendance,
        absentees=absentees,
        chart_labels=chart_labels,
        chart_values=chart_values,
        absentees_list=absentees_list,
        low_attendance_list=low_attendance_list,
        low_threshold=low_threshold,
        filters=filters,
        role=current_user_role()
    )


# -------------------- ATTENDANCE --------------------
@app.route('/attendance')
def attendance():
    filters = get_filters()

    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM attendance WHERE 1=1"
    params = []

    query, params = apply_class_filters(query, params, filters, table_type="attendance")

    query += " ORDER BY date DESC, time DESC"

    cursor.execute(query, params)
    data = cursor.fetchall()

    conn.close()

    return render_template(
        "attendance.html",
        data=data,
        filters=filters,
        role=current_user_role()
    )


@app.route('/attendance/export')
def export_attendance():
    filters = get_filters()
    conn = get_db()
    cursor = conn.cursor()

    query = "SELECT * FROM attendance WHERE 1=1"
    params = []
    query, params = apply_class_filters(query, params, filters, table_type="attendance")
    query += " ORDER BY date DESC, time DESC"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    lines = ["ID,Student ID,Name,Register Number,Program,Department,Year,Section,Date,Time,Status"]

    for row in rows:
        escaped = [str(item).replace('"', '""') if item is not None else "" for item in row]
        lines.append(",".join(f'"{item}"' for item in escaped))

    csv_data = "\n".join(lines)

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=attendance.csv"}
    )


@app.route('/reports')
def reports():
    selected_month = request.args.get("month", datetime.date.today().strftime("%Y-%m"))
    start, end = month_bounds(selected_month)
    total_days = (end - start).days + 1

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT student_id, name, register_number, program, department, year, section
        FROM students
        ORDER BY name
    """)
    students_data = cursor.fetchall()

    report_rows = []

    for student in students_data:
        cursor.execute("""
            SELECT COUNT(DISTINCT date)
            FROM attendance
            WHERE register_number = ? AND status = 'Present' AND date BETWEEN ? AND ?
        """, (student[2], start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
        present_days = cursor.fetchone()[0]
        percentage = round((present_days / total_days) * 100, 1) if total_days else 0
        report_rows.append(student + (present_days, total_days, percentage))

    conn.close()

    low_threshold = int(os.environ.get("LOW_ATTENDANCE_PERCENT", "75"))

    return render_template(
        "reports.html",
        report_rows=report_rows,
        month=selected_month,
        low_threshold=low_threshold,
        role=current_user_role()
    )


@app.route('/reports/print')
def print_report():
    selected_month = request.args.get("month", datetime.date.today().strftime("%Y-%m"))
    start, end = month_bounds(selected_month)
    total_days = (end - start).days + 1

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, register_number, program, department, year, section
        FROM students
        ORDER BY name
    """)
    students_data = cursor.fetchall()

    report_rows = []

    for student in students_data:
        cursor.execute("""
            SELECT COUNT(DISTINCT date)
            FROM attendance
            WHERE register_number = ? AND status = 'Present' AND date BETWEEN ? AND ?
        """, (student[1], start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")))
        present_days = cursor.fetchone()[0]
        percentage = round((present_days / total_days) * 100, 1) if total_days else 0
        report_rows.append(student + (present_days, total_days, percentage))

    conn.close()

    return render_template(
        "report_print.html",
        report_rows=report_rows,
        month=selected_month,
        generated_on=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    )


@app.route('/backup_db')
def backup_db():
    return send_file(
        DB_PATH,
        as_attachment=True,
        download_name=f"attendance_backup_{datetime.date.today().strftime('%Y%m%d')}.db"
    )


# -------------------- REGISTER PAGE --------------------
@app.route('/register')
def register():
    return render_template('register.html', role=current_user_role())


@app.route('/students')
def students():
    search = request.args.get("search", "").strip()
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT student_id, name, register_number, program, department, year, section, created_at
        FROM students
        WHERE 1=1
    """
    params = []

    if search:
        query += " AND (name LIKE ? OR register_number LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    query += " ORDER BY student_id DESC"
    cursor.execute(query, params)
    student_rows = cursor.fetchall()
    conn.close()

    return render_template("students.html", students=student_rows, search=search, role=current_user_role())


@app.route('/students/<int:student_id>/edit', methods=['POST'])
def edit_student(student_id):
    name = request.form.get("name", "").strip()
    reg = request.form.get("register_number", "").strip()
    program = request.form.get("program", "").strip()
    dept = request.form.get("department", "").strip()
    year = request.form.get("year", "").strip()
    section = request.form.get("section", "").strip()

    if not all([name, reg, program, dept, year, section]):
        return redirect(url_for("students"))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name, register_number FROM students WHERE student_id = ?", (student_id,))
    existing = cursor.fetchone()

    if not existing:
        conn.close()
        return redirect(url_for("students"))

    old_name, old_reg = existing

    try:
        cursor.execute("""
            UPDATE students
            SET name = ?, register_number = ?, program = ?, department = ?, year = ?, section = ?
            WHERE student_id = ?
        """, (name, reg, program, dept, year, section, student_id))
        cursor.execute("""
            UPDATE attendance
            SET student_id = ?, name = ?, register_number = ?, program = ?, department = ?, year = ?, section = ?
            WHERE register_number = ?
        """, (student_id, name, reg, program, dept, year, section, old_reg))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()
        return redirect(url_for("students"))

    conn.close()

    old_folder = find_student_folder(old_reg)

    if old_folder:
        new_folder = os.path.join(DATASET_DIR, safe_dataset_folder_name(reg, name))

        if os.path.abspath(old_folder) != os.path.abspath(new_folder) and not os.path.exists(new_folder):
            os.rename(old_folder, new_folder)

    return redirect(url_for("students"))


@app.route('/students/<int:student_id>/delete', methods=['POST'])
def delete_student(student_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT register_number, name FROM students WHERE student_id = ?", (student_id,))
    student = cursor.fetchone()

    if student:
        reg, name = student
        cursor.execute("DELETE FROM attendance WHERE register_number = ?", (reg,))
        cursor.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
        conn.commit()

        folder_path = find_student_folder(reg) or os.path.join(DATASET_DIR, safe_dataset_folder_name(reg, name))

        if os.path.isdir(folder_path):
            shutil.rmtree(folder_path)

    conn.close()

    return redirect(url_for("students"))


@app.route('/student_photo/<register_number>')
def student_photo(register_number):
    folder_path = find_student_folder(register_number)

    if folder_path:
        photos = sorted(
            photo for photo in os.listdir(folder_path)
            if photo.lower().endswith((".jpg", ".jpeg", ".png"))
        )

        if photos:
            return send_from_directory(folder_path, photos[0])

    return Response(status=404)


@app.route('/train_model', methods=['POST'])
def train_model():
    try:
        result = subprocess.run(
            [sys.executable, "trainModel.py"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=120
        )

        return jsonify({
            "success": result.returncode == 0,
            "message": "Training completed" if result.returncode == 0 else "Training failed",
            "output": result.stdout[-1000:] + result.stderr[-1000:]
        })

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/recognition/start', methods=['POST'])
def start_recognition():
    global recognition_process

    if recognition_process and recognition_process.poll() is None:
        return jsonify({"success": True, "message": "Recognition is already running"})

    camera_index = request.form.get("camera_index", os.environ.get("CAMERA_INDEX", "0")).strip() or "0"

    if not camera_index.isdigit():
        return jsonify({"success": False, "message": "Camera index must be a number"}), 400

    if not os.path.exists(MODEL_PATH):
        return jsonify({"success": False, "message": "Train the face model before starting recognition"}), 400

    env = os.environ.copy()
    env["CAMERA_INDEX"] = camera_index
    recognition_process = subprocess.Popen([sys.executable, "recognize.py"], cwd=BASE_DIR, env=env)

    return jsonify({"success": True, "message": f"Recognition started on camera {camera_index}"})


@app.route('/recognition/stop', methods=['POST'])
def stop_recognition():
    global recognition_process

    if not recognition_process or recognition_process.poll() is not None:
        return jsonify({"success": True, "message": "Recognition is not running"})

    recognition_process.terminate()
    recognition_process = None

    return jsonify({"success": True, "message": "Recognition stopped"})


# -------------------- SAVE FACE --------------------
@app.route('/save_face', methods=['POST'])
def save_face():

    data = request.get_json(silent=True)

    if not data:
        return jsonify({"message": "No data received!"}), 400

    name = str(data.get('name', '')).strip()
    reg = str(data.get('reg', '')).strip()
    program = str(data.get('program', '')).strip()
    dept = str(data.get('dept', '')).strip()
    year = str(data.get('year', '')).strip()
    section = str(data.get('section', '')).strip()
    image_data = data.get('image', '')

    if not all([name, reg, program, dept, year, section, image_data]):
        return jsonify({"message": "All fields and image are required"}), 400

    # ---------------- DATABASE ----------------
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM students WHERE register_number = ?", (reg,))
    existing = cursor.fetchone()

    if not existing:
        try:
            cursor.execute("""
                INSERT INTO students (name, register_number, program, department, year, section)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, reg, program, dept, year, section))

            conn.commit()

        except Exception as e:
            conn.close()
            return jsonify({"message": f"DB Error: {str(e)}"}), 500

    conn.close()

    # ---------------- SAVE IMAGE ----------------
    folder_name = safe_dataset_folder_name(reg, name)
    folder_path = os.path.join(DATASET_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    try:
        image_data = image_data.split(",")[1]
        image_bytes = base64.b64decode(image_data)
    except Exception:
        return jsonify({"message": "Invalid image data"}), 400

    filename = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S%f')}.jpg"
    file_path = os.path.join(folder_path, filename)

    with open(file_path, "wb") as f:
        f.write(image_bytes)

    return jsonify({"message": "Saved"})


# -------------------- RUN --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, port=port)
