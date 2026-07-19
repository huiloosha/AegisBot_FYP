"""
AegisBot backend — application factory.

We build the Flask app inside a function (create_app) instead of at module
top level. This is the "application factory" pattern. Benefits:
  - No global app object, so tests can spin up a fresh app per test.
  - Configuration can be passed in (dev vs. test vs. prod).
  - Blueprints (route groups) are registered in one clear place.

Run it via run.py, which just calls create_app() and app.run().
"""
from pathlib import Path

from flask import Flask, send_from_directory
from flask_cors import CORS


def create_app(config: dict | None = None) -> Flask:
    project_root = Path(__file__).resolve().parents[2]
    frontend_dir = project_root / "frontend"

    app = Flask(
        __name__,
        static_folder=str(frontend_dir),
        static_url_path="",
    )

    # Default config. Override by passing a dict (e.g. in tests).
    app.config.update(
        JSON_SORT_KEYS=False,   # keep our response key order as-is
        # SQLite database file. Override in tests to point at a temp file or
        # ":memory:" so tests never touch the real data.
        DATABASE=None,          # None -> db.py falls back to backend/aegisbot.db
        # Origins the browser is allowed to call this API from. A browser blocks
        # cross-origin requests by default; CORS response headers tell it which
        # frontend origins are trusted. We list local dev servers explicitly
        # rather than using "*", so we don't expose the API to any website.
        CORS_ORIGINS=[
            "http://localhost:3000",   # React / Next.js default
            "http://127.0.0.1:3000",
            "http://localhost:5173",   # Vite default
            "http://127.0.0.1:5173",
            "http://localhost:5500",
            "http://127.0.0.1:5500",
        ],
    )
    if config:
        app.config.update(config)

    # --- Enable CORS ---
    # Applied only to /api/* routes. When you deploy, add your real frontend
    # domain to CORS_ORIGINS (or override it via the config argument).
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    # --- Register blueprints (groups of routes) ---
    # Each feature area lives in its own module under app/routes/ and exposes
    # a Blueprint. We import here (inside the factory) to avoid circular imports.
    from app.routes.health import health_bp
    app.register_blueprint(health_bp)

    from app.routes.predict import predict_bp
    app.register_blueprint(predict_bp)

    from app.routes.assessments import assessments_bp
    app.register_blueprint(assessments_bp)

    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)

    @app.get("/")
    def landing_page():
        return send_from_directory(frontend_dir, "landing.html")


    @app.get("/<path:filename>")
    def frontend_file(filename: str):
        return send_from_directory(frontend_dir, filename)

    # --- Database ---
    # Register teardown + the `init-db` CLI command, then make sure the SQLite
    # file exists and the questions table is seeded, so a fresh checkout works
    # with just `python run.py`.
    from app.models import db as database
    database.init_app(app)
    database.ensure_db(app)

    return app