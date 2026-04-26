"""
Arsenal & Barcelona Daily News → LINE Flex Message
- แปลภาษาไทยด้วย Google Translate (ฟรี)
- กรองเฉพาะฟุตบอลชายเท่านั้น
- รันผ่าน GitHub Actions ทุกวัน 8 โมงเช้า (ไทย)
"""

import feedparser
import requests
import os
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser
from deep_translator import GoogleTranslator

# ============================================================
# Config
# ============================================================
LINE_TOKEN   = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]

TH_TZ = timezone(timedelta(hours=7))

TH_MONTHS = [
    "", "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]

TEAMS = {
    "arsenal": {
        "name": "Arsenal",
        "header_color": "#CC0000",
        "badge_color": "#FF3333",
        "light_color": "#FFE5E5",
        "emoji": "🔴",
        "keywords": [
            "arsenal", "gunners", "emirates", "arteta",
            "saka", "odegaard", "havertz", "white", "saliba",
            "martinelli", "trossard", "rice", "jesus", "zinchenko",
        ],
    },
    "barcelona": {
        "name": "Barcelona",
        "header_color": "#003780",
        "badge_color": "#0057B8",
        "light_color": "#E5EEFF",
        "emoji": "🔵",
        "keywords": [
            "barcelona", "barça", "barca", "blaugrana",
            "nou camp", "camp nou", "flick",
            "lewandowski", "yamal", "pedri", "gavi",
            "raphinha", "dani olmo", "kounde", "araujo",
        ],
    },
}

WOMENS_KEYWORDS = [
    "women", "women's", "womens", "wsl", "nwsl", "fa wsl",
    "lionesses", "ladies", "female", "girls", "femeni", "féminin",
    "arsenal women", "barcelona women", "barça women",
    "world cup women", "euro women", "uwcl",
]

RSS_FEEDS = [
    {"name": "BBC Sport",   "url": "https://feeds.bbci.co.uk/sport/football/rss.xml"},
    {"name": "Sky Sports",  "url": "https://www.skysports.com/rss/12040"},
    {"name": "ESPN FC",     "url": "https://www.espn.com/espn/rss/soccer/news"},
    {"name": "Goal.com",    "url": "https://www.goal.com/feeds/en/news"},
    {"name": "Football365", "url": "https://www.football365.com/feed"},
]


# ============================================================
# Helpers
# ============================================================

def th_date(dt: datetime) -> str:
    return f"{dt.day} {TH_MONTHS[dt.month]} {dt.year + 543}"


def is_womens(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in WOMENS_KEYWORDS)


def classify(title: str, summary: str) -> list[str]:
    text = (title + " " + summary).lower()
    return [k for k, v in TEAMS.items() if any(kw in text for kw in v["keywords"])]


# ============================================================
# Fetch
# ============================================================

def fetch_news(hours_back: int = 24) -> dict[str, list[dict]]:
    cutoff = datetime.now(tz=TH_TZ) - timedelta(hours=hours_back)
    results: dict[str, list[dict]] = {k: [] for k in TEAMS}
    seen_links: set[str] = set()

    for feed_info in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_info["url"])
        except Exception as e:
            print(f"[WARN] {feed_info['name']}: {e}")
            continue

        for entry in feed.entries:
            title   = entry.get("title", "").strip()
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            link    = entry.get("link", "")

            if link in seen_links or is_womens(title, summary):
                continue

            matched = classify(title, summary)
            if not matched:
                continue

            pub = datetime.now(tz=TH_TZ)
            if getattr(entry, "published_parsed", None):
                try:
                    pub = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc).astimezone(TH_TZ)
                except Exception:
                    pass
            elif getattr(entry, "published", None):
                try:
                    pub = dateparser.parse(entry.published).astimezone(TH_TZ)
                except Exception:
                    pass

            if pub < cutoff:
                continue

            seen_links.add(link)
            art = {
                "title":   title,
                "summary": summary[:250].rstrip(),
                "source":  feed_info["name"],
                "pub":     pub,
            }
            for team_key in matched:
                results[team_key].append(art)

    for key in results:
        seen_titles: set[str] = set()
        unique = []
        for art in sorted(results[key], key=lambda x: x["pub"], reverse=True):
            norm = art["title"].lower()[:60]
            if norm not in seen_titles:
                seen_titles.add(norm)
                unique.append(art)
        results[key] = unique[:7]

    return results


# ============================================================
# Translate
# ============================================================

_translator = GoogleTranslator(source="auto", target="th")


def safe_translate(text: str) -> str:
    if not text:
        return ""
    try:
        return _translator.translate(text[:400])
    except Exception:
        return text


def translate_article(art: dict) -> tuple[str, str]:
    """Return (title_th, summary_th)"""
    title_th   = safe_translate(art["title"])
    summary_th = safe_translate(art["summary"]) if art.get("summary") else ""
    # ถ้า summary แปลออกมาเหมือน title ไม่ต้องแสดง
    if summary_th and summary_th.strip().lower() == title_th.strip().lower():
        summary_th = ""
    return title_th, summary_th


# ============================================================
# Flex Message Builder
# ============================================================

def _article_box(art: dict, badge_color: str) -> dict:
    title_th, summary_th = translate_article(art)
    time_str = art["pub"].strftime("%H:%M")

    contents = [
        # แถวบน: เวลา + แหล่งข่าว
        {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "box",
                    "layout": "vertical",
                    "width": "46px",
                    "height": "20px",
                    "cornerRadius": "10px",
                    "backgroundColor": badge_color,
                    "justifyContent": "center",
                    "contents": [{
                        "type": "text",
                        "text": time_str,
                        "color": "#FFFFFF",
                        "size": "xxs",
                        "align": "center",
                        "offsetTop": "1px",
                    }],
                },
                {
                    "type": "text",
                    "text": art["source"],
                    "size": "xxs",
                    "color": "#AAAAAA",
                    "align": "end",
                    "flex": 1,
                    "gravity": "center",
                },
            ],
        },
        # หัวข่าวภาษาไทย
        {
            "type": "text",
            "text": title_th or art["title"],
            "size": "sm",
            "weight": "bold",
            "color": "#111111",
            "wrap": True,
            "maxLines": 3,
            "margin": "sm",
        },
    ]

    # เพิ่ม summary ถ้ามี
    if summary_th:
        contents.append({
            "type": "text",
            "text": summary_th,
            "size": "xs",
            "color": "#666666",
            "wrap": True,
            "maxLines": 3,
            "margin": "xs",
        })

    return {
        "type": "box",
        "layout": "vertical",
        "spacing": "none",
        "paddingBottom": "12px",
        "contents": contents,
    }


def _team_bubble(team_key: str, articles: list[dict], date_str: str) -> dict:
    info = TEAMS[team_key]

    # Header
    header = {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": info["header_color"],
        "paddingAll": "16px",
        "contents": [
            {
                "type": "box",
                "layout": "horizontal",
                "contents": [
                    {
                        "type": "text",
                        "text": info["emoji"],
                        "size": "xxl",
                        "flex": 0,
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "flex": 1,
                        "paddingStart": "8px",
                        "contents": [
                            {
                                "type": "text",
                                "text": info["name"],
                                "color": "#FFFFFF",
                                "size": "xl",
                                "weight": "bold",
                            },
                            {
                                "type": "text",
                                "text": f"ข่าวล่าสุด {len(articles)} รายการ",
                                "color": "#DDDDDD",
                                "size": "xs",
                            },
                        ],
                    },
                ],
            },
            {
                "type": "text",
                "text": f"⚽ ฟุตบอลชาย · {date_str}",
                "color": "#BBBBBB",
                "size": "xxs",
                "margin": "sm",
            },
        ],
    }

    # Body — articles with separators
    body_contents = []
    for i, art in enumerate(articles):
        body_contents.append(_article_box(art, info["badge_color"]))
        if i < len(articles) - 1:
            body_contents.append({
                "type": "separator",
                "color": "#EEEEEE",
                "margin": "none",
            })

    body = {
        "type": "box",
        "layout": "vertical",
        "paddingAll": "14px",
        "spacing": "none",
        "contents": body_contents,
    }

    return {
        "type": "bubble",
        "size": "mega",
        "header": header,
        "body": body,
        "styles": {
            "header": {"separator": False},
            "body": {"backgroundColor": "#FAFAFA"},
        },
    }


def _no_news_bubble(date_str: str) -> dict:
    return {
        "type": "bubble",
        "size": "kilo",
        "body": {
            "type": "box",
            "layout": "vertical",
            "justifyContent": "center",
            "paddingAll": "24px",
            "spacing": "md",
            "contents": [
                {"type": "text", "text": "⚽", "align": "center", "size": "5xl"},
                {
                    "type": "text",
                    "text": "ไม่มีข่าวใหม่",
                    "align": "center",
                    "size": "lg",
                    "weight": "bold",
                    "color": "#333333",
                },
                {
                    "type": "text",
                    "text": f"Arsenal & Barcelona\n{date_str}",
                    "align": "center",
                    "size": "sm",
                    "color": "#888888",
                    "wrap": True,
                },
            ],
        },
    }


def build_flex_message(news: dict[str, list[dict]]) -> dict:
    date_str = th_date(datetime.now(TH_TZ))
    bubbles = []

    for team_key in ["arsenal", "barcelona"]:
        articles = news.get(team_key, [])
        if articles:
            info = TEAMS[team_key]
            print(f"   แปล {info['name']} {len(articles)} ข่าว...")
            bubbles.append(_team_bubble(team_key, articles, date_str))

    if not bubbles:
        bubbles.append(_no_news_bubble(date_str))

    return {
        "type": "flex",
        "altText": f"⚽ ข่าวฟุตบอลชาย Arsenal & Barcelona — {date_str}",
        "contents": {
            "type": "carousel",
            "contents": bubbles,
        },
    }


# ============================================================
# Send LINE
# ============================================================

def send_line(message: dict) -> None:
    resp = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json",
        },
        json={"to": LINE_USER_ID, "messages": [message]},
        timeout=15,
    )
    if resp.status_code == 200:
        print("✅ ส่ง LINE สำเร็จ")
    else:
        raise RuntimeError(f"LINE API error {resp.status_code}: {resp.text}")


# ============================================================
# Main
# ============================================================

def main():
    print(f"🕗 {datetime.now(TH_TZ).strftime('%d/%m/%Y %H:%M')} (TH) — ดึงข่าวฟุตบอลชาย")

    news = fetch_news(hours_back=24)
    for team_key, info in TEAMS.items():
        print(f"   {info['name']}: {len(news.get(team_key, []))} ข่าว")

    flex = build_flex_message(news)
    send_line(flex)


if __name__ == "__main__":
    main()
