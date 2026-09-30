"""
Jednorazowe zasilenie tabel news_articles i news_digests.

1. Pobiera newsy z RSS (domyślnie 2 doby wstecz).
2. Generuje pierwsze podsumowanie (wybór po tytułach -> treść -> digest).

Idempotentny: artykuły deduplikowane po URL, digest dopisuje się jako nowy wpis.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import func

from src.common.database import Base, SessionLocal, engine
from src.etl.extract.news_rss import fetch_and_save_news
from src.etl.transform.news_digest import generate_digest
from src.models_db.news import NewsArticle, NewsDigest


def seed_news():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--days-back", type=int, default=2)
    parser.add_argument("--skip-digest", action="store_true", help="tylko artykuły, bez LLM")
    parser.add_argument("--digest-only", action="store_true", help="tylko digest z danych w bazie")
    parser.add_argument("--force", action="store_true", help="nadpisz dzisiejszy digest")

    args = parser.parse_args()

    if args.skip_digest and args.digest_only:
        parser.error("--skip-digest i --digest-only wykluczają się nawzajem")

    Base.metadata.create_all(bind=engine)
    print("Rozpoczynam seedowanie newsów")

    if not args.digest_only:
        fetch_and_save_news(days_back=args.days_back)
    if not args.skip_digest:
        generate_digest(force=args.force)

    session = SessionLocal()
    try:
        total, first, last = session.query(
            func.count(NewsArticle.id),
            func.min(NewsArticle.published_utc),
            func.max(NewsArticle.published_utc),
        ).one()
        n_digests, last_digest = session.query(
            func.count(NewsDigest.id), func.max(NewsDigest.generated_utc)
        ).one()
        print(f"\nW bazie: {total} artykułów, od {first} do {last} (UTC)")
        print(f"Digestów: {n_digests}, ostatni wygenerowany: {last_digest}")
    finally:
        session.close()


if __name__ == "__main__":
    seed_news()
