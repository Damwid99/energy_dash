from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func

from src.common.database import Base


class DAPriceForecast(Base):
    __tablename__ = "da_price_forecasts"

    datetime_utc = Column(DateTime(timezone=True), primary_key=True)
    model_version = Column(String, primary_key=True)

    forecast_pln_mwh = Column(Float, nullable=False)

    p05 = Column(Float)
    p10 = Column(Float)
    p25 = Column(Float)
    p50 = Column(Float)
    p75 = Column(Float)
    p90 = Column(Float)
    p95 = Column(Float)
    mc_n_paths = Column(Integer)

    mlflow_run_id = Column(String)
    created_at_utc = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
