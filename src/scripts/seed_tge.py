"""Jednorazowe zasilenie tabeli energy_prices historią z TGE (Fixing I, Fixing II, wolumeny).

TGE trzyma na stronie tylko ~60 dni wstecz, więc to jest maksimum, jakie da się pobrać.
Skrypt jest idempotentny - można go uruchamiać wielokrotnie (upsert, nie dubluje).
Nie rusza kolumn rce_pln_mwh / rb_pln_mwh.

Uruchamianie z katalogu głównego projektu:
    uv run python -m scripts.tge_history
    uv run python -m scripts.tge_history --from 2026-09-01 --to 2026-09-27

Daty to daty DOSTAWY (YYYY-MM-DD).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func

from src.common.database import SessionLocal
from src.etl.extract.tge_api import fetch_and_save_tge
from src.models_db.energy import EnergyPrice


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--from", dest="start", help="pierwsza doba dostawy (domyślnie: początek okna TGE)"
    )
    parser.add_argument(
        "--to", dest="end", help="ostatnia doba dostawy (domyślnie: najnowsza opublikowana)"
    )
    args = parser.parse_args()

    # Bez --from podajemy datę z dawnej przeszłości - fetch_and_save_tge przytnie ją
    # do początku okna TGE (~60 dni) i wypisze ostrzeżenie.
    failed = fetch_and_save_tge(start_date=args.start or "2000-01-01", end_date=args.end)

    session = SessionLocal()
    try:
        total, first, last, f1, f2 = session.query(
            func.count(EnergyPrice.datetime_utc),
            func.min(EnergyPrice.datetime_utc),
            func.max(EnergyPrice.datetime_utc),
            func.count(EnergyPrice.fixing_1_pln_mwh),
            func.count(EnergyPrice.fixing_2_pln_mwh),
        ).one()
        print(f"\nW bazie: {total} wierszy, od {first} do {last} (UTC)")
        print(f"  z Fixing I: {f1}, z Fixing II: {f2}")
    finally:
        session.close()

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
