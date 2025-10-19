# Task Backlog

## Authentication & User Profile
- [ ] Implement MySQL-backed signup with email verification workflow, reusing `app.py` SMTP setup and persisting verification tokens.
- [ ] Add password reset/change flow gated by email verification, updating relevant `forgot/` pages and API endpoints.
- [ ] Extend profile APIs to support full CRUD on user fields and surface data in `profile/` screens; confirm DB writes succeed.

## Reader Module
- [ ] Keep existing PDF web-view UX while ensuring assets in `reader/books/` load reliably across devices.
- [ ] Persist last-read book and page per user so the History tab can show "Last opened" entries.

## Translation & TTS
- [ ] Wire translation endpoint to OpenAI using mandated prompt (7 target languages, no asterisks) and update `translator_simple/` & `ai-translator/` UIs.
- [ ] Add text-to-speech for each translated language using Python TTS or Web Speech API; expose playback controls alongside translations.
## Quiz System
- [ ] Build REST endpoints for 4-choice quizzes (CRUD) and client logic within `quiz/` for question retrieval, answer submission, and scoring.
- [ ] Persist quiz attempts and scores per user; surface aggregated history under the History tab with filtering.

## Admin Dashboard
- [ ] Expose `/admin` page guarded by front-end password prompt that validates against hard-coded demo credential.
- [ ] Implement user management views: list all members, show online counts, allow profile edits.
- [ ] Build quiz management interface for creating, editing, and deleting questions.
- [ ] Develop dashboard cards summarizing member totals, active users, and recent activity metrics.

## Infrastructure & Ops
- [ ] Produce initial `requirements.txt` and development bootstrap scripts (venv creation, DB migration stubs).
- [ ] Align layout/styles with mobile-first Figma design while keeping desktop parity for testing.
