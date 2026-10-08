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
from src.etl.extract.pse_api import (
    fetch_and_save_cen,
    fetch_and_save_oze,
    fetch_and_save_oze_actuals,
    fetch_and_save_rce,
)
from src.models_db.energy import EnergyPrice, PseOzeActual, PseOzeForecast


def seed_rce():
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


def seed_cen():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--from", dest="start", help="pierwsza doba dostawy (YYYY-MM-DD)")
    parser.add_argument("--to", dest="end", help="ostatnia doba dostawy (YYYY-MM-DD)")
    args = parser.parse_args()

    print("Rozpoczynam seedowanie danych CEN z PSE")

    fetch_and_save_cen(start_date=args.start, end_date=args.end, days_back=60)

    session = SessionLocal()
    try:
        total, first, last, cen_count = session.query(
            func.count(EnergyPrice.datetime_utc),
            func.min(EnergyPrice.datetime_utc),
            func.max(EnergyPrice.datetime_utc),
            func.count(EnergyPrice.cen_pln_mwh),
        ).one()

        print(f"\nW bazie: {total} wierszy (punkty 15-minutowe), od {first} do {last} (UTC)")
        print(f"  z przypisaną ceną CEN: {cen_count}")

    finally:
        session.close()


def seed_oze():
    parser = argparse.ArgumentParser(
        description="Seedowanie OZE/KSE", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--from", dest="start", help="pierwsza doba dostawy (YYYY-MM-DD)")
    parser.add_argument("--to", dest="end", help="ostatnia doba dostawy (YYYY-MM-DD)")
    args = parser.parse_args()

    print("Rozpoczynam seedowanie danych OZE/KSE z PSE")
    fetch_and_save_oze(start_date=args.start, end_date=args.end, days_back=60)

    session = SessionLocal()
    try:
        total, first, last, pv_count, wind_count = session.query(
            func.count(PseOzeForecast.issue_datetime_utc),
            func.min(PseOzeForecast.issue_datetime_utc),
            func.max(PseOzeForecast.issue_datetime_utc),
            func.count(PseOzeForecast.pv_fcst_pse),
            func.count(PseOzeForecast.wind_fcst_pse),
        ).one()

        print(f"\nW bazie (tabela pse_forecasts): {total} wierszy, od {first} do {last} (UTC)")
        print(f"  z przypisaną prognozą PV: {pv_count}")
        print(f"  z przypisaną prognozą Wiatru: {wind_count}")

    finally:
        session.close()


def seed_oze_actuals():
    parser = argparse.ArgumentParser(
        description="Seedowanie rzeczywistych danych OZE/KSE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--from", dest="start", help="pierwsza doba dostawy (YYYY-MM-DD)")
    parser.add_argument("--to", dest="end", help="ostatnia doba dostawy (YYYY-MM-DD)")
    args = parser.parse_args()

    print("Rozpoczynam seedowanie RZECZYWISTYCH danych OZE/KSE z PSE (his-wlk-cal)")
    fetch_and_save_oze_actuals(start_date=args.start, end_date=args.end, days_back=60)

    session = SessionLocal()
    try:
        total, first, last, pv_count, wind_count = session.query(
            func.count(PseOzeActual.datetime_utc),
            func.min(PseOzeActual.datetime_utc),
            func.max(PseOzeActual.datetime_utc),
            func.count(PseOzeActual.pv_actual_pse),
            func.count(PseOzeActual.wind_actual_pse),
        ).one()

        print(f"\nW bazie (tabela pse_actuals): {total} wierszy, od {first} do {last} (UTC)")
        print(f"  z zapisanym wykonaniem PV: {pv_count}")
        print(f"  z zapisanym wykonaniem Wiatru: {wind_count}")

    finally:
        session.close()


if __name__ == "__main__":
    # seed_rce()
    # seed_cen()
    # seed_oze()
    seed_oze_actuals()
