from datetime import UTC, datetime

from sqlalchemy import Column, Date, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from src.common.database import Base


def _now():
    return datetime.now(UTC)


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(Text, nullable=False, unique=True)
    real_url = Column(Text, nullable=True)
    title = Column(Text, nullable=False)
    source = Column(String(200), nullable=True)
    topic = Column(String(30), nullable=False)
    published_utc = Column(DateTime(timezone=True), index=True)
    fetched_utc = Column(DateTime(timezone=True), default=_now)
    body = Column(Text, nullable=True)


class NewsDigest(Base):
    __tablename__ = "news_digests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    issued_day_utc = Column(Date, nullable=False, unique=True)  # doba, której dotyczy podsumowanie
    generated_utc = Column(DateTime(timezone=True), default=_now, index=True)
    model = Column(String(100))
    n_articles = Column(Integer)
    items = Column(JSONB, nullable=False)
