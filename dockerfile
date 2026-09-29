FROM python:3.12-slim

WORKDIR /app

# системные зависимости (на всякий случай)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# каталог для SQLite
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV TZ=Europe/Moscow

# при старте: сиды (если БД пустая) + бот
CMD ["sh", "-c", "python seed.py && python main.py"]