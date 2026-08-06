FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge --yes --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY tick_mvp ./tick_mvp
COPY migrations ./migrations
COPY scripts ./scripts

CMD ["uvicorn", "tick_mvp.app:app", "--host", "0.0.0.0", "--port", "8787"]
