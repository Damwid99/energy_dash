from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from src.common.config import DATABASE_URL

engine = create_engine(DATABASE_URL, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """
    Generator sesji bazt danych
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
