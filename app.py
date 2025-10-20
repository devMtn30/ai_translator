import os
import uuid
from datetime import datetime, timedelta

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_from_directory, session, url_for
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

ACTIVE_SESSIONS = set()


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def json_response(success, message, data=None, status=200):
    payload = {"success": success, "message": message}
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status


def isoformat_utc(value):
    if isinstance(value, datetime):
        return f"{value.isoformat()}Z"
    return value


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


DEFAULT_QUIZZES = [
    {
        "title": "Cebuano Basics",
        "description": "Learn essential Cebuano vocabulary.",
        "language": "Cebuano",
        "questions": [
            {
                "prompt": "Gwapa",
                "explanation": "The word 'Gwapa' is used to describe someone who is beautiful or attractive.",
                "options": [
                    {"text": "Maganda", "is_correct": True},
                    {"text": "Masama", "is_correct": False},
                    {"text": "Pangit", "is_correct": False},
                    {"text": "Maliit", "is_correct": False},
                ],
            },
            {
                "prompt": "Dili",
                "explanation": "'Dili' means 'no' or 'not' in Cebuano.",
                "options": [
                    {"text": "Oo", "is_correct": False},
                    {"text": "Siguro", "is_correct": False},
                    {"text": "Hindi", "is_correct": True},
                    {"text": "Palagi", "is_correct": False},
                ],
            },
            {
                "prompt": "Maayong Buntag",
                "explanation": "It is the Cebuano greeting for 'Good Morning'.",
                "options": [
                    {"text": "Magandang Araw", "is_correct": False},
                    {"text": "Magandang Umaga", "is_correct": True},
                    {"text": "Magandang Hapon", "is_correct": False},
                    {"text": "Magandang Gabi", "is_correct": False},
                ],
            },
            {
                "prompt": "Lami",
                "explanation": "'Lami' means 'delicious' or 'tasty' in Cebuano.",
                "options": [
                    {"text": "Maasim", "is_correct": False},
                    {"text": "Mapait", "is_correct": False},
                    {"text": "Maanghang", "is_correct": False},
                    {"text": "Masarap", "is_correct": True},
                ],
            },
            {
                "prompt": "Mangaon ta",
                "explanation": "'Mangaon ta' means 'Let's eat!'.",
                "options": [
                    {"text": "Kain tayo", "is_correct": True},
                    {"text": "Alis tayo", "is_correct": False},
                    {"text": "Busog pa ako", "is_correct": False},
                    {"text": "Gutom na ako", "is_correct": False},
                ],
            },
        ],
    },
    {
        "title": "Tagalog Everyday",
        "description": "Daily Tagalog words and phrases.",
        "language": "Tagalog",
        "questions": [
            {
                "prompt": "Maganda",
                "explanation": "Means 'beautiful' or 'pretty' in Tagalog.",
                "options": [
                    {"text": "Beautiful", "is_correct": True},
                    {"text": "Ugly", "is_correct": False},
                    {"text": "Small", "is_correct": False},
                    {"text": "Big", "is_correct": False},
                ],
            },
            {
                "prompt": "Kumusta",
                "explanation": "'Kumusta' asks how someone is doing.",
                "options": [
                    {"text": "Hello", "is_correct": False},
                    {"text": "Goodbye", "is_correct": False},
                    {"text": "How are you", "is_correct": True},
                    {"text": "Thank you", "is_correct": False},
                ],
            },
            {
                "prompt": "Salamat",
                "explanation": "Expression of gratitude in Tagalog.",
                "options": [
                    {"text": "Please", "is_correct": False},
                    {"text": "Sorry", "is_correct": False},
                    {"text": "Thank you", "is_correct": True},
                    {"text": "Excuse me", "is_correct": False},
                ],
            },
            {
                "prompt": "Bahay",
                "explanation": "'Bahay' translates to house or home.",
                "options": [
                    {"text": "House", "is_correct": True},
                    {"text": "Car", "is_correct": False},
                    {"text": "School", "is_correct": False},
                    {"text": "Food", "is_correct": False},
                ],
            },
            {
                "prompt": "Kain tayo",
                "explanation": "An invitation meaning 'Let's eat'.",
                "options": [
                    {"text": "Let's eat", "is_correct": True},
                    {"text": "Let's sleep", "is_correct": False},
                    {"text": "Let's go", "is_correct": False},
                    {"text": "Let's play", "is_correct": False},
                ],
            },
        ],
    },
    {
        "title": "Hiligaynon Hearts",
        "description": "Affectionate terms from Hiligaynon.",
        "language": "Hiligaynon",
        "questions": [
            {
                "prompt": "Palangga",
                "explanation": "Means 'beloved' or 'my love'.",
                "options": [
                    {"text": "Kaibigan", "is_correct": False},
                    {"text": "Minamahal", "is_correct": True},
                    {"text": "Bata", "is_correct": False},
                    {"text": "Damit", "is_correct": False},
                ],
            },
            {
                "prompt": "Amigo",
                "explanation": "Borrowed from Spanish, means male friend.",
                "options": [
                    {"text": "Kaibigan", "is_correct": True},
                    {"text": "Tubig", "is_correct": False},
                    {"text": "Salamat", "is_correct": False},
                    {"text": "Masaya", "is_correct": False},
                ],
            },
            {
                "prompt": "Pagkaon",
                "explanation": "Refers to food, from root word 'kaon'.",
                "options": [
                    {"text": "Balay", "is_correct": False},
                    {"text": "Tulog", "is_correct": False},
                    {"text": "Bayo", "is_correct": False},
                    {"text": "Pagkain", "is_correct": True},
                ],
            },
            {
                "prompt": "Asta sa liwat",
                "explanation": "Means 'See you again'.",
                "options": [
                    {"text": "Hindi", "is_correct": False},
                    {"text": "Maganda Gabi", "is_correct": False},
                    {"text": "Hanggang sa muli", "is_correct": True},
                    {"text": "Oo", "is_correct": False},
                ],
            },
            {
                "prompt": "Balay",
                "explanation": "Means 'house' or 'home'.",
                "options": [
                    {"text": "Bahay", "is_correct": True},
                    {"text": "Maganda", "is_correct": False},
                    {"text": "Salamat", "is_correct": False},
                    {"text": "Kaibigan", "is_correct": False},
                ],
            },
        ],
    },
    {
        "title": "Bicolano Expressions",
        "description": "Common expressions from the Bicol region.",
        "language": "Bicolano",
        "questions": [
            {
                "prompt": "Marhay na aldaw",
                "explanation": "A greeting meaning 'Good day'.",
                "options": [
                    {"text": "Magandang umaga", "is_correct": False},
                    {"text": "Magandang hapon", "is_correct": False},
                    {"text": "Magandang gabi", "is_correct": False},
                    {"text": "Magandang araw", "is_correct": True},
                ],
            },
            {
                "prompt": "Daraga",
                "explanation": "Means lady or unmarried young woman.",
                "options": [
                    {"text": "Babae o dalaga", "is_correct": True},
                    {"text": "Patawad", "is_correct": False},
                    {"text": "Kaibigan", "is_correct": False},
                    {"text": "Salamat", "is_correct": False},
                ],
            },
            {
                "prompt": "Pangadyi",
                "explanation": "Refers to prayer.",
                "options": [
                    {"text": "Pagkain", "is_correct": False},
                    {"text": "Panalangin", "is_correct": True},
                    {"text": "Kaibigan", "is_correct": False},
                    {"text": "Bahay", "is_correct": False},
                ],
            },
            {
                "prompt": "Harayo",
                "explanation": "Means far or distant.",
                "options": [
                    {"text": "Malayo", "is_correct": True},
                    {"text": "Malapit", "is_correct": False},
                    {"text": "Sa loob", "is_correct": False},
                    {"text": "Sa labas", "is_correct": False},
                ],
            },
            {
                "prompt": "Kaigwa",
                "explanation": "Means friend.",
                "options": [
                    {"text": "Kapitbahay", "is_correct": False},
                    {"text": "Estranghero", "is_correct": False},
                    {"text": "Kaibigan", "is_correct": True},
                    {"text": "Kaaway", "is_correct": False},
                ],
            },
        ],
    },
    {
        "title": "Kapampangan Greetings",
        "description": "Warm greetings from the Kapampangan language.",
        "language": "Kapampangan",
        "questions": [
            {
                "prompt": "Mayaus",
                "explanation": "Means 'beautiful' in Kapampangan.",
                "options": [
                    {"text": "Matalino", "is_correct": False},
                    {"text": "Mabait", "is_correct": False},
                    {"text": "Maganda", "is_correct": True},
                    {"text": "Malakas", "is_correct": False},
                ],
            },
            {
                "prompt": "Mayap a bengi",
                "explanation": "Means 'good evening'.",
                "options": [
                    {"text": "Magandang umaga", "is_correct": False},
                    {"text": "Magandang hapon", "is_correct": False},
                    {"text": "Magandang gabi", "is_correct": True},
                    {"text": "Paalam", "is_correct": False},
                ],
            },
            {
                "prompt": "Dakal a salamat",
                "explanation": "Means 'thank you very much'.",
                "options": [
                    {"text": "Magandang umaga", "is_correct": False},
                    {"text": "Maraming salamat", "is_correct": True},
                    {"text": "Paalam", "is_correct": False},
                    {"text": "Pakiusap", "is_correct": False},
                ],
            },
            {
                "prompt": "Balen",
                "explanation": "Means 'house'.",
                "options": [
                    {"text": "Lalaki", "is_correct": False},
                    {"text": "Kaibigan", "is_correct": False},
                    {"text": "Pamilya", "is_correct": False},
                    {"text": "Bahay", "is_correct": True},
                ],
            },
            {
                "prompt": "Mangan tamu",
                "explanation": "Means 'let's eat'.",
                "options": [
                    {"text": "Kain na tayo", "is_correct": True},
                    {"text": "Matulog na tayo", "is_correct": False},
                    {"text": "Tara na", "is_correct": False},
                    {"text": "Tara laro tayo", "is_correct": False},
                ],
            },
        ],
    },
]


def normalize_quiz_questions(questions):
    if not isinstance(questions, list) or not questions:
        raise ValueError("At least one question is required.")

    normalized = []
    for index, question in enumerate(questions, start=1):
        prompt = (question.get("prompt") or "").strip()
        if not prompt:
            raise ValueError(f"Question {index} requires a prompt.")

        raw_options = question.get("options") or []
        filtered_options = []
        for option in raw_options:
            text = (option.get("text") or "").strip()
            if not text:
                continue
            filtered_options.append(
                {
                    "text": text,
                    "is_correct": bool(option.get("is_correct")),
                }
            )

        if len(filtered_options) < 2:
            raise ValueError(f"Question {index} requires at least two options.")

        if not any(option["is_correct"] for option in filtered_options):
            filtered_options[0]["is_correct"] = True

        normalized.append(
            {
                "prompt": prompt,
                "explanation": (question.get("explanation") or "").strip() or None,
                "options": filtered_options,
            }
        )

    return normalized


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
        last_read_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uniq_user_book (user_id, book_name),
        CONSTRAINT fk_reading_progress_user FOREIGN KEY (user_id)
            REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS quiz_history (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        quiz_title VARCHAR(255) NOT NULL,
        score INT DEFAULT 0,
        total_questions INT DEFAULT 0,
        completed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_quiz_history_user FOREIGN KEY (user_id)
            REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS quizzes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        description VARCHAR(500),
        language VARCHAR(50),
        is_active TINYINT(1) DEFAULT 1,
        created_by INT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_quizzes_active (is_active)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS quiz_questions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        quiz_id INT NOT NULL,
        prompt TEXT NOT NULL,
        explanation TEXT,
        order_index INT DEFAULT 0,
        CONSTRAINT fk_quiz_questions_quiz FOREIGN KEY (quiz_id)
            REFERENCES quizzes(id) ON DELETE CASCADE,
        INDEX idx_questions_quiz (quiz_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS quiz_options (
        id INT AUTO_INCREMENT PRIMARY KEY,
        question_id INT NOT NULL,
        text VARCHAR(255) NOT NULL,
        is_correct TINYINT(1) DEFAULT 0,
        CONSTRAINT fk_quiz_options_question FOREIGN KEY (question_id)
            REFERENCES quiz_questions(id) ON DELETE CASCADE,
        INDEX idx_options_question (question_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS quiz_attempts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        quiz_id INT NOT NULL,
        user_id INT NOT NULL,
        score INT DEFAULT 0,
        total_questions INT DEFAULT 0,
        completed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_attempt_quiz FOREIGN KEY (quiz_id)
            REFERENCES quizzes(id) ON DELETE CASCADE,
        CONSTRAINT fk_attempt_user FOREIGN KEY (user_id)
            REFERENCES users(id) ON DELETE CASCADE,
        INDEX idx_attempts_user (user_id),
        INDEX idx_attempts_quiz (quiz_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS quiz_attempt_answers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        attempt_id INT NOT NULL,
        question_id INT NOT NULL,
        option_id INT NULL,
        is_correct TINYINT(1) DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_attempt_answers_attempt FOREIGN KEY (attempt_id)
            REFERENCES quiz_attempts(id) ON DELETE CASCADE,
        CONSTRAINT fk_attempt_answers_question FOREIGN KEY (question_id)
            REFERENCES quiz_questions(id) ON DELETE CASCADE,
        CONSTRAINT fk_attempt_answers_option FOREIGN KEY (option_id)
            REFERENCES quiz_options(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
]


def ensure_reading_progress_schema(cursor):
    """
    Aligns the reading_progress table with the simplified
    "book + last_read_at" contract specified for the reader module.
    """
    try:
        cursor.execute("SHOW COLUMNS FROM reading_progress LIKE 'last_read_at'")
        last_read_column = cursor.fetchone()
    except mysql.connector.Error:
        return

    try:
        if not last_read_column:
            cursor.execute("SHOW COLUMNS FROM reading_progress LIKE 'updated_at'")
            updated_column = cursor.fetchone()
            if updated_column:
                cursor.execute(
                    """
                    ALTER TABLE reading_progress
                    CHANGE COLUMN updated_at last_read_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    """
                )
            else:
                cursor.execute(
                    """
                    ALTER TABLE reading_progress
                    ADD COLUMN last_read_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    """
                )
    except mysql.connector.Error:
        pass

    try:
        cursor.execute("SHOW COLUMNS FROM reading_progress LIKE 'progress'")
        if cursor.fetchone():
            cursor.execute("ALTER TABLE reading_progress DROP COLUMN progress")
    except mysql.connector.Error:
        pass


def seed_default_quizzes(cursor):
    try:
        cursor.execute("SELECT COUNT(*) FROM quizzes")
        existing = cursor.fetchone()
    except mysql.connector.Error:
        return

    count = existing[0] if existing else 0
    if count:
        return

    for quiz in DEFAULT_QUIZZES:
        cursor.execute(
            """
            INSERT INTO quizzes (title, description, language, is_active)
            VALUES (%s, %s, %s, %s)
            """,
            (quiz["title"], quiz.get("description"), quiz.get("language"), 1),
        )
        quiz_id = cursor.lastrowid
        for index, question in enumerate(quiz.get("questions", []), start=1):
            cursor.execute(
                """
                INSERT INTO quiz_questions (quiz_id, prompt, explanation, order_index)
                VALUES (%s, %s, %s, %s)
                """,
                (quiz_id, question["prompt"], question.get("explanation"), index),
            )
            question_id = cursor.lastrowid
            for option in question.get("options", []):
                cursor.execute(
                    """
                    INSERT INTO quiz_options (question_id, text, is_correct)
                    VALUES (%s, %s, %s)
                    """,
                    (question_id, option["text"], 1 if option.get("is_correct") else 0),
                )


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
        ensure_reading_progress_schema(cursor)
        seed_default_quizzes(cursor)
        conn.commit()
    except mysql.connector.Error as exc:
        conn.rollback()
        print(f"[init] Database initialization error: {exc}")
    finally:
        cursor.close()
        conn.close()


initialize_database()


def fetch_reading_history_entries(cursor, user_id):
    cursor.execute(
        """
        SELECT book_name, last_read_at
        FROM reading_progress
        WHERE user_id = %s
        ORDER BY last_read_at DESC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    entries = []
    for row in rows:
        last_read_str = isoformat_utc(row.get("last_read_at"))
        entries.append(
            {
                "type": "reading",
                "book_name": row.get("book_name"),
                "last_read_at": last_read_str,
                "occurred_at": last_read_str,
            }
        )
    return entries


def fetch_quiz_history_entries(cursor, user_id):
    cursor.execute(
        """
        SELECT qa.id, qa.quiz_id, qa.score, qa.total_questions, qa.completed_at,
               q.title AS quiz_title
        FROM quiz_attempts qa
        JOIN quizzes q ON q.id = qa.quiz_id
        WHERE qa.user_id = %s
        ORDER BY qa.completed_at DESC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    entries = []
    for row in rows:
        completed_str = isoformat_utc(row.get("completed_at"))
        entries.append(
            {
                "type": "quiz",
                "quiz_title": row.get("quiz_title"),
                "score": row.get("score"),
                "total_questions": row.get("total_questions"),
                "completed_at": completed_str,
                "occurred_at": completed_str,
                "quiz_id": row.get("quiz_id"),
                "attempt_id": row.get("id"),
            }
        )
    return entries


def fetch_quiz_list(cursor, include_inactive=False):
    query = """
        SELECT q.id, q.title, q.description, q.language, q.is_active,
               (SELECT COUNT(*) FROM quiz_questions qq WHERE qq.quiz_id = q.id) AS question_count
        FROM quizzes q
    """
    params = []
    if not include_inactive:
        query += " WHERE q.is_active = 1"
    query += " ORDER BY q.title ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    quizzes = []
    for row in rows:
        quizzes.append(
            {
                "id": row.get("id"),
                "title": row.get("title"),
                "description": row.get("description"),
                "language": row.get("language"),
                "is_active": bool(row.get("is_active")),
                "question_count": row.get("question_count") or 0,
            }
        )
    return quizzes


def fetch_quiz_detail(cursor, quiz_id, include_correct=False):
    cursor.execute(
        """
        SELECT id, title, description, language, is_active
        FROM quizzes
        WHERE id = %s
        """,
        (quiz_id,),
    )
    quiz = cursor.fetchone()
    if not quiz:
        return None

    cursor.execute(
        """
        SELECT id, prompt, explanation, order_index
        FROM quiz_questions
        WHERE quiz_id = %s
        ORDER BY order_index ASC, id ASC
        """,
        (quiz_id,),
    )
    questions = cursor.fetchall()
    question_ids = [question["id"] for question in questions]
    options_by_question = {question_id: [] for question_id in question_ids}
    correct_option_by_question = {}

    if question_ids:
        placeholders = ", ".join(["%s"] * len(question_ids))
        cursor.execute(
            f"""
            SELECT id, question_id, text, is_correct
            FROM quiz_options
            WHERE question_id IN ({placeholders})
            ORDER BY id ASC
            """,
            question_ids,
        )
        for option in cursor.fetchall():
            question_id = option["question_id"]
            option_payload = {
                "id": option["id"],
                "text": option["text"],
            }
            if include_correct:
                option_payload["is_correct"] = bool(option.get("is_correct"))
            options_by_question.setdefault(question_id, []).append(option_payload)
            if option.get("is_correct"):
                correct_option_by_question[question_id] = option["id"]

    payload_questions = []
    for question in questions:
        entry = {
            "id": question["id"],
            "prompt": question["prompt"],
            "explanation": question.get("explanation"),
            "order_index": question.get("order_index"),
            "options": options_by_question.get(question["id"], []),
        }
        if include_correct:
            entry["correct_option_id"] = correct_option_by_question.get(question["id"])
        payload_questions.append(entry)

    return {
        "id": quiz["id"],
        "title": quiz["title"],
        "description": quiz.get("description"),
        "language": quiz.get("language"),
        "is_active": bool(quiz.get("is_active")),
        "questions": payload_questions,
    }


def grade_quiz_attempt(cursor, quiz_id, responses):
    cursor.execute(
        "SELECT id, title FROM quizzes WHERE id = %s",
        (quiz_id,),
    )
    quiz = cursor.fetchone()
    if not quiz:
        return None, None

    cursor.execute(
        """
        SELECT id, prompt, explanation
        FROM quiz_questions
        WHERE quiz_id = %s
        ORDER BY order_index ASC, id ASC
        """,
        (quiz_id,),
    )
    questions = cursor.fetchall()
    if not questions:
        return quiz, {"score": 0, "total_questions": 0, "breakdown": [], "responses": []}

    question_ids = [question["id"] for question in questions]
    placeholders = ", ".join(["%s"] * len(question_ids))
    cursor.execute(
        f"""
        SELECT id, question_id, text, is_correct
        FROM quiz_options
        WHERE question_id IN ({placeholders})
        """,
        question_ids,
    )
    options = cursor.fetchall()

    options_by_id = {opt["id"]: opt for opt in options}
    correct_option_by_question = {}
    for opt in options:
        if opt.get("is_correct"):
            correct_option_by_question[opt["question_id"]] = opt["id"]

    response_map = {}
    for response in responses:
        qid = response.get("question_id")
        oid = response.get("option_id")
        option = options_by_id.get(oid)
        if qid and option and option.get("question_id") == qid:
            response_map[qid] = oid

    score = 0
    breakdown = []
    for question in questions:
        qid = question["id"]
        correct_option_id = correct_option_by_question.get(qid)
        selected_option_id = response_map.get(qid)
        is_correct = selected_option_id == correct_option_id and correct_option_id is not None
        if is_correct:
            score += 1
        breakdown.append(
            {
                "question_id": qid,
                "prompt": question["prompt"],
                "explanation": question.get("explanation"),
                "selected_option_id": selected_option_id,
                "correct_option_id": correct_option_id,
                "is_correct": is_correct,
            }
        )

    return quiz, {
        "score": score,
        "total_questions": len(questions),
        "breakdown": breakdown,
        "questions": questions,
        "options_by_id": options_by_id,
    }


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


@app.errorhandler(403)
def handle_forbidden(error):
    if request.path.startswith("/api/"):
        message = getattr(error, "description", "Forbidden.")
        return json_response(False, message, status=403)
    login_url = url_for("static", filename="login/login.html")
    return redirect(login_url)


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
        ACTIVE_SESSIONS.add(user["id"])

        return json_response(True, "Login successful.", {"user": serialize_user(user)})
    finally:
        cursor.close()
        conn.close()


@app.route("/api/logout", methods=["POST"])
def logout():
    user_id = session.get("user_id")
    session.clear()
    if user_id and user_id in ACTIVE_SESSIONS:
        ACTIVE_SESSIONS.discard(user_id)
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


def ensure_authenticated():
    if not session.get("user_id"):
        return json_response(False, "Authentication required.", status=401)
    return None


@app.route("/api/admin/users", methods=["GET"])
def admin_users():
    auth_error = ensure_authenticated()
    if auth_error:
        return auth_error

    limit = request.args.get("limit", 100, type=int) or 100
    limit = max(1, min(limit, 500))
    offset = request.args.get("offset", 0, type=int) or 0
    search = (request.args.get("search") or "").strip()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        if search:
            like = f"%{search.lower()}%"
            cursor.execute(
                """
                SELECT id, email, firstname, lastname, student_id, year, year_level, gender,
                       verified, verified_at, created_at
                FROM users
                WHERE LOWER(email) LIKE %s OR LOWER(firstname) LIKE %s OR LOWER(lastname) LIKE %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (like, like, like, limit, offset),
            )
        else:
            cursor.execute(
                """
                SELECT id, email, firstname, lastname, student_id, year, year_level, gender,
                       verified, verified_at, created_at
                FROM users
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            )
        users = cursor.fetchall()
        formatted = []
        for row in users:
            formatted.append(
                {
                    "id": row.get("id"),
                    "email": row.get("email"),
                    "firstname": row.get("firstname"),
                    "lastname": row.get("lastname"),
                    "student_id": row.get("student_id"),
                    "year": row.get("year") or row.get("year_level"),
                    "gender": row.get("gender"),
                    "verified": bool(row.get("verified")) or row.get("verified_at") is not None,
                    "created_at": isoformat_utc(row.get("created_at")),
                }
            )
        return json_response(True, "Admin user list fetched.", {"users": formatted})
    finally:
        cursor.close()
        conn.close()


@app.route("/api/admin/users/<int:user_id>", methods=["PUT"])
def admin_update_user(user_id):
    auth_error = ensure_authenticated()
    if auth_error:
        return auth_error

    data = request.get_json() or {}
    allowed_fields = {
        "firstname": "firstname",
        "lastname": "lastname",
        "year": "year",
        "student_id": "student_id",
        "gender": "gender",
        "verified": "verified",
    }

    updates = []
    values = []
    for key, column in allowed_fields.items():
        if key in data:
            if key == "verified":
                updates.append("verified = %s")
                values.append(1 if data[key] else 0)
            else:
                updates.append(f"{column} = %s")
                values.append(data[key])

    if not updates:
        return json_response(False, "No fields provided for update.", status=400)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        values.append(user_id)
        cursor.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
            tuple(values),
        )
        conn.commit()

        cursor.execute(
            """
            SELECT id, email, firstname, lastname, student_id, year, year_level, gender,
                   verified, verified_at, created_at
            FROM users
            WHERE id = %s
            """,
            (user_id,),
        )
        user = cursor.fetchone()
        if not user:
            return json_response(False, "User not found.", status=404)

        payload = {
            "id": user.get("id"),
            "email": user.get("email"),
            "firstname": user.get("firstname"),
            "lastname": user.get("lastname"),
            "student_id": user.get("student_id"),
            "year": user.get("year") or user.get("year_level"),
            "gender": user.get("gender"),
            "verified": bool(user.get("verified")) or user.get("verified_at") is not None,
            "created_at": isoformat_utc(user.get("created_at")),
        }
        return json_response(True, "User updated.", {"user": payload})
    except mysql.connector.Error as exc:
        conn.rollback()
        return json_response(False, f"Database error: {exc}", status=500)
    finally:
        cursor.close()
        conn.close()


@app.route("/api/admin/online", methods=["GET"])
def admin_online():
    auth_error = ensure_authenticated()
    if auth_error:
        return auth_error
    return json_response(True, "Online count fetched.", {"online": len(ACTIVE_SESSIONS)})


@app.route("/api/admin/quizzes", methods=["GET", "POST"])
def admin_quizzes():
    if request.method == "GET":
        auth_error = ensure_authenticated()
        if auth_error:
            return auth_error

        include_inactive = request.args.get("include_inactive", "1") != "0"
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            quizzes = fetch_quiz_list(cursor, include_inactive=include_inactive)
            return json_response(True, "Admin quiz list fetched.", {"quizzes": quizzes})
        finally:
            cursor.close()
            conn.close()

    return quizzes_collection()


@app.route("/api/admin/quizzes/<int:quiz_id>", methods=["GET", "PUT", "DELETE"])
def admin_quiz_resource(quiz_id):
    return quiz_resource(quiz_id)


@app.route("/api/admin/analytics", methods=["GET"])
def admin_analytics():
    auth_error = ensure_authenticated()
    if auth_error:
        return auth_error

    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_users,
                SUM(CASE WHEN verified = 1 OR verified_at IS NOT NULL THEN 1 ELSE 0 END) AS verified_users,
                SUM(CASE WHEN created_at >= %s THEN 1 ELSE 0 END) AS new_users_7d
            FROM users
            """,
            (last_7d,),
        )
        user_stats = cursor.fetchone() or {}

        cursor.execute("SELECT COUNT(*) AS total_quizzes FROM quizzes")
        quiz_stats = cursor.fetchone() or {}

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_attempts,
                SUM(CASE WHEN completed_at >= %s THEN 1 ELSE 0 END) AS attempts_24h
            FROM quiz_attempts
            """,
            (last_24h,),
        )
        attempt_stats = cursor.fetchone() or {}

        cursor.execute(
            """
            SELECT COUNT(*) AS recent_reads
            FROM reading_progress
            WHERE last_read_at >= %s
            """,
            (last_24h,),
        )
        reading_stats = cursor.fetchone() or {}

        analytics = {
            "total_users": user_stats.get("total_users", 0) or 0,
            "verified_users": user_stats.get("verified_users", 0) or 0,
            "new_users_last_7_days": user_stats.get("new_users_7d", 0) or 0,
            "active_sessions": len(ACTIVE_SESSIONS),
            "total_quizzes": quiz_stats.get("total_quizzes", 0) or 0,
            "total_attempts": attempt_stats.get("total_attempts", 0) or 0,
            "attempts_last_24h": attempt_stats.get("attempts_24h", 0) or 0,
            "reading_updates_last_24h": reading_stats.get("recent_reads", 0) or 0,
            "translations_last_24h": 0,
        }
        return json_response(True, "Analytics fetched.", {"analytics": analytics})
    finally:
        cursor.close()
        conn.close()


@app.route("/api/quizzes", methods=["GET", "POST"])
def quizzes_collection():
    if request.method == "GET":
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            quizzes = fetch_quiz_list(cursor)
            return json_response(True, "Quizzes fetched.", {"quizzes": quizzes})
        finally:
            cursor.close()
            conn.close()

    # POST
    user_id = session.get("user_id")
    if not user_id:
        return json_response(False, "Authentication required.", status=401)

    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    if not title:
        return json_response(False, "Quiz title is required.", status=400)

    try:
        normalized_questions = normalize_quiz_questions(data.get("questions"))
    except ValueError as exc:
        return json_response(False, str(exc), status=400)

    description = (data.get("description") or "").strip() or None
    language = (data.get("language") or "").strip() or None
    is_active = 1 if data.get("is_active", True) else 0

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            INSERT INTO quizzes (title, description, language, is_active, created_by)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (title, description, language, is_active, user_id),
        )
        quiz_id = cursor.lastrowid

        for index, question in enumerate(normalized_questions, start=1):
            cursor.execute(
                """
                INSERT INTO quiz_questions (quiz_id, prompt, explanation, order_index)
                VALUES (%s, %s, %s, %s)
                """,
                (quiz_id, question["prompt"], question.get("explanation"), index),
            )
            question_id = cursor.lastrowid
            for option in question["options"]:
                cursor.execute(
                    """
                    INSERT INTO quiz_options (question_id, text, is_correct)
                    VALUES (%s, %s, %s)
                    """,
                    (question_id, option["text"], 1 if option["is_correct"] else 0),
                )

        conn.commit()
        quiz = fetch_quiz_detail(cursor, quiz_id, include_correct=True)
        return json_response(True, "Quiz created.", {"quiz": quiz}, status=201)
    except mysql.connector.Error as exc:
        conn.rollback()
        return json_response(False, f"Database error: {exc}", status=500)
    finally:
        cursor.close()
        conn.close()


@app.route("/api/quizzes/<int:quiz_id>", methods=["GET", "PUT", "DELETE"])
def quiz_resource(quiz_id):
    if request.method == "GET":
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            quiz = fetch_quiz_detail(cursor, quiz_id, include_correct=True)
            if not quiz:
                return json_response(False, "Quiz not found.", status=404)
            return json_response(True, "Quiz fetched.", {"quiz": quiz})
        finally:
            cursor.close()
            conn.close()

    if not session.get("user_id"):
        return json_response(False, "Authentication required.", status=401)

    data = request.get_json() or {}
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT id FROM quizzes WHERE id = %s", (quiz_id,))
        if not cursor.fetchone():
            return json_response(False, "Quiz not found.", status=404)

        if request.method == "DELETE":
            cursor.execute("DELETE FROM quizzes WHERE id = %s", (quiz_id,))
            conn.commit()
            return json_response(True, "Quiz deleted.")

        # PUT
        title = data.get("title")
        description = data.get("description") if "description" in data else None
        language = data.get("language") if "language" in data else None
        is_active = data.get("is_active") if "is_active" in data else None

        update_fields = []
        values = []
        if title is not None:
            title = title.strip()
            if not title:
                return json_response(False, "Quiz title cannot be empty.", status=400)
            update_fields.append("title = %s")
            values.append(title)
        if description is not None:
            description = description.strip() or None
            update_fields.append("description = %s")
            values.append(description)
        if language is not None:
            language = language.strip() or None
            update_fields.append("language = %s")
            values.append(language)
        if is_active is not None:
            update_fields.append("is_active = %s")
            values.append(1 if is_active else 0)

        if update_fields:
            values.append(quiz_id)
            cursor.execute(
                f"UPDATE quizzes SET {', '.join(update_fields)} WHERE id = %s",
                tuple(values),
            )

        if "questions" in data:
            try:
                normalized_questions = normalize_quiz_questions(data.get("questions"))
            except ValueError as exc:
                conn.rollback()
                return json_response(False, str(exc), status=400)

            cursor.execute("DELETE FROM quiz_questions WHERE quiz_id = %s", (quiz_id,))
            for index, question in enumerate(normalized_questions, start=1):
                cursor.execute(
                    """
                    INSERT INTO quiz_questions (quiz_id, prompt, explanation, order_index)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (quiz_id, question["prompt"], question.get("explanation"), index),
                )
                question_id = cursor.lastrowid
                for option in question["options"]:
                    cursor.execute(
                        """
                        INSERT INTO quiz_options (question_id, text, is_correct)
                        VALUES (%s, %s, %s)
                        """,
                        (question_id, option["text"], 1 if option["is_correct"] else 0),
                    )

        conn.commit()
        updated_quiz = fetch_quiz_detail(cursor, quiz_id, include_correct=True)
        return json_response(True, "Quiz updated.", {"quiz": updated_quiz})
    except mysql.connector.Error as exc:
        conn.rollback()
        return json_response(False, f"Database error: {exc}", status=500)
    finally:
        cursor.close()
        conn.close()


@app.route("/api/quizzes/<int:quiz_id>/attempts", methods=["POST"])
def submit_quiz_attempt(quiz_id):
    user_id = session.get("user_id")
    if not user_id:
        return json_response(False, "Authentication required.", status=401)

    data = request.get_json() or {}
    responses = data.get("responses") or []

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        quiz, grading = grade_quiz_attempt(cursor, quiz_id, responses)
        if quiz is None:
            return json_response(False, "Quiz not found.", status=404)
        if grading["total_questions"] == 0:
            return json_response(False, "Quiz has no questions.", status=400)

        timestamp = datetime.utcnow()
        cursor.execute(
            """
            INSERT INTO quiz_attempts (quiz_id, user_id, score, total_questions, completed_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (quiz_id, user_id, grading["score"], grading["total_questions"], timestamp),
        )
        attempt_id = cursor.lastrowid

        for item in grading["breakdown"]:
            cursor.execute(
                """
                INSERT INTO quiz_attempt_answers (attempt_id, question_id, option_id, is_correct)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    attempt_id,
                    item["question_id"],
                    item["selected_option_id"],
                    1 if item["is_correct"] else 0,
                ),
            )

        cursor.execute(
            """
            INSERT INTO quiz_history (user_id, quiz_title, score, total_questions, completed_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, quiz["title"], grading["score"], grading["total_questions"], timestamp),
        )

        conn.commit()
        payload = {
            "quiz_id": quiz_id,
            "quiz_title": quiz["title"],
            "score": grading["score"],
            "total_questions": grading["total_questions"],
            "completed_at": isoformat_utc(timestamp),
            "breakdown": grading["breakdown"],
        }
        return json_response(True, "Quiz submitted.", payload)
    except mysql.connector.Error as exc:
        conn.rollback()
        return json_response(False, f"Database error: {exc}", status=500)
    finally:
        cursor.close()
        conn.close()


@app.route("/api/history/quizzes", methods=["GET"])
def quiz_history():
    user_id = session.get("user_id")
    if not user_id:
        return json_response(False, "Authentication required.", status=401)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        entries = fetch_quiz_history_entries(cursor, user_id)
        history = []
        for entry in entries:
            history.append(
                {
                    "quiz_title": entry.get("quiz_title"),
                    "score": entry.get("score"),
                    "total_questions": entry.get("total_questions"),
                    "completed_at": entry.get("completed_at"),
                    "quiz_id": entry.get("quiz_id"),
                    "attempt_id": entry.get("attempt_id"),
                }
            )
        return json_response(True, "Quiz history fetched.", {"history": history})
    finally:
        cursor.close()
        conn.close()


@app.route("/api/save_progress", methods=["POST"])
def save_progress():
    user_id = session.get("user_id")
    if not user_id:
        return json_response(False, "Authentication required.", status=401)

    data = request.get_json() or {}
    book_name = data.get("book_name")

    if not book_name:
        return json_response(False, "Book name is required.", status=400)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        timestamp = datetime.utcnow()
        cursor.execute(
            """
            INSERT INTO reading_progress (user_id, book_name, last_read_at)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE last_read_at = VALUES(last_read_at)
            """,
            (user_id, book_name, timestamp),
        )
        conn.commit()
        entry = {"book_name": book_name, "last_read_at": f"{timestamp.isoformat()}Z"}
        return json_response(True, "Reading activity recorded.", {"entry": entry})
    except mysql.connector.Error as exc:  # pragma: no cover - depends on DB
        conn.rollback()
        return json_response(False, f"Database error: {exc}", status=500)
    finally:
        cursor.close()
        conn.close()


@app.route("/api/history/quiz", methods=["POST"])
def log_quiz_history():
    return json_response(False, "Deprecated endpoint. Use POST /api/quizzes/<id>/attempts.", status=410)


@app.route("/api/get_progress", methods=["GET"])
def get_progress():
    return reading_history_response()


@app.route("/api/history/reading", methods=["GET"])
def history_reading():
    return reading_history_response()


def reading_history_response():
    user_id = session.get("user_id")
    if not user_id:
        return json_response(False, "Authentication required.", status=401)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        history_entries = fetch_reading_history_entries(cursor, user_id)
        response_history = [
            {"book_name": entry["book_name"], "last_read_at": entry["last_read_at"]}
            for entry in history_entries
        ]
        return json_response(True, "Reading history fetched.", {"history": response_history})
    except mysql.connector.Error as exc:  # pragma: no cover - depends on DB
        return json_response(False, f"Database error: {exc}", status=500)
    finally:
        cursor.close()
        conn.close()


@app.route("/api/history", methods=["GET"])
def unified_history():
    user_id = session.get("user_id")
    if not user_id:
        return json_response(False, "Authentication required.", status=401)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        entries = fetch_reading_history_entries(cursor, user_id)
        entries.extend(fetch_quiz_history_entries(cursor, user_id))
        entries.sort(key=lambda item: item.get("occurred_at") or "", reverse=True)
        for entry in entries:
            entry.pop("occurred_at", None)
        return json_response(True, "History fetched.", {"history": entries})
    except mysql.connector.Error as exc:  # pragma: no cover - depends on DB
        return json_response(False, f"Database error: {exc}", status=500)
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
