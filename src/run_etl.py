import time

import schedule


def job():
    print("ETL Worker żyje i czeka na zadania...")


# Symulacja: uruchamiaj co minutę
schedule.every(1).minutes.do(job)

if __name__ == "__main__":
    print("Startowanie workera ETL...")
    job()  # Wywołaj raz na start
    while True:
        schedule.run_pending()
        time.sleep(1)
