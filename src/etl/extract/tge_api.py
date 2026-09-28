import re
import sys
import time
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from src.common.database import SessionLocal
from src.models_db.energy import EnergyPrice

TGE_URL = "https://tge.pl/energia-elektryczna-rdn"
WARSAW = ZoneInfo("Europe/Warsaw")

# TGE pozwala się cofnąć maksymalnie o ~60 dni (liczone od dzisiaj)
TGE_WINDOW_DAYS = 60
# Kursy Fixing II (15-minutowe) TGE publikuje ok. 13:50 - po 14:00 jest już doba D+1
TGE_PUBLISH_HOUR = 14


def latest_delivery_date(now: datetime = None) -> date:
    """Najnowsza doba dostawy, dla której są już dane Fixing II."""
    now = now or datetime.now(WARSAW)
    return now.date() + timedelta(days=1) if now.hour >= TGE_PUBLISH_HOUR else now.date()


def earliest_delivery_date(now: datetime = None) -> date:
    """Najstarsza doba dostawy dostępna na stronie TGE."""
    now = now or datetime.now(WARSAW)
    return now.date() - timedelta(days=TGE_WINDOW_DAYS - 1)


def _num(text: str):
    """'1 116,80' -> 1116.8 ; '-' -> None"""
    t = "".join(text.split())
    if t in ("", "-"):
        return None
    return float(t.replace(",", "."))


def _fetch_html(session: requests.Session, delivery_date: date) -> bytes:
    # dateShow=27-09-2026 zwraca tabelę z dostawą na 28-09-2026.
    trading_date = delivery_date - timedelta(days=1)
    params = {"dateShow": trading_date.strftime("%d-%m-%Y"), "dateAction": "prev"}
    last_error = None
    for attempt in range(3):
        try:
            response = session.get(TGE_URL, params=params, timeout=30)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            last_error = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"nie udało się pobrać strony TGE: {last_error}")


def _expected_quarters(d: date) -> int:
    """96 w zwykłej dobie, 92 / 100 w dniach zmiany czasu."""
    start = datetime.combine(d, dtime.min, tzinfo=WARSAW).astimezone(UTC)
    end = datetime.combine(d + timedelta(days=1), dtime.min, tzinfo=WARSAW).astimezone(UTC)
    return int((end - start) / timedelta(minutes=15))


def parse_tge_day(html: bytes, delivery_date: date) -> list[dict]:
    """Zamienia HTML strony TGE na listę 15-minutowych rekordów dla doby dostawy."""
    table = BeautifulSoup(html, "lxml").find("table", id="rdn")
    if table is None:
        raise ValueError("brak tabeli #rdn na stronie TGE")

    headers = [
        " ".join(th.get_text().split())
        for th in table.find("thead").find_all("tr")[1].find_all("th")
    ]
    if (
        len(headers) != 17
        or headers[2] != "Kurs [PLN/MWh]"
        or headers[3] != "Wolumen [MW]"
        or headers[7] != "Kurs jednolity [PLN/MWh]"
        or headers[8] != "Wolumen [MW]"
    ):
        raise ValueError(f"zmienił się układ tabeli TGE: {headers}")

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cells = [" ".join(td.get_text().split()) for td in tr.find_all("td")]
        m = re.match(r"^(\d{4}-\d{2}-\d{2})_Q\d{2}:\d{2}", cells[0]) if cells else None
        if not m:
            continue
        if m.group(1) != delivery_date.isoformat():
            raise ValueError(f"strona dotyczy dostawy {m.group(1)}, a oczekiwano {delivery_date}")
        rows.append(cells)

    expected = _expected_quarters(delivery_date)
    if len(rows) != expected:
        raise ValueError(f"{delivery_date}: {len(rows)} kwadransów, oczekiwano {expected}")

    day_start = datetime.combine(delivery_date, dtime.min, tzinfo=WARSAW).astimezone(UTC)
    result = []
    for i, c in enumerate(rows):
        result.append(
            {
                # etykieta Q00:15 = kwadrans 00:00-00:15 -> do bazy idzie POCZĄTEK kwadransa
                "datetime_utc": day_start + timedelta(minutes=15 * i),
                "fixing_1_pln_mwh": _num(c[2]),
                "fixing_1_volume": _num(c[3]),
                "fixing_2_pln_mwh": _num(c[7]),
                "fixing_2_volume": _num(c[8]),
            }
        )
    return result


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def save_tge_day(session, rows: list[dict]) -> int:
    """Upsert jednej doby. Rusza tylko kolumny TGE - rb_pln_mwh i rce_pln_mwh zostają."""
    day_from = rows[0]["datetime_utc"]
    day_to = rows[-1]["datetime_utc"]
    existing = {
        _as_utc(r.datetime_utc): r
        for r in session.query(EnergyPrice)
        .filter(EnergyPrice.datetime_utc >= day_from, EnergyPrice.datetime_utc <= day_to)
        .all()
    }
    for row in rows:
        record = existing.get(row["datetime_utc"])
        if record is None:
            session.add(EnergyPrice(**row))
        else:
            record.fixing_1_pln_mwh = row["fixing_1_pln_mwh"]
            record.fixing_1_volume = row["fixing_1_volume"]
            record.fixing_2_pln_mwh = row["fixing_2_pln_mwh"]
            record.fixing_2_volume = row["fixing_2_volume"]
    return len(rows)


def fetch_and_save_tge(
    start_date: str = None, end_date: str = None, days_back: int = 3
) -> list[date]:
    """
    Pobiera 15-minutowe ceny Fixing I / Fixing II z TGE (RDN) i zapisuje/aktualizuje je w bazie.

    Parametry (daty to daty DOSTAWY):
    - start_date (opcjonalny): format 'YYYY-MM-DD'
    - end_date (opcjonalny): format 'YYYY-MM-DD' (domyślnie: najnowsza opublikowana doba)
    - days_back: ile dób wstecz od najnowszej pobrać, jeśli nie podano start_date

    Zwraca listę dób, które się nie udały (pusta = wszystko OK).
    Dni pobieramy zawsze od nowa (upsert), więc pominięty dzień uzupełni się sam.
    """
    latest = latest_delivery_date()
    end = min(date.fromisoformat(end_date), latest) if end_date else latest
    start = date.fromisoformat(start_date) if start_date else end - timedelta(days=days_back)

    earliest = earliest_delivery_date()
    if start < earliest:
        print(f"TGE udostępnia ~{TGE_WINDOW_DAYS} dni wstecz - zaczynam od {earliest}.")
        start = earliest
    if start > end:
        print(f"Pusty zakres dat: {start} > {end}.")
        return []

    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    print(f"Pobieranie danych TGE (Fixing I/II) za dostawy: {start} do {end} ({len(days)} dób)...")

    http = requests.Session()
    http.headers["User-Agent"] = "tge-etl/1.0 (python-requests)"
    session = SessionLocal()
    failed = []
    saved_total = 0
    try:
        for d in days:
            try:
                rows = parse_tge_day(_fetch_html(http, d), d)
                if all(r["fixing_2_pln_mwh"] is None for r in rows):
                    print(f"{d}: Fixing II jeszcze nieopublikowany (zapisuję to, co jest).")
                saved = save_tge_day(session, rows)
                session.commit()
                saved_total += saved
                print(f"{d}: zapisano {saved} kwadransów.")
            except Exception as e:
                session.rollback()
                failed.append(d)
                print(f"{d}: BŁĄD - {e}")
            time.sleep(1)
    finally:
        session.close()

    print(f"Zaktualizowano {saved_total} punktów TGE w bazie danych.")
    if failed:
        print("Nieudane dni:", ", ".join(map(str, failed)))
    return failed


if __name__ == "__main__":
    failed_days = fetch_and_save_tge(days_back=3)

    session = SessionLocal()
    try:
        latest_rows = (
            session.query(EnergyPrice)
            .filter(EnergyPrice.fixing_2_pln_mwh.isnot(None))
            .order_by(EnergyPrice.datetime_utc.desc())
            .limit(5)
            .all()
        )
        print("\nOstatnie 5 rekordów z Fixing II w bazie:")
        for row in latest_rows:
            print(
                f"UTC: {row.datetime_utc} | Fixing I: {row.fixing_1_pln_mwh} | "
                f"Fixing II: {row.fixing_2_pln_mwh} PLN/MWh"
            )
    finally:
        session.close()

    sys.exit(1 if failed_days else 0)
