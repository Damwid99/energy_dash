import time
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

import requests
from energy_dash.core.http import build_retrying_session

from energy_dash.core.db import SessionLocal
from energy_dash.features.power_system.models import PseOzeActual, PseOzeForecast


def fetch_and_save_oze_actuals(
    start_date: str | None = None, end_date: str | None = None, days_back: int = 5
):
    """
    Pobiera rzeczywiste wykonanie zapotrzebowania, generacji OZE i wymiany z API PSE
    (endpoint his-wlk-cal) i zapisuje je w bazie.
    """
    today = date.today()

    end = date.fromisoformat(end_date) if end_date else today
    start = date.fromisoformat(start_date) if start_date else today - timedelta(days=days_back)

    if start > end:
        print(f"Pusty zakres dat od {start} do {end}")
        return

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    print(f"Pobieranie RZECZYWISTYCH danych OZE/KSE za dostawy: {start} do {end} ({len(days)} dób)")

    http = build_retrying_session()
    session = SessionLocal()
    total_saved = 0

    try:
        for d in days:
            d_str = d.strftime("%Y-%m-%d")
            filter_query = f"business_date eq '{d_str}'"
            url = f"https://api.raporty.pse.pl/api/his-wlk-cal?$filter={filter_query}"

            try:
                response = http.get(url, timeout=20)
                response.raise_for_status()
                data = response.json().get("value", [])

                if not data:
                    print(f"{d_str}: Brak danych rzeczywistych OZE/KSE")
                    continue

                parsed_rows: list[dict[str, Any]] = []
                for row in data:
                    dtime_utc_str = row.get("dtime_utc")
                    pv_actual = row.get("pv")
                    wind_actual = row.get("wi")
                    demand_actual = row.get("demand")

                    swm_p = row.get("swm_p")
                    swm_np = row.get("swm_np")

                    if (
                        not dtime_utc_str
                        or pv_actual is None
                        or wind_actual is None
                        or demand_actual is None
                    ):
                        continue

                    exchange_actual = float(swm_p or 0.0) + float(swm_np or 0.0)

                    naive_dt = datetime.strptime(dtime_utc_str, "%Y-%m-%d %H:%M:%S")
                    dt_utc = naive_dt.replace(tzinfo=UTC) - timedelta(minutes=15)

                    parsed_rows.append(
                        {
                            "datetime_utc": dt_utc,
                            "pv_actual_pse": float(pv_actual),
                            "wind_actual_pse": float(wind_actual),
                            "demand_actual_pse": float(demand_actual),
                            "exchange_actual_pse": exchange_actual,
                            "resload_actual_pse": float(demand_actual)
                            - float(pv_actual)
                            - float(wind_actual),
                        }
                    )

                if not parsed_rows:
                    continue

                day_from = parsed_rows[0]["datetime_utc"]
                day_to = parsed_rows[-1]["datetime_utc"]

                existing: dict[Any, PseOzeActual] = {
                    r.datetime_utc: r
                    for r in session.query(PseOzeActual)
                    .filter(
                        PseOzeActual.datetime_utc >= day_from,
                        PseOzeActual.datetime_utc <= day_to,
                    )
                    .all()
                }

                saved = 0
                for row in parsed_rows:
                    dt = row["datetime_utc"]
                    record = existing.get(dt)

                    if record is None:
                        record = PseOzeActual(
                            datetime_utc=dt,
                            pv_actual_pse=row["pv_actual_pse"],
                            wind_actual_pse=row["wind_actual_pse"],
                            demand_actual_pse=row["demand_actual_pse"],
                            exchange_actual_pse=row["exchange_actual_pse"],
                            resload_actual_pse=row["resload_actual_pse"],
                        )
                        session.add(record)
                    else:
                        record.pv_actual_pse = row["pv_actual_pse"]
                        record.wind_actual_pse = row["wind_actual_pse"]
                        record.demand_actual_pse = row["demand_actual_pse"]
                        record.exchange_actual_pse = row["exchange_actual_pse"]
                        record.resload_actual_pse = row["resload_actual_pse"]

                    saved += 1

                session.commit()
                total_saved += saved
                print(f"{d_str}: zapisano {saved} punktów RZECZYWISTYCH (OZE/KSE).")

            except Exception as e:
                print(f"{d_str}: BŁĄD - {e}")
                session.rollback()

            time.sleep(0.5)

    finally:
        session.close()
        print(f"Zaktualizowano łącznie {total_saved} RZECZYWISTYCH punktów OZE/KSE w bazie danych.")


def _fetch_kse_demand_hourly(http: requests.Session, d_str: str) -> dict[datetime, float]:
    """
    Pobiera load_fcst z kse-load (kwadranse) dla doby handlowej i agreguje do godzin
    (średnia z 4 kwadransów, bo to moc w MW). Klucz: początek godziny UTC.
    """
    url = f"https://api.raporty.pse.pl/api/kse-load?$filter=business_date eq '{d_str}'"
    response = http.get(url, timeout=20)
    response.raise_for_status()
    data = response.json().get("value", [])

    quarters = defaultdict(list)
    for row in data:
        utc_str = row.get("dtime_utc")
        load_fcst = row.get("load_fcst")
        if not utc_str or load_fcst is None:
            continue
        ts = datetime.strptime(utc_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC) - timedelta(
            minutes=15
        )
        quarters[ts.replace(minute=0, second=0, microsecond=0)].append(float(load_fcst))

    return {hour: sum(vals) / 4 for hour, vals in quarters.items() if len(vals) == 4}


def fetch_and_save_oze(
    start_date: str | None = None,
    end_date: str | None = None,
    days_back: int = 5,
    days_forward: int = 2,
    keep_past_fcst: bool = False,
):
    """
    Pobiera prognozy dla RDN i zapisuje je w bazie (PseOzeForecast):
    - pv, wind, exchange z API PSE (endpoint pk5l-wp),
    - demand z API PSE (endpoint kse-load, load_fcst, średnia godzinowa z kwadransów),
    - resload = demand - pv - wind.
    keep_past_fcst=True: nie nadpisuje istniejących prognoz dla minionych dób.
    """
    today = date.today()

    end = date.fromisoformat(end_date) if end_date else today + timedelta(days=days_forward)
    start = date.fromisoformat(start_date) if start_date else today - timedelta(days=days_back)

    if start > end:
        print(f"Pusty zakres dat od {start} do {end}")
        return

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    print(f"Pobieranie prognoz KSE za dostawy: {start} do {end} ({len(days)} dób)")

    http = build_retrying_session()
    session = SessionLocal()
    total_saved = 0
    total_no_demand = 0

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

                demand_by_hour = _fetch_kse_demand_hourly(http, d_str)

                parsed_rows: list[dict[str, Any]] = []
                no_demand = 0
                for row in data:
                    issued_utc_str = row.get("plan_dtime_utc")
                    publication_ts_str = row.get("publication_ts_utc")
                    pv_fcst_pse = row.get("fcst_pv_tot_gen")
                    wind_fcst_pse = row.get("fcst_wi_tot_gen")
                    exchange_fcst_pse = row.get("planned_exchange")
                    if (
                        not issued_utc_str
                        or publication_ts_str is None
                        or pv_fcst_pse is None
                        or wind_fcst_pse is None
                        or exchange_fcst_pse is None
                    ):
                        continue

                    naive_dt = datetime.strptime(issued_utc_str, "%Y-%m-%d %H:%M:%S")
                    issued_utc_dt = naive_dt.replace(tzinfo=UTC) - timedelta(hours=1)

                    demand_fcst_pse = demand_by_hour.get(issued_utc_dt)
                    if demand_fcst_pse is None:
                        no_demand += 1
                        continue

                    publication_utc = datetime.strptime(
                        publication_ts_str.split(".")[0], "%Y-%m-%d %H:%M:%S"
                    ).replace(tzinfo=UTC)
                    pv_fcst_pse = float(pv_fcst_pse)
                    wind_fcst_pse = float(wind_fcst_pse)
                    exchange_fcst_pse = float(exchange_fcst_pse)
                    resload_fcst_pse = demand_fcst_pse - pv_fcst_pse - wind_fcst_pse
                    parsed_rows.append(
                        {
                            "issue_datetime_utc": issued_utc_dt,
                            "publication_datetime_utc": publication_utc,
                            "pv_fcst_pse": pv_fcst_pse,
                            "wind_fcst_pse": wind_fcst_pse,
                            "demand_fcst_pse": demand_fcst_pse,
                            "exchange_fcst_pse": exchange_fcst_pse,
                            "resload_fcst_pse": resload_fcst_pse,
                        }
                    )

                total_no_demand += no_demand
                if no_demand:
                    print(f"{d_str}: pominięto {no_demand} godz. bez popytu z kse-load")

                if not parsed_rows:
                    continue
                day_from: datetime = min(
                    cast(datetime, r["issue_datetime_utc"]) for r in parsed_rows
                )
                day_to: datetime = max(cast(datetime, r["issue_datetime_utc"]) for r in parsed_rows)

                existing: dict[Any, PseOzeForecast] = {
                    r.issue_datetime_utc: r
                    for r in session.query(PseOzeForecast)
                    .filter(
                        cast(Any, PseOzeForecast.issue_datetime_utc >= day_from),
                        cast(Any, PseOzeForecast.issue_datetime_utc <= day_to),
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
                            resload_fcst_pse=row["resload_fcst_pse"],
                        )
                        session.add(record)
                    else:
                        if keep_past_fcst and d < today:
                            continue
                        record.publication_datetime_utc = row["publication_datetime_utc"]
                        record.pv_fcst_pse = row["pv_fcst_pse"]
                        record.wind_fcst_pse = row["wind_fcst_pse"]
                        record.demand_fcst_pse = row["demand_fcst_pse"]
                        record.exchange_fcst_pse = row["exchange_fcst_pse"]
                        record.resload_fcst_pse = row["resload_fcst_pse"]
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
        print(
            f"Zaktualizowano łącznie {total_saved} punktów OZE/KSE w bazie danych "
            f"(pominięto {total_no_demand} godz. bez popytu)."
        )
