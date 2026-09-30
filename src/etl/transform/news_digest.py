import os
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import trafilatura
from googlenewsdecoder import gnewsdecoder

from src.common.database import SessionLocal
from src.common.llm import MODEL, ask_structured
from src.models_db.news import NewsArticle, NewsDigest
from src.schemas.news import Digest, Selection

WARSAW_TZ = ZoneInfo("Europe/Warsaw")
TITLES_LIMIT = int(os.getenv("NEWS_TITLES_LIMIT", "100"))
SELECT_MAX = int(os.getenv("NEWS_SELECT_MAX", "15"))
BODY_MAX = int(os.getenv("NEWS_BODY_MAX_CHARS", "4000"))

SELECT_PROMPT = f"""Jesteś analitykiem rynku energii w Polsce. Dostajesz ponumerowaną listę nagłówków
z ostatnich dwóch dni (energia elektryczna, gaz, ropa, CO2).

Wybierz maksymalnie {SELECT_MAX} artykułów, które mogą realnie wpłynąć na ceny energii w Polsce
(krótko- lub długoterminowo). Z duplikatów tego samego wydarzenia wybierz jeden. Pomiń clickbait,
reklamy i tematy bez związku z rynkiem."""

DIGEST_PROMPT = """Jesteś analitykiem rynku energii w Polsce. Dostajesz ponumerowane artykuły
(pełna treść albo tylko nagłówek) ze wstępną oceną horyzontu wpływu.

Zrób z nich listę najważniejszych punktów dla rynku energii w Polsce.
Zasady:
- Jeden punkt = jedno wydarzenie lub wątek. Łącz artykuły o tym samym w jeden punkt (kilka source_ids).
- Używaj WYŁĄCZNIE informacji z dostarczonych tekstów. Nie zmyślaj liczb ani faktów.
- Przy artykułach oznaczonych "(tylko nagłówek)" nie wyciągaj daleko idących wniosków;
  jeśli kierunek wpływu jest niejasny, ustaw impact na "unclear".
- source_ids mogą zawierać wyłącznie numery z listy wejściowej.
- Maksymalnie 8 punktów na horyzont."""


def today_utc() -> date:
    return datetime.now(UTC).date()


def digest_exists(day: date) -> bool:
    session = SessionLocal()
    try:
        return (
            session.query(NewsDigest.id).filter(NewsDigest.issued_day_utc == day).first()
            is not None
        )
    finally:
        session.close()


def ensure_body(session, art: NewsArticle):
    """
    Rozwija link Google News i pobiera treść. Przy porażce zapisuje "" (bez ponownych prób).
    """
    if art.body is not None:
        return
    try:
        res = gnewsdecoder(art.url, interval=1)
        art.real_url = res["decoded_url"] if res.get("status") else art.url
        downloaded = trafilatura.fetch_url(art.real_url)
        text = trafilatura.extract(downloaded, include_comments=False) if downloaded else None
        art.body = text or ""
    except Exception as e:
        print(f"[DIGEST] Brak treści dla [{art.id}]: {e}")
        art.body = ""
    session.commit()


def generate_digest(force: bool = False):
    day = today_utc()
    if not force and digest_exists(day):
        print(f"[DIGEST] Podsumowanie na {day} już istnieje, pomijam.")
        return

    since = datetime.now(UTC) - timedelta(days=2)
    session = SessionLocal()
    try:
        articles = (
            session.query(NewsArticle)
            .filter(NewsArticle.published_utc >= since)
            .order_by(NewsArticle.published_utc.desc())
            .limit(TITLES_LIMIT)
            .all()
        )
        if not articles:
            print("[DIGEST] Brak artykułów, pomijam.")
            return
        by_id = {a.id: a for a in articles}

        print(f"[DIGEST] Etap 1: wybór z {len(articles)} tytułów ({MODEL})...")
        lines = [
            f"[{a.id}] {a.published_utc.astimezone(WARSAW_TZ):%d.%m %H:%M} | {a.topic} | "
            f"{a.title} — {a.source or '?'}"
            for a in articles
        ]
        selection = ask_structured(SELECT_PROMPT, "\n".join(lines), Selection)
        chosen: dict[int, str] = {}
        for s in selection.selected:
            if s.id in by_id:
                chosen.setdefault(s.id, s.horizon)
        chosen = dict(list(chosen.items())[:SELECT_MAX])
        if not chosen:
            print("[DIGEST] Model nic nie wybrał, pomijam.")
            return
        print(f"[DIGEST] Wybrano {len(chosen)} artykułów.")

        print("[DIGEST] Etap 2: pobieranie treści i podsumowanie...")
        blocks = []
        for aid, horizon in chosen.items():
            art = by_id[aid]
            ensure_body(session, art)
            body = (art.body or "")[:BODY_MAX] or "(tylko nagłówek)"
            blocks.append(
                f"[{art.id}] {art.title} ({art.source or '?'}, horyzont: {horizon})\n{body}"
            )

        now_pl = datetime.now(WARSAW_TZ)
        digest = ask_structured(
            DIGEST_PROMPT,
            f"Dziś jest {now_pl:%Y-%m-%d %H:%M}.\n\n" + "\n\n---\n\n".join(blocks),
            Digest,
        )

        items = []
        for it in digest.items:
            sources = [
                {
                    "id": by_id[i].id,
                    "title": by_id[i].title,
                    "source": by_id[i].source,
                    "url": by_id[i].real_url or by_id[i].url,
                }
                for i in dict.fromkeys(it.source_ids)
                if i in chosen
            ]
            if not sources:
                continue
            items.append({**it.model_dump(exclude={"source_ids"}), "sources": sources})

        if not items:
            print("[DIGEST] Brak punktów z poprawnymi źródłami, pomijam.")
            return

        session.query(NewsDigest).filter(NewsDigest.issued_day_utc == day).delete()
        session.add(
            NewsDigest(issued_day_utc=day, model=MODEL, n_articles=len(chosen), items=items)
        )
        session.commit()
        print(f"[DIGEST] Zapisano {len(items)} punktów.")
    except Exception as e:
        session.rollback()
        print(f"[DIGEST] BŁĄD: {e}")
    finally:
        session.close()
