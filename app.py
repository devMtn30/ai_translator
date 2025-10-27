import os
import random
import re
import uuid
from datetime import datetime, timedelta
from urllib.parse import unquote

import mysql.connector
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_from_directory, session, url_for
from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_mail import Mail, Message
from openai import OpenAI

load_dotenv()

app = Flask(__name__, static_folder="www", static_url_path="")
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
PUBLIC_HTML_ROOTS = {"login", "register", "forgot"}
PUBLIC_HTML_PATHS = {"/index.html"}

PROFILE_UPLOAD_SUBDIR = os.getenv("PROFILE_UPLOAD_SUBDIR", "uploads/profile")
PROFILE_UPLOAD_FOLDER = os.path.abspath(os.path.join(app.root_path, PROFILE_UPLOAD_SUBDIR))
ALLOWED_PROFILE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
MAX_PROFILE_IMAGE_BYTES = int(os.getenv("PROFILE_UPLOAD_MAX_BYTES", 5 * 1024 * 1024))
REGISTRATION_CODE_EXPIRY_MINUTES = int(os.getenv("REGISTRATION_CODE_EXPIRY_MINUTES", 15))
PASSWORD_POLICY = re.compile(r"^(?=.*[A-Za-z])(?=.*[!@#$%^&*(),.?':{}|<>]).{8,}$")

os.makedirs(PROFILE_UPLOAD_FOLDER, exist_ok=True)


class ForbiddenRedirectMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        is_api_request = path.startswith("/api/")
        redirected = {"value": False}

        def redirecting_start_response(status, headers, exc_info=None):
            if status.startswith("403") and not is_api_request:
                redirected["value"] = True
                filtered_headers = [(k, v) for (k, v) in headers if k.lower() != "location"]
                filtered_headers.append(("Location", "/login/login.html"))
                return start_response("302 FOUND", filtered_headers, exc_info)
            return start_response(status, headers, exc_info)

        response_iterable = self.app(environ, redirecting_start_response)

        if redirected["value"]:
            close = getattr(response_iterable, "close", None)
            if callable(close):
                close()
            return []

        return response_iterable


app.wsgi_app = ForbiddenRedirectMiddleware(app.wsgi_app)


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
               password_hash, password, verified, verified_at, created_at, profile_image_path
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
               password_hash, password, verified, verified_at, created_at, profile_image_path
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
        "title": "Cebuano Conversations",
        "description": "Practice Cebuano daily conversation lines.",
        "language": "Cebuano",
        "questions": [
            {
                "prompt": "“Unsa imong ngalan?”",
                "explanation": "This is how you ask someone for their name in Cebuano.",
                "options": [
                    {"text": "What is your name?", "is_correct": True},
                    {"text": "How old are you?", "is_correct": False},
                    {"text": "Where do you live?", "is_correct": False},
                    {"text": "What do you do?", "is_correct": False},
                ],
            },
            {
                "prompt": "“Taga-asa ka?”",
                "explanation": "Common question used when meeting new friends.",
                "options": [
                    {"text": "Where are you from?", "is_correct": True},
                    {"text": "Are you hungry?", "is_correct": False},
                    {"text": "Do you understand?", "is_correct": False},
                    {"text": "What time is it?", "is_correct": False},
                ],
            },
            {
                "prompt": "Meaning of “Salamat kaayo”",
                "explanation": "The word “kaayo” intensifies the gratitude.",
                "options": [
                    {"text": "Thank you very much", "is_correct": True},
                    {"text": "Good morning", "is_correct": False},
                    {"text": "Please wait", "is_correct": False},
                    {"text": "See you soon", "is_correct": False},
                ],
            },
            {
                "prompt": "“Pila imong edad?”",
                "explanation": "Asked when you want to know somebody's age politely.",
                "options": [
                    {"text": "How old are you?", "is_correct": True},
                    {"text": "Where do you study?", "is_correct": False},
                    {"text": "What is your name?", "is_correct": False},
                    {"text": "Do you like Cebu?", "is_correct": False},
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
        "title": "Tagalog Story Challenge",
        "description": "Comprehension check for narrated Tagalog stories.",
        "language": "Tagalog",
        "questions": [
            {
                "prompt": "What does “kabayanihan” describe?",
                "explanation": "Used often when retelling Philippine hero stories.",
                "options": [
                    {"text": "Heroism or brave acts", "is_correct": True},
                    {"text": "Childhood memories", "is_correct": False},
                    {"text": "Daily routine", "is_correct": False},
                    {"text": "Weather", "is_correct": False},
                ],
            },
            {
                "prompt": "“Pinagpawisan siya matapos ang paglalakbay.” means?",
                "options": [
                    {"text": "He was drenched in sweat after the journey.", "is_correct": True},
                    {"text": "He fell asleep on the trip.", "is_correct": False},
                    {"text": "He started a fight while traveling.", "is_correct": False},
                    {"text": "He lost his bag along the way.", "is_correct": False},
                ],
            },
            {
                "prompt": "“Bumuhos ang malakas na ulan” best translates to?",
                "options": [
                    {"text": "Heavy rain poured down.", "is_correct": True},
                    {"text": "The sun rose slowly.", "is_correct": False},
                    {"text": "Winds became calm.", "is_correct": False},
                    {"text": "The waves disappeared.", "is_correct": False},
                ],
            },
            {
                "prompt": "Meaning of “pangarap na katuparan”",
                "options": [
                    {"text": "Dream come true", "is_correct": True},
                    {"text": "Unfinished dream", "is_correct": False},
                    {"text": "Nightmare", "is_correct": False},
                    {"text": "Lesson learned", "is_correct": False},
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
    {
        "title": "Hiligaynon Journeys",
        "description": "Travel-related expressions for Hiligaynon learners.",
        "language": "Hiligaynon",
        "questions": [
            {
                "prompt": "“Diin ka makadto?” asks about?",
                "options": [
                    {"text": "Where are you going?", "is_correct": True},
                    {"text": "What is your name?", "is_correct": False},
                    {"text": "Who is with you?", "is_correct": False},
                    {"text": "When will you leave?", "is_correct": False},
                ],
            },
            {
                "prompt": "“Palihog” in Hiligaynon",
                "options": [
                    {"text": "Please", "is_correct": True},
                    {"text": "Thank you", "is_correct": False},
                    {"text": "Maybe", "is_correct": False},
                    {"text": "Goodbye", "is_correct": False},
                ],
            },
            {
                "prompt": "Meaning of “Gani?”",
                "options": [
                    {"text": "Really?", "is_correct": True},
                    {"text": "Later", "is_correct": False},
                    {"text": "Let’s go", "is_correct": False},
                    {"text": "No thanks", "is_correct": False},
                ],
            },
            {
                "prompt": "“Lakat na kita” best matches?",
                "options": [
                    {"text": "Let’s start walking.", "is_correct": True},
                    {"text": "Sit down now.", "is_correct": False},
                    {"text": "Stay quiet.", "is_correct": False},
                    {"text": "Cover your head.", "is_correct": False},
                ],
            },
        ],
    },
    {
        "title": "Bikol Grammar Warmup",
        "description": "Short drills for core Bikol words.",
        "language": "Bikol",
        "questions": [
            {
                "prompt": "“Dios mabalos” conveys?",
                "options": [
                    {"text": "Thank you", "is_correct": True},
                    {"text": "Goodbye", "is_correct": False},
                    {"text": "Good evening", "is_correct": False},
                    {"text": "See you tomorrow", "is_correct": False},
                ],
            },
            {
                "prompt": "Meaning of “dakula”",
                "options": [
                    {"text": "Big", "is_correct": True},
                    {"text": "Small", "is_correct": False},
                    {"text": "Short", "is_correct": False},
                    {"text": "Open", "is_correct": False},
                ],
            },
            {
                "prompt": "“Masiram” refers to",
                "options": [
                    {"text": "Delicious", "is_correct": True},
                    {"text": "Bitter", "is_correct": False},
                    {"text": "Spicy", "is_correct": False},
                    {"text": "Cold", "is_correct": False},
                ],
            },
            {
                "prompt": "“Harong” best translates to",
                "options": [
                    {"text": "House", "is_correct": True},
                    {"text": "School", "is_correct": False},
                    {"text": "Child", "is_correct": False},
                    {"text": "Book", "is_correct": False},
                ],
            },
        ],
    },
    {
        "title": "Bikol Expressions Drill",
        "description": "Conversational follow-ups for Bikol learners.",
        "language": "Bikol",
        "questions": [
            {
                "prompt": "“Kamusta ka man?” means",
                "options": [
                    {"text": "How are you?", "is_correct": True},
                    {"text": "Where are you going?", "is_correct": False},
                    {"text": "Did you eat?", "is_correct": False},
                    {"text": "Are you sleepy?", "is_correct": False},
                ],
            },
            {
                "prompt": "Translation of “Magayon”",
                "options": [
                    {"text": "Beautiful", "is_correct": True},
                    {"text": "Angry", "is_correct": False},
                    {"text": "Hungry", "is_correct": False},
                    {"text": "Thirsty", "is_correct": False},
                ],
            },
            {
                "prompt": "“Tara na” conveys",
                "options": [
                    {"text": "Let’s go", "is_correct": True},
                    {"text": "Stay quiet", "is_correct": False},
                    {"text": "Bring that", "is_correct": False},
                    {"text": "Cook first", "is_correct": False},
                ],
            },
            {
                "prompt": "Meaning of “Nagadan”",
                "options": [
                    {"text": "Passing through", "is_correct": True},
                    {"text": "Falling down", "is_correct": False},
                    {"text": "Standing up", "is_correct": False},
                    {"text": "Jumping high", "is_correct": False},
                ],
            },
        ],
    },
    {
        "title": "Waray Greetings",
        "description": "Starter Waray phrases for polite greetings.",
        "language": "Waray",
        "questions": [
            {
                "prompt": "“Maupay nga aga” translates to",
                "options": [
                    {"text": "Good morning", "is_correct": True},
                    {"text": "Good afternoon", "is_correct": False},
                    {"text": "Goodbye", "is_correct": False},
                    {"text": "Welcome", "is_correct": False},
                ],
            },
            {
                "prompt": "Meaning of “Salamat han imo bulig”",
                "options": [
                    {"text": "Thank you for your help", "is_correct": True},
                    {"text": "Can you help me?", "is_correct": False},
                    {"text": "I don't need help", "is_correct": False},
                    {"text": "Where do you live?", "is_correct": False},
                ],
            },
            {
                "prompt": "“Kumusta ka?” equals",
                "options": [
                    {"text": "How are you?", "is_correct": True},
                    {"text": "Where are you going?", "is_correct": False},
                    {"text": "Are you hungry?", "is_correct": False},
                    {"text": "Can you dance?", "is_correct": False},
                ],
            },
            {
                "prompt": "“Pasayloa ako” best means",
                "options": [
                    {"text": "Forgive me", "is_correct": True},
                    {"text": "Come here", "is_correct": False},
                    {"text": "Listen please", "is_correct": False},
                    {"text": "Leave now", "is_correct": False},
                ],
            },
        ],
    },
    {
        "title": "Waray Dialogues",
        "description": "Follow-on practice for Waray conversations.",
        "language": "Waray",
        "questions": [
            {
                "prompt": "Meaning of “Karuyag mo ba?”",
                "options": [
                    {"text": "Do you like it?", "is_correct": True},
                    {"text": "Are you afraid?", "is_correct": False},
                    {"text": "Do you need help?", "is_correct": False},
                    {"text": "Can you sing?", "is_correct": False},
                ],
            },
            {
                "prompt": "“Kadamo han tawo” describes",
                "options": [
                    {"text": "There are many people.", "is_correct": True},
                    {"text": "The people are gone.", "is_correct": False},
                    {"text": "Only one person is there.", "is_correct": False},
                    {"text": "People are sleeping.", "is_correct": False},
                ],
            },
            {
                "prompt": "“Ayaw kabaraka” best matches",
                "options": [
                    {"text": "Don't worry.", "is_correct": True},
                    {"text": "Don't move.", "is_correct": False},
                    {"text": "Don't forget.", "is_correct": False},
                    {"text": "Don't whisper.", "is_correct": False},
                ],
            },
            {
                "prompt": "“Kadi dinhi” is used to",
                "options": [
                    {"text": "Ask someone to come here.", "is_correct": True},
                    {"text": "Tell someone to leave.", "is_correct": False},
                    {"text": "Say thank you.", "is_correct": False},
                    {"text": "Apologize.", "is_correct": False},
                ],
            },
        ],
    },
]

DEFAULT_MODULES = [
    {
        "id": "cebuano_pathway",
        "title": "Visayan Explorer",
        "dialect": "Cebuano",
        "accent_color": "#4C7EFF",
        "summary": "Work through Cebuano handouts then lock in the lesson with targeted quizzes.",
        "icon": "/assets/icons/Cebuano.png",
        "courses": [
            {
                "id": "ceb101",
                "title": "Cebuano Foundations",
                "handout_label": "Handout 01",
                "page_range": "pp. 1-20",
                "book_name": "cebuano.pdf",
                "book_display_name": "Cebuano For Beginners",
                "estimated_minutes": 15,
                "quiz_title": "Cebuano Basics",
                "quiz_description": "Vocabulary check covering greetings, feelings, and food.",
            },
            {
                "id": "ceb201",
                "title": "Cebuano Dialogues",
                "handout_label": "Handout 02",
                "page_range": "pp. 21-40",
                "book_name": "cebuano.pdf",
                "book_display_name": "Cebuano Story Samples",
                "estimated_minutes": 18,
                "quiz_title": "Cebuano Conversations",
                "quiz_description": "Scenario-based quiz that practices introductions and polite chat.",
            },
        ],
    },
    {
        "id": "bikol_storytrack",
        "title": "Bikol Scholar Track",
        "dialect": "Bikol",
        "accent_color": "#FF8A65",
        "summary": "Break Bikol grammar into bite-sized study cards paired with comprehension quizzes.",
        "icon": "/assets/icons/Bikol.png",
        "courses": [
            {
                "id": "bik101",
                "title": "Grammar Notes Starter",
                "handout_label": "Handout A",
                "page_range": "Chapters 1-2",
                "book_name": "bikol.pdf",
                "book_display_name": "Bikol Grammar Notes",
                "estimated_minutes": 12,
                "quiz_title": "Bikol Grammar Warmup",
                "quiz_description": "Rapid-fire translation checks from the grammar section.",
            },
            {
                "id": "bik201",
                "title": "Story Circle",
                "handout_label": "Handout B",
                "page_range": "Chapters 3-4",
                "book_name": "bikol.pdf",
                "book_display_name": "Bikol Story Circle",
                "estimated_minutes": 16,
                "quiz_title": "Bikol Expressions Drill",
                "quiz_description": "Conversation role-play focusing on idioms and expression recall.",
            },
        ],
    },
    {
        "id": "tagalog_reader",
        "title": "Tagalog Story Lab",
        "dialect": "Tagalog",
        "accent_color": "#FFB347",
        "summary": "Follow the Sabayan stories and pause for comprehension quizzes.",
        "icon": "/assets/icons/Sabayan.png",
        "courses": [
            {
                "id": "tag101",
                "title": "Sabayan Reader — Part 1",
                "handout_label": "Reader 1",
                "page_range": "Chapters 1-3",
                "book_name": "sabayan.pdf",
                "book_display_name": "Sa Bayan ng Anihan",
                "estimated_minutes": 20,
                "quiz_title": "Tagalog Everyday",
                "quiz_description": "Checks day-to-day usage from the first half of the story.",
            },
            {
                "id": "tag201",
                "title": "Sabayan Reader — Part 2",
                "handout_label": "Reader 2",
                "page_range": "Chapters 4-6",
                "book_name": "sabayan.pdf",
                "book_display_name": "Sa Bayan ng Anihan (cont.)",
                "estimated_minutes": 20,
                "quiz_title": "Tagalog Story Challenge",
                "quiz_description": "Scenario-based comprehension for the story finale.",
            },
        ],
    },
    {
        "id": "hiligaynon_path",
        "title": "Hiligaynon Journey",
        "dialect": "Hiligaynon",
        "accent_color": "#7ED957",
        "summary": "Blend affectionate phrases with real-life travel prompts.",
        "icon": "/assets/icons/Cebuano.png",
        "courses": [
            {
                "id": "hil101",
                "title": "Hearts & Home",
                "handout_label": "Handout Alpha",
                "page_range": "Lessons 1-2",
                "book_name": "hiligaynon.pdf",
                "book_display_name": "Hiligaynon Hearts Sampler",
                "estimated_minutes": 14,
                "quiz_title": "Hiligaynon Hearts",
                "quiz_description": "Covers endearing terms and family references.",
            },
            {
                "id": "hil201",
                "title": "Journeys & Directions",
                "handout_label": "Handout Beta",
                "page_range": "Lessons 3-4",
                "book_name": "hiligaynon.pdf",
                "book_display_name": "Hiligaynon Journeys Notes",
                "estimated_minutes": 17,
                "quiz_title": "Hiligaynon Journeys",
                "quiz_description": "Focuses on asking for help and navigating new places.",
            },
        ],
    },
    {
        "id": "waray_path",
        "title": "Waray Waves",
        "dialect": "Waray",
        "accent_color": "#57D3FF",
        "summary": "Stack warm-up readings with Waray practice quizzes.",
        "icon": "/assets/icons/Bikol.png",
        "courses": [
            {
                "id": "war101",
                "title": "Greetings Playbook",
                "handout_label": "Sheet 1",
                "page_range": "Sections 1-2",
                "book_name": "waray.pdf",
                "book_display_name": "Waray Primer — Greetings",
                "estimated_minutes": 10,
                "quiz_title": "Waray Greetings",
                "quiz_description": "Validates polite greetings and gratitude patterns.",
            },
            {
                "id": "war201",
                "title": "Dialog Practice",
                "handout_label": "Sheet 2",
                "page_range": "Sections 3-4",
                "book_name": "waray.pdf",
                "book_display_name": "Waray Primer — Dialogues",
                "estimated_minutes": 13,
                "quiz_title": "Waray Dialogues",
                "quiz_description": "Moves into situational prompts and daily chat.",
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
        profile_image_path VARCHAR(255),
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
    CREATE TABLE IF NOT EXISTS pending_registrations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        email VARCHAR(255) NOT NULL UNIQUE,
        student_id VARCHAR(64) NOT NULL UNIQUE,
        firstname VARCHAR(100) NOT NULL,
        lastname VARCHAR(100) NOT NULL,
        year VARCHAR(50) NOT NULL,
        gender VARCHAR(20) NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        verification_code VARCHAR(10) NOT NULL,
        expires_at DATETIME NOT NULL,
        attempts INT DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_pending_expires (expires_at)
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
    """
    CREATE TABLE IF NOT EXISTS module_definitions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        slug VARCHAR(64) NOT NULL UNIQUE,
        title VARCHAR(255) NOT NULL,
        dialect VARCHAR(100),
        accent_color VARCHAR(16),
        summary VARCHAR(500),
        icon VARCHAR(255),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS module_courses (
        id INT AUTO_INCREMENT PRIMARY KEY,
        module_id INT NOT NULL,
        slug VARCHAR(64) NOT NULL,
        title VARCHAR(255) NOT NULL,
        handout_label VARCHAR(120),
        page_range VARCHAR(120),
        book_name VARCHAR(255),
        book_display_name VARCHAR(255),
        estimated_minutes INT DEFAULT 0,
        order_index INT DEFAULT 0,
        is_active TINYINT(1) DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uniq_module_course_slug (module_id, slug),
        CONSTRAINT fk_module_courses_module FOREIGN KEY (module_id)
            REFERENCES module_definitions(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS module_course_quizzes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        course_id INT NOT NULL,
        title VARCHAR(255) NOT NULL,
        description VARCHAR(500),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_module_course_quizzes_course FOREIGN KEY (course_id)
            REFERENCES module_courses(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS module_course_quiz_questions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        quiz_id INT NOT NULL,
        prompt TEXT NOT NULL,
        explanation TEXT,
        order_index INT DEFAULT 0,
        CONSTRAINT fk_module_course_quiz_questions_quiz FOREIGN KEY (quiz_id)
            REFERENCES module_course_quizzes(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS module_course_quiz_options (
        id INT AUTO_INCREMENT PRIMARY KEY,
        question_id INT NOT NULL,
        text VARCHAR(255) NOT NULL,
        is_correct TINYINT(1) DEFAULT 0,
        CONSTRAINT fk_module_course_quiz_options_question FOREIGN KEY (question_id)
            REFERENCES module_course_quiz_questions(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS module_course_attempts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        course_id INT NOT NULL,
        user_id INT NOT NULL,
        score INT DEFAULT 0,
        total_questions INT DEFAULT 0,
        completed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_module_course_attempts_course FOREIGN KEY (course_id)
            REFERENCES module_courses(id) ON DELETE CASCADE,
        CONSTRAINT fk_module_course_attempts_user FOREIGN KEY (user_id)
            REFERENCES users(id) ON DELETE CASCADE,
        INDEX idx_module_course_attempt_user (user_id),
        INDEX idx_module_course_attempt_course (course_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS module_course_attempt_answers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        attempt_id INT NOT NULL,
        question_id INT NOT NULL,
        option_id INT NULL,
        is_correct TINYINT(1) DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_module_course_attempt_answers_attempt FOREIGN KEY (attempt_id)
            REFERENCES module_course_attempts(id) ON DELETE CASCADE,
        CONSTRAINT fk_module_course_attempt_answers_question FOREIGN KEY (question_id)
            REFERENCES module_course_quiz_questions(id) ON DELETE CASCADE,
        CONSTRAINT fk_module_course_attempt_answers_option FOREIGN KEY (option_id)
            REFERENCES module_course_quiz_options(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS module_course_resets (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        course_id INT NOT NULL,
        reset_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uniq_module_course_reset (user_id, course_id),
        CONSTRAINT fk_module_course_resets_user FOREIGN KEY (user_id)
            REFERENCES users(id) ON DELETE CASCADE,
        CONSTRAINT fk_module_course_resets_course FOREIGN KEY (course_id)
            REFERENCES module_courses(id) ON DELETE CASCADE
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


def ensure_profile_image_column(cursor):
    try:
        cursor.execute("SHOW COLUMNS FROM users LIKE 'profile_image_path'")
        column = cursor.fetchone()
    except mysql.connector.Error:
        return

    if column:
        return

    try:
        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN profile_image_path VARCHAR(255) NULL AFTER gender
            """
        )
    except mysql.connector.Error:
        pass


def seed_default_quizzes(cursor):
    try:
        cursor.execute("SELECT title FROM quizzes")
        rows = cursor.fetchall()
    except mysql.connector.Error:
        return

    existing_titles = {
        (row[0].strip().lower()) for row in rows if row and row[0]
    }
    for quiz in DEFAULT_QUIZZES:
        title = (quiz.get("title") or "").strip()
        if not title:
            continue
        title_key = title.lower()
        if title_key in existing_titles:
            continue
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
        existing_titles.add(title_key)


def seed_default_module_data(cursor):
    quiz_lookup = {quiz["title"]: quiz for quiz in DEFAULT_QUIZZES if quiz.get("title")}

    for module in DEFAULT_MODULES:
        slug = module.get("id") or module.get("slug")
        if not slug:
            continue

        cursor.execute("SELECT id FROM module_definitions WHERE slug = %s", (slug,))
        row = cursor.fetchone()
        if row:
            module_id = row[0]
            cursor.execute(
                """
                UPDATE module_definitions
                SET title = %s,
                    dialect = %s,
                    accent_color = %s,
                    summary = %s,
                    icon = %s
                WHERE id = %s
                """,
                (
                    module.get("title"),
                    module.get("dialect"),
                    module.get("accent_color"),
                    module.get("summary"),
                    module.get("icon"),
                    module_id,
                ),
            )
        else:
            cursor.execute(
                """
                INSERT INTO module_definitions (slug, title, dialect, accent_color, summary, icon)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    slug,
                    module.get("title"),
                    module.get("dialect"),
                    module.get("accent_color"),
                    module.get("summary"),
                    module.get("icon"),
                ),
            )
            module_id = cursor.lastrowid

        courses = module.get("courses") or []
        for order_index, course in enumerate(courses, start=1):
            course_slug = course.get("id") or course.get("slug")
            if not course_slug:
                continue

            cursor.execute(
                """
                SELECT id FROM module_courses
                WHERE module_id = %s AND slug = %s
                """,
                (module_id, course_slug),
            )
            course_row = cursor.fetchone()
            estimated_minutes = course.get("estimated_minutes") or 0

            if course_row:
                course_id = course_row[0]
                cursor.execute(
                    """
                    UPDATE module_courses
                    SET title = %s,
                        handout_label = %s,
                        page_range = %s,
                        book_name = %s,
                        book_display_name = %s,
                        estimated_minutes = %s,
                        order_index = %s,
                        is_active = 1
                    WHERE id = %s
                    """,
                    (
                        course.get("title"),
                        course.get("handout_label"),
                        course.get("page_range"),
                        course.get("book_name"),
                        course.get("book_display_name"),
                        estimated_minutes,
                        order_index,
                        course_id,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO module_courses (
                        module_id,
                        slug,
                        title,
                        handout_label,
                        page_range,
                        book_name,
                        book_display_name,
                        estimated_minutes,
                        order_index,
                        is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                    """,
                    (
                        module_id,
                        course_slug,
                        course.get("title"),
                        course.get("handout_label"),
                        course.get("page_range"),
                        course.get("book_name"),
                        course.get("book_display_name"),
                        estimated_minutes,
                        order_index,
                    ),
                )
                course_id = cursor.lastrowid

            cursor.execute(
                "SELECT id FROM module_course_quizzes WHERE course_id = %s",
                (course_id,),
            )
            quiz_row = cursor.fetchone()
            quiz_title = course.get("quiz_title")
            quiz_description = course.get("quiz_description")

            if quiz_row:
                quiz_id = quiz_row[0]
                cursor.execute(
                    "UPDATE module_course_quizzes SET title = %s, description = %s WHERE id = %s",
                    (quiz_title, quiz_description, quiz_id),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO module_course_quizzes (course_id, title, description)
                    VALUES (%s, %s, %s)
                    """,
                    (course_id, quiz_title, quiz_description),
                )
                quiz_id = cursor.lastrowid

            cursor.execute(
                "SELECT COUNT(*) FROM module_course_quiz_questions WHERE quiz_id = %s",
                (quiz_id,),
            )
            question_count = cursor.fetchone()[0]
            if question_count:
                continue

            default_quiz = quiz_lookup.get(quiz_title)
            if not default_quiz:
                continue

            for question_index, question in enumerate(default_quiz.get("questions", []), start=1):
                cursor.execute(
                    """
                    INSERT INTO module_course_quiz_questions (quiz_id, prompt, explanation, order_index)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        quiz_id,
                        question.get("prompt"),
                        question.get("explanation"),
                        question_index,
                    ),
                )
                question_id = cursor.lastrowid
                for option in question.get("options", []):
                    cursor.execute(
                        """
                        INSERT INTO module_course_quiz_options (question_id, text, is_correct)
                        VALUES (%s, %s, %s)
                        """,
                        (
                            question_id,
                            option.get("text"),
                            1 if option.get("is_correct") else 0,
                        ),
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
        ensure_profile_image_column(cursor)
        seed_default_quizzes(cursor)
        seed_default_module_data(cursor)
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


def fetch_quiz_attempt_summary(cursor, user_id):
    cursor.execute(
        """
        SELECT quiz_id, score, total_questions, completed_at
        FROM quiz_attempts
        WHERE user_id = %s
        ORDER BY completed_at DESC
        """,
        (user_id,),
    )
    rows = cursor.fetchall()
    summary = {}
    for row in rows:
        quiz_id = row.get("quiz_id")
        if not quiz_id:
            continue
        if quiz_id not in summary:
            summary[quiz_id] = {
                "score": row.get("score"),
                "total_questions": row.get("total_questions"),
                "completed_at": row.get("completed_at"),
                "attempts": 1,
            }
        else:
            summary[quiz_id]["attempts"] += 1
    return summary


def fetch_module_structures(cursor):
    cursor.execute(
        """
        SELECT id, slug, title, dialect, accent_color, summary, icon
        FROM module_definitions
        ORDER BY id ASC
        """
    )
    modules = cursor.fetchall() or []
    structures = []
    for module in modules:
        module_entry = dict(module)
        cursor.execute(
            """
            SELECT id, module_id, slug, title, handout_label, page_range, book_name,
                   book_display_name, estimated_minutes, order_index
            FROM module_courses
            WHERE module_id = %s AND is_active = 1
            ORDER BY order_index ASC, id ASC
            """,
            (module["id"],),
        )
        courses = cursor.fetchall() or []
        for course in courses:
            cursor.execute(
                """
                SELECT id, title, description
                FROM module_course_quizzes
                WHERE course_id = %s
                """,
                (course["id"],),
            )
            quiz = cursor.fetchone()
            if quiz:
                cursor.execute(
                    "SELECT COUNT(*) AS question_count FROM module_course_quiz_questions WHERE quiz_id = %s",
                    (quiz["id"],),
                )
                count_row = cursor.fetchone() or {}
                quiz["question_count"] = count_row.get("question_count", 0)
            course["quiz"] = quiz
        module_entry["courses"] = courses
        structures.append(module_entry)
    return structures


def fetch_module_course_attempt_summary(cursor, user_id):
    cursor.execute(
        """
        SELECT course_id, score, total_questions, completed_at
        FROM module_course_attempts
        WHERE user_id = %s
        ORDER BY completed_at DESC
        """,
        (user_id,),
    )
    rows = cursor.fetchall() or []
    summary = {}
    for row in rows:
        course_id = row.get("course_id")
        if not course_id:
            continue
        entry = summary.setdefault(
            course_id,
            {
                "score": row.get("score"),
                "total_questions": row.get("total_questions"),
                "completed_at": row.get("completed_at"),
                "attempts": 0,
            },
        )
        entry["attempts"] += 1
    return summary


def fetch_module_course_reset_lookup(cursor, user_id):
    cursor.execute(
        """
        SELECT course_id, reset_at
        FROM module_course_resets
        WHERE user_id = %s
        """,
        (user_id,),
    )
    rows = cursor.fetchall() or []
    return {
        row.get("course_id"): row.get("reset_at")
        for row in rows
        if row.get("course_id")
    }


def fetch_module_course_quiz(cursor, course_id, include_correct=False):
    cursor.execute(
        """
        SELECT q.id, q.course_id, q.title, q.description
        FROM module_course_quizzes q
        WHERE q.course_id = %s
        """,
        (course_id,),
    )
    quiz = cursor.fetchone()
    if not quiz:
        return None

    cursor.execute(
        """
        SELECT id, prompt, explanation, order_index
        FROM module_course_quiz_questions
        WHERE quiz_id = %s
        ORDER BY order_index ASC, id ASC
        """,
        (quiz["id"],),
    )
    questions = cursor.fetchall() or []
    question_ids = [question["id"] for question in questions]
    options_by_question = {question_id: [] for question_id in question_ids}
    correct_option_by_question = {}

    if question_ids:
        placeholders = ", ".join(["%s"] * len(question_ids))
        cursor.execute(
            f"""
            SELECT id, question_id, text, is_correct
            FROM module_course_quiz_options
            WHERE question_id IN ({placeholders})
            ORDER BY id ASC
            """,
            tuple(question_ids),
        )
        for option in cursor.fetchall() or []:
            question_id = option.get("question_id")
            if question_id not in options_by_question:
                continue
            option_payload = {
                "id": option.get("id"),
                "text": option.get("text"),
            }
            if include_correct:
                option_payload["is_correct"] = bool(option.get("is_correct"))
            options_by_question.setdefault(question_id, []).append(option_payload)
            if option.get("is_correct"):
                correct_option_by_question[question_id] = option.get("id")

    payload_questions = []
    for question in questions:
        question_id = question.get("id")
        payload_questions.append(
            {
                "id": question_id,
                "prompt": question.get("prompt"),
                "explanation": question.get("explanation"),
                "order_index": question.get("order_index"),
                "options": options_by_question.get(question_id, []),
                "correct_option_id": correct_option_by_question.get(question_id),
            }
        )

    quiz_payload = {
        "id": quiz.get("id"),
        "course_id": quiz.get("course_id"),
        "title": quiz.get("title"),
        "description": quiz.get("description"),
        "questions": payload_questions,
    }
    return quiz_payload


def grade_module_course_quiz(cursor, course_id, responses):
    quiz = fetch_module_course_quiz(cursor, course_id, include_correct=True)
    if not quiz:
        return None, None

    questions = quiz.get("questions", [])
    if not questions:
        return quiz, {"score": 0, "total_questions": 0, "breakdown": []}

    correct_map = {
        question["id"]: question.get("correct_option_id") for question in questions
    }
    response_map = {item.get("question_id"): item.get("option_id") for item in responses}

    score = 0
    breakdown = []
    for question in questions:
        question_id = question.get("id")
        correct_option_id = correct_map.get(question_id)
        selected_option_id = response_map.get(question_id)
        is_correct = selected_option_id == correct_option_id and correct_option_id is not None
        if is_correct:
            score += 1
        breakdown.append(
            {
                "question_id": question_id,
                "selected_option_id": selected_option_id,
                "correct_option_id": correct_option_id,
                "is_correct": is_correct,
            }
        )

    grading = {
        "score": score,
        "total_questions": len(questions),
        "breakdown": breakdown,
    }
    return quiz, grading


def slugify_value(value, fallback="course"):
    if not value:
        return fallback
    slug = "".join(ch if ch.isalnum() else "-" for ch in value.lower())
    slug = "-".join(filter(None, slug.split("-")))
    return slug or fallback


def generate_module_course_slug(title):
    base = slugify_value(title, fallback="course")
    return f"{base}-{uuid.uuid4().hex[:6]}"


def normalize_module_quiz_questions(raw_questions):
    if not isinstance(raw_questions, list) or not raw_questions:
        raise ValueError("At least one quiz question is required.")

    normalized = []
    for index, question in enumerate(raw_questions, start=1):
        prompt = (question.get("prompt") or "").strip()
        if not prompt:
            raise ValueError(f"Question {index} requires a prompt.")

        raw_options = question.get("options") or []
        normalized_options = []
        has_correct = False
        for option in raw_options:
            text = (option.get("text") or "").strip()
            if not text:
                continue
            is_correct = bool(option.get("is_correct"))
            if is_correct:
                has_correct = True
            normalized_options.append({"text": text, "is_correct": is_correct})

        if not normalized_options:
            raise ValueError(f"Question {index} requires at least one option.")
        if not has_correct:
            normalized_options[0]["is_correct"] = True

        normalized.append(
            {
                "prompt": prompt,
                "explanation": (question.get("explanation") or "").strip() or None,
                "options": normalized_options,
            }
        )

    return normalized


def fetch_module_course_admin_detail(cursor, course_id):
    cursor.execute(
        """
        SELECT c.id, c.module_id, c.slug, c.title, c.handout_label, c.page_range,
               c.book_name, c.book_display_name, c.estimated_minutes, c.order_index,
               m.title AS module_title, m.slug AS module_slug
        FROM module_courses c
        JOIN module_definitions m ON m.id = c.module_id
        WHERE c.id = %s
        """,
        (course_id,),
    )
    course = cursor.fetchone()
    if not course:
        return None

    quiz = fetch_module_course_quiz(cursor, course_id, include_correct=True)
    course["quiz"] = quiz
    return course


def build_course_module_payload(cursor, user_id):
    reading_entries = fetch_reading_history_entries(cursor, user_id)
    reading_lookup = {}
    for entry in reading_entries:
        key = (entry.get("book_name") or "").strip().lower()
        if key:
            reading_lookup[key] = entry

    attempts_summary = fetch_module_course_attempt_summary(cursor, user_id)
    reset_lookup = fetch_module_course_reset_lookup(cursor, user_id)
    module_structures = fetch_module_structures(cursor)

    modules_payload = []
    for module in module_structures:
        courses_payload = []
        flow_steps = []
        module_completed = 0
        module_total = 0

        courses = module.get("courses") or []
        for course in courses:
            course_steps_completed = 0
            course_id = course.get("id")
            book_name = course.get("book_name")
            book_key = (book_name or "").strip().lower()
            reading_entry = reading_lookup.get(book_key)
            reading_completed = reading_entry is not None
            pdf_url = f"/reader/books/{book_name}" if book_name else None
            last_read_at = reading_entry.get("last_read_at") if reading_entry else None

            module_total += 1
            if reading_completed:
                module_completed += 1
                course_steps_completed += 1

            flow_steps.append(
                {
                    "type": "course",
                    "course_id": course_id,
                    "course_slug": course.get("slug"),
                    "title": course.get("title"),
                    "status": "completed" if reading_completed else "pending",
                    "book": {
                        "file": book_name,
                        "display_name": course.get("book_display_name"),
                        "page_range": course.get("page_range"),
                        "handout_label": course.get("handout_label"),
                        "last_read_at": last_read_at,
                        "pdf_url": pdf_url,
                    },
                }
            )

            quiz_meta = course.get("quiz") or {}
            quiz_id = quiz_meta.get("id")
            quiz_summary = attempts_summary.get(course_id)
            reset_entry = reset_lookup.get(course_id)

            quiz_completed = False
            quiz_completed_at = quiz_summary.get("completed_at") if quiz_summary else None
            if quiz_summary:
                if reset_entry and quiz_completed_at:
                    quiz_completed = quiz_completed_at > reset_entry
                elif reset_entry and not quiz_completed_at:
                    quiz_completed = False
                else:
                    quiz_completed = True

            module_total += 1
            if quiz_completed:
                module_completed += 1
                course_steps_completed += 1

            flow_steps.append(
                {
                    "type": "quiz",
                    "course_id": course_id,
                    "quiz_id": quiz_id,
                    "title": quiz_meta.get("title"),
                    "status": "completed" if quiz_completed else "pending",
                    "quiz": {
                        "id": quiz_id,
                        "course_id": course_id,
                        "title": quiz_meta.get("title"),
                        "description": quiz_meta.get("description"),
                        "score": quiz_summary.get("score") if quiz_summary else None,
                        "total_questions": quiz_summary.get("total_questions") if quiz_summary else None,
                        "completed_at": isoformat_utc(quiz_completed_at) if quiz_completed_at else None,
                        "attempts": quiz_summary.get("attempts") if quiz_summary else 0,
                        "reset_requested_at": isoformat_utc(reset_entry) if reset_entry else None,
                    },
                }
            )

            score_label = None
            if quiz_summary and quiz_summary.get("total_questions"):
                score_label = f"{quiz_summary.get('score')}/{quiz_summary.get('total_questions')}"

            course_payload = {
                "id": course_id,
                "slug": course.get("slug"),
                "title": course.get("title"),
                "handout_label": course.get("handout_label"),
                "page_range": course.get("page_range"),
                "estimated_minutes": course.get("estimated_minutes"),
                "book": {
                    "file": book_name,
                    "display_name": course.get("book_display_name"),
                    "pdf_url": pdf_url,
                    "last_read_at": last_read_at,
                    "status": "completed" if reading_completed else "pending",
                },
                "quiz": {
                    "id": quiz_id,
                    "course_id": course_id,
                    "title": quiz_meta.get("title"),
                    "description": quiz_meta.get("description"),
                    "status": "completed" if quiz_completed else "pending",
                    "score_label": score_label,
                    "completed_at": isoformat_utc(quiz_completed_at) if quiz_completed_at else None,
                },
                "progress": {
                    "completed_steps": course_steps_completed,
                    "total_steps": 2,
                    "percentage": round((course_steps_completed / 2) * 100, 1),
                },
            }
            courses_payload.append(course_payload)

        total_steps = module_total or 1
        module_percentage = round((module_completed / total_steps) * 100, 1)
        actionable_index = None
        for idx, step in enumerate(flow_steps):
            if step.get("status") != "completed":
                actionable_index = idx
                break
        if actionable_index is None and flow_steps:
            actionable_index = len(flow_steps) - 1

        for idx, step in enumerate(flow_steps, start=1):
            step["step_number"] = idx

        modules_payload.append(
            {
                "id": module.get("id"),
                "slug": module.get("slug"),
                "title": module.get("title"),
                "dialect": module.get("dialect"),
                "summary": module.get("summary"),
                "accent_color": module.get("accent_color"),
                "icon": module.get("icon"),
                "courses": courses_payload,
                "flow": flow_steps,
                "progress": {
                    "completed_steps": module_completed,
                    "total_steps": total_steps,
                    "percentage": module_percentage,
                },
                "actionable_step_index": actionable_index or 0,
            }
        )

    return {
        "modules": modules_payload,
        "generated_at": isoformat_utc(datetime.utcnow()),
    }


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
    avatar_path = row.get("profile_image_path")
    avatar_url = None
    if avatar_path:
        normalized = avatar_path.lstrip("/")
        base_url = build_base_url()
        if base_url:
            avatar_url = f"{base_url}/{normalized}"
        else:
            avatar_url = f"/{normalized}"
    return {
        "id": row.get("id"),
        "email": row.get("email"),
        "firstname": row.get("firstname"),
        "lastname": row.get("lastname"),
        "student_id": row.get("student_id"),
        "year": row.get("year") or row.get("year_level"),
        "gender": row.get("gender"),
        "verified": verified,
        "profile_image_path": avatar_path,
        "profile_image_url": avatar_url,
    }


def resolve_avatar_abs_path(relative_path):
    if not relative_path:
        return None
    normalized = relative_path.lstrip("/\\")
    absolute_path = os.path.abspath(os.path.join(app.root_path, normalized))
    try:
        common = os.path.commonpath([absolute_path, PROFILE_UPLOAD_FOLDER])
    except ValueError:
        return None
    if common != PROFILE_UPLOAD_FOLDER:
        return None
    return absolute_path


def remove_profile_image(relative_path):
    absolute_path = resolve_avatar_abs_path(relative_path)
    if not absolute_path:
        return
    try:
        if os.path.isfile(absolute_path):
            os.remove(absolute_path)
    except OSError:
        pass


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.before_request
def enforce_login_for_pages():
    if session.get("user_id"):
        return

    if request.method not in ("GET", "HEAD"):
        return

    path = unquote(request.path or "")
    if path == "/" or path.startswith("/api/"):
        return

    if not path.endswith(".html"):
        return

    normalized = path.rstrip("/")
    if normalized in PUBLIC_HTML_PATHS:
        return

    first_segment = normalized.lstrip("/").split("/", 1)[0]
    if first_segment in PUBLIC_HTML_ROOTS:
        return

    login_url = url_for("static", filename="login/login.html")
    return redirect(login_url)


@app.errorhandler(403)
def handle_forbidden(error):
    if request.path.startswith("/api/"):
        message = getattr(error, "description", "Forbidden.")
        return json_response(False, message, status=403)
    login_url = url_for("static", filename="login/login.html")
    return redirect(login_url)


@app.after_request
def redirect_forbidden_responses(response):
    if response.status_code == 403 and not request.path.startswith("/api/"):
        login_url = url_for("static", filename="login/login.html")
        return redirect(login_url)
    return response


@app.route("/reset/<token>", methods=["GET"])
def serve_reset_page(token):
    return send_from_directory(os.path.join(app.static_folder, "forgot"), "newpassword.html")


def _sanitize_registration_payload(data):
    return {
        "firstname": (data.get("firstname") or "").strip(),
        "lastname": (data.get("lastname") or "").strip(),
        "student_id": (data.get("student_id") or "").strip(),
        "email": (data.get("email") or "").strip().lower(),
        "password": data.get("password") or "",
        "year": (data.get("year") or "").strip(),
        "gender": (data.get("gender") or "").strip(),
    }


def _generate_verification_code():
    return f"{random.randint(0, 999999):06d}"


def _send_registration_code_email(email, firstname, code):
    greeting = firstname or "there"
    msg = Message(
        "Your PronoCoach verification code",
        recipients=[email],
        body=(
            f"Hello {greeting},\n\n"
            f"Use the following verification code to complete your PronoCoach registration:\n\n"
            f"{code}\n\n"
            f"This code will expire in {REGISTRATION_CODE_EXPIRY_MINUTES} minutes.\n"
            "If you did not request this, you can safely ignore this email."
        ),
    )
    mail.send(msg)


def _process_registration_send_code():
    data = request.get_json() or {}
    payload = _sanitize_registration_payload(data)

    required_fields = ["firstname", "lastname", "student_id", "email", "password", "year", "gender"]
    missing = [field for field in required_fields if not payload.get(field)]
    if missing:
        return json_response(False, f"Missing fields: {', '.join(missing)}", status=400)

    if not re.fullmatch(r"\d{11}", payload["student_id"]):
        return json_response(False, "Student ID must be exactly 11 digits.", status=400)

    if not PASSWORD_POLICY.match(payload["password"]):
        return json_response(
            False,
            "Password must be at least 8 characters and contain at least 1 letter and 1 special character.",
            status=400,
        )

    hashed_password = bcrypt.generate_password_hash(payload["password"]).decode("utf-8")
    code = _generate_verification_code()
    expires_at = datetime.utcnow() + timedelta(minutes=REGISTRATION_CODE_EXPIRY_MINUTES)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s", (payload["email"],))
        if cursor.fetchone():
            return json_response(False, "This email is already registered.", status=400)

        cursor.execute("SELECT id FROM users WHERE student_id = %s", (payload["student_id"],))
        if cursor.fetchone():
            return json_response(False, "This student ID is already registered.", status=400)

        cursor.execute(
            """
            SELECT email
            FROM pending_registrations
            WHERE student_id = %s AND email <> %s
            """,
            (payload["student_id"], payload["email"]),
        )
        if cursor.fetchone():
            return json_response(
                False,
                "This student ID already has a pending verification. Please use the original email or wait for it to expire.",
                status=400,
            )

        cursor.execute(
            """
            INSERT INTO pending_registrations (
                email, student_id, firstname, lastname, year, gender,
                password_hash, verification_code, expires_at, attempts
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0)
            ON DUPLICATE KEY UPDATE
                student_id = VALUES(student_id),
                firstname = VALUES(firstname),
                lastname = VALUES(lastname),
                year = VALUES(year),
                gender = VALUES(gender),
                password_hash = VALUES(password_hash),
                verification_code = VALUES(verification_code),
                expires_at = VALUES(expires_at),
                attempts = 0,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                payload["email"],
                payload["student_id"],
                payload["firstname"],
                payload["lastname"],
                payload["year"],
                payload["gender"],
                hashed_password,
                code,
                expires_at,
            ),
        )

        _send_registration_code_email(payload["email"], payload["firstname"], code)
        conn.commit()
        return json_response(
            True,
            "Verification code sent. Please check your email.",
            {"expires_in_minutes": REGISTRATION_CODE_EXPIRY_MINUTES},
            status=200,
        )
    except mysql.connector.Error as exc:
        conn.rollback()
        if getattr(exc, "errno", None) == 1062:
            lowered = str(exc).lower()
            if "email" in lowered:
                return json_response(False, "This email is already registered.", status=400)
            if "student_id" in lowered:
                return json_response(False, "This student ID is already registered.", status=400)
        return json_response(False, f"Unable to send verification code: {exc}", status=400)
    except Exception as err:  # pragma: no cover - SMTP configuration dependent
        conn.rollback()
        return json_response(False, f"Failed to send verification email: {err}", status=500)
    finally:
        cursor.close()
        conn.close()


@app.route("/api/register/send-code", methods=["POST"])
def register_send_code():
    return _process_registration_send_code()


@app.route("/api/register", methods=["POST"])
def register():
    return _process_registration_send_code()


@app.route("/api/register/verify-code", methods=["POST"])
def register_verify_code():
    data = request.get_json() or {}
    email = (data.get("email") or "").strip().lower()
    code = (data.get("code") or "").strip()

    if not email or not code:
        return json_response(False, "Email and verification code are required.", status=400)

    if not re.fullmatch(r"\d{6}", code):
        return json_response(False, "Verification code must be exactly 6 digits.", status=400)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT *
            FROM pending_registrations
            WHERE email = %s
            """,
            (email,),
        )
        pending = cursor.fetchone()
        if not pending:
            return json_response(False, "No pending registration found for this email. Please request a new code.", status=400)

        if pending.get("expires_at") and pending["expires_at"] < datetime.utcnow():
            cursor.execute("DELETE FROM pending_registrations WHERE id = %s", (pending["id"],))
            conn.commit()
            return json_response(False, "Verification code expired. Please request a new code.", status=400)

        if pending.get("attempts", 0) >= 5:
            cursor.execute("DELETE FROM pending_registrations WHERE id = %s", (pending["id"],))
            conn.commit()
            return json_response(False, "Too many invalid attempts. Please request a new code.", status=400)

        if pending["verification_code"] != code:
            cursor.execute(
                "UPDATE pending_registrations SET attempts = attempts + 1, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (pending["id"],),
            )
            conn.commit()
            return json_response(False, "Invalid verification code.", status=400)

        cursor.execute("SELECT id FROM users WHERE email = %s", (pending["email"],))
        if cursor.fetchone():
            cursor.execute("DELETE FROM pending_registrations WHERE id = %s", (pending["id"],))
            conn.commit()
            return json_response(False, "This email is already registered.", status=400)

        cursor.execute("SELECT id FROM users WHERE student_id = %s", (pending["student_id"],))
        if cursor.fetchone():
            cursor.execute("DELETE FROM pending_registrations WHERE id = %s", (pending["id"],))
            conn.commit()
            return json_response(False, "This student ID is already registered.", status=400)

        cursor.execute(
            """
            INSERT INTO users (firstname, lastname, year, student_id, gender, email, password, verified, verified_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s)
            """,
            (
                pending["firstname"],
                pending["lastname"],
                pending["year"],
                pending["student_id"],
                pending["gender"],
                pending["email"],
                pending["password_hash"],
                datetime.utcnow(),
            ),
        )
        cursor.execute("DELETE FROM pending_registrations WHERE id = %s", (pending["id"],))
        conn.commit()
        user_summary = {
            "email": pending["email"],
            "firstname": pending["firstname"],
            "lastname": pending["lastname"],
            "student_id": pending["student_id"],
            "year": pending["year"],
            "gender": pending["gender"],
        }
        return json_response(True, "Registration complete. You can now log in.", {"user": user_summary}, status=201)
    except mysql.connector.Error as exc:
        conn.rollback()
        if getattr(exc, "errno", None) == 1062:
            lowered = str(exc).lower()
            if "email" in lowered:
                message = "This email is already registered."
            elif "student_id" in lowered:
                message = "This student ID is already registered."
            else:
                message = "Duplicate account detected."
            return json_response(False, message, status=400)
        return json_response(False, f"Registration failed: {exc}", status=400)
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


@app.route("/api/profile/me", methods=["GET"])
def get_own_profile():
    user_id = session.get("user_id")
    if not user_id:
        return json_response(False, "Authentication required.", status=401)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        user = fetch_user_by_id(cursor, user_id)
        if not user:
            return json_response(False, "User not found.", status=404)
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


@app.route("/api/profile/avatar", methods=["POST"])
def upload_profile_avatar():
    user_id = session.get("user_id")
    if not user_id:
        return json_response(False, "Authentication required.", status=401)

    if "file" not in request.files:
        return json_response(False, "No file uploaded.", status=400)
    file = request.files["file"]
    if not file or not file.filename:
        return json_response(False, "No file selected.", status=400)

    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in ALLOWED_PROFILE_EXTENSIONS:
        return json_response(False, "Unsupported image type. Use PNG, JPG, JPEG, GIF, or WEBP.", status=400)

    content_length = request.content_length or 0
    if MAX_PROFILE_IMAGE_BYTES and content_length > MAX_PROFILE_IMAGE_BYTES:
        return json_response(False, "Image exceeds the allowed size limit.", status=413)

    new_filename = f"{uuid.uuid4().hex}{extension}"
    relative_path = f"{PROFILE_UPLOAD_SUBDIR}/{new_filename}"
    absolute_path = os.path.join(PROFILE_UPLOAD_FOLDER, new_filename)

    try:
        file.save(absolute_path)
    except Exception as exc:
        return json_response(False, f"Failed to save uploaded image: {exc}", status=500)

    if MAX_PROFILE_IMAGE_BYTES:
        try:
            actual_size = os.path.getsize(absolute_path)
        except OSError:
            actual_size = 0
        if actual_size > MAX_PROFILE_IMAGE_BYTES:
            remove_profile_image(relative_path)
            return json_response(False, "Image exceeds the allowed size limit.", status=413)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT profile_image_path FROM users WHERE id = %s",
            (user_id,),
        )
        row = cursor.fetchone() or {}
        previous_path = row.get("profile_image_path")

        cursor.execute(
            "UPDATE users SET profile_image_path = %s WHERE id = %s",
            (relative_path, user_id),
        )
        conn.commit()

        if previous_path and previous_path != relative_path:
            remove_profile_image(previous_path)

        user = fetch_user_by_id(cursor, user_id)
        return json_response(True, "Profile image updated successfully.", {"profile": serialize_user(user)})
    except mysql.connector.Error as exc:
        conn.rollback()
        remove_profile_image(relative_path)
        return json_response(False, f"Database error: {exc}", status=500)
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


@app.route("/api/admin/module_courses", methods=["GET", "POST"])
def admin_module_courses_collection():
    if request.method == "GET":
        auth_error = ensure_authenticated()
        if auth_error:
            return auth_error

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            modules = fetch_module_structures(cursor)
            return json_response(True, "Module courses fetched.", {"modules": modules})
        finally:
            cursor.close()
            conn.close()

    auth_error = ensure_authenticated()
    if auth_error:
        return auth_error

    data = request.get_json() or {}
    module_id = data.get("module_id")
    if module_id is None:
        return json_response(False, "module_id is required.", status=400)
    try:
        module_id = int(module_id)
    except (TypeError, ValueError):
        return json_response(False, "module_id must be an integer.", status=400)

    course_payload = data.get("course") or {}
    quiz_payload = data.get("quiz") or {}
    quiz_title = (quiz_payload.get("title") or "").strip()
    if not quiz_title:
        return json_response(False, "Quiz title is required.", status=400)

    try:
        questions = normalize_module_quiz_questions(quiz_payload.get("questions") or [])
    except ValueError as exc:
        return json_response(False, str(exc), status=400)

    course_title = (course_payload.get("title") or "").strip()
    if not course_title:
        return json_response(False, "Course title is required.", status=400)

    slug_value = course_payload.get("slug")
    slug = slugify_value(slug_value, fallback="course") if slug_value else generate_module_course_slug(course_title)

    order_index = course_payload.get("order_index")
    if order_index is not None:
        try:
            order_index = int(order_index)
        except (TypeError, ValueError):
            return json_response(False, "order_index must be a number.", status=400)

    estimated_minutes = course_payload.get("estimated_minutes")
    if estimated_minutes is not None:
        try:
            estimated_minutes = int(estimated_minutes)
        except (TypeError, ValueError):
            return json_response(False, "estimated_minutes must be a number.", status=400)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id FROM module_definitions WHERE id = %s", (module_id,))
        if not cursor.fetchone():
            return json_response(False, "Module not found.", status=404)

        if order_index is None:
            cursor.execute(
                "SELECT COALESCE(MAX(order_index), 0) + 1 AS next_order FROM module_courses WHERE module_id = %s",
                (module_id,),
            )
            order_row = cursor.fetchone()
            if isinstance(order_row, tuple):
                order_index = order_row[0] if order_row and order_row[0] is not None else 1
            else:
                order_index = (order_row or {}).get("next_order") or 1

        cursor.execute(
            """
            INSERT INTO module_courses (
                module_id,
                slug,
                title,
                handout_label,
                page_range,
                book_name,
                book_display_name,
                estimated_minutes,
                order_index,
                is_active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            """,
            (
                module_id,
                slug,
                course_title,
                (course_payload.get("handout_label") or "").strip() or None,
                (course_payload.get("page_range") or "").strip() or None,
                (course_payload.get("book_name") or "").strip() or None,
                (course_payload.get("book_display_name") or "").strip() or None,
                estimated_minutes,
                order_index,
            ),
        )
        course_id = cursor.lastrowid

        cursor.execute(
            """
            INSERT INTO module_course_quizzes (course_id, title, description)
            VALUES (%s, %s, %s)
            """,
            (course_id, quiz_title, (quiz_payload.get("description") or "").strip() or None),
        )
        quiz_id = cursor.lastrowid

        for question_index, question in enumerate(questions, start=1):
            cursor.execute(
                """
                INSERT INTO module_course_quiz_questions (quiz_id, prompt, explanation, order_index)
                VALUES (%s, %s, %s, %s)
                """,
                (quiz_id, question["prompt"], question.get("explanation"), question_index),
            )
            question_id = cursor.lastrowid
            for option in question["options"]:
                cursor.execute(
                    """
                    INSERT INTO module_course_quiz_options (question_id, text, is_correct)
                    VALUES (%s, %s, %s)
                    """,
                    (question_id, option["text"], 1 if option.get("is_correct") else 0),
                )

        conn.commit()
        detail = fetch_module_course_admin_detail(cursor, course_id)
        return json_response(True, "Module course created.", {"course": detail})
    except (ValueError, TypeError) as exc:
        conn.rollback()
        return json_response(False, str(exc), status=400)
    except mysql.connector.Error as exc:
        conn.rollback()
        return json_response(False, f"Database error: {exc}", status=500)
    finally:
        cursor.close()
        conn.close()


@app.route("/api/admin/module_courses/<int:course_id>", methods=["GET", "PUT", "DELETE"])
def admin_module_course_resource(course_id):
    auth_error = ensure_authenticated()
    if auth_error:
        return auth_error

    if request.method == "GET":
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            detail = fetch_module_course_admin_detail(cursor, course_id)
            if not detail:
                return json_response(False, "Module course not found.", status=404)
            return json_response(True, "Module course fetched.", {"course": detail})
        finally:
            cursor.close()
            conn.close()

    if request.method == "DELETE":
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM module_courses WHERE id = %s", (course_id,))
            if cursor.rowcount == 0:
                conn.rollback()
                return json_response(False, "Module course not found.", status=404)
            conn.commit()
            return json_response(True, "Module course deleted.", {"course_id": course_id})
        except mysql.connector.Error as exc:
            conn.rollback()
            return json_response(False, f"Database error: {exc}", status=500)
        finally:
            cursor.close()
            conn.close()

    # PUT
    data = request.get_json() or {}
    course_payload = data.get("course") or {}
    quiz_payload = data.get("quiz") or {}

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM module_courses WHERE id = %s", (course_id,))
        existing_course = cursor.fetchone()
        if not existing_course:
            return json_response(False, "Module course not found.", status=404)

        module_id = data.get("module_id", existing_course.get("module_id"))
        try:
            module_id = int(module_id)
        except (TypeError, ValueError):
            return json_response(False, "module_id must be an integer.", status=400)

        cursor.execute("SELECT id FROM module_definitions WHERE id = %s", (module_id,))
        if not cursor.fetchone():
            return json_response(False, "Module not found.", status=404)

        course_title = (course_payload.get("title") or existing_course.get("title") or "").strip()
        if not course_title:
            return json_response(False, "Course title is required.", status=400)

        slug_value = course_payload.get("slug")
        if slug_value is not None and slug_value.strip():
            slug = slugify_value(slug_value, fallback="course")
        else:
            slug = existing_course.get("slug") or generate_module_course_slug(course_title)

        order_index = course_payload.get("order_index")
        if order_index is not None:
            try:
                order_index = int(order_index)
            except (TypeError, ValueError):
                return json_response(False, "order_index must be a number.", status=400)
        else:
            order_index = existing_course.get("order_index")

        estimated_minutes = course_payload.get("estimated_minutes")
        if estimated_minutes is not None:
            try:
                estimated_minutes = int(estimated_minutes)
            except (TypeError, ValueError):
                return json_response(False, "estimated_minutes must be a number.", status=400)
        else:
            estimated_minutes = existing_course.get("estimated_minutes")

        quiz_title = (quiz_payload.get("title") or "").strip()
        if not quiz_title:
            return json_response(False, "Quiz title is required.", status=400)

        try:
            questions = normalize_module_quiz_questions(quiz_payload.get("questions") or [])
        except ValueError as exc:
            return json_response(False, str(exc), status=400)

        cursor.execute(
            """
            UPDATE module_courses
            SET module_id = %s,
                slug = %s,
                title = %s,
                handout_label = %s,
                page_range = %s,
                book_name = %s,
                book_display_name = %s,
                estimated_minutes = %s,
                order_index = %s
            WHERE id = %s
            """,
            (
                module_id,
                slug,
                course_title,
                (course_payload.get("handout_label") or "").strip() or None,
                (course_payload.get("page_range") or "").strip() or None,
                (course_payload.get("book_name") or "").strip() or None,
                (course_payload.get("book_display_name") or "").strip() or None,
                estimated_minutes,
                order_index,
                course_id,
            ),
        )

        cursor.execute("SELECT id FROM module_course_quizzes WHERE course_id = %s", (course_id,))
        quiz_row = cursor.fetchone()
        if quiz_row:
            quiz_id = quiz_row["id"]
            cursor.execute(
                "UPDATE module_course_quizzes SET title = %s, description = %s WHERE id = %s",
                (quiz_title, (quiz_payload.get("description") or "").strip() or None, quiz_id),
            )
            cursor.execute("DELETE FROM module_course_quiz_questions WHERE quiz_id = %s", (quiz_id,))
        else:
            cursor.execute(
                """
                INSERT INTO module_course_quizzes (course_id, title, description)
                VALUES (%s, %s, %s)
                """,
                (course_id, quiz_title, (quiz_payload.get("description") or "").strip() or None),
            )
            quiz_id = cursor.lastrowid

        for question_index, question in enumerate(questions, start=1):
            cursor.execute(
                """
                INSERT INTO module_course_quiz_questions (quiz_id, prompt, explanation, order_index)
                VALUES (%s, %s, %s, %s)
                """,
                (quiz_id, question["prompt"], question.get("explanation"), question_index),
            )
            question_id = cursor.lastrowid
            for option in question["options"]:
                cursor.execute(
                    """
                    INSERT INTO module_course_quiz_options (question_id, text, is_correct)
                    VALUES (%s, %s, %s)
                    """,
                    (question_id, option["text"], 1 if option.get("is_correct") else 0),
                )

        conn.commit()
        detail = fetch_module_course_admin_detail(cursor, course_id)
        return json_response(True, "Module course updated.", {"course": detail})
    except (ValueError, TypeError) as exc:
        conn.rollback()
        return json_response(False, str(exc), status=400)
    except mysql.connector.Error as exc:
        conn.rollback()
        return json_response(False, f"Database error: {exc}", status=500)
    finally:
        cursor.close()
        conn.close()
@app.route("/api/admin/analytics", methods=["GET"])
def admin_analytics():
    auth_error = ensure_authenticated()
    if auth_error:
        return auth_error

    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    last_7d_start = (now - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)

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

        cursor.execute(
            """
            SELECT DATE(created_at) AS day, COUNT(*) AS signups
            FROM users
            WHERE created_at >= %s
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at) ASC
            """,
            (last_7d_start,),
        )
        signups_by_day = cursor.fetchall() or []

        cursor.execute(
            """
            SELECT DATE(completed_at) AS day, COUNT(*) AS attempts
            FROM quiz_attempts
            WHERE completed_at >= %s
            GROUP BY DATE(completed_at)
            ORDER BY DATE(completed_at) ASC
            """,
            (last_7d_start,),
        )
        attempts_by_day = cursor.fetchall() or []

        daily_signups_lookup = {
            row["day"].isoformat() if hasattr(row["day"], "isoformat") else str(row["day"]): row.get("signups", 0) or 0
            for row in signups_by_day
            if row.get("day") is not None
        }
        daily_attempts_lookup = {
            row["day"].isoformat() if hasattr(row["day"], "isoformat") else str(row["day"]): row.get("attempts", 0) or 0
            for row in attempts_by_day
            if row.get("day") is not None
        }

        daily_series = []
        for offset in range(7):
            day = (last_7d_start.date() + timedelta(days=offset)).isoformat()
            daily_series.append(
                {
                    "date": day,
                    "quiz_attempts": daily_attempts_lookup.get(day, 0),
                    "signups": daily_signups_lookup.get(day, 0),
                }
            )

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
            "daily_activity": daily_series,
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

    data = {}
    if request.method == "PUT":
        data = request.get_json(silent=True)
        if data is None:
            return json_response(False, "Invalid or missing JSON payload.", status=400)

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


@app.route("/api/course_modules", methods=["GET"])
def course_modules():
    user_id = session.get("user_id")
    if not user_id:
        return json_response(False, "Authentication required.", status=401)

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        payload = build_course_module_payload(cursor, user_id)
        return json_response(True, "Course modules fetched.", payload)
    finally:
        cursor.close()
        conn.close()


@app.route("/api/course_modules/reset", methods=["POST"])
def course_module_reset():
    user_id = session.get("user_id")
    if not user_id:
        return json_response(False, "Authentication required.", status=401)

    data = request.get_json() or {}
    course_id = data.get("course_id")
    try:
        course_id = int(course_id)
    except (TypeError, ValueError):
        return json_response(False, "course_id must be provided.", status=400)

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM module_courses WHERE id = %s", (course_id,))
        course = cursor.fetchone()
        if not course:
            return json_response(False, "Course not found.", status=404)

        timestamp = datetime.utcnow()
        cursor.execute(
            """
            INSERT INTO module_course_resets (user_id, course_id, reset_at)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE reset_at = VALUES(reset_at)
            """,
            (user_id, course_id, timestamp),
        )
        conn.commit()
        return json_response(
            True,
            "Module course progress flagged for reset.",
            {"course_id": course_id, "reset_at": isoformat_utc(timestamp)},
        )
    except mysql.connector.Error as exc:
        conn.rollback()
        return json_response(False, f"Database error: {exc}", status=500)
    finally:
        cursor.close()
        conn.close()


@app.route("/api/module_courses/<int:course_id>/quiz", methods=["GET"])
def module_course_quiz_detail(course_id):
    auth_error = ensure_authenticated()
    if auth_error:
        return auth_error

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        quiz = fetch_module_course_quiz(cursor, course_id)
        if not quiz:
            return json_response(False, "Quiz not found.", status=404)
        return json_response(True, "Quiz fetched.", {"quiz": quiz})
    finally:
        cursor.close()
        conn.close()


@app.route("/api/module_courses/<int:course_id>/quiz/attempts", methods=["POST"])
def module_course_quiz_attempt(course_id):
    auth_error = ensure_authenticated()
    if auth_error:
        return auth_error

    user_id = session.get("user_id")
    data = request.get_json() or {}
    responses = data.get("responses") or []

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        quiz, grading = grade_module_course_quiz(cursor, course_id, responses)
        if quiz is None:
            return json_response(False, "Quiz not found.", status=404)
        if grading["total_questions"] == 0:
            return json_response(False, "Quiz has no questions.", status=400)

        timestamp = datetime.utcnow()
        cursor.execute(
            """
            INSERT INTO module_course_attempts (course_id, user_id, score, total_questions, completed_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (course_id, user_id, grading["score"], grading["total_questions"], timestamp),
        )
        attempt_id = cursor.lastrowid

        for item in grading["breakdown"]:
            cursor.execute(
                """
                INSERT INTO module_course_attempt_answers (attempt_id, question_id, option_id, is_correct)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    attempt_id,
                    item["question_id"],
                    item.get("selected_option_id"),
                    1 if item["is_correct"] else 0,
                ),
            )

        cursor.execute(
            "DELETE FROM module_course_resets WHERE user_id = %s AND course_id = %s",
            (user_id, course_id),
        )

        conn.commit()
        payload = {
            "course_id": course_id,
            "quiz_id": quiz.get("id"),
            "quiz_title": quiz.get("title"),
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


@app.route("/api/module_courses/<int:course_id>/quiz/reset", methods=["POST"])
def module_course_quiz_reset(course_id):
    auth_error = ensure_authenticated()
    if auth_error:
        return auth_error

    user_id = session.get("user_id")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM module_courses WHERE id = %s", (course_id,))
        if not cursor.fetchone():
            return json_response(False, "Course not found.", status=404)

        timestamp = datetime.utcnow()
        cursor.execute(
            """
            INSERT INTO module_course_resets (user_id, course_id, reset_at)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE reset_at = VALUES(reset_at)
            """,
            (user_id, course_id, timestamp),
        )
        conn.commit()
        return json_response(
            True,
            "Module quiz reset.",
            {"course_id": course_id, "reset_at": isoformat_utc(timestamp)},
        )
    except mysql.connector.Error as exc:
        conn.rollback()
        return json_response(False, f"Database error: {exc}", status=500)
    finally:
        cursor.close()
        conn.close()


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
    source_language = data.get("source_language", "")
    target_language = data.get("target_language", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        translation, explanation = perform_explain_translation(text, source_language, target_language)
        return jsonify({"translation": translation, "explanation": explanation})
    except Exception as exc:  # pragma: no cover - OpenAI dependency
        return jsonify({"error": str(exc)}), 500


def perform_simple_translation(text: str, source_language: str, target_language: str) -> str:
    """Translate text with language context for the simple translator routes."""
    source = (source_language or "").strip() or "English"
    target = (target_language or "").strip() or "Tagalog"
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an accurate translation engine similar to Google Translate.\n"
                    f"Translate user text from {source} to {target}.\n"
                    "Return only the translated text with no additional commentary or formatting.\n"
                    "Avoid using the * character unless it appears in the translation naturally."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Source language: {source}\n"
                    f"Target language: {target}\n"
                    f"Text: {text}"
                ),
            },
        ],
    )
    return response.choices[0].message.content


def parse_translation_response(raw_text: str) -> tuple[str, str]:
    translation = ""
    explanation = ""
    for line in (raw_text or "").splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith("translation:"):
            translation = stripped.split(":", 1)[1].strip()
        elif lowered.startswith("explanation:"):
            explanation = stripped.split(":", 1)[1].strip()
        elif not translation and stripped:
            translation = stripped
    translation = translation or (raw_text or "").strip()
    return translation, explanation


def perform_explain_translation(text: str, source_language: str, target_language: str) -> tuple[str, str]:
    """Translate text with optional explanation while honoring selected languages."""
    source_raw = (source_language or "").strip()
    auto_detect = not source_raw or source_raw.lower() == "auto"
    source = source_raw if source_raw else "Auto"
    target = (target_language or "").strip() or "Tagalog"
    system_instructions = (
        "You are a helpful translation assistant similar to Google Translate but with brief tips.\n"
        f"{'Detect the language of the user text before translating it.' if auto_detect else f'The user text is in {source}.'}\n"
        f"Translate the text into {target}.\n"
        "Respond using exactly two lines:\n"
        "Translation: <translated text in the target language>\n"
        "Explanation: <a short usage tip in English>\n"
        "Do not add extra text, emojis, or markdown. Avoid the * character unless required by the translation."
    )
    user_prompt = (
        f"Source language: {source}\n"
        f"Target language: {target}\n"
        f"Text: {text}"
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_instructions},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = response.choices[0].message.content or ""
    return parse_translation_response(raw)


@app.route("/translate_simple", methods=["POST"])
def translate_simple():
    data = request.get_json() or {}
    text = data.get("text", "")
    source_language = data.get("source_language", "")
    target_language = data.get("target_language", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        translation = perform_simple_translation(text, source_language, target_language)
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
    source_language = request.form.get("source_language", "")
    target_language = request.form.get("target_language", "")
    try:
        transcription = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=(audio_file.filename, audio_file.stream, audio_file.content_type),
        )
        text = transcription.text
        translation, explanation = perform_explain_translation(text, source_language, target_language)
        return jsonify({"original": text, "translation": translation, "explanation": explanation})
    except Exception as exc:  # pragma: no cover - OpenAI dependency
        return jsonify({"error": str(exc)}), 500


@app.route("/stt_simple", methods=["POST"])
def stt_simple():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    audio_file = request.files["file"]
    source_language = request.form.get("source_language", "")
    target_language = request.form.get("target_language", "")
    try:
        transcription = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=(audio_file.filename, audio_file.stream, audio_file.content_type),
        )
        text = transcription.text
        translation = perform_simple_translation(text, source_language, target_language)
        return jsonify({"original": text, "translation": translation})
    except Exception as exc:  # pragma: no cover - OpenAI dependency
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=443,
        # ssl_context=(cert_path, key_path)  # Configure when certificates are available.
    )
