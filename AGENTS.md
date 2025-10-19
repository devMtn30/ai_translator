# Repository Guidelines

## Project Structure & Module Organization
- `app.py` hosts the Flask application, REST endpoints, and external integrations (MySQL, OpenAI, SMTP). Keep backend logic here or in future `/app` submodules; extract shared helpers into dedicated packages when refactoring.
- Feature-specific static assets live in sibling folders (`login/`, `main/`, `reader/`, `quiz/`, `profile/`, `forgot/`, `translator_simple/`), each bundling its `*.html`, `*.css`, and `*.js`. Shared visuals live under `assets/`, while reader PDFs sit in `reader/books/`.
- Flask serves files from the `www/` directory; when you touch front-end assets, ensure the deployment bundle copies fresh builds into `www` so `index.html` and feature routes resolve correctly.

## Build, Test, and Development Commands
- `python -m venv .venv && .\.venv\Scripts\activate`: create and enter a Windows virtual environment before installing packages.
- `pip install -r requirements.txt`: install Flask, Flask-Bcrypt, Flask-Mail, python-dotenv, mysql-connector-python, openai, and any new dependencies (remember to update the file).
- `python app.py`: launch the TLS-enabled development server; override `MAIL_*`, database, and certificate paths through environment variables for local runs.
- `set FLASK_ENV=development` (PowerShell: `$env:FLASK_ENV = "development"`): enable debug logging and auto-reload while iterating.

## Coding Style & Naming Conventions
- Python: follow PEP 8, 4-space indents, lowercase_with_underscores for functions/modules, CamelCase for classes. Keep endpoint handlers lean and move repeated logic into helpers.
- JavaScript: use ES6 features, camelCase functions, SCREAMING_CASE constants. Scope DOM selectors to the feature directory to avoid conflicts.
- CSS: prefer BEM-style selectors (`.menu__item--active`) and keep component styles alongside their HTML/JS counterparts.

## Testing Guidelines
- No automated suite exists yet; add `pytest` cases under `tests/` mirroring the feature (`tests/test_auth.py`, etc.). Include fixtures for Flask’s `test_client`.
- Mock external services (MySQL, SMTP, OpenAI) with `pytest-mock` or `unittest.mock` so tests remain self-contained.
- Smoke-test UI flows with Playwright scripts in `tests/ui/`; target elements via `data-testid` attributes for stability.

## Commit & Pull Request Guidelines
- Use imperative, concise commit subjects (`Add email verification`) and include context in the body when backend and UI both change.
- Keep commits scoped to a single concern and run `python app.py` (or relevant tests) before pushing.
- Pull requests must summarize changes, list verification steps, link related issues, and attach screenshots or clips for UI updates. Call out schema or environment-variable changes early.

## Configuration & Secrets
- Store secrets in `.env` (e.g., `MAIL_USERNAME`, `MAIL_PASSWORD`, `OPENAI_API_KEY`) and provide sanitized examples in `.env.example`; never commit live credentials.
- Document database schema or config changes in `README.md` so deployment environments stay synchronized.
