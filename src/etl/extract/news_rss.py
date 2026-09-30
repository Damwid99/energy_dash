from datetime import UTC, datetime
from urllib.parse import quote_plus

import feedparser
from sqlalchemy.dialects.postgresql import insert

from src.common.database import SessionLocal
from src.models_db.news import NewsArticle

# (temat, zapytanie, hl, gl, ceid)
FEEDS = [
    ("power", "rynek energii OR ceny prądu OR TGE OR PSE", "pl", "PL", "PL:pl"),
    ("gas", "gaz TTF OR ceny gazu OR magazyny gazu", "pl", "PL", "PL:pl"),
    ("oil", "ropa Brent OR OPEC OR ceny ropy", "pl", "PL", "PL:pl"),
    ("co2", "EU ETS OR uprawnienia do emisji CO2", "pl", "PL", "PL:pl"),
    ("gas", "TTF gas price OR Europe gas storage OR LNG", "en", "US", "US:en"),
    ("oil", "Brent crude OR OPEC+ OR oil price", "en", "US", "US:en"),
    ("power", "European power prices OR Germany electricity price", "en", "US", "US:en"),
]


def _feed_url(query: str, hl: str, gl: str, ceid: str, days_back: int) -> str:
    q = quote_plus(f"{query} when:{days_back}d")
    return f"https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={ceid}"


def fetch_and_save_news(days_back: int = 2):
    print(f"[NEWS] Pobieranie newsów z ostatnich {days_back} dób...")
    rows = {}

    for topic, query, hl, gl, ceid in FEEDS:
        try:
            feed = feedparser.parse(_feed_url(query, hl, gl, ceid, days_back))
        except Exception as e:
            print(f"[NEWS] BŁĄD feedu '{query}': {e}")
            continue

        for e in feed.entries:
            url, title = e.get("link"), e.get("title")
            if not url or not title or not e.get("published_parsed"):
                continue

            source = (e.get("source") or {}).get("title")
            if source and title.endswith(f" - {source}"):
                title = title[: -len(f" - {source}")]

            rows.setdefault(
                url,
                {
                    "url": url,
                    "title": title.strip(),
                    "source": source,
                    "topic": topic,
                    "published_utc": datetime(*e.published_parsed[:6], tzinfo=UTC),
                },
            )

    if not rows:
        print("[NEWS] Brak wpisów.")
        return

    session = SessionLocal()
    try:
        stmt = (
            insert(NewsArticle)
            .values(list(rows.values()))
            .on_conflict_do_nothing(index_elements=["url"])
            .returning(NewsArticle.id)
        )
        new_count = len(session.execute(stmt).fetchall())
        session.commit()
        print(f"[NEWS] Nowych artykułów: {new_count} (z {len(rows)} pobranych).")
    except Exception as e:
        session.rollback()
        print(f"[NEWS] BŁĄD zapisu: {e}")
    finally:
        session.close()
