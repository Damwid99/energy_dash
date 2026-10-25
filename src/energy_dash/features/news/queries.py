from datetime import UTC, date, datetime, time, timedelta

import pandas as pd

from energy_dash.core.db import session_scope
from energy_dash.features.news.models import NewsArticle, NewsDigest


def get_news_articles(issued_day: date) -> pd.DataFrame:
    """Pobiera artykuły opublikowane w 24-godzinnym oknie przed godziną 07:00 UTC."""
    end = datetime.combine(issued_day, time(7, 0, tzinfo=UTC))
    start = end - timedelta(days=1)

    with session_scope() as session:
        rows = (
            session.query(NewsArticle)
            .filter(NewsArticle.published_utc >= start)  # type: ignore[arg-type]
            .filter(NewsArticle.published_utc < end)  # type: ignore[arg-type]
            .order_by(NewsArticle.published_utc.desc())
            .all()
        )
        records = [
            {
                "id": r.id,
                "topic": r.topic,
                "title": r.title,
                "source": r.source,
                "url": r.real_url or r.url,
                "published_utc": r.published_utc,
            }
            for r in rows
        ]
    return pd.DataFrame(records)


def get_news_digest(issued_day: date) -> dict | None:
    """Pobiera najświeższe podsumowanie prasowe wygenerowane dla danej doby."""
    with session_scope() as session:
        d = (
            session.query(NewsDigest)
            .filter(NewsDigest.issued_day_utc == issued_day)
            .order_by(NewsDigest.generated_utc.desc())
            .first()
        )
        if d is None:
            return None
        return {
            "items": d.items,
            "generated_utc": d.generated_utc,
            "model": d.model,
            "n_articles": d.n_articles,
        }


def get_dates_of_summaries() -> list[date]:
    """Zwraca posortowaną listę dat, dla których istnieją podsumowania prasowe."""
    with session_scope() as session:
        rows = (  # type: ignore[var-annotated]
            session.query(NewsDigest.issued_day_utc)
            .order_by(NewsDigest.issued_day_utc.desc())
            .all()
        )
    return [r[0] for r in rows]
