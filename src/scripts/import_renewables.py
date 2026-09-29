import sys
from pathlib import Path

import pandas as pd
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from src.common.database import Base, SessionLocal, engine
from src.models_db.renewables import RenewableFarm, RenewableGeneration

RAW_DATA_DIR = BASE_DIR / "data" / "raw"

FARMS = {
    "farma_wiatrowa_Pomorze.csv": {
        "code": "wind_pomorze",
        "name": "Pomorze",
        "technology": "wind",
        "capacity_mw": 50,
        "region": "Pomorze",
        "latitude": 54.3421,
        "longitude": 17.5512,
        "description": "Typowa polska farma lądowa; zmienne wiatry i średnia autokorelacja.",
    },
    "farma_wiatrowa_Baltyk.csv": {
        "code": "wind_baltyk",
        "name": "Bałtyk",
        "technology": "wind",
        "capacity_mw": 120,
        "region": "Bałtyk",
        "latitude": 55.0543,
        "longitude": 17.2031,
        "description": "Przykładowa farma offshore; wysoka korelacja i mniejsza zmienność.",
    },
    "farma_wiatrowa_Wielkopolska.csv": {
        "code": "wind_wielkopolska",
        "name": "Wielkopolska",
        "technology": "wind",
        "capacity_mw": 25,
        "region": "Wielkopolska",
        "latitude": 52.1265,
        "longitude": 17.1508,
        "description": "Mniejsza farma lądowa o niższej średniej wietrzności.",
    },
    "farma_sloneczna_Wielkopolska.csv": {
        "code": "solar_wielkopolska",
        "name": "Wielkopolska",
        "technology": "solar",
        "capacity_mw": 150,
        "region": "Wielkopolska",
        "latitude": 51.9832,
        "longitude": 16.8845,
        "description": "Przykładowa farma utility-scale.",
    },
    "farma_sloneczna_Podkarpacie.csv": {
        "code": "solar_podkarpacie",
        "name": "Podkarpacie",
        "technology": "solar",
        "capacity_mw": 40,
        "region": "Podkarpacie",
        "latitude": 49.9512,
        "longitude": 21.8523,
        "description": "Przykładowa farma z południa Polski.",
    },
    "farma_sloneczna_Dachowa_Gizycko.csv": {
        "code": "solar_gizycko",
        "name": "Dachowa Giżycko",
        "technology": "solar",
        "capacity_mw": 5,
        "region": "Giżycko",
        "latitude": 54.0345,
        "longitude": 21.7612,
        "description": "Mała przykładowa instalacja na północy Polski.",
    },
}


def create_tables() -> None:
    Base.metadata.create_all(bind=engine)


def get_or_create_farm(session, metadata: dict) -> RenewableFarm:
    farm = session.query(RenewableFarm).filter(RenewableFarm.code == metadata["code"]).one_or_none()

    if farm is None:
        farm = RenewableFarm(**metadata)
        session.add(farm)
        session.flush()
    else:
        for key, value in metadata.items():
            setattr(farm, key, value)

        session.flush()

    return farm


def load_csv(path: Path, farm_id: int) -> int:
    df = pd.read_csv(path)

    required_columns = {
        "datetime",
        "generation [MWh]",
        "generation_forecast [MWh]",
    }

    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(f"{path.name}: brakuje kolumn: {sorted(missing_columns)}")

    local_datetime = pd.to_datetime(
        df["datetime"],
        format="%Y-%m-%d %H:%M:%S",
    )

    local_datetime = local_datetime.dt.tz_localize(
        "Europe/Warsaw",
        ambiguous=False,
        nonexistent="NaT",
    )

    invalid_rows = local_datetime.isna()

    if invalid_rows.any():
        print(
            f"{path.name}: pomijam {invalid_rows.sum()} "
            "rekordów przypadających na nieistniejący czas DST."
        )

    df = df.loc[~invalid_rows].copy()
    local_datetime = local_datetime.loc[~invalid_rows]

    utc_datetime = local_datetime.dt.tz_convert("UTC")

    rows = pd.DataFrame(
        {
            "farm_id": farm_id,
            "datetime_utc": [timestamp.to_pydatetime() for timestamp in utc_datetime],
            "generation_mwh": pd.to_numeric(
                df["generation [MWh]"],
                errors="raise",
            ),
            "generation_forecast_mwh": pd.to_numeric(
                df["generation_forecast [MWh]"],
                errors="raise",
            ),
            "source_file": path.name,
        }
    )

    records = rows.to_dict(orient="records")

    with SessionLocal() as session:
        batch_size = 1000

        for start in range(0, len(records), batch_size):
            batch = records[start : start + batch_size]

            statement = insert(RenewableGeneration).values(batch)

            statement = statement.on_conflict_do_update(
                index_elements=[
                    RenewableGeneration.farm_id,
                    RenewableGeneration.datetime_utc,
                ],
                set_={
                    "generation_mwh": statement.excluded.generation_mwh,
                    "generation_forecast_mwh": statement.excluded.generation_forecast_mwh,
                    "source_file": statement.excluded.source_file,
                },
            )

            session.execute(statement)

        session.commit()

    return len(records)


def main() -> None:
    create_tables()

    total_rows = 0

    with SessionLocal() as session:
        for filename, metadata in FARMS.items():
            path = RAW_DATA_DIR / filename

            if not path.exists():
                raise FileNotFoundError(f"Nie znaleziono pliku: {path}")

            farm = get_or_create_farm(session, metadata)
            session.commit()

            rows_count = load_csv(path, farm.id)
            total_rows += rows_count

            print(f"{filename}: zapisano {rows_count} rekordów dla farmy {farm.code}")

    print(f"\nŁącznie zapisano lub zaktualizowano: {total_rows} rekordów.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, IntegrityError) as error:
        print(f"BŁĄD: {error}", file=sys.stderr)
        sys.exit(1)
