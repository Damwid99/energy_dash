FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV STREAMLIT_SERVER_HEADLESS=true
ENV UV_HTTP_TIMEOUT=300

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY src/ /app/src/

EXPOSE 8501

CMD ["streamlit", "run", "src/app/main.py"]