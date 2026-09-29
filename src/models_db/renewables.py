from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.common.database import Base


class RenewableFarm(Base):
    __tablename__ = "renewable_farms"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    technology: Mapped[str] = mapped_column(String(16))

    capacity_mw: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    region: Mapped[str | None] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Warsaw")
    description: Mapped[str | None] = mapped_column(String)


class RenewableGeneration(Base):
    __tablename__ = "renewable_generation"

    farm_id: Mapped[int] = mapped_column(
        ForeignKey("renewable_farms.id"),
        primary_key=True,
    )
    datetime_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
    )

    generation_mwh: Mapped[float | None] = mapped_column(Float)
    generation_forecast_mwh: Mapped[float | None] = mapped_column(Float)
    source_file: Mapped[str | None] = mapped_column(String(255))
