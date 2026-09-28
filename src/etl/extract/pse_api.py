import time
from datetime import UTC, date, datetime, timedelta

import requests

from src.common.database import SessionLocal
from src.models_db.energy import EnergyPrice


def fetch_and_save_rce(start_date: str = None, end_date: str = None, days_back: int = 3):
    """
    Pobiera dane RCE z API PSE i zapisuje/aktualizuje je w bazie.
    Działa iteracyjnie (dzień po dniu), aby ominąć limit 100 rekordów API PSE.
    """
    today = date.today()

    end = date.fromisoformat(end_date) if end_date else today
    start = date.fromisoformat(start_date) if start_date else today - timedelta(days=days_back)

    if start > end:
        print(f"Pusty zakres dat: {start} > {end}.")
        return

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    print(f"Pobieranie RCE z PSE za dostawy: {start} do {end} ({len(days)} dób)...")

    http = requests.Session()
    session = SessionLocal()
    total_saved = 0

    try:
        for d in days:
            d_str = d.strftime("%Y-%m-%d")
            filter_query = f"business_date eq '{d_str}'"
            url = f"https://api.raporty.pse.pl/api/rce-pln?$filter={filter_query}"

            try:
                response = http.get(url, timeout=20)
                response.raise_for_status()
                data = response.json().get("value", [])

                if not data:
                    print(f"{d_str}: Brak danych RCE.")
                    continue

                parsed_rows = []
                for row in data:
                    utc_str = row.get("dtime_utc")
                    rce_val = row.get("rce_pln")
                    if not utc_str or rce_val is None:
                        continue

                    naive_dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
                    utc_dt = naive_dt.replace(tzinfo=UTC) - timedelta(minutes=15)
                    rce_price = float(rce_val)

                    parsed_rows.append({"datetime_utc": utc_dt, "rce_pln_mwh": rce_price})

                if not parsed_rows:
                    continue

                day_from = parsed_rows[0]["datetime_utc"]
                day_to = parsed_rows[-1]["datetime_utc"]

                existing = {
                    r.datetime_utc: r
                    for r in session.query(EnergyPrice)
                    .filter(
                        EnergyPrice.datetime_utc >= day_from, EnergyPrice.datetime_utc <= day_to
                    )
                    .all()
                }

                saved = 0
                for row in parsed_rows:
                    dt = row["datetime_utc"]
                    record = existing.get(dt)
                    if record is None:
                        session.add(EnergyPrice(datetime_utc=dt, rce_pln_mwh=row["rce_pln_mwh"]))
                    else:
                        record.rce_pln_mwh = row["rce_pln_mwh"]
                    saved += 1

                session.commit()
                total_saved += saved
                print(f"{d_str}: zapisano {saved} kwadransów.")

            except Exception as e:
                print(f"{d_str}: BŁĄD - {e}")
                session.rollback()

            time.sleep(0.5)

    finally:
        session.close()

    print(f"Zaktualizowano łącznie {total_saved} punktów RCE w bazie danych.")


if __name__ == "__main__":
    fetch_and_save_rce(days_back=3)

    session = SessionLocal()
    try:
        latest = (
            session.query(EnergyPrice)
            .filter(EnergyPrice.rce_pln_mwh.isnot(None))
            .order_by(EnergyPrice.datetime_utc.desc())
            .limit(5)
            .all()
        )
        print("\nOstatnie 5 rekordów z RCE w bazie:")
        for row in latest:
            print(f"UTC: {row.datetime_utc} | RCE: {row.rce_pln_mwh} PLN/MWh")
    finally:
        session.close()
