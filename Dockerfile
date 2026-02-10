FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-additional.txt requirements-dev.txt ./

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements-additional.txt && \
    pip install --no-cache-dir -r requirements-dev.txt

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]