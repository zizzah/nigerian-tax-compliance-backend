FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    poppler-utils \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# Copy all requirements files
COPY requirements-main_.txt requirements-additional.txt requirements-dev.txt ./

# Upgrade pip
RUN pip install --upgrade pip

# Install Python dependencies in order
RUN pip install --no-cache-dir -r requirements-main_.txt
RUN pip install --no-cache-dir -r requirements-additional.txt
RUN pip install --no-cache-dir -r requirements-dev.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Start command
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]