import json
import logging
import os
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import List, Dict

import requests
from cachetools import cached, TTLCache

logger = logging.getLogger(__name__)

_BASE_DIR = Path(__file__).resolve().parent

# ---------------- 配置区：你可以根据需要修改 ----------------

CITY_NAME = "Guangzhou"
COUNTRY_CODE = "CN"
RECIPIENT_EMAIL = "hema1998@163.com"


def get_env(name: str, default: str | None = None) -> str:
    """读取环境变量，没有就用默认值或抛异常。"""
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Environment variable '{name}' is required but not set.")
    return value


# ---------------- 获取天气、新闻、待办 ----------------

@cached(cache=TTLCache(maxsize=1, ttl=600))
def fetch_weather() -> Dict:
    """
    使用 OpenWeatherMap 获取当前天气信息。
    如果没有配置 OPENWEATHER_API_KEY，则返回本地示例数据。
    结果缓存 10 分钟。
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        logger.info("未配置 OPENWEATHER_API_KEY，使用示例天气数据")
        return {
            "city": CITY_NAME,
            "temp": 26,
            "feels_like": 28,
            "temp_min": 23,
            "temp_max": 30,
            "humidity": 70,
            "description": "多云转晴（示例数据，无真实 API）",
        }

    url = (
        "https://api.openweathermap.org/data/2.5/weather"
        f"?q={CITY_NAME},{COUNTRY_CODE}&appid={api_key}&units=metric&lang=zh_cn"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        main = data.get("main", {})
        weather_list = data.get("weather", [])
        weather_desc = weather_list[0]["description"] if weather_list else "未知"

        return {
            "city": data.get("name", CITY_NAME),
            "temp": main.get("temp"),
            "feels_like": main.get("feels_like"),
            "temp_min": main.get("temp_min"),
            "temp_max": main.get("temp_max"),
            "humidity": main.get("humidity"),
            "description": weather_desc,
        }
    except Exception as exc:
        logger.error("调用 OpenWeatherMap 失败，使用示例天气数据。错误: %s", exc)
        return {
            "city": CITY_NAME,
            "temp": 26,
            "feels_like": 28,
            "temp_min": 23,
            "temp_max": 30,
            "humidity": 70,
            "description": "多云转晴（示例数据，实时天气获取失败）",
        }


def _fetch_reddit_news(subreddit: str, limit: int) -> List[Dict]:
    """Fetch headlines from a Reddit subreddit (free, no API key)."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit * 2}"
    headers = {"User-Agent": "my-api/1.0 daily-brief-agent"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        posts = resp.json()["data"]["children"]
        items = []
        for p in posts:
            data = p["data"]
            if data.get("stickied"):
                continue
            title = data.get("title", "").strip()
            if not title or len(title) < 15:
                continue
            items.append({
                "title": title,
                "source": f"r/{subreddit}",
                "url": f"https://www.reddit.com{data['permalink']}",
            })
            if len(items) >= limit:
                break
        return items
    except Exception as exc:
        logger.warning("Reddit r/%s 获取失败: %s", subreddit, exc)
        return []


def _fetch_rss_feed(feed_url: str, source_name: str, limit: int) -> List[Dict]:
    """Fetch headlines from an RSS feed."""
    import feedparser
    try:
        feed = feedparser.parse(feed_url)
        if feed.bozo:
            logger.warning("RSS %s 解析异常: %s", source_name, feed.bozo_exception)
        items = []
        for entry in feed.entries[:limit]:
            title = entry.get("title", "").strip()
            url = entry.get("link", "")
            if not title or not url:
                continue
            items.append({"title": title, "source": source_name, "url": url})
        return items
    except Exception as exc:
        logger.warning("RSS %s 获取失败: %s", source_name, exc)
        return []


@cached(cache=TTLCache(maxsize=1, ttl=300))
def fetch_news(limit: int = 5) -> List[Dict]:
    """
    从多个免费公开来源聚合新闻头条：
      1. Reddit r/worldnews 热门帖
      2. Reddit r/news 热门帖
      3. NPR 新闻 RSS
      4. The Guardian 国际 RSS
    如果配置了 NEWS_API_KEY，优先使用 NewsAPI。
    结果缓存 5 分钟。
    """
    api_key = os.getenv("NEWS_API_KEY")

    # 优先使用 NewsAPI（如果配置了 key）
    if api_key:
        url = (
            "https://newsapi.org/v2/top-headlines"
            f"?country=cn&pageSize={limit}&apiKey={api_key}"
        )
        try:
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            articles = resp.json().get("articles", [])[:limit]
            return [
                {
                    "title": a.get("title", "").strip(),
                    "source": (a.get("source") or {}).get("name", ""),
                    "url": a.get("url", ""),
                }
                for a in articles
            ]
        except Exception as exc:
            logger.warning("NewsAPI 调用失败，回退到公开来源: %s", exc)

    # 从多个免费公开来源聚合
    all_items: List[Dict] = []

    # Reddit 来源
    all_items.extend(_fetch_reddit_news("worldnews", limit))
    if len(all_items) < limit:
        all_items.extend(_fetch_reddit_news("news", limit - len(all_items)))

    # RSS 来源
    if len(all_items) < limit:
        all_items.extend(_fetch_rss_feed(
            "https://feeds.npr.org/1001/rss.xml", "NPR", limit - len(all_items)
        ))
    if len(all_items) < limit:
        all_items.extend(_fetch_rss_feed(
            "https://www.theguardian.com/world/rss", "The Guardian", limit - len(all_items)
        ))

    if not all_items:
        logger.warning("所有新闻来源均不可用，返回空列表")
        return []

    logger.info("从公开来源聚合了 %d 条新闻", len(all_items))
    return all_items[:limit]


def load_todos(path: str | None = None) -> List[Dict]:
    """
    从本地 JSON 读取待办事项。
    格式示例：
    [
      {"title": "晨跑 20 分钟", "done": false},
      {"title": "查看工作邮件", "done": false}
    ]
    """
    if path is None:
        path = str(_BASE_DIR / "todos.json")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return []
    if isinstance(data, list):
        return data
    return []


# ---------------- 组装邮件内容 ----------------

def build_email_content(
    weather: Dict, news: List[Dict], todos: List[Dict]
) -> tuple[str, str]:
    """返回 (subject, html_body)"""
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"每日简报 - {today} - {weather.get('city', CITY_NAME)}"

    weather_lines = [
        f"{weather.get('city', CITY_NAME)} 今日天气：{weather.get('description', '')}",
        f"当前气温：{weather.get('temp', '?')}℃（体感 {weather.get('feels_like', '?')}℃）",
        f"最高 {weather.get('temp_max', '?')}℃ / 最低 {weather.get('temp_min', '?')}℃",
        f"空气湿度：{weather.get('humidity', '?')}%",
    ]

    news_html = ""
    if news:
        items = []
        for i, n in enumerate(news, start=1):
            title = n.get("title") or "无标题"
            source = n.get("source") or ""
            url = n.get("url") or "#"
            source_text = f"（{source}）" if source else ""
            items.append(
                f"<li>{i}. <a href='{url}'>{title}</a>{source_text}</li>"
            )
        news_html = "<ol>" + "".join(items) + "</ol>"
    else:
        news_html = "<p>暂无新闻数据。</p>"

    todos_html = ""
    if todos:
        li_items = []
        for t in todos:
            title = t.get("title") or "未命名任务"
            done = t.get("done", False)
            status = "✅ 已完成" if done else "⬜ 待完成"
            li_items.append(f"<li>{status} - {title}</li>")
        todos_html = "<ul>" + "".join(li_items) + "</ul>"
    else:
        todos_html = "<p>今天还没有记录待办事项，可以在 todos.json 中添加。</p>"

    html_body = f"""
    <html>
      <body>
        <h2>早安，今日简报</h2>

        <h3>📍 天气</h3>
        <p>{'<br>'.join(weather_lines)}</p>

        <h3>📰 新闻速览</h3>
        {news_html}

        <h3>✅ 今日待办</h3>
        {todos_html}

        <hr>
        <p style="font-size: 12px; color: #888;">
          本邮件由本地 Python 脚本自动生成和发送。
        </p>
      </body>
    </html>
    """
    return subject, html_body


# ---------------- 发送邮件 ----------------

def send_email(subject: str, html_body: str) -> None:
    """
    使用 SMTP 发送邮件。
    需要配置的环境变量：
      SMTP_HOST       如 smtp.163.com
      SMTP_PORT       如 465（SSL）
      SMTP_USER       登录用户名，一般是完整邮箱
      SMTP_PASSWORD   邮箱授权码/应用密码
    """
    smtp_host = get_env("SMTP_HOST", "smtp.163.com")
    smtp_port = int(get_env("SMTP_PORT", "465"))
    smtp_user = get_env("SMTP_USER")
    smtp_password = get_env("SMTP_PASSWORD")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = RECIPIENT_EMAIL

    plain_text = "本邮件包含 HTML 内容，请使用支持 HTML 的邮件客户端查看。"
    part1 = MIMEText(plain_text, "plain", "utf-8")
    part2 = MIMEText(html_body, "html", "utf-8")

    msg.attach(part1)
    msg.attach(part2)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
        server.login(smtp_user, smtp_password)
        server.send_message(msg)


def main() -> None:
    """主流程：获取数据 -> 组装内容 -> 发邮件"""
    weather = fetch_weather()
    news = fetch_news(limit=5)
    todos = load_todos()

    subject, html_body = build_email_content(weather, news, todos)
    send_email(subject, html_body)


if __name__ == "__main__":
    main()
