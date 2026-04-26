"""
Arsenal & Barcelona Daily News → LINE Messaging API
- สรุปและแปลเป็นภาษาไทยด้วย Claude API
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

TEAMS = {
    "arsenal": {
        "name": "Arsenal",
        "color": "#EF0107",
        "emoji": "🔴",
        "keywords": [
            "arsenal", "gunners", "emirates", "arteta",
            "saka", "odegaard", "havertz", "white", "saliba",
            "martinelli", "trossard", "rice", "jesus", "zinchenko",
        ],
    },
    "barcelona": {
        "name": "Barcelona",
        "color": "#004D98",
        "emoji": "🔵",
        "keywords": [
            "barcelona", "barça", "barca", "blaugrana",
            "nou camp", "camp nou", "flick",
            "lewandowski", "yamal", "pedri", "gavi",
            "raphinha", "dani olmo", "kounde", "araujo",
        ],
    },
}

# คำที่บ่งบอกว่าเป็นฟุตบอลหญิง — ตัดออกทั้งหมด
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
# Fetch & Filter
# ============================================================

def is_womens(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in WOMENS_KEYWORDS)


def classify(title: str, summary: str) -> list[str]:
    text = (title + " " + summary).lower()
    return [k for k, v in TEAMS.items() if any(kw in text for kw in v["keywords"])]


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

            if link in seen_links:
                continue

            # ตัดข่าวฟุตบอลหญิงออก
            if is_womens(title, summary):
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
            article = {
                "title":   title,
                "summary": summary[:300].rstrip(),
                "source":  feed_info["name"],
                "pub":     pub,
            }
            for team_key in matched:
                results[team_key].append(article)

    # Deduplicate + sort newest first
    for key in results:
        seen_titles: set[str] = set()
        unique = []
        for art in sorted(results[key], key=lambda x: x["pub"], reverse=True):
            norm = art["title"].lower()[:60]
            if norm not in seen_titles:
                seen_titles.add(norm)
                unique.append(art)
        results[key] = unique[:8]  # max 8 ข่าวต่อทีม

    return results


# ============================================================
# Translate with Google Translate (ฟรี ไม่ต้อง API Key)
# ============================================================

translator = GoogleTranslator(source="auto", target="th")


def translate_article(article: dict) -> str:
    """แปล title + summary เป็นภาษาไทย แล้วรวมเป็นประโยคเดียว"""
    try:
        title_th = translator.translate(article["title"])
    except Exception:
        title_th = article["title"]

    # แปล summary ถ้ามี
    summary_th = ""
    if article.get("summary"):
        try:
            # ตัดให้สั้นลงก่อนส่งแปล
            short = article["summary"][:200]
            summary_th = translator.translate(short)
        except Exception:
            pass

    if summary_th and summary_th.lower() != title_th.lower():
        return f"{title_th} — {summary_th}"
    return title_th


# ============================================================
# LINE Message Builder (Text-based, ไม่มี link)
# ============================================================

def build_line_messages(news: dict[str, list[dict]]) -> list[dict]:
    messages = []
    date_str = datetime.now(TH_TZ).strftime("%-d %B %Y").replace(
        "January","มกราคม").replace("February","กุมภาพันธ์").replace(
        "March","มีนาคม").replace("April","เมษายน").replace(
        "May","พฤษภาคม").replace("June","มิถุนายน").replace(
        "July","กรกฎาคม").replace("August","สิงหาคม").replace(
        "September","กันยายน").replace("October","ตุลาคม").replace(
        "November","พฤศจิกายน").replace("December","ธันวาคม")

    has_news = any(len(arts) > 0 for arts in news.values())

    if not has_news:
        return [{
            "type": "text",
            "text": f"⚽ ข่าวฟุตบอลประจำวัน {date_str}\n\nไม่มีข่าวใหม่ใน 24 ชั่วโมงที่ผ่านมา"
        }]

    for team_key in ["arsenal", "barcelona"]:
        articles = news.get(team_key, [])
        if not articles:
            continue

        info = TEAMS[team_key]
        print(f"   กำลังแปล {info['name']} {len(articles)} ข่าว ด้วย Google Translate...")

        lines = [f"{info['emoji']} {info['name']} — {date_str}"]
        lines.append("─" * 28)

        for i, art in enumerate(articles, 1):
            time_str = art["pub"].strftime("%H:%M")
            thai_text = translate_article(art)
            lines.append(f"{i}. [{time_str}] {thai_text}")

        text = "\n".join(lines)

        messages.append({
            "type": "text",
            "text": text,
        })

    return messages


# ============================================================
# Send LINE
# ============================================================

def send_line(messages: list[dict]) -> None:
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json",
    }
    # LINE รับได้สูงสุด 5 messages ต่อ request
    payload = {
        "to": LINE_USER_ID,
        "messages": messages[:5],
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    if resp.status_code == 200:
        print("✅ ส่ง LINE สำเร็จ")
    else:
        raise RuntimeError(f"LINE API error {resp.status_code}: {resp.text}")


# ============================================================
# Main
# ============================================================

def main():
    print(f"🕗 ดึงข่าว Arsenal & Barcelona — {datetime.now(TH_TZ).strftime('%d/%m/%Y %H:%M')} (TH)")

    news = fetch_news(hours_back=24)

    for team_key, info in TEAMS.items():
        count = len(news.get(team_key, []))
        print(f"   {info['name']}: {count} ข่าว (ชายเท่านั้น)")

    messages = build_line_messages(news)
    send_line(messages)


if __name__ == "__main__":
    main()
