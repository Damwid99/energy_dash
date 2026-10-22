from sqlalchemy import Column, DateTime, Float

from energy_dash.core.db import Base


class PseOzeForecast(Base):
    __tablename__ = "pse_forecasts"

    issue_datetime_utc = Column(DateTime(timezone=True), primary_key=True)
    publication_datetime_utc = Column(DateTime(timezone=True), index=True)

    pv_fcst_pse = Column(Float, nullable=True)
    wind_fcst_pse = Column(Float, nullable=True)
    demand_fcst_pse = Column(Float, nullable=True)
    exchange_fcst_pse = Column(Float, nullable=True)

    resload_fcst_pse = Column(Float, nullable=True)


class PseOzeActual(Base):
    __tablename__ = "pse_actuals"

    datetime_utc = Column(DateTime(timezone=True), primary_key=True)

    pv_actual_pse = Column(Float, nullable=True)
    wind_actual_pse = Column(Float, nullable=True)
    demand_actual_pse = Column(Float, nullable=True)
    exchange_actual_pse = Column(Float, nullable=True)
    resload_actual_pse = Column(Float, nullable=True)
