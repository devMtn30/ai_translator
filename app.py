from flask import Flask, request, jsonify, send_from_directory
import mysql.connector
from flask_bcrypt import Bcrypt
from flask_cors import CORS
import os
from dotenv import load_dotenv
from openai import OpenAI
import bcrypt

# =================== 🔹 추가 import (이메일 인증 / 재설정용) ===================
from flask_mail import Mail, Message
import uuid
from datetime import datetime, timedelta
from flask import session
# ============================================================================

# -------------------- 초기 설정 --------------------
load_dotenv()

app = Flask(__name__, static_folder="www", static_url_path="")
CORS(app)
bcrypt = Bcrypt(app)

# ✅ Flask 세션용 secret key
app.secret_key = "super_secret_key_123"

# -------------------- Flask-Mail 설정 (추가됨) --------------------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_USERNAME")
mail = Mail(app)
# ============================================================================

# OpenAI 클라이언트
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# -------------------- MySQL 연결 --------------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="jpjy1023!!",
        database="pronoappsys"
    )

# -------------------- 정적 파일 --------------------
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")
	
# -------------------- 비밀번호 재설정 페이지 라우트 --------------------
@app.route("/reset/<token>", methods=["GET"])
def serve_reset_page(token):
    """
    이메일의 https://pronocoach.duckdns.org/reset/<token> 링크를 클릭하면
    newpassword.html 페이지를 보여줌
    """
    return send_from_directory(os.path.join(app.static_folder, "forgot"), "newpassword.html")

# -------------------------------
# 🔹 비밀번호 재설정 API
# -------------------------------

@app.route("/api/reset_password/<token>", methods=["POST"])
def reset_password(token):
    data = request.get_json() or {}
    new_password = data.get("new_password") or data.get("password")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 🔹 1) 토큰으로 사용자 찾기
    cursor.execute("SELECT email FROM password_reset_tokens WHERE token = %s", (token,))
    token_row = cursor.fetchone()
    if not token_row:
        return jsonify({"success": False, "message": "Invalid or expired token"}), 400

    email = token_row["email"]

    # 🔹 2) 현재 비밀번호 조회
    cursor.execute("SELECT password FROM users WHERE email = %s", (email,))
    user_row = cursor.fetchone()
    if not user_row:
        return jsonify({"success": False, "message": "User not found"}), 404

    current_hashed = user_row["password"]

    # ✅ 여기! 함수 안쪽(4칸 들여쓰기 유지)
    print("DEBUG current_hashed =", current_hashed)

    # 🔹 3) 새 비밀번호와 기존 비밀번호 비교 (확실한 비교 방식)
    test_rehash = bcrypt.hashpw(new_password.encode("utf-8"), current_hashed.encode("utf-8"))
    if test_rehash == current_hashed.encode("utf-8"):
        print("🚫 same password detected, blocking update")
        return jsonify({
            "success": False,
            "message": "New password cannot be the same as the old password"
        }), 400









    # 🔹 4) 비밀번호 해싱 후 저장
    hashed_pw = bcrypt.generate_password_hash(new_password).decode("utf-8")
    cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_pw, email))
    conn.commit()

    # 🔹 5) 사용한 토큰 삭제 (보안상 필수)
    cursor.execute("DELETE FROM password_reset_tokens WHERE token = %s", (token,))
    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({"success": True, "message": "Password successfully updated"})




# -------------------- 회원가입 --------------------
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    hashed_pw = bcrypt.generate_password_hash(data['password']).decode('utf-8')

    # ✅ 이메일 인증용 토큰 추가
    token = str(uuid.uuid4())
    expiry = datetime.utcnow() + timedelta(hours=1)

    conn = get_db_connection()
    cursor = conn.cursor()
    # ✅ verified, token, expiry 컬럼 추가 저장
    query = """INSERT INTO users (firstname, lastname, year, student_id, gender, email, password, verified, verification_token, verification_expiry)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    values = (
        data['firstname'], data['lastname'], data['year'],
        data['student_id'], data['gender'], data['email'], hashed_pw,
        False, token, expiry
    )

    try:
        cursor.execute(query, values)
        conn.commit()

        # ✅ 이메일 전송
        verify_url = f"https://pronocoach.duckdns.org/api/verify/{token}"
        msg = Message("Verify your PronoCoach account", recipients=[data['email']])
        msg.body = f"""
Hello {data['firstname']},

Welcome to PronoCoach!
Please verify your account by clicking the link below:
{verify_url}

This link will expire in 1 hour.
        """
        mail.send(msg)

        return jsonify({"message": "Verification email sent! Please check your inbox."}), 201
    except Exception as e:
        if "Duplicate entry" in str(e):
            if "users.student_id" in str(e):
                return jsonify({"error": "This Student ID is already registered."}), 400
            if "users.email" in str(e):
                return jsonify({"error": "This Email is already registered."}), 400
        return jsonify({"error": str(e)}), 400
    finally:
        cursor.close()
        conn.close()

# -------------------- 이메일 인증 --------------------
@app.route("/api/verify/<token>", methods=["GET"])
def verify_email(token):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, verification_expiry FROM users WHERE verification_token=%s", (token,))
    user = cursor.fetchone()

    if not user:
        return jsonify({"error": "Invalid verification token"}), 400
    if datetime.utcnow() > user["verification_expiry"]:
        return jsonify({"error": "Verification link expired"}), 400

    cursor.execute(
        "UPDATE users SET verified=%s, verification_token=NULL, verification_expiry=NULL WHERE id=%s",
        (True, user["id"])
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "✅ Email verified successfully! You may now log in."})

# -------------------- 비밀번호 재설정 --------------------
@app.route("/api/forgot", methods=["POST"])
def forgot_password():
    data = request.json
    email = data.get("email")

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()

    if not user:
        return jsonify({"error": "No account found with that email."}), 404

    token = str(uuid.uuid4())
    expiry = datetime.utcnow() + timedelta(hours=1)
    cursor.execute("""
        UPDATE users SET verification_token=%s, verification_expiry=%s WHERE email=%s
    """, (token, expiry, email))
    conn.commit()

    reset_url = f"https://pronocoach.duckdns.org/reset/{token}"
    msg = Message("Reset your PronoCoach password", recipients=[email])
    msg.body = f"""
Hello {user['firstname']},

We received a request to reset your password.
Click the link below to set a new password:
{reset_url}

If you didn’t request this, please ignore this email.
This link will expire in 1 hour.
    """
    mail.send(msg)
    cursor.close()
    conn.close()
    return jsonify({"message": "Password reset link sent to your email."}), 200

@app.route("/api/reset/<token>", methods=["POST"])
def reset_password_old(token):  # ← 기존 reset_password → reset_password_old 로 이름만 변경
    data = request.json
    new_pw = data.get("password")

    if not new_pw:
        return jsonify({"error": "Password required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE verification_token=%s", (token,))
    user = cursor.fetchone()

    if not user:
        return jsonify({"error": "Invalid or expired reset token"}), 400
    if datetime.utcnow() > user["verification_expiry"]:
        return jsonify({"error": "Reset link expired"}), 400

    hashed = bcrypt.generate_password_hash(new_pw).decode("utf-8")
    cursor.execute("""
        UPDATE users SET password=%s, verification_token=NULL, verification_expiry=NULL WHERE id=%s
    """, (hashed, user["id"]))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"message": "Password updated successfully."}), 200

# ============================================================================

# 🔹 이하 기존 코드 (번역, TTS, STT, 진행률 등)는 절대 수정하지 않고 그대로 둡니다.
# ============================================================================



# -------------------- 로그인 --------------------
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    student_id = data['student_id']
    password = data['password']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE student_id = %s", (student_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user and bcrypt.check_password_hash(user['password'], password):
        return jsonify({
            "message": "Login successful!",
            "user": user['firstname'],
            "student_id": user['student_id']
        }), 200
    return jsonify({"error": "Invalid Student ID or password"}), 401

# -------------------- 프로필 --------------------
@app.route('/api/profile/<student_id>', methods=['GET'])
def profile(student_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT firstname, lastname, year, student_id, gender, email FROM users WHERE student_id = %s", (student_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if user:
        return jsonify(user), 200
    else:
        return jsonify({"error": "User not found"}), 404

# ============================================================
# 설명형 번역기 API
# ============================================================
@app.route("/translate_explain", methods=["POST"])
def translate_explain():
    data = request.json
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content":
                 "You are a helpful translation assistant.\n"
                 "Always translate the user's input into 6 target languages:\n"
                 " Tagalog, Cebuano, Kapampangan, bicolano, Waray, and Hiligaynon.\n"
				 "Do not use * latter \n"
                 "After showing translations, add a short, simple explanation of how the phrase is typically used.\n"
                 "Do not refuse. No matter the input language, always translate into the 7 target languages."},
                {"role": "user", "content": text}
            ]
        )
        translation = response.choices[0].message.content
        return jsonify({"translation": translation})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 순수형 번역기 API
# ============================================================
@app.route("/translate_simple", methods=["POST"])
def translate_simple():
    data = request.json
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content":
                 "You are a strict translation engine.\n"
                 "Always return translations in exactly 6 target languages, each clearly labeled:\n"
                 " Tagalog: ...\n"
                 " Cebuano: ...\n"
                 " Kapampangan: ...\n"
                 " bicolano: ...\n"
                 " Waray: ...\n"
                 " Hiligaynon: ...\n"
                 "Do not add explanations. Do not add extra sentences. Only output in this exact labeled format."
				 "Do not use * latter \n"
                },
                {"role": "user", "content": text}
            ]
        )
        translation = response.choices[0].message.content
        return jsonify({"translation": translation})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 공용 TTS
# ============================================================
@app.route("/tts", methods=["POST"])
def tts():
    data = request.json
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400
    try:
        response = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text
        )
        audio_bytes = b"".join(response.iter_bytes())
        return app.response_class(audio_bytes, mimetype="audio/mpeg")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# STT → 설명형
# ============================================================
@app.route("/stt_explain", methods=["POST"])
def stt_explain():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    audio_file = request.files["file"]
    try:
        transcription = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=(audio_file.filename, audio_file.stream, audio_file.content_type)
        )
        text = transcription.text
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content":
                 "You are a helpful translation assistant.\n"
                 "Always translate the user's input into 6 target languages:\n"
                 " Tagalog, Cebuano, Kapampangan, bicolano, Waray, and Hiligaynon.\n"
                 "After showing translations, add a short, simple explanation of how the phrase is typically used.\n"
				 "Do not use * latter \n"
                 "Do not refuse. No matter the input language, always translate into the 7 target languages."},
                {"role": "user", "content": text}
            ]
        )
        translation = response.choices[0].message.content
        return jsonify({"original": text, "translation": translation})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# STT → 순수형
# ============================================================
@app.route("/stt_simple", methods=["POST"])
def stt_simple():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    audio_file = request.files["file"]
    try:
        # 1) 음성 → 텍스트
        transcription = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=(audio_file.filename, audio_file.stream, audio_file.content_type)
        )
        text = transcription.text

        # 2) 텍스트 → 번역
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a strict translation engine.\n"
                        "Always return translations in exactly 6 target languages, each clearly labeled:\n"
                        " Tagalog: ...\n"
                        " Cebuano: ...\n"
                        " Kapampangan: ...\n"
                        " bicolan: ...\n"
                        " Waray: ...\n"
                        " Hiligaynon: ...\n"
						"Do not use * latter \n"
                        "Do not add explanations. Do not add extra sentences. Only output in this exact labeled format."
                    )
                },
                {"role": "user", "content": text}
            ]
        )
        translation = response.choices[0].message.content

        return jsonify({"original": text, "translation": translation})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============================================================
# 📚 독서 진행률 API (세션 기반 / Flask 로그인 통합)
# ============================================================

from flask import session

@app.route("/api/save_progress", methods=["POST"])
def save_progress():
    """로그인한 계정의 진행률 저장"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    data = request.json
    book_name = data.get("book_name")
    progress = data.get("progress")

    if not book_name or progress is None:
        return jsonify({"error": "Missing parameters"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO reading_progress (user_id, book_name, progress)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE progress = %s
        """, (user_id, book_name, progress, progress))
        conn.commit()
        return jsonify({"message": "Progress saved"}), 200
    except Exception as e:
        print("DB Error:", e)
        return jsonify({"error": "Database error"}), 500
    finally:
        cursor.close()
        conn.close()


@app.route("/api/get_progress", methods=["GET"])
def get_progress():
    """로그인된 계정의 책 진행률 가져오기"""
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"error": "Not logged in"}), 401

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT book_name, progress FROM reading_progress WHERE user_id = %s", (user_id,))
        rows = cursor.fetchall()
        return jsonify(rows), 200
    except Exception as e:
        print("DB Error:", e)
        return jsonify({"error": "Database error"}), 500
    finally:
        cursor.close()
        conn.close()

@app.route("/api/profile/<email>", methods=["GET"])
def get_profile(email):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT firstname, lastname, year, student_id, gender, email
        FROM users WHERE email = %s
    """, (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        return jsonify({"success": False, "message": "User not found"}), 404

    return jsonify({"success": True, "profile": user})


@app.route("/api/profile/update", methods=["PUT"])
def update_profile():
    data = request.get_json()
    email = data.get("email")
    firstname = data.get("firstname")
    lastname = data.get("lastname")
    year = data.get("year")
    student_id = data.get("student_id")
    gender = data.get("gender")

    if not email:
        return jsonify({"success": False, "message": "Email required"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        UPDATE users
        SET firstname = %s, lastname = %s, year = %s, student_id = %s, gender = %s
        WHERE email = %s
    """
    cursor.execute(query, (firstname, lastname, year, student_id, gender, email))
    conn.commit()

    cursor.close()
    conn.close()

    return jsonify({"success": True, "message": "Profile updated successfully"})



# -------------------- 실행 --------------------
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=443,
        # ssl_context=(
        #     "C:/Users/Administrator/my-app/pronocoach.duckdns.org-crt.pem",
        #     "C:/Users/Administrator/my-app/pronocoach.duckdns.org-key.pem"
        # )
    )

