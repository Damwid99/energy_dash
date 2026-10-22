import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


def build_retrying_session(
    total: int = 3,
    backoff_factor: float = 1,
    status_forcelist: tuple[int, ...] = (500, 502, 503, 504),
) -> requests.Session:
    """Sesja HTTP z automatycznym ponawianiem prób przy błędach 5xx."""
    http = requests.Session()
    retries = Retry(
        total=total,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist),
    )
    http.mount("https://", HTTPAdapter(max_retries=retries))
    return http
