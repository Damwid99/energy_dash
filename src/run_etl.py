from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.common.database import Base, engine
from src.etl.extract.pse_api import fetch_and_save_cen, fetch_and_save_rce
from src.etl.extract.tge_api import fetch_and_save_tge

WARSAW_TZ = ZoneInfo("Europe/Warsaw")


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


if __name__ == "__main__":
    print("[ETL] Start workera...")
    init_db()

    task_cen()
    task_daily_market_data()

    scheduler = BlockingScheduler(timezone=WARSAW_TZ)

    scheduler.add_job(
        task_cen,
        trigger=CronTrigger(hour="7-18", minute="0,30", timezone=WARSAW_TZ),
        id="cen_peak",
        name="CEN co 30 minut w szczycie",
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

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("[ETL] Zatrzymano scheduler.")
