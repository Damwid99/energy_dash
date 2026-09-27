from datetime import UTC, date, datetime, timedelta

import requests

from src.common.database import SessionLocal
from src.models_db.energy import EnergyPrice


def fetch_and_save_rce(
    start_date: str = None, end_date: str = None, days_back: int = 3
):
    """
    Pobiera dane RCE z API PSE i zapisuje/aktualizuje je w bazie.

    Parametry:
    - start_date (opcjonalny): format 'YYYY-MM-DD'
    - end_date (opcjonalny): format 'YYYY-MM-DD'
    - days_back: ile dni wstecz od dzisiaj pobrać, jeśli nie podano dat ręcznie
    """
    today = date.today()
    if not end_date:
        end_date = today.strftime("%Y-%m-%d")
    if not start_date:
        start_date = (today - timedelta(days=days_back)).strftime("%Y-%m-%d")

    # Filtrujemy po właściwej kolumnie: business_date
    filter_query = f"business_date ge '{start_date}' and business_date le '{end_date}'"
    url = f"https://api.raporty.pse.pl/api/rce-pln?$filter={filter_query}"

    try:
        print(f"Pobieranie danych RCE z PSE za okres: {start_date} do {end_date}...")
        response = requests.get(url, timeout=20)
        response.raise_for_status()

        payload = response.json()
        data = payload.get("value", [])

        if not data:
            print(
                f"Brak danych zwróconych przez PSE dla zakresu {start_date} - {end_date}."
            )
            return

        session = SessionLocal()
        saved_count = 0

        for row in data:
            # PSE zwraca gotowy znacznik czasu w UTC np. '2024-06-13 22:15:00'
            utc_str = row.get("dtime_utc")
            if not utc_str:
                continue

            naive_dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
            utc_dt = naive_dt.replace(tzinfo=UTC)

            rce_val = row.get("rce_pln")
            if rce_val is None:
                continue
            rce_price = float(rce_val)

            # Upsert do bazy
            existing = session.query(EnergyPrice).filter_by(datetime_utc=utc_dt).first()
            if existing:
                existing.rce_pln_mwh = rce_price
            else:
                new_price = EnergyPrice(
                    datetime_utc=utc_dt,
                    rce_pln_mwh=rce_price,
                )
                session.add(new_price)

            saved_count += 1

        session.commit()
        print(f"Pomyślnie zaktualizowano {saved_count} punktów RCE w bazie danych.")

    except Exception as e:
        print(f"Błąd podczas pobierania lub zapisu RCE: {e}")
        if "session" in locals():
            session.rollback()
    finally:
        if "session" in locals():
            session.close()


if __name__ == "__main__":
    fetch_and_save_rce(days_back=3)

    session = SessionLocal()
    try:
        latest = (
            session.query(EnergyPrice)
            .order_by(EnergyPrice.datetime_utc.desc())
            .limit(5)
            .all()
        )
        print("\nOstatnie 5 rekordów w bazie:")
        for row in latest:
            print(f"UTC: {row.datetime_utc} | RCE: {row.rce_pln_mwh} PLN/MWh")
    finally:
        session.close()
