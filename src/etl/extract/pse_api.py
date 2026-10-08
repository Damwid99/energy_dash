import time
from datetime import UTC, date, datetime, timedelta

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from src.common.database import SessionLocal
from src.models_db.energy import EnergyPrice, PseOzeForecast


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
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
    )
    http.mount("https://", HTTPAdapter(max_retries=retries))
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


def fetch_and_save_cen(start_date: str = None, end_date: str = None, days_back: int = 5):
    """
    Pobiera ceny CEN oraz status kontraktowania/bilansowania KSE z API PSE
    (endpoint price-cost / price-fcst) i zapisuje/aktualizuje w bazie.
    """
    today = date.today()

    end = date.fromisoformat(end_date) if end_date else today
    start = date.fromisoformat(start_date) if start_date else today - timedelta(days=days_back)

    if start > end:
        print(f"Pusty zakres dat od: {start} > {end}")
        return

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    print(f"Pobieranie CEN z PSE za dostawy: {start} do {end} ({len(days)} dób)...")

    # Automatyczne ponawianie prób przy błędach 500/502/503/504
    http = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
    )
    http.mount("https://", HTTPAdapter(max_retries=retries))

    session = SessionLocal()
    total_saved = 0

    try:
        for d in days:
            d_str = d.strftime("%Y-%m-%d")
            filter_query = f"business_date eq '{d_str}'"

            url = f"https://api.raporty.pse.pl/api/price-cost?$filter={filter_query}"

            try:
                response = http.get(url, timeout=20)
                response.raise_for_status()
                data = response.json().get("value", [])

                if not data and d == today:
                    url_fcst = f"https://api.raporty.pse.pl/api/price-fcst?$filter={filter_query}"
                    resp_fcst = http.get(url_fcst, timeout=20)
                    if resp_fcst.status_code == 200:
                        data = resp_fcst.json().get("value", [])

                if not data:
                    print(f"{d_str}: Brak danych CEN.")
                    continue

                parsed_rows = []
                for row in data:
                    utc_str = row.get("dtime_utc")

                    cen_value = row.get("cen_cost")
                    if cen_value is None:
                        cen_value = row.get("cen_fcst")

                    contract_status = row.get("imb_energy")

                    if not utc_str or cen_value is None:
                        continue

                    naive_dt = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S")
                    utc_dt = naive_dt.replace(tzinfo=UTC) - timedelta(minutes=15)
                    cen_price = float(cen_value)

                    parsed_rows.append(
                        {
                            "datetime_utc": utc_dt,
                            "cen_pln_mwh": cen_price,
                            "kse_contracting_status": contract_status,
                        }
                    )

                if not parsed_rows:
                    continue

                day_from = parsed_rows[0]["datetime_utc"]
                day_to = parsed_rows[-1]["datetime_utc"]

                existing = {
                    r.datetime_utc: r
                    for r in session.query(EnergyPrice)
                    .filter(
                        EnergyPrice.datetime_utc >= day_from,
                        EnergyPrice.datetime_utc <= day_to,
                    )
                    .all()
                }

                saved = 0
                for row in parsed_rows:
                    dt = row["datetime_utc"]
                    record = existing.get(dt)

                    if record is None:
                        record = EnergyPrice(
                            datetime_utc=dt,
                            cen_pln_mwh=row["cen_pln_mwh"],
                            kse_contracting_status=row["kse_contracting_status"],
                        )
                        session.add(record)
                    else:
                        record.cen_pln_mwh = row["cen_pln_mwh"]
                        record.kse_contracting_status = row["kse_contracting_status"]

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

    print(f"Zaktualizowano łącznie {total_saved} punktów CEN w bazie danych.")


def fetch_and_save_oze(
    start_date: str = None, end_date: str = None, days_back: int = 5, days_forward=2
):
    """
    Pobiera zapotrzebowanie mocy KSE z API PSE (endpoint kse-load) i zapisuje je w bazie.
    """
    today = date.today()

    end = date.fromisoformat(end_date) if end_date else today + timedelta(days=days_forward)
    start = date.fromisoformat(start_date) if start_date else today - timedelta(days=days_back)

    if start > end:
        print(f"Pusty zakres dat od {start} do {end}")
        return

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    print(f"Pobieranie zapotrzebowania KSE za dostawy: {start} do {end} ({len(days)} dób)")

    http = requests.Session()
    retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])

    http.mount("https://", HTTPAdapter(max_retries=retries))

    session = SessionLocal()
    total_saved = 0

    try:
        for d in days:
            d_str = d.strftime("%Y-%m-%d")
            filter_query = f"business_date eq '{d_str}'"

            url = f"https://api.raporty.pse.pl/api/pk5l-wp?$filter={filter_query}"
            try:
                response = http.get(url, timeout=20)
                response.raise_for_status()
                data = response.json().get("value", [])

                if not data:
                    print(f"{d_str}: Brak danych OZE/KSE")
                    continue

                parsed_rows = []
                for row in data:
                    issued_utc_str = row.get("plan_dtime_utc")
                    publication_ts_str = row.get("publication_ts_utc")
                    pv_fcst_pse = row.get("fcst_pv_tot_gen")
                    wind_fcst_pse = row.get("fcst_wi_tot_gen")
                    demand_fcst_pse = row.get("grid_demand_fcst")
                    exchange_fcst_pse = row.get("planned_exchange")
                    if (
                        not issued_utc_str
                        or publication_ts_str is None
                        or pv_fcst_pse is None
                        or wind_fcst_pse is None
                        or demand_fcst_pse is None
                        or exchange_fcst_pse is None
                    ):
                        continue

                    naive_dt = datetime.strptime(issued_utc_str, "%Y-%m-%d %H:%M:%S")
                    issued_utc_dt = naive_dt.replace(tzinfo=UTC) - timedelta(hours=1)
                    publication_utc = datetime.strptime(
                        publication_ts_str.split(".")[0], "%Y-%m-%d %H:%M:%S"
                    )
                    publication_utc = publication_utc.replace(tzinfo=UTC)
                    pv_fcst_pse = float(pv_fcst_pse)
                    wind_fcst_pse = float(wind_fcst_pse)
                    demand_fcst_pse = float(demand_fcst_pse)
                    exchange_fcst_pse = float(exchange_fcst_pse)
                    parsed_rows.append(
                        {
                            "issue_datetime_utc": issued_utc_dt,
                            "publication_datetime_utc": publication_utc,
                            "pv_fcst_pse": pv_fcst_pse,
                            "wind_fcst_pse": wind_fcst_pse,
                            "demand_fcst_pse": demand_fcst_pse,
                            "exchange_fcst_pse": exchange_fcst_pse,
                        }
                    )

                if not parsed_rows:
                    continue

                day_from = parsed_rows[0]["issue_datetime_utc"]
                day_to = parsed_rows[-1]["issue_datetime_utc"]

                existing = {
                    r.issue_datetime_utc: r
                    for r in session.query(PseOzeForecast)
                    .filter(
                        PseOzeForecast.issue_datetime_utc >= day_from,
                        PseOzeForecast.issue_datetime_utc <= day_to,
                    )
                    .all()
                }
                saved = 0
                for row in parsed_rows:
                    dt = row["issue_datetime_utc"]
                    record = existing.get(dt)

                    if record is None:
                        record = PseOzeForecast(
                            issue_datetime_utc=dt,
                            publication_datetime_utc=row["publication_datetime_utc"],
                            pv_fcst_pse=row["pv_fcst_pse"],
                            wind_fcst_pse=row["wind_fcst_pse"],
                            demand_fcst_pse=row["demand_fcst_pse"],
                            exchange_fcst_pse=row["exchange_fcst_pse"],
                        )
                        session.add(record)
                    else:
                        record.publication_datetime_utc = row["publication_datetime_utc"]
                        record.pv_fcst_pse = row["pv_fcst_pse"]
                        record.wind_fcst_pse = row["wind_fcst_pse"]
                        record.demand_fcst_pse = row["demand_fcst_pse"]
                        record.exchange_fcst_pse = row["exchange_fcst_pse"]
                    saved += 1
                session.commit()
                total_saved += saved
                print(f"{d_str}: zapisano {saved} punktów (OZE/KSE).")
            except Exception as e:
                print(f"{d_str}: BŁĄD - {e}")
                session.rollback()

            time.sleep(0.5)

    finally:
        session.close()
        print(f"Zaktualizowano łącznie {total_saved} punktów OZE/KSE w bazie danych.")


if __name__ == "__main__":
    fetch_and_save_oze(start_date="2026-10-10", end_date="2026-10-10")
