# Task Backlog

## Authentication & User Profile

* [x] Implement MySQL-backed signup with email verification workflow, reusing `app.py` SMTP setup and persisting verification tokens.
* [x] Add password reset/change flow gated by email verification, updating relevant `forgot/` pages and API endpoints.
* [x] Extend profile APIs to support full CRUD on user fields and surface data in `profile/` screens; confirm DB writes succeed.

---

## Reader Module

* [x] Keep the current structure where the server only serves PDF files and the client opens them locally on the device.
* [x] For each user, store only the book title and the last read timestamp.
* [x] If the user reads the same book again, update the timestamp instead of creating a new record.
* [x] In the History view, display the records sorted by the most recently read time.

### Pending — Requirement #2: PDF Reader & Quiz Flow

* [x] **Course↔Quiz Pairing (docs/TECH_SPEC.md §§4.2, 4.4):** For every module course, fetch its PDF via `/reader/<book_id>` and the matching quiz via `/api/quizzes/<quiz_id>`, ensuring the FE consumes the same metadata that `app.py` exposes so 1 course always routes to 1 quiz.
* [x] **Progress Calculation (shared FE/BE logic):** Reuse `/api/save_progress`, `reading_progress`, and `quiz_attempts` to compute completion % for each course–quiz pair; surface the % in the UI and make sure advancing from Course 1 → Quiz 1 → Course 2 → Quiz 2 bumps the same backend counters.
* [x] **Interactive Reader UI (refer to `course-example.html`):** Build the dual-pane layout where the left column lists modules/courses (sticky) and the right panel renders the PDF + quiz detail, matching the styling/UX patterns from the sample.
* [x] **Prev/Next & Skip Rules:** Implement Next/Prev buttons that disable on the first/last step, treat already-solved quizzes as “Skip” by default, and include a “Reset attempt” control so users can opt back into quizzes instead of skipping.
* [x] **Sequential Flow Enforcement:** Guard navigation so the Next chain always follows Course n → Quiz n order and persists the state server-side, preventing users from jumping ahead without finishing the paired quiz.

---

## Translation & AI Voice Input

### 1. AI Translator  
> Provides smart translation with **usage explanations** included.

- [x] **Translate (Chat):** Translates the input text into 7 target languages **and adds short explanations or usage notes** under each translation.  
- [x] **Translate (Voice):** Converts speech input from the microphone to text (via OpenAI transcription), translates it into 7 target languages, **and appends explanations**.  
- [x] **Speak + Translate:** Records user speech input, performs transcription → translation → adds explanations (optionally plays TTS audio).  
- [x] **Voice Control Fix:** Rewire AI translator buttons so voice flow starts recording before translation and mic stop reuses the original handler without stacking listeners.

---

### 2. Basic Translator  
> Performs **simple translations without explanations**.

- [x] **Translate (Chat):** Translates the input text into 7 target languages only (no extra notes).  
- [x] **Translate + Speak:** Performs translation and plays back the result using TTS (no explanations).  
- [x] **Speak + Translate:** Converts speech input into text and translates it into 7 target languages (no explanations).  

---

## Quiz System

* [x] Build REST endpoints for 4-choice quizzes (CRUD) and client logic within `quiz/` for question retrieval, answer submission, and scoring.
* [x] Persist quiz attempts and scores per user; surface aggregated history under the History tab with filtering.

---

## Admin Dashboard

* [x] Expose `/admin` page guarded by front-end password prompt that validates against hard-coded demo credential.
* [x] Implement user management views: list all members, show online counts, allow profile edits.
* [x] Build quiz management interface for creating, editing, and deleting questions.
* [x] Develop dashboard cards summarizing member totals, active users, and recent activity metrics.
