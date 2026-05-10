import json
import logging
import random
import re
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, g, jsonify, redirect, render_template, request, url_for
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from dotenv import load_dotenv

load_dotenv()

from daily_digest import (
    build_email_content,
    fetch_news,
    fetch_weather,
    load_todos,
    send_email,
)
from db import close_db, get_db, init_db, row_to_dict

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

# --- App setup ---
app = Flask(__name__)
CORS(app)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)

app.teardown_appcontext(close_db)
init_db()

# --- Validation ---
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# --- Template context ---

@app.context_processor
def inject_now():
    return {"current_year": datetime.now().year}


# --- Routes ---

@app.route("/", methods=["GET"])
def home():
    db = get_db()
    posts = db.execute(
        "SELECT id, title, slug, excerpt, created_at FROM posts ORDER BY created_at DESC"
    ).fetchall()

    portfolio_path = Path(__file__).resolve().parent / "portfolio.json"
    portfolio = {}
    if portfolio_path.exists():
        with open(portfolio_path, "r", encoding="utf-8") as f:
            try:
                portfolio = json.load(f)
            except json.JSONDecodeError:
                pass

    return render_template(
        "home.html",
        posts=[row_to_dict(p) for p in posts],
        portfolio=portfolio,
    )


@app.route("/api", methods=["GET"])
def api_info():
    return jsonify({
        "message": "my-api",
        "endpoints": ["/api", "/users", "/health", "/daily-brief", "/send-daily-brief"],
    })


@app.route("/blog/<slug>", methods=["GET"])
def blog_post(slug):
    db = get_db()
    post = db.execute(
        "SELECT id, title, slug, content, excerpt, created_at, updated_at FROM posts WHERE slug = ?",
        (slug,)
    ).fetchone()
    if post is None:
        abort(404)
    return render_template("post.html", post=row_to_dict(post))


@app.route("/admin", methods=["GET", "POST"])
@limiter.exempt
def admin():
    error = None
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        content = (request.form.get("content") or "").strip()
        excerpt = (request.form.get("excerpt") or "").strip()
        if not title or not content:
            error = "Title and content are required."
        else:
            # Generate slug: attempt English transliteration, fall back to date-based
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
            if not slug:
                slug = datetime.now().strftime("post-%Y%m%d-%H%M%S")

            db = get_db()
            try:
                db.execute(
                    "INSERT INTO posts (title, slug, content, excerpt) VALUES (?, ?, ?, ?)",
                    (title, slug, content, excerpt or None)
                )
                db.commit()
            except sqlite3.IntegrityError:
                slug = f"{slug}-{random.randint(1000, 9999)}"
                db.execute(
                    "INSERT INTO posts (title, slug, content, excerpt) VALUES (?, ?, ?, ?)",
                    (title, slug, content, excerpt or None)
                )
                db.commit()

            logger.info("Post created: slug=%s", slug)
            return redirect(url_for("blog_post", slug=slug))
    return render_template("admin.html", error=error)


@app.route("/health", methods=["GET"])
def health():
    try:
        db = get_db()
        db.execute("SELECT 1")
        db_ok = True
    except Exception:
        logger.exception("Database health check failed")
        db_ok = False

    return jsonify({
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
    }), 200 if db_ok else 503


@app.route("/users", methods=["GET"])
def get_users():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, email, created_at FROM users ORDER BY id"
    ).fetchall()
    users = [row_to_dict(r) for r in rows]
    return jsonify({"users": users, "count": len(users)}), 200


@app.route("/users", methods=["POST"])
def create_user():
    if not request.is_json:
        return jsonify({
            "error": "Bad request",
            "message": "Content-Type must be application/json",
        }), 400

    data = request.get_json()
    if not data:
        return jsonify({
            "error": "Bad request",
            "message": "Request body cannot be empty",
        }), 400

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()

    if not name:
        return jsonify({
            "error": "Validation error",
            "message": 'Field "name" is required',
        }), 400
    if not email:
        return jsonify({
            "error": "Validation error",
            "message": 'Field "email" is required',
        }), 400
    if not EMAIL_RE.match(email):
        return jsonify({
            "error": "Validation error",
            "message": "Invalid email format",
        }), 400

    try:
        db = get_db()
        cursor = db.execute(
            "INSERT INTO users (name, email) VALUES (?, ?)", (name, email)
        )
        db.commit()
        user_id = cursor.lastrowid
        row = db.execute(
            "SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        logger.info("User created: id=%s email=%s", user_id, email)
        return jsonify({
            "message": "User created successfully",
            "user": row_to_dict(row),
        }), 201
    except sqlite3.IntegrityError:
        return jsonify({
            "error": "Conflict",
            "message": f'User with email "{email}" already exists',
        }), 409


@app.route("/daily-brief", methods=["GET"])
def daily_brief():
    weather = fetch_weather()
    news = fetch_news(limit=5)
    todos = load_todos()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    return render_template(
        "daily_brief.html", weather=weather, news=news, todos=todos, now_str=now_str
    )


@app.route("/send-daily-brief", methods=["POST"])
@limiter.limit("5 per hour")
def send_daily_brief():
    weather = fetch_weather()
    news = fetch_news(limit=5)
    todos = load_todos()

    subject, html_body = build_email_content(weather, news, todos)

    def _send() -> None:
        try:
            send_email(subject, html_body)
            logger.info("Daily brief email sent to %s", subject)
        except Exception:
            logger.exception("Failed to send daily brief email")

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()

    return jsonify({
        "message": "简报已发送到邮箱，请查收。",
        "email": "hema1998@163.com",
    }), 200


# --- Error handlers ---

@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/users") or request.path.startswith("/health") or request.path.startswith("/api"):
        return jsonify({
            "error": "Not found",
            "message": "The requested resource was not found",
        }), 404
    return render_template("404.html"), 404


@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "error": "Method not allowed",
        "message": "The HTTP method is not allowed for this endpoint",
    }), 405


@app.errorhandler(429)
def ratelimit_handler(error):
    return jsonify({
        "error": "Too many requests",
        "message": "Rate limit exceeded. Please try again later.",
    }), 429


@app.errorhandler(500)
def internal_error(error):
    logger.exception("Internal server error")
    return jsonify({
        "error": "Internal server error",
        "message": "An unexpected error occurred",
    }), 500


# --- Entry point ---

if __name__ == "__main__":
    from waitress import serve
    logger.info("Starting server on 0.0.0.0:5000")
    serve(app, host="0.0.0.0", port=5000, threads=4)
