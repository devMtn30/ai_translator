import os
import uuid
from datetime import datetime, timedelta

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory, session
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_mail import Mail, Message
from openai import OpenAI

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)
bcrypt = Bcrypt(app)

app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")

app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "true").lower() == "true"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
default_sender = os.getenv("MAIL_DEFAULT_SENDER") or app.config["MAIL_USERNAME"] or "no-reply@example.com"
app.config["MAIL_DEFAULT_SENDER"] = default_sender
mail = Mail(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", os.getenv("DB_HOST", "localhost")),
    "user": os.getenv("MYSQL_USER", os.getenv("DB_USER", "root")),
    "password": os.getenv("MYSQL_PASSWORD", os.getenv("DB_PASSWORD", "")),
    "database": os.getenv("MYSQL_DB", os.getenv("DB_NAME", "pronoappsys")),
}


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def json_response(success, message, data=None, status=200):
    payload = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def build_base_url():
    override = os.getenv("APP_BASE_URL")
    if override:
        return override.rstrip("/")
    try:
        return request.host_url.rstrip("/")
    except RuntimeError:
        return ""


def create_token(cursor, table_name, user_id, hours_valid=24):
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(hours=hours_valid)
    cursor.execute(
        f"INSERT INTO {table_name} (user_id, token, expires_at) VALUES (%s, %s, %s)",
        (user_id, token, expires_at),
    )
    return token, expires_at


def mark_token_consumed(cursor, table_name, token_id):
    cursor.execute(
        f"UPDATE {table_name} SET consumed_at = %s WHERE id = %s",
        (datetime.utcnow(), token_id),
    )


def fetch_user_by_email(cursor, email):
    cursor.execute(
        """
        SELECT id, email, firstname, lastname, student_id, year, year_level, gender,
               password_hash, password, verified, verified_at, created_at
        FROM users
        WHERE email = %s
        """,
        (email,),
    )
    return cursor.fetchone()


def fetch_user_by_id(cursor, user_id):
    cursor.execute(
        """
        SELECT id, email, firstname, lastname, student_id, year, year_level, gender,
               password_hash, password, verified, verified_at, created_at
        FROM users
        WHERE id = %s
        """,
        (user_id,),
    )
    return cursor.fetchone()


def update_user_password(cursor, user_id, hashed_password):
    try:
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (hashed_password, user_id),
        )
    except mysql.connector.Error:
        pass
    cursor.execute(
        "UPDATE users SET password = %s WHERE id = %s",
        (hashed_password, user_id),
    )


def mark_user_verified(cursor, user_id, verified_at=None):
    if verified_at is None:
        verified_at = datetime.utcnow()
    cursor.execute(
        "UPDATE users SET verified = %s WHERE id = %s",
        (True, user_id),
    )
    try:
        cursor.execute(
            "UPDATE users SET verified_at = %s WHERE id = %s",
            (verified_at, user_id),
        )
    except mysql.connector.Error:
        pass


TABLE_DEFINITIONS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        student_id VARCHAR(64) UNIQUE,
        password VARCHAR(255) NOT NULL,
        password_hash VARCHAR(255),
        firstname VARCHAR(100),
        lastname VARCHAR(100),
        year VARCHAR(50),
        year_level VARCHAR(50),
        gender VARCHAR(20),
        verified TINYINT(1) DEFAULT 0,
        verified_at DATETIME NULL,
        verification_token VARCHAR(255),
        verification_expiry DATETIME NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_users_email (email),
        INDEX idx_users_student (student_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS email_verification_tokens (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        token VARCHAR(255) NOT NULL UNIQUE,
        expires_at DATETIME NOT NULL,
        consumed_at DATETIME NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_email_tokens_user FOREIGN KEY (user_id)
            REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        token VARCHAR(255) NOT NULL UNIQUE,
        expires_at DATETIME NOT NULL,
        consumed_at DATETIME NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_reset_tokens_user FOREIGN KEY (user_id)
            REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS reading_progress (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        book_name VARCHAR(255) NOT NULL,
        progress INT DEFAULT 0,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uniq_user_book (user_id, book_name),
        CONSTRAINT fk_reading_progress_user FOREIGN KEY (user_id)
            REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
]


def initialize_database():
    try:
        conn = get_db_connection()
    except mysql.connector.Error as exc:
        print(f"[init] Database connection failed; skipping auto-migrations: {exc}")
        return

    cursor = conn.cursor()
    try:
        for ddl in TABLE_DEFINITIONS:
            cursor.execute(ddl)
        conn.commit()
    except mysql.connector.Error as exc:
        conn.rollback()
        print(f"[init] Database initialization error: {exc}")
    finally:
        cursor.close()
        conn.close()


initialize_database()


def serialize_user(row):
    if not row:
        return None
    verified = row.get("verified_at") is not None or bool(row.get("verified"))
    return {
        "id": row.get("id"),
        "email": row.get("email"),
        "firstname": row.get("firstname"),
        "lastname": row.get("lastname"),
        "student_id": row.get("student_id"),
        "year": row.get("year") or row.get("year_level"),
        "gender": row.get("gender"),
        "verified": verified,
    }


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/reset/<token>", methods=["GET"])
def serve_reset_page(token):
    return send_from_directory(os.path.join(app.static_folder, "forgot"), "newpassword.html")


@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json() or {}
    required_fields = ["email", "password", "firstname", "lastname", "student_id", "year", "gender"]
    missing = [field for field in required_fields if not data.get(field)]
    if missing:
        return json_response(False, f"Missing fields: {', '.join(missing)}", status=400)

    hashed_password = bcrypt.generate_password_hash(data["password"]).decode("utf-8")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    token = None

    try:
        cursor.execute(
            """
            INSERT INTO users (firstname, lastname, year, student_id, gender, email, password, verified)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                data["firstname"],
                data["lastname"],
                data["year"],
                data["student_id"],
                data["gender"],
                data["email"],
                hashed_password,
                False,
            ),
        )
        user_id = cursor.lastrowid
        try:
            token, _ = create_token(cursor, "email_verification_tokens", user_id, hours_valid=24)
        except mysql.connector.Error:
            token = str(uuid.uuid4())
            expiry = datetime.utcnow() + timedelta(hours=24)
            cursor.execute(
                """
                UPDATE users
                SET verification_token = %s, verification_expiry = %s
                WHERE id = %s
                """,
                (token, expiry, user_id),
            )
        conn.commit()
    except mysql.connector.Error as exc:
        conn.rollback()
        if getattr(exc, "errno", None) == 1062:
            lowered = str(exc).lower()
            if "email" in lowered:
                return json_response(False, "This email is already registered.", status=400)
            if "student_id" in lowered:
                return json_response(False, "This student ID is already registered.", status=400)
        return json_response(False, f"Registration failed: {exc}", status=400)
    else:
        base_url = build_base_url()
        verify_url = f"{base_url}/api/verify/{token}" if base_url else f"/api/verify/{token}"
        msg = Message(
            "Verify your PronoCoach account",
            recipients=[data["email"]],
            body=(
                f"Hello {data['firstname']},\n\n"
                "Welcome to PronoCoach!\n"
                "Please verify your account by clicking the link below:\n"
                f"{verify_url}\n\n"
                "This link will expire in 24 hours."
            ),
        )
        try:
            mail.send(msg)
        except Exception as err:  # pragma: no cover - SMTP configuration dependent
            return json_response(
                False,
                f"Account created but failed to send verification email: {err}",
                status=500,
            )
        user_summary = {
            "email": data["email"],
            "firstname": data["firstname"],
            "lastname": data["lastname"],
            "student_id": data["student_id"],
            "year": data["year"],
            "gender": data["gender"],
        }
        return json_response(True, "Verification email sent. Please check your inbox.", {"user": user_summary}, status=201)
    finally:
        cursor.close()
        conn.close()


@app.route("/api/verify/<token>", methods=["GET"])
def verify_email(token):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        verification = None
        token_source = "table"
        try:
            cursor.execute(
                """
                SELECT evt.id, evt.user_id, evt.expires_at, evt.consumed_at
                FROM email_verification_tokens evt
                WHERE evt.token = %s
                """,
                (token,),
            )
            verification = cursor.fetchone()
        except mysql.connector.Error:
            verification = None

        if not verification:
            token_source = "legacy"
            cursor.execute(
                """
                SELECT id AS user_id, verification_expiry AS expires_at
                FROM users
                WHERE verification_token = %s
                """,
                (token,),
            )
            verification = cursor.fetchone()
            if not verification:
                return json_response(False, "Invalid verification token.", status=400)

        expires_at = verification.get("expires_at")
        if expires_at and datetime.utcnow() > expires_at:
            return json_response(False, "Verification link expired.", status=400)

        user_id = verification["user_id"]
        mark_user_verified(cursor, user_id)

        if token_source == "table":
            mark_token_consumed(cursor, "email_verification_tokens", verification["id"])
        else:
            cursor.execute(
                """
                UPDATE users
                SET verification_token = NULL, verification_expiry = NULL
                WHERE id = %s
                """,
                (user_id,),
            )

        conn.commit()
        return json_response(True, "Email verified successfully.")
    finally:
        cursor.close()
        conn.close()


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    identifier = data.get("email") or data.get("student_id")
    password = data.get("password")

    if not identifier or not password:
        return json_response(False, "Email or student ID and password are required.", status=400)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if data.get("email"):
            user = fetch_user_by_email(cursor, data["email"])
        else:
            cursor.execute(
                """
                SELECT id, email, firstname, lastname, student_id, year, year_level, gender,
                       password_hash, password, verified, verified_at
                FROM users
                WHERE student_id = %s
                """,
                (data["student_id"],),
            )
            user = cursor.fetchone()

        if not user:
            return json_response(False, "Invalid credentials.", status=401)

        stored_hash = user.get("password_hash") or user.get("password")
        if not stored_hash or not bcrypt.check_password_hash(stored_hash, password):
            return json_response(False, "Invalid credentials.", status=401)

        if not (user.get("verified") or user.get("verified_at")):
            return json_response(False, "Account is not verified yet.", status=403)

        session["user_id"] = user["id"]
        session["email"] = user["email"]
        session.permanent = True

        return json_response(True, "Login successful.", {"user": serialize_user(user)})
    finally:
        cursor.close()
        conn.close()


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return json_response(True, "Logged out.")


@app.route("/api/forgot", methods=["POST"])
def forgot_password():
    data = request.get_json() or {}
    email = data.get("email")
    if not email:
        return json_response(False, "Email is required.", status=400)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        user = fetch_user_by_email(cursor, email)
        if not user:
            return json_response(False, "No account found with that email.", status=404)

        user_id = user["id"]
        try:
            token, _ = create_token(cursor, "password_reset_tokens", user_id, hours_valid=1)
        except mysql.connector.Error:
            token = str(uuid.uuid4())
            expiry = datetime.utcnow() + timedelta(hours=1)
            cursor.execute(
                """
                UPDATE users
                SET verification_token = %s, verification_expiry = %s
                WHERE id = %s
                """,
                (token, expiry, user_id),
            )

        conn.commit()
    finally:
        cursor.close()
        conn.close()

    base_url = build_base_url()
    reset_url = f"{base_url}/reset/{token}" if base_url else f"/reset/{token}"
    msg = Message(
        "Reset your PronoCoach password",
        recipients=[email],
        body=(
            f"Hello {user['firstname']},\n\n"
            "We received a request to reset your password.\n"
            f"Click the link below to set a new password:\n{reset_url}\n\n"
            "If you did not request this, you can ignore this email.\n"
            "This link will expire in 1 hour."
        ),
    )
    try:
        mail.send(msg)
    except Exception as err:  # pragma: no cover - SMTP configuration dependent
        return json_response(False, f"Failed to send reset email: {err}", status=500)

    return json_response(True, "Password reset link sent to your email.")


def _handle_password_reset(token, new_password):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        token_row = None
        token_source = "table"
        try:
            cursor.execute(
                """
                SELECT prt.id, prt.user_id, prt.expires_at, prt.consumed_at,
                       u.password_hash, u.password
                FROM password_reset_tokens prt
                JOIN users u ON u.id = prt.user_id
                WHERE prt.token = %s
                """,
                (token,),
            )
            token_row = cursor.fetchone()
        except mysql.connector.Error:
            token_row = None

        if not token_row:
            token_source = "legacy"
            cursor.execute(
                """
                SELECT id AS user_id, verification_expiry AS expires_at,
                       password_hash, password
                FROM users
                WHERE verification_token = %s
                """,
                (token,),
            )
            token_row = cursor.fetchone()
            if not token_row:
                return json_response(False, "Invalid or expired reset token.", status=400)

        if token_row.get("consumed_at"):
            return json_response(False, "Reset link already used.", status=400)

        expires_at = token_row.get("expires_at")
        if expires_at and datetime.utcnow() > expires_at:
            return json_response(False, "Reset link expired.", status=400)

        stored_hash = token_row.get("password_hash") or token_row.get("password")
        if stored_hash and bcrypt.check_password_hash(stored_hash, new_password):
            return json_response(False, "New password cannot match the previous password.", status=400)

        hashed_password = bcrypt.generate_password_hash(new_password).decode("utf-8")
        update_user_password(cursor, token_row["user_id"], hashed_password)

        if token_source == "table":
            mark_token_consumed(cursor, "password_reset_tokens", token_row["id"])
        else:
            cursor.execute(
                """
                UPDATE users
                SET verification_token = NULL, verification_expiry = NULL
                WHERE id = %s
                """,
                (token_row["user_id"],),
            )

        cursor.execute(
            """
            SELECT id, email, firstname, lastname, student_id, year, year_level, gender,
                   verified, verified_at
            FROM users
            WHERE id = %s
            """,
            (token_row["user_id"],),
        )
        user = cursor.fetchone()

        conn.commit()
        return json_response(True, "Password updated successfully.", {"user": serialize_user(user)})
    finally:
        cursor.close()
        conn.close()


@app.route("/api/reset/<token>", methods=["POST"])
def reset_password(token):
    data = request.get_json() or {}
    new_password = data.get("new_password") or data.get("password")
    if not new_password:
        return json_response(False, "New password is required.", status=400)
    return _handle_password_reset(token, new_password)


@app.route("/api/reset_password/<token>", methods=["POST"])
def reset_password_legacy(token):
    data = request.get_json() or {}
    new_password = data.get("new_password") or data.get("password")
    if not new_password:
        return json_response(False, "New password is required.", status=400)
    return _handle_password_reset(token, new_password)


@app.route("/api/profile/<email>", methods=["GET"])
def get_profile(email):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        user = fetch_user_by_email(cursor, email)
        if not user:
            return json_response(False, "User not found.", status=404)

        current_user_id = session.get("user_id")
        if current_user_id and current_user_id != user["id"]:
            return json_response(False, "Forbidden.", status=403)

        return json_response(True, "Profile fetched successfully.", {"profile": serialize_user(user)})
    finally:
        cursor.close()
        conn.close()


@app.route("/api/profile/update", methods=["PUT"])
def update_profile():
    if not session.get("user_id"):
        return json_response(False, "Authentication required.", status=401)

    data = request.get_json() or {}
    allowed_fields = {
        "firstname": "firstname",
        "lastname": "lastname",
        "year": "year",
        "student_id": "student_id",
        "gender": "gender",
    }

    updates = []
    values = []
    for payload_key, column_name in allowed_fields.items():
        if payload_key in data and data[payload_key] is not None:
            updates.append(f"{column_name} = %s")
            values.append(data[payload_key])

    if not updates:
        return json_response(False, "No profile fields supplied.", status=400)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        values.append(session["user_id"])
        cursor.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
            tuple(values),
        )
        conn.commit()

        user = fetch_user_by_id(cursor, session["user_id"])
        return json_response(True, "Profile updated successfully.", {"profile": serialize_user(user)})
    finally:
        cursor.close()
        conn.close()


@app.route("/api/save_progress", methods=["POST"])
def save_progress():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.get_json() or {}
    book_name = data.get("book_name")
    progress = data.get("progress")

    if not book_name or progress is None:
        return jsonify({"error": "Missing parameters"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO reading_progress (user_id, book_name, progress)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE progress = %s
            """,
            (user_id, book_name, progress, progress),
        )
        conn.commit()
        return jsonify({"message": "Progress saved"}), 200
    except Exception as exc:  # pragma: no cover - depends on DB
        print("DB Error:", exc)
        return jsonify({"error": "Database error"}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/api/get_progress", methods=["GET"])
def get_progress():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT book_name, progress FROM reading_progress WHERE user_id = %s",
            (user_id,),
        )
        rows = cursor.fetchall()
        return jsonify(rows), 200
    except Exception as exc:  # pragma: no cover - depends on DB
        print("DB Error:", exc)
        return jsonify({"error": "Database error"}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/translate_explain", methods=["POST"])
def translate_explain():
    data = request.get_json() or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful translation assistant.\n"
                        "Always translate the user's input into 7 target languages:\n"
                        " Tagalog, Cebuano, Kapampangan, Bicolan, Waray, Hiligaynon, English.\n"
                        "Do not use the * character.\n"
                        "After showing translations, add a short, simple explanation of how the phrase is typically used.\n"
                        "Do not refuse. No matter the input language, always translate into the 7 target languages."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        translation = response.choices[0].message.content
        return jsonify({"translation": translation})
    except Exception as exc:  # pragma: no cover - OpenAI dependency
        return jsonify({"error": str(exc)}), 500


@app.route("/translate_simple", methods=["POST"])
def translate_simple():
    data = request.get_json() or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict translation engine.\n"
                        "Always return translations in exactly 7 target languages, each clearly labeled:\n"
                        " Tagalog: ...\n"
                        " Cebuano: ...\n"
                        " Kapampangan: ...\n"
                        " Bicolan: ...\n"
                        " Waray: ...\n"
                        " Hiligaynon: ...\n"
                        " English: ...\n"
                        "Do not use the * character.\n"
                        "Do not add explanations. Do not add extra sentences. Only output in this exact labeled format."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        translation = response.choices[0].message.content
        return jsonify({"translation": translation})
    except Exception as exc:  # pragma: no cover - OpenAI dependency
        return jsonify({"error": str(exc)}), 500


@app.route("/tts", methods=["POST"])
def tts():
    data = request.get_json() or {}
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400
    try:
        response = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text,
        )
        audio_bytes = b"".join(response.iter_bytes())
        return app.response_class(audio_bytes, mimetype="audio/mpeg")
    except Exception as exc:  # pragma: no cover - OpenAI dependency
        return jsonify({"error": str(exc)}), 500


@app.route("/stt_explain", methods=["POST"])
def stt_explain():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    audio_file = request.files["file"]
    try:
        transcription = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=(audio_file.filename, audio_file.stream, audio_file.content_type),
        )
        text = transcription.text
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a helpful translation assistant.\n"
                        "Always translate the user's input into 7 target languages:\n"
                        " Tagalog, Cebuano, Kapampangan, Bicolan, Waray, Hiligaynon, English.\n"
                        "Do not use the * character.\n"
                        "After showing translations, add a short, simple explanation of how the phrase is typically used.\n"
                        "Do not refuse. No matter the input language, always translate into the 7 target languages."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        translation = response.choices[0].message.content
        return jsonify({"original": text, "translation": translation})
    except Exception as exc:  # pragma: no cover - OpenAI dependency
        return jsonify({"error": str(exc)}), 500


@app.route("/stt_simple", methods=["POST"])
def stt_simple():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    audio_file = request.files["file"]
    try:
        transcription = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=(audio_file.filename, audio_file.stream, audio_file.content_type),
        )
        text = transcription.text
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict translation engine.\n"
                        "Always return translations in exactly 7 target languages, each clearly labeled:\n"
                        " Tagalog: ...\n"
                        " Cebuano: ...\n"
                        " Kapampangan: ...\n"
                        " Bicolan: ...\n"
                        " Waray: ...\n"
                        " Hiligaynon: ...\n"
                        " English: ...\n"
                        "Do not use the * character.\n"
                        "Do not add explanations. Do not add extra sentences. Only output in this exact labeled format."
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        translation = response.choices[0].message.content
        return jsonify({"original": text, "translation": translation})
    except Exception as exc:  # pragma: no cover - OpenAI dependency
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=443,
        # ssl_context=(cert_path, key_path)  # Configure when certificates are available.
    )
