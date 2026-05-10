"""Translation dictionaries for en / zh."""

T = {
    "en": {
        "site_name": "Crimson Studio",
        "nav_blog": "Blog",
        "nav_brief": "Daily Brief",
        "nav_admin": "Admin",
        "hero_eyebrow": "A personal journal",
        "hero_title": "Thoughts, notes,<br><span class=\"text-accent\">observations.</span>",
        "hero_subtitle": "A brutalist editorial space for ideas that deserve room to breathe. No distractions, no algorithms — just words on a dark canvas.",
        "section_about": "About",
        "section_projects": "Projects",
        "section_currently": "Currently",
        "section_writings": "Writings",
        "currently_learning": "Learning",
        "currently_building": "Building",
        "currently_reading": "Reading",
        "post_back": "← Back to journal",
        "post_updated": "Last updated",
        "post_empty": "No posts yet. The ink is still drying.",
        "post_empty_cta": "Write the first post →",
        "admin_title": "New Post",
        "admin_subtitle": "Compose in Markdown. Headings, lists, links, and code are all supported.",
        "admin_label_title": "Title",
        "admin_label_excerpt": "Excerpt",
        "admin_label_excerpt_hint": "optional short description",
        "admin_label_content": "Content",
        "admin_btn_publish": "Publish",
        "admin_error_required": "Title and content are required.",
        "brief_eyebrow": "DAILY BRIEF",
        "brief_title": "Your morning <span class=\"text-accent\">pulse.</span>",
        "brief_weather": "Weather",
        "brief_headlines": "Headlines",
        "brief_tasks": "Tasks",
        "brief_feels_like": "Feels like",
        "brief_high": "High",
        "brief_low": "Low",
        "brief_humidity": "Humidity",
        "brief_send": "Send to Email →",
        "brief_empty_news": "No headlines available right now.",
        "brief_empty_todos": "No tasks yet. Add some to todos.json",
        "e404_code": "404",
        "e404_title": "Page not found",
        "e404_text": "This page does not exist.<br>Perhaps it never did.",
        "e404_home": "Return Home →",
        "cta_text": "Got something to say?",
        "cta_link": "Get in touch →",
        "footer_crafted": "Crafted with",
        "footer_brand": "Crimson Studio",
        "lang_toggle": "中文",
        "lang_toggle_href": "?lang=zh",
    },
    "zh": {
        "site_name": "深红工作室",
        "nav_blog": "博客",
        "nav_brief": "每日简报",
        "nav_admin": "管理",
        "hero_eyebrow": "个人日志",
        "hero_title": "思考、笔记、<br><span class=\"text-accent\">观察。</span>",
        "hero_subtitle": "一个属于思想的野兽派编辑空间。没有干扰，没有算法 — 只有黑色画布上的文字。",
        "section_about": "关于",
        "section_projects": "项目",
        "section_currently": "当前动态",
        "section_writings": "文章",
        "currently_learning": "正在学习",
        "currently_building": "正在构建",
        "currently_reading": "正在阅读",
        "post_back": "← 返回日志",
        "post_updated": "最近更新",
        "post_empty": "暂无文章，笔墨未干。",
        "post_empty_cta": "撰写第一篇文章 →",
        "admin_title": "新建文章",
        "admin_subtitle": "使用 Markdown 格式编写。支持标题、列表、链接和代码块。",
        "admin_label_title": "标题",
        "admin_label_excerpt": "摘要",
        "admin_label_excerpt_hint": "可选简短描述",
        "admin_label_content": "内容",
        "admin_btn_publish": "发布",
        "admin_error_required": "标题和内容不能为空。",
        "brief_eyebrow": "每日简报",
        "brief_title": "你的清晨 <span class=\"text-accent\">脉搏。</span>",
        "brief_weather": "天气",
        "brief_headlines": "新闻头条",
        "brief_tasks": "待办事项",
        "brief_feels_like": "体感温度",
        "brief_high": "最高",
        "brief_low": "最低",
        "brief_humidity": "湿度",
        "brief_send": "发送到邮箱 →",
        "brief_empty_news": "暂无新闻数据。",
        "brief_empty_todos": "暂无待办事项，请在 todos.json 中添加。",
        "e404_code": "404",
        "e404_title": "页面未找到",
        "e404_text": "此页面不存在。<br>或许它从未存在过。",
        "e404_home": "返回首页 →",
        "cta_text": "有话想说？",
        "cta_link": "联系我 →",
        "footer_crafted": "用心打造于",
        "footer_brand": "深红工作室",
        "lang_toggle": "English",
        "lang_toggle_href": "?lang=en",
    },
}


def detect_locale(request) -> str:
    """Return 'zh' or 'en' based on query param or Accept-Language header."""
    qp = request.args.get("lang", "").lower()
    if qp in ("zh", "zh-cn", "zh-tw", "zh-hk"):
        return "zh"
    if qp == "en":
        return "en"

    header = request.headers.get("Accept-Language", "")
    if "zh" in header.lower():
        return "zh"
    return "en"


def t(key: str, locale: str = "en") -> str:
    """Look up translation, falling back to 'en' if key is missing in locale."""
    table = T.get(locale, T["en"])
    return table.get(key, T["en"].get(key, key))
