import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=BASE_DIR / ".env")

DB_USER = os.getenv("POSTGRES_USER", "energy_user")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD", "super_secret_password_123")

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = os.getenv("POSTGRES_PORT", "5458")
DB_NAME = os.getenv("POSTGRES_DB", "energy_db")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
