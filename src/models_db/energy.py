from sqlalchemy import Column, DateTime, Float

from src.common.database import Base


class EnergyPrice(Base):
    __tablename__ = "energy_prices"

    datetime_utc = Column(DateTime(timezone=True), primary_key=True)

    fixing_1_pln_mwh = Column(Float, nullable=True)
    fixing_2_pln_mwh = Column(Float, nullable=True)
    cen_pln_mwh = Column(Float, nullable=True)
    rce_pln_mwh = Column(Float, nullable=True)
    fixing_1_volume = Column(Float, nullable=True)
    fixing_2_volume = Column(Float, nullable=True)
    kse_contracting_status = Column(Float, nullable=True)

    def __repr__(self):
        return f"<EnergyPrice(datetime_utc='{self.datetime_utc}', rce='{self.rce_pln_mwh}')>"


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


class VEnergySummary(Base):
    __tablename__ = "v_energy_summary"

    datetime_utc = Column(DateTime(timezone=True), primary_key=True)

    pv_fcst_pse = Column(Float)
    wind_fcst_pse = Column(Float)
    demand_fcst_pse = Column(Float)
    exchange_fcst_pse = Column(Float)
    resload_fcst_pse = Column(Float)

    pv_actual_pse = Column(Float)
    wind_actual_pse = Column(Float)
    demand_actual_pse = Column(Float)
    exchange_actual_pse = Column(Float)
    resload_actual_pse = Column(Float)

    fixing_1_pln_mwh = Column(Float)
    fixing_2_pln_mwh = Column(Float)
    cen_pln_mwh = Column(Float)
