from datetime import UTC, date, datetime, time, timedelta

import pandas as pd
import streamlit as st

from energy_dash.core.db import SessionLocal
from energy_dash.features.news.models import NewsArticle, NewsDigest


@st.cache_data(ttl=300)
def get_news_articles(issued_day: date) -> pd.DataFrame:
    end = datetime.combine(issued_day, time(7, 0, tzinfo=UTC))
    start = end - timedelta(days=1)

    with SessionLocal() as session:
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


@st.cache_data(ttl=300)
def get_news_digest(issued_day: date) -> dict | None:
    with SessionLocal() as session:
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


@st.cache_data(ttl=300)
def get_dates_of_summaries() -> list[date]:
    with SessionLocal() as session:
        rows = session.query(NewsDigest.issued_day_utc).order_by(NewsDigest.issued_day_utc).all()  # type: ignore[var-annotated]
    return [r[0] for r in rows]
