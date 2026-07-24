FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml ./
COPY sql ./sql
COPY src ./src

RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir .

EXPOSE 10000

CMD ["sh", "-c", "python -m uyjoy_etl.cli migrate && python -m uyjoy_etl.cli train-valuation-model --days 30 || echo 'Model training skipped; packaged model will be used'; exec uvicorn uyjoy_etl.web_app:app --host 0.0.0.0 --port ${PORT:-10000}"]
