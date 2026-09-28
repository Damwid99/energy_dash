"""
Jednorazowe zasilenie tabeli energy_prices historią z PSE (RCE).

Domyślnie pobiera 60 dni wstecz.
Skrypt jest idempotentny - można go uruchamiać wielokrotnie (upsert, nie dubluje).
Nie rusza pozostałych kolumn w tabeli.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func

from src.common.database import SessionLocal
from src.etl.extract.pse_api import fetch_and_save_rce
from src.models_db.energy import EnergyPrice


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--from", dest="start", help="pierwsza doba dostawy (YYYY-MM-DD)")
    parser.add_argument("--to", dest="end", help="ostatnia doba dostawy (YYYY-MM-DD)")
    args = parser.parse_args()

    print("Rozpoczynam seedowanie danych RCE z PSE")

    fetch_and_save_rce(start_date=args.start, end_date=args.end, days_back=60)

    session = SessionLocal()
    try:
        total, first, last, rce_count = session.query(
            func.count(EnergyPrice.datetime_utc),
            func.min(EnergyPrice.datetime_utc),
            func.max(EnergyPrice.datetime_utc),
            func.count(EnergyPrice.rce_pln_mwh),
        ).one()

        print(f"\nW bazie: {total} wierszy (punkty 15-minutowe), od {first} do {last} (UTC)")
        print(f"  z przypisaną ceną RCE: {rce_count}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
