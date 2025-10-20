# Task Backlog

## Authentication & User Profile

* [x] Implement MySQL-backed signup with email verification workflow, reusing `app.py` SMTP setup and persisting verification tokens.
* [x] Add password reset/change flow gated by email verification, updating relevant `forgot/` pages and API endpoints.
* [x] Extend profile APIs to support full CRUD on user fields and surface data in `profile/` screens; confirm DB writes succeed.

---

## Reader Module

* [ ] Keep the current structure where the server only serves PDF files and the client opens them locally on the device.
* [ ] For each user, store only the book title and the last read timestamp.
* [ ] If the user reads the same book again, update the timestamp instead of creating a new record.
* [ ] In the History view, display the records sorted by the most recently read time.

---

Translation & AI Voice Input

1. AI Translator  
- [ ] Translate (Chat): Translates the input text into 7 target languages.
- [ ] Translate (Voice): Captures the user’s speech through the microphone, sends the audio file to the server, converts it to text using OpenAI’s transcription model, and translates it into 7 target languages.
→ Both modes use the same translation prompt; the only difference is the input type (text vs. voice).

2. Basic Translation  
- [ ] Translate (Chat): Translates the input text into 7 target languages and adds a short explanation or usage note under each translation.
- [ ] Translate + Speak: Performs the same translation and explanation, then plays the TTS audio of the translated result.
- [ ] Speak + Translate: Records the user’s speech input, converts it to text on the server, and returns translated output with explanations.

---

## Quiz System

* [ ] Build REST endpoints for 4-choice quizzes (CRUD) and client logic within `quiz/` for question retrieval, answer submission, and scoring.
* [ ] Persist quiz attempts and scores per user; surface aggregated history under the History tab with filtering.

---

## Admin Dashboard

* [ ] Expose `/admin` page guarded by front-end password prompt that validates against hard-coded demo credential.
* [ ] Implement user management views: list all members, show online counts, allow profile edits.
* [ ] Build quiz management interface for creating, editing, and deleting questions.
* [ ] Develop dashboard cards summarizing member totals, active users, and recent activity metrics.

---

## Infrastructure & Ops

* [ ] Produce initial `requirements.txt` and development bootstrap scripts (venv creation, DB migration stubs).
* [ ] Align layout/styles with mobile-first Figma design while keeping desktop parity for testing.
