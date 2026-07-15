FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt pyproject.toml ./
COPY src ./src
COPY sql ./sql

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir -e .

RUN mkdir -p /app/logs

EXPOSE 8000

CMD ["sh", "-c", "uvicorn uyjoy_etl.web_app:app --host 0.0.0.0 --port ${PORT:-8000}"]
