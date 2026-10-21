import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from energy_dash.core.db import Base, engine
from src.etl.extract.news_rss import fetch_and_save_news
from src.etl.extract.pse_api import (
    fetch_and_save_cen,
    fetch_and_save_rce,
    fetch_and_save_oze,
    fetch_and_save_oze_actuals,
)
from src.etl.extract.tge_api import fetch_and_save_tge
from src.etl.transform.news_digest import digest_exists, generate_digest, today_utc
from src.models_db import energy, news, renewables, forecasts
from src.ml.fix_I_forecast.evaluation import evaluate_forecasts
from energy_dash.core.settings import get_settings

settings = get_settings()
WARSAW_TZ = settings.tz
NEWS_HOUR = settings.scheduler.news_hour

_news_lock = threading.Lock()


def task_daily_forecast():
    from src.ml.fix_I_forecast.predictor import run_daily_forecast

    print("[ETL] Uruchamianie prognozy cen Fixing I...")
    try:
        run_daily_forecast()
    except Exception as e:
        print(f"[ETL] Prognoza nie powiodła się: {e}")


def task_evaluate_forecasts(days_back: int):
    try:
        n = evaluate_forecasts(days_back)
        print(f"[ETL] Zewaluowano {n} runów prognoz.")
    except Exception as e:
        print(f"[ETL] Ewaluacja prognoz nie powiodła się: {e}")


def init_db():
    print("[ETL] Inicjalizacja bazy: sprawdzanie i tworzenie tabel...")
    Base.metadata.create_all(bind=engine)
    print("[ETL] Tabele są gotowe.")


def task_cen():
    print("[ETL] Uruchamianie pobierania CEN...")
    fetch_and_save_cen(days_back=2)


def task_daily_market_data():
    print("[ETL] Uruchamianie pobierania RCE i TGE (codzienny batch)...")
    fetch_and_save_rce(days_back=5)
    fetch_and_save_tge(days_back=3)
    fetch_and_save_oze_actuals(days_back=5)
    task_evaluate_forecasts(days_back=4)


def task_forecast_pipeline():
    print("[ETL] Pobieranie prognoz OZE na jutro i prognoza cen...")
    fetch_and_save_oze(days_back=0, days_forward=1)
    task_daily_forecast()


def task_news_daily():
    """Newsy raz dziennie: pobranie RSS + podsumowanie.

    Uruchamiane o 7:00, a potem co godzinę do 11:00 oraz przy starcie workera po 7:00.
    Kolejne uruchomienia coś robią tylko wtedy, gdy podsumowania na dziś jeszcze nie ma
    (np. awaria LLM o 7:00 albo restart kontenera).
    """
    if not _news_lock.acquire(blocking=False):
        print("[ETL] Newsy już się generują, pomijam.")
        return
    try:
        if digest_exists(today_utc()):
            print("[ETL] Podsumowanie newsów na dziś już jest, pomijam.")
            return
        print("[ETL] Pobieranie newsów...")
        fetch_and_save_news(days_back=2)
        print("[ETL] Generowanie podsumowania newsów...")
        generate_digest()
    finally:
        _news_lock.release()


if __name__ == "__main__":
    print("[ETL] Start workera...")
    init_db()

    task_cen()
    task_daily_market_data()
    fetch_and_save_oze(days_back=3, days_forward=1)

    scheduler = BlockingScheduler(timezone=WARSAW_TZ)

    scheduler.add_job(
        task_cen,
        trigger=CronTrigger(hour="7-18", minute="0,30", timezone=WARSAW_TZ),
        id="cen_peak",
        name="CEN co 30 minut w szczycie",
    )

    scheduler.add_job(
        task_forecast_pipeline,
        trigger=CronTrigger(hour="7-12", minute="2,17,32,47", timezone=WARSAW_TZ),
        id="daily_forecast",
        name="Prognoza Fixing I (pobranie + prognoza co 15 min)",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=600,
    )

    scheduler.add_job(
        task_cen,
        trigger=CronTrigger(hour="0-6,19-23", minute="0", timezone=WARSAW_TZ),
        id="cen_offpeak",
        name="CEN co 1h poza szczytem",
    )

    scheduler.add_job(
        task_daily_market_data,
        trigger=CronTrigger(hour=14, minute=0, timezone=WARSAW_TZ),
        id="daily_rce_tge",
        name="RCE i TGE o 14:00",
    )

    scheduler.add_job(
        task_news_daily,
        trigger=CronTrigger(hour=f"{NEWS_HOUR}-11", minute=0, timezone=WARSAW_TZ),
        id="news_daily",
        name="Newsy: digest raz dziennie o 7:00 (+ ponowienia do 11:00 tylko gdy brak)",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )

    if datetime.now(WARSAW_TZ).hour >= NEWS_HOUR:
        scheduler.add_job(
            task_news_daily,
            trigger="date",
            run_date=datetime.now(WARSAW_TZ),
            id="news_catchup",
            name="Newsy: nadrobienie po starcie",
            misfire_grace_time=600,
        )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("[ETL] Zatrzymano scheduler.")
