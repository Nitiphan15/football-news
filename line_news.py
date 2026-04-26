"""
Arsenal & Barcelona Daily News → LINE Messaging API
รันผ่าน GitHub Actions ทุกวัน 8 โมงเช้า (ไทย)
"""

import feedparser
import requests
import json
import os
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser

# ============================================================
# Config — อ่านจาก Environment Variables (GitHub Secrets)
# ============================================================
LINE_TOKEN = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID = os.environ["LINE_USER_ID"]

TEAMS = {
    "arsenal": {
        "name": "Arsenal",
        "color": "#EF0107",
        "icon": "https://upload.wikimedia.org/wikipedia/en/5/53/Arsenal_FC.svg",
        "emoji": "🔴",
        "keywords": [
            "arsenal", "gunners", "emirates", "arteta",
            "saka", "odegaard", "havertz", "white", "saliba",
            "martinelli", "trossard", "rice",
        ],
    },
    "barcelona": {
        "name": "Barcelona",
        "color": "#A50044",
        "icon": "https://upload.wikimedia.org/wikipedia/en/4/47/FC_Barcelona_%28crest%29.svg",
        "emoji": "🔵",
        "keywords": [
            "barcelona", "barça", "barca", "blaugrana",
            "nou camp", "camp nou", "flick",
            "lewandowski", "yamal", "pedri", "gavi",
            "raphinha", "dani olmo", "kounde", "araujo",
        ],
    },
}

RSS_FEEDS = [
    {"name": "BBC Sport",   "url": "https://feeds.bbci.co.uk/sport/football/rss.xml"},
    {"name": "Sky Sports",  "url": "https://www.skysports.com/rss/12040"},
    {"name": "ESPN FC",     "url": "https://www.espn.com/espn/rss/soccer/news"},
    {"name": "Goal.com",    "url": "https://www.goal.com/feeds/en/news"},
    {"name": "Football365", "url": "https://www.football365.com/feed"},
]

TH_TZ = timezone(timedelta(hours=7))


# ============================================================
# Fetch
# ============================================================

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

            matched = classify(title, summary)
            if not matched:
                continue

            # Parse date
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
                "summary": summary[:180].rstrip(),
                "link":    link,
                "source":  feed_info["name"],
                "pub":     pub,
            }
            for team_key in matched:
                results[team_key].append(article)

    # Deduplicate within each team (same title from different feeds)
    for key in results:
        seen_titles: set[str] = set()
        unique = []
        for art in sorted(results[key], key=lambda x: x["pub"], reverse=True):
            norm = art["title"].lower()[:60]
            if norm not in seen_titles:
                seen_titles.add(norm)
                unique.append(art)
        results[key] = unique

    return results


# ============================================================
# LINE Flex Message builder
# ============================================================

def make_team_bubble(team_key: str, articles: list[dict]) -> dict:
    info = TEAMS[team_key]

    # Header
    header = {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": info["color"],
        "paddingAll": "14px",
        "contents": [
            {
                "type": "text",
                "text": f"{info['emoji']} {info['name']}",
                "color": "#FFFFFF",
                "size": "xl",
                "weight": "bold",
            },
            {
                "type": "text",
                "text": f"{len(articles)} ข่าว  ·  อัปเดต {datetime.now(TH_TZ).strftime('%d %b %Y')}",
                "color": "#FFFFFF",
                "size": "xs",
                "margin": "xs",
            },
        ],
    }

    # Body — list of articles
    body_contents = []
    for i, art in enumerate(articles[:8]):          # max 8 per team
        time_str = art["pub"].strftime("%H:%M")
        item = {
            "type": "box",
            "layout": "vertical",
            "spacing": "xs",
            "paddingBottom": "10px",
            "action": {"type": "uri", "uri": art["link"] or "https://www.bbc.co.uk/sport/football"},
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {
                            "type": "text",
                            "text": time_str,
                            "size": "xxs",
                            "color": "#AAAAAA",
                            "flex": 0,
                        },
                        {
                            "type": "text",
                            "text": art["source"],
                            "size": "xxs",
                            "color": "#AAAAAA",
                            "align": "end",
                            "flex": 1,
                        },
                    ],
                },
                {
                    "type": "text",
                    "text": art["title"],
                    "size": "sm",
                    "weight": "bold",
                    "wrap": True,
                    "maxLines": 2,
                },
            ],
        }
        body_contents.append(item)

        if i < len(articles[:8]) - 1:
            body_contents.append({
                "type": "separator",
                "margin": "sm",
            })

    body = {
        "type": "box",
        "layout": "vertical",
        "paddingAll": "12px",
        "spacing": "none",
        "contents": body_contents,
    }

    return {
        "type": "bubble",
        "size": "kilo",
        "header": header,
        "body": body,
    }


def make_empty_bubble() -> dict:
    return {
        "type": "bubble",
        "size": "kilo",
        "body": {
            "type": "box",
            "layout": "vertical",
            "justifyContent": "center",
            "paddingAll": "20px",
            "contents": [
                {
                    "type": "text",
                    "text": "⚽",
                    "align": "center",
                    "size": "3xl",
                },
                {
                    "type": "text",
                    "text": "ไม่มีข่าวใหม่\nใน 24 ชั่วโมงที่ผ่านมา",
                    "align": "center",
                    "wrap": True,
                    "color": "#888888",
                    "size": "sm",
                    "margin": "md",
                },
            ],
        },
    }


def build_flex_message(news: dict[str, list[dict]]) -> dict:
    bubbles = []
    for team_key in ["arsenal", "barcelona"]:
        arts = news.get(team_key, [])
        if arts:
            bubbles.append(make_team_bubble(team_key, arts))

    if not bubbles:
        bubbles.append(make_empty_bubble())

    return {
        "type": "flex",
        "altText": f"⚽ ข่าวฟุตบอลประจำวัน — Arsenal & Barcelona",
        "contents": {
            "type": "carousel",
            "contents": bubbles,
        },
    }


# ============================================================
# Send LINE Push Message
# ============================================================

def send_line(message: dict) -> None:
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": LINE_USER_ID,
        "messages": [message],
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

    arsenal_count  = len(news.get("arsenal", []))
    barcelona_count = len(news.get("barcelona", []))
    print(f"   Arsenal: {arsenal_count} ข่าว  |  Barcelona: {barcelona_count} ข่าว")

    if arsenal_count == 0 and barcelona_count == 0:
        print("ℹ️  ไม่มีข่าวใหม่ — ส่ง LINE แจ้งให้ทราบ")

    flex_msg = build_flex_message(news)
    send_line(flex_msg)


if __name__ == "__main__":
    main()
