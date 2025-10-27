# Technical Specification ??Philippine Multilingual Learning WebApp

## 1. Project Overview
- **Goal**: Deliver a mobile-first web application that enables Filipino students to translate study materials, read bundled PDFs, and practice via quizzes, while administrators manage content and monitor usage.
- **Timeline**: Code complete by **22 Oct 2025 (Wed AM)**; customer handles Windows-hosted deployment afterward.
- **Platform**: Responsive web app (primary mobile layout) backed by Flask + MySQL.
- **Provided Assets**: Existing HTML/CSS/JS screens, Figma design, OpenAI API key, optional remote desktop access.

## 2. System Architecture
- **Frontend (`/frontend/`)**: Static HTML/CSS/JS bundles per feature (Login, Reader, Translator, Quiz, Profile, Admin). Uses Fetch API to call backend, Web Speech API for TTS fallback.
- **Backend (`/backend/app.py`)**: Flask REST server with session cookies, bcrypt password handling, SMTP mailer, OpenAI SDK, and MySQL connector.
- **Database (`/db/`)**: MySQL schema for users, verification tokens, reading progress, quiz definitions, quiz history, analytics snapshots (no stored admin credentials needed).
- **External Services**:
  - SMTP (Gmail or customer mail server) for verification and reset emails.
  - OpenAI GPT for translation; optional TTS engine (gTTS/pyttsx3) when browser Speech API unavailable.
  - TLS certificates supplied by customer for HTTPS.

## 3. Module Responsibilities
| Module | Key Responsibilities |
| --- | --- |
| Auth & Profile | Signup with email verification, login, password reset/change, profile CRUD |
| Reader | Serve bundled PDFs in lightweight viewer, log last opened book/page per user |
| Translator & TTS | Multi-language translation (7 languages) and audio playback per language |
| Quiz | CRUD quiz bank, run 4-option quizzes, store scores/history |
| Admin Dashboard | Demo-only, client-side password gate with user management, quiz tools, usage analytics |

## 4. Backend API Specification

### 4.1 Authentication & Profile
| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/api/register/send-code` | Validate signup details, generate a 6-digit code, and email it to the user (alias: `/api/register`). |
| `POST` | `/api/register/verify-code` | Confirm the emailed code and create a verified user record immediately. |
| `GET` | `/api/verify/<token>` | Legacy link-based verification (kept for backward compatibility). |
| `POST` | `/api/login` | Authenticate; sets session cookie; returns user summary. |
| `POST` | `/api/forgot` | Request password reset; sends token link. |
| `POST` | `/api/reset/<token>` | Validate token and set new password (requires new != old). |
| `POST` | `/api/reset_password/<token>` | (Legacy) Update password; to be superseded by `/api/reset/<token>`. |
| `PUT` | `/api/profile/update` | Update profile fields (firstname, lastname, year, student_id, gender). |
| `GET` | `/api/profile/<email>` | Fetch profile by email; restricted to owner/admin. |

**Signup Flow Examples**

Step 1 – request verification code:
```json
{
  "email": "student@example.com",
  "password": "Str0ngPass!",
  "firstname": "Ana",
  "lastname": "Santos",
  "student_id": "02000123456",
  "year": "Grade 10",
  "gender": "F"
}
```

Step 2 – verify code and create account:
```json
{
  "email": "student@example.com",
  "code": "483192"
}
```

- Verification codes expire after 15 minutes; changing any signup details requires requesting a fresh code.

**Common Response Schema**
```json
{ "success": true, "message": "Human readable summary", "data": {...} }
```

### 4.2 Reader & History
| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/reader/<book_id>` | Serve PDF asset (secured). |
| `POST` | `/api/save_progress` | Body: `{ "book_name": "Sabayan", "page": 12 }`; stores last opened page per user/book. |
| `GET` | `/api/get_progress` | Returns minimal history: `{ "book_name": "...", "page": 12, "updated_at": "..." }`. |
| `GET` | `/api/history/reading` | (Optional) Alias for `/api/get_progress` when History tab needs listing. |

### 4.3 Translation & TTS
| Method | Endpoint | Behavior |
| --- | --- | --- |
| `POST` | `/translate_simple` | Body: `{ "text": "Hello", "source_language": "English", "target_language": "Tagalog" }`; returns only the translated string. |
| `POST` | `/translate_explain` | Body: `{ "text": "Hello", "source_language": "Auto", "target_language": "Tagalog" }`; returns the translation plus a short usage explanation. |
| `POST` | `/tts` | Body: `{ "text": "Kamusta" }`; streams generated audio using the default OpenAI voice. |

**OpenAI Prompt Contract**
```
You are an accurate translation engine similar to Google Translate.
Translate the user text from <source_language> to <target_language>.
Return only the translated text with no additional commentary.
```

### 4.4 Quiz System
| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/quizzes` | List available quizzes metadata. |
| `GET` | `/api/quizzes/<quiz_id>` | Retrieve quiz with questions and 4 options each. |
| `POST` | `/api/quizzes/<quiz_id>/attempts` | Submit answers `{ "responses": [{ "question_id":1,"option_id":4 }] }`; returns score + breakdown. |
| `GET` | `/api/history/quizzes` | Fetch past attempts for History tab. |

### 4.5 Admin Dashboard
Admin access is guarded purely on the client: `admin.html` prompts for a demo password stored in the script. Once authorized, the page unlocks management panels. Backend endpoints do **not** enforce additional authentication beyond any existing user session; this is acceptable for the exhibition scope but must not be reused in production.

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/admin/users` | Paginated user listing with filters. |
| `PUT` | `/api/admin/users/<user_id>` | Update user profile or status. |
| `GET` | `/api/admin/online` | Return count of active sessions. |
| `GET` | `/api/admin/quizzes` | List quiz records for management. |
| `POST` | `/api/admin/quizzes` | Create quiz & 4 options per question. |
| `PUT` | `/api/admin/quizzes/<quiz_id>` | Update quiz. |
| `DELETE` | `/api/admin/quizzes/<quiz_id>` | Remove quiz. |
| `GET` | `/api/admin/analytics` | Summary metrics: total users, new signups, active users, recent quiz attempts, translation usage. |

## 5. Database Schema (Initial Draft)

### 5.1 Tables
| Table | Purpose | Key Columns |
| --- | --- | --- |
| `users` | Core user accounts | `id (PK)`, `email (unique)`, `password_hash`, `firstname`, `lastname`, `student_id`, `year_level`, `gender`, `profile_image_path`, `created_at`, `verified_at` |
| `email_verification_tokens` | Signup verification | `id`, `user_id`, `token`, `expires_at`, `consumed_at` |
| `pending_registrations` | Staged signup data awaiting code confirmation | `email`, `student_id`, `password_hash`, `verification_code`, `expires_at`, `attempts` |
| `password_reset_tokens` | Password reset flow | `id`, `user_id`, `token`, `expires_at`, `consumed_at` |
| `reading_progress` | Last-read state per book | `id`, `user_id`, `book_name`, `page`, `updated_at` |
| `quizzes` | Quiz metadata | `id`, `title`, `description`, `language`, `is_active`, `created_by` |
| `quiz_questions` | Quiz questions | `id`, `quiz_id`, `prompt`, `order_index` |
| `quiz_options` | 4 choices per question | `id`, `question_id`, `text`, `is_correct` |
| `quiz_attempts` | Attempt header | `id`, `quiz_id`, `user_id`, `score`, `started_at`, `completed_at` |
| `quiz_attempt_answers` | Attempt detail | `id`, `attempt_id`, `question_id`, `option_id`, `is_correct` |
| `usage_metrics` | Cached stats for dashboard | `id`, `snapshot_at`, `total_users`, `active_users`, `quiz_attempts_24h`, `translations_24h` |

### 5.2 Relationships & Constraints
- `users.email` unique; cascade delete tokens when user removed.
- `reading_progress` unique constraint on `(user_id, book_name)`.
- `quiz_questions` and `quiz_options` cascade on parent delete.
- Index tokens on `token` for fast lookup.

### 5.3 Sample DDL Snippet (`/db/schema.sql`)
```sql
CREATE TABLE users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  firstname VARCHAR(100),
  lastname VARCHAR(100),
  student_id VARCHAR(50),
  year_level VARCHAR(50),
  gender VARCHAR(20),
  profile_image_path VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  verified_at TIMESTAMP NULL
);
```

## 6. Frontend Interaction Contracts
- Use Fetch with JSON bodies; include `credentials: "include"` to send session cookies.
- On auth-required pages, redirect to login if backend returns HTTP `401`.
- History tab merges `/api/history/reading` and `/api/history/quizzes` responses into a unified timeline.
- Translator UI ensures prompt format (no `*`) and renders audio buttons per language; fallback to backend-generated MP3 if browser `speechSynthesis` unsupported.

## 7. Configuration & Environment
- `.env` Keys:
- `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_SERVER`, `MAIL_PORT`
- `OPENAI_API_KEY`
- `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DB`
- `SECRET_KEY`
- `REGISTRATION_CODE_EXPIRY_MINUTES` (optional, defaults to 15)
- `TTS_PROVIDER` (`web`, `gtts`, `pyttsx3`)
- TLS certificate paths configurable via `.env` to replace hard-coded Windows paths.
- Logging: enable Flask logging + separate audit log for admin changes (`/logs/admin.log`).

## 8. Testing Strategy
- **Unit Tests**: Pytest for auth flows, translation request mocking, quiz scoring.
- **Integration Tests**: Use Flask test client + temporary MySQL schema; ensure email and OpenAI calls mocked.
- **UI Smoke Tests**: Playwright scripts validating login, translation, quiz attempt, admin flow in mobile viewport.
- **Security Note**: Admin password gate is front-end only; testing should confirm the prompt behavior but no backend auth expectations.
- **Performance**: Optional load testing for translation endpoint (limit concurrency via rate limiter).

## 9. Open Questions
- Confirm exact mobile breakpoints from Figma and whether dark mode is required.
- Determine preferred TTS engine for offline Windows deployment.
- Clarify analytics retention policy for `usage_metrics` snapshots.
