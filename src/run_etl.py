import time

import schedule

from src.common.database import Base, engine
from src.etl.extract.pse_api import fetch_and_save_rce


def init_db():
    """Tworzy tabele w bazie danych (jeśli jeszcze nie istnieją)."""
    print("[ETL] Inicjalizacja bazy: sprawdzanie i tworzenie tabel...")
    Base.metadata.create_all(bind=engine)
    print("[ETL] Tabele są gotowe.")


def run_pipeline():
    print("[ETL] Uruchamianie zaplanowanego pobierania danych RCE...")
    fetch_and_save_rce(days_back=3)


if __name__ == "__main__":
    print("[ETL] Start workera...")
    init_db()
    run_pipeline()

    # 3. Harmonogram: odpytuj co godzinę w 15. minucie
    schedule.every().hour.at(":15").do(run_pipeline)

    while True:
        schedule.run_pending()
        time.sleep(1)
