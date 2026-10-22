from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import TextClause, create_engine
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from energy_dash.core.settings import get_settings
from energy_dash.core.timeutils import WARSAW

engine = create_engine(
    get_settings().db.url,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Zapewnia automatyczny commit przy sukcesie, rollback w razie błędu i zamknięcie sesji
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def read_df(
    sql: str | TextClause,
    *,
    params: dict[str, Any] | None = None,
    index_col: str | None = "datetime_utc",
    tz: ZoneInfo | None = WARSAW,
) -> pd.DataFrame:
    """Wykonuje zapytanie SQL i zwraca DataFrame z opcjonalnym DatetimeIndex.

    Args:
        sql: Zapytanie SQL (string lub sqlalchemy.text).
        params: Parametry bindowane do zapytania SQL.
        index_col: Nazwa kolumny, która ma stać się indeksem czasowym.
        tz: Docelowa strefa czasowa indeksu (domyślnie WARSAW; None = czysty UTC).
    """

    with engine.connect() as conn:
        df = pd.read_sql(sql, con=conn, params=params)

    if df.empty:
        return df

    if index_col and index_col in df.columns:
        df[index_col] = pd.to_datetime(df[index_col], utc=True)
        if tz is not None:
            local_col = "datetime_local" if index_col == "datetime_utc" else index_col
            df[local_col] = df[index_col].dt.tz_convert(tz)
            df.set_index(local_col, inplace=True)
            if local_col != index_col and index_col in df.columns:
                df.drop(columns=[index_col], inplace=True)
        else:
            df.set_index(index_col, inplace=True)
        df.sort_index(inplace=True)

    return df


def postgres_upsert(
    table_model: type[Base],
    records: list[dict[str, Any]],
    index_elements: list[str],
    update_columns: list[str],
):
    """Wstawia rekordy do tabeli PostgreSQL z aktualizacją przy konflikcie klucza (UPSERT).

    Args:
        table_model: Klasa modelu SQLAlchemy (dziedzicząca po Base).
        records: Lista słowników z danymi rekordów.
        index_elements: Kolumny tworzące unikalny klucz/indeks.
        update_columns: Kolumny do zaktualizowania przy konflikcie.

    Returns:
        Liczba przetworzonych rekordów.
    """

    if not records:
        return 0

    stmt = insert(table_model).values(records)
    update_dict = {col: getattr(stmt.excluded, col) for col in update_columns}
    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=index_elements,
        set_=update_dict,
    )

    with engine.begin() as conn:
        conn.execute(upsert_stmt)
    return len(records)
