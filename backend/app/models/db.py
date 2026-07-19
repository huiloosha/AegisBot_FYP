"""
Database access layer for AegisBot.

Uses Python's built-in sqlite3 -- no extra dependency, which suits an FYP
prototype and keeps deployment to a single file on disk (aegisbot.db).

What this module provides:
  - get_db()      : a per-request connection (row access by column name)
  - init_db()     : create tables from schema.sql, then seed the questions table
  - close_db()    : teardown, registered on the Flask app
  - init_app(app) : wire the above into the application factory

The questions table is seeded from rubric.QUESTIONS so the database and the ML
rubric never drift apart -- rubric.py stays the single source of truth for the
20 questions, their categories, response types, and risk directions.
"""
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from flask import current_app, g

# rubric.py lives in ml/src; make it importable the same way predictor.py does.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ML_SRC = _PROJECT_ROOT / "ml" / "src"
if str(_ML_SRC) not in sys.path:
    sys.path.insert(0, str(_ML_SRC))

from rubric import QUESTIONS, CATEGORY_NAMES  # noqa: E402

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# Default DB location: backend/aegisbot.db. Overridable via app config DATABASE.
_DEFAULT_DB = _PROJECT_ROOT / "backend" / "aegisbot.db"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db() -> sqlite3.Connection:
    """Return the connection for the current request, creating it on first use.

    sqlite3.Row makes rows behave like dicts (row["column"]), which keeps the
    data-access code readable. foreign_keys is enabled per connection because
    SQLite defaults it OFF.
    """
    if "db" not in g:
        db_path = current_app.config.get("DATABASE") or str(_DEFAULT_DB)
        g.db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


def close_db(exception=None) -> None:
    """Close the request's connection, if one was opened."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """Create all tables from schema.sql, then seed the questions table.

    Safe to call repeatedly: the schema uses CREATE TABLE IF NOT EXISTS, and
    seeding is idempotent (INSERT OR IGNORE keyed on the unique question_code).
    """
    db = get_db()
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        db.executescript(f.read())
    _seed_questions(db)
    db.commit()


def _seed_questions(db: sqlite3.Connection) -> None:
    """Populate the questions lookup table from rubric.QUESTIONS.

    display_order follows the order questions appear in rubric.py. INSERT OR
    IGNORE means re-running never duplicates or overwrites -- if you later change
    a question's text in rubric.py and want it reflected, clear the row (or the
    db) and re-seed.
    """
    rows = []
    for order, q in enumerate(QUESTIONS, start=1):
        rows.append((
            q["code"],
            q["text"],
            q.get("evidence", ""),
            CATEGORY_NAMES.get(q["category"], q["category"]),
            q["response_type"],
            q["risk_direction"],
            order,
        ))
    db.executemany(
        """
        INSERT OR IGNORE INTO questions
            (question_code, question_text, explanation, category,
             response_type, risk_direction, display_order)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def question_id_map(db: sqlite3.Connection) -> dict:
    """Return {question_code: question_id} for fast FK lookups when saving."""
    cur = db.execute("SELECT question_id, question_code FROM questions")
    return {r["question_code"]: r["question_id"] for r in cur.fetchall()}


def init_app(app) -> None:
    """Register DB teardown and an init-db CLI command on the Flask app.

    After create_app(), run `flask --app run init-db` once to create the file,
    or call ensure_db() at startup (see create_app).
    """
    app.teardown_appcontext(close_db)

    @app.cli.command("init-db")
    def init_db_command():  # pragma: no cover - CLI convenience
        init_db()
        print("Initialized the database and seeded questions.")


def ensure_db(app) -> None:
    """Create + seed the database at startup if it doesn't exist yet.

    Called from the application factory so a fresh checkout works with just
    `python run.py`, without a separate manual init step.
    """
    with app.app_context():
        db_path = Path(app.config.get("DATABASE") or str(_DEFAULT_DB))
        needs_init = not db_path.exists()
        # Even if the file exists, init_db() is safe (idempotent), so we call it
        # to guarantee the schema/seed are present.
        init_db()
        if needs_init:
            app.logger.info("Created new AegisBot database at %s", db_path)
