"""
Entry point for the AegisBot backend dev server.

Run from docs/backend/ with:
    python run.py

For production you would NOT use this (Flask's dev server is single-threaded
and not hardened). Instead use a WSGI server, e.g.:
    gunicorn "app:create_app()"
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # host=127.0.0.1 keeps it local; use 0.0.0.0 to expose on your network.
    # debug=True gives auto-reload + tracebacks. Turn OFF for production.
    app.run(host="127.0.0.1", port=5000, debug=True)