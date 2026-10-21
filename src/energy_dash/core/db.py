from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from energy_dash.core.settings import get_settings

engine = create_engine(get_settings().db.url, echo=False)

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
