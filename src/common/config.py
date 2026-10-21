from src.config.settings import get_settings

settings = get_settings()

DATABASE_URL = settings.db.url
DB_USER = settings.db.user
DB_HOST = settings.db.host
DB_PORT = settings.db.port
DB_NAME = settings.db.db
