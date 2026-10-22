"""Testy jednostkowe modułu energy_dash.core.db (pula, transakcje, read_df, upsert)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from sqlalchemy import Column, Integer, String

from energy_dash.core.db import Base, postgres_upsert, read_df, session_scope


class DummyModel(Base):
    __tablename__ = "dummy_table"
    id = Column(Integer, primary_key=True)
    name = Column(String(50))
    val = Column(Integer)


def test_session_scope_commits_on_success():
    mock_session = MagicMock()
    with patch("energy_dash.core.db.SessionLocal", return_value=mock_session):
        with session_scope() as s:
            s.add(DummyModel(id=1, name="test", val=10))
        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()
        mock_session.close.assert_called_once()


def test_session_scope_rollbacks_on_exception():
    mock_session = MagicMock()
    with patch("energy_dash.core.db.SessionLocal", return_value=mock_session):
        with pytest.raises(RuntimeError, match="Błąd symulowany"):
            with session_scope():
                raise RuntimeError("Błąd symulowany")
        mock_session.commit.assert_not_called()
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()


def test_read_df_converts_utc_to_warsaw_by_default():
    sample_data = pd.DataFrame(
        {
            "datetime_utc": [datetime(2026, 10, 20, 10, 0, tzinfo=UTC)],
            "val": [123.45],
        }
    )
    with patch("energy_dash.core.db.pd.read_sql", return_value=sample_data):
        df = read_df("SELECT * FROM dummy")
        assert df.index.name == "datetime_local"
        assert str(df.index.tz) == "Europe/Warsaw"
        assert "datetime_utc" not in df.columns
        assert df.iloc[0]["val"] == 123.45


def test_read_df_keeps_utc_when_tz_is_none():
    sample_data = pd.DataFrame(
        {
            "datetime_utc": [datetime(2026, 10, 20, 10, 0, tzinfo=UTC)],
            "val": [123.45],
        }
    )
    with patch("energy_dash.core.db.pd.read_sql", return_value=sample_data):
        df = read_df("SELECT * FROM dummy", tz=None)
        assert df.index.name == "datetime_utc"
        assert str(df.index.tz) == "UTC"
        assert df.iloc[0]["val"] == 123.45


def test_read_df_returns_empty_when_sql_empty():
    with patch("energy_dash.core.db.pd.read_sql", return_value=pd.DataFrame()):
        df = read_df("SELECT * FROM dummy")
        assert df.empty


def test_postgres_upsert_empty_records_returns_zero():
    count = postgres_upsert(DummyModel, [], index_elements=["id"], update_columns=["val"])  # type: ignore[call-arg]
    assert count == 0


def test_postgres_upsert_executes_valid_statement():
    mock_conn = MagicMock()
    mock_begin = MagicMock()
    mock_begin.__enter__.return_value = mock_conn

    with patch("energy_dash.core.db.engine.begin", return_value=mock_begin):
        records = [{"id": 1, "name": "A", "val": 100}]
        count = postgres_upsert(DummyModel, records, index_elements=["id"], update_columns=["val"])  # type: ignore[call-arg]
        assert count == 1
        mock_conn.execute.assert_called_once()
