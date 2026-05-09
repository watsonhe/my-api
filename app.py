import logging
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, g, jsonify, render_template_string, request
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

# --- SQLite setup ---
DB_PATH = Path(__file__).resolve().parent / "users.db"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exception=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    with app.app_context():
        db = sqlite3.connect(str(DB_PATH))
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()
        db.close()


app.teardown_appcontext(close_db)
init_db()

# --- Validation ---
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# --- Helper ---
def row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


# --- Routes ---

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "Welcome to my-api",
        "endpoints": ["/users", "/daily-brief", "/send-daily-brief", "/health"],
    })


@app.route("/health", methods=["GET"])
def health():
    try:
        db = sqlite3.connect(str(DB_PATH))
        db.execute("SELECT 1")
        db.close()
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

    template = """
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>今日简报预览</title>
        <style>
          :root {
            --bg: #f0f2f5;
            --surface: rgba(255,255,255,0.72);
            --surface-hover: rgba(255,255,255,0.88);
            --text: #1a1a2e;
            --text-secondary: #6b7280;
            --border: rgba(255,255,255,0.5);
            --accent: #6366f1;
            --accent-2: #8b5cf6;
            --accent-3: #a78bfa;
            --shadow: 0 4px 24px rgba(0,0,0,0.06);
            --shadow-lg: 0 12px 40px rgba(0,0,0,0.10);
            --radius: 16px;
            --radius-sm: 10px;
            --gradient-bg: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          }

          @media (prefers-color-scheme: dark) {
            :root {
              --bg: #0f0f1a;
              --surface: rgba(30,30,50,0.70);
              --surface-hover: rgba(40,40,65,0.85);
              --text: #e5e7eb;
              --text-secondary: #9ca3af;
              --border: rgba(255,255,255,0.08);
              --shadow: 0 4px 24px rgba(0,0,0,0.30);
              --shadow-lg: 0 12px 40px rgba(0,0,0,0.45);
            }
          }

          * { box-sizing: border-box; margin: 0; padding: 0; }

          body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans SC", sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            position: relative;
            overflow-x: hidden;
          }

          /* Animated gradient orbs */
          .bg-orb {
            position: fixed;
            border-radius: 50%;
            filter: blur(80px);
            opacity: 0.50;
            pointer-events: none;
            z-index: 0;
          }
          .bg-orb-1 {
            width: 500px; height: 500px;
            background: #818cf8;
            top: -200px; right: -150px;
            animation: float1 18s ease-in-out infinite;
          }
          .bg-orb-2 {
            width: 400px; height: 400px;
            background: #a78bfa;
            bottom: -150px; left: -100px;
            animation: float2 22s ease-in-out infinite;
          }
          .bg-orb-3 {
            width: 300px; height: 300px;
            background: #c4b5fd;
            top: 40%; left: 50%;
            animation: float3 20s ease-in-out infinite;
          }

          @keyframes float1 {
            0%, 100% { transform: translate(0, 0) scale(1); }
            33% { transform: translate(-60px, 40px) scale(1.08); }
            66% { transform: translate(30px, -30px) scale(0.94); }
          }
          @keyframes float2 {
            0%, 100% { transform: translate(0, 0) scale(1); }
            33% { transform: translate(50px, -30px) scale(1.06); }
            66% { transform: translate(-40px, 20px) scale(0.92); }
          }
          @keyframes float3 {
            0%, 100% { transform: translate(0, 0) scale(1); }
            50% { transform: translate(-30px, 40px) scale(1.10); }
          }

          /* Fade-in animation for cards */
          @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(24px); }
            to { opacity: 1; transform: translateY(0); }
          }

          .container {
            position: relative;
            z-index: 1;
            max-width: 720px;
            margin: 0 auto;
            padding: 40px 20px 60px;
          }

          /* Header */
          .header {
            text-align: center;
            margin-bottom: 32px;
          }
          .header h1 {
            font-size: 32px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #6366f1, #a78bfa, #6366f1);
            background-size: 200% 200%;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            animation: gradientShift 4s ease-in-out infinite;
            margin-bottom: 10px;
          }
          @keyframes gradientShift {
            0%, 100% { background-position: 0% 50%; }
            50% { background-position: 100% 50%; }
          }

          .meta-bar {
            display: inline-flex;
            align-items: center;
            gap: 16px;
            background: var(--surface);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--border);
            border-radius: 999px;
            padding: 8px 20px;
            font-size: 13px;
            color: var(--text-secondary);
            box-shadow: var(--shadow);
          }
          .meta-bar .dot {
            width: 6px; height: 6px;
            border-radius: 50%;
            background: #22c55e;
            animation: pulse 2s ease-in-out infinite;
          }
          @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
          }

          /* Sections */
          .section {
            background: var(--surface);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: var(--shadow);
            animation: fadeInUp 0.5s ease-out both;
            transition: box-shadow 0.3s ease, transform 0.3s ease;
          }
          .section:hover {
            box-shadow: var(--shadow-lg);
            transform: translateY(-2px);
          }
          .section:nth-child(2) { animation-delay: 0.05s; }
          .section:nth-child(3) { animation-delay: 0.15s; }
          .section:nth-child(4) { animation-delay: 0.25s; }

          .section-header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 18px;
          }
          .section-header .icon {
            width: 36px; height: 36px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
          }
          .icon-weather { background: rgba(251,191,36,0.15); }
          .icon-news { background: rgba(59,130,246,0.15); }
          .icon-todos { background: rgba(34,197,94,0.15); }

          .section-header h2 {
            font-size: 17px;
            font-weight: 700;
            color: var(--text);
          }

          /* Weather */
          .weather-main {
            display: flex;
            align-items: center;
            gap: 24px;
            margin-bottom: 20px;
          }
          .weather-temp {
            font-size: 56px;
            font-weight: 800;
            line-height: 1;
            letter-spacing: -2px;
            background: linear-gradient(180deg, var(--text) 0%, var(--text-secondary) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
          }
          .weather-desc {
            font-size: 15px;
            color: var(--text-secondary);
          }
          .weather-details {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
          }
          .weather-stat {
            background: rgba(128,128,128,0.06);
            border-radius: var(--radius-sm);
            padding: 12px;
            text-align: center;
          }
          .weather-stat .value {
            font-size: 18px;
            font-weight: 700;
          }
          .weather-stat .label {
            font-size: 11px;
            color: var(--text-secondary);
            margin-top: 2px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
          }

          /* News */
          .news-item {
            display: block;
            padding: 14px 16px;
            border-radius: var(--radius-sm);
            text-decoration: none;
            color: var(--text);
            transition: background 0.2s ease, transform 0.2s ease;
            margin-bottom: 4px;
          }
          .news-item:hover {
            background: rgba(99,102,241,0.08);
            transform: translateX(4px);
          }
          .news-item .news-title {
            font-size: 14px;
            font-weight: 600;
            line-height: 1.5;
            margin-bottom: 4px;
          }
          .news-item .news-source {
            font-size: 12px;
            color: var(--text-secondary);
          }
          .news-empty {
            text-align: center;
            color: var(--text-secondary);
            padding: 20px;
            font-size: 14px;
          }

          /* Todos */
          .todo-item {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 14px;
            border-radius: var(--radius-sm);
            transition: background 0.2s ease;
          }
          .todo-item:hover {
            background: rgba(128,128,128,0.05);
          }
          .todo-check {
            width: 22px; height: 22px;
            border-radius: 6px;
            border: 2px solid #d1d5db;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            transition: all 0.2s ease;
            font-size: 12px;
          }
          .todo-item.done .todo-check {
            background: #22c55e;
            border-color: #22c55e;
            color: #fff;
          }
          .todo-item.done .todo-title {
            text-decoration: line-through;
            color: var(--text-secondary);
          }
          .todo-title {
            font-size: 14px;
            transition: color 0.2s ease;
          }

          /* Button */
          .btn-row {
            display: flex;
            justify-content: center;
            margin-top: 28px;
            animation: fadeInUp 0.5s ease-out 0.35s both;
          }
          .btn-send {
            position: relative;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            color: #fff;
            border: none;
            border-radius: 999px;
            padding: 14px 48px;
            font-size: 16px;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 4px 20px rgba(99,102,241,0.35);
            transition: all 0.3s ease;
            letter-spacing: 1px;
            overflow: hidden;
          }
          .btn-send::after {
            content: '';
            position: absolute;
            inset: 0;
            background: linear-gradient(135deg, #8b5cf6, #6366f1);
            opacity: 0;
            transition: opacity 0.3s ease;
          }
          .btn-send:hover {
            transform: translateY(-2px) scale(1.03);
            box-shadow: 0 8px 32px rgba(99,102,241,0.50);
          }
          .btn-send:hover::after { opacity: 1; }
          .btn-send span {
            position: relative;
            z-index: 1;
          }
          .btn-send:active {
            transform: scale(0.97);
          }

          /* Footer */
          .footer {
            text-align: center;
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 32px;
            opacity: 0.7;
          }

          /* Responsive */
          @media (max-width: 640px) {
            .container { padding: 20px 14px 40px; }
            .header h1 { font-size: 26px; }
            .weather-temp { font-size: 42px; }
            .weather-details { grid-template-columns: repeat(3, 1fr); gap: 8px; }
            .weather-stat { padding: 10px 6px; }
            .weather-stat .value { font-size: 15px; }
            .section { padding: 18px; }
            .btn-send { padding: 12px 36px; font-size: 15px; }
          }
        </style>
      </head>
      <body>
        <div class="bg-orb bg-orb-1"></div>
        <div class="bg-orb bg-orb-2"></div>
        <div class="bg-orb bg-orb-3"></div>

        <div class="container">
          <div class="header">
            <h1>今日简报预览</h1>
            <div class="meta-bar">
              <span>📍 {{ weather.city }}</span>
              <span class="dot"></span>
              <span>🕐 {{ now_str }}</span>
            </div>
          </div>

          <!-- Weather -->
          <div class="section">
            <div class="section-header">
              <div class="icon icon-weather">☀️</div>
              <h2>天气</h2>
            </div>
            <div class="weather-main">
              <div class="weather-temp">{{ weather.temp }}°</div>
              <div class="weather-desc">
                <div>{{ weather.description }}</div>
                <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;">
                  体感 {{ weather.feels_like }}℃
                </div>
              </div>
            </div>
            <div class="weather-details">
              <div class="weather-stat">
                <div class="value">{{ weather.temp_max }}°</div>
                <div class="label">最高</div>
              </div>
              <div class="weather-stat">
                <div class="value">{{ weather.temp_min }}°</div>
                <div class="label">最低</div>
              </div>
              <div class="weather-stat">
                <div class="value">{{ weather.humidity }}%</div>
                <div class="label">湿度</div>
              </div>
            </div>
          </div>

          <!-- News -->
          <div class="section">
            <div class="section-header">
              <div class="icon icon-news">📰</div>
              <h2>新闻速览</h2>
            </div>
            {% if news %}
              {% for item in news %}
                <a href="{{ item.url }}" target="_blank" class="news-item" rel="noopener">
                  <div class="news-title">{{ item.title }}</div>
                  {% if item.source %}
                    <div class="news-source">{{ item.source }}</div>
                  {% endif %}
                </a>
              {% endfor %}
            {% else %}
              <div class="news-empty">暂无新闻数据。</div>
            {% endif %}
          </div>

          <!-- Todos -->
          <div class="section">
            <div class="section-header">
              <div class="icon icon-todos">✅</div>
              <h2>今日待办</h2>
            </div>
            {% if todos %}
              {% for t in todos %}
                <div class="todo-item{% if t.done %} done{% endif %}">
                  <div class="todo-check">{% if t.done %}✓{% endif %}</div>
                  <div class="todo-title">{{ t.title }}</div>
                </div>
              {% endfor %}
            {% else %}
              <div class="news-empty">今天还没有记录待办事项，可以在 todos.json 中添加。</div>
            {% endif %}
          </div>

          <!-- Send button -->
          <form method="post" action="/send-daily-brief">
            <div class="btn-row">
              <button type="submit" class="btn-send"><span>📬 发送到邮箱</span></button>
            </div>
          </form>

          <div class="footer">
            由本地 Python 脚本自动生成
          </div>
        </div>
      </body>
    </html>
    """

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    return render_template_string(
        template, weather=weather, news=news, todos=todos, now_str=now_str
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
    return jsonify({
        "error": "Not found",
        "message": "The requested resource was not found",
    }), 404


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
