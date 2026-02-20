FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    poppler-utils \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (better caching)
COPY requirements-main.txt requirements-additional.txt requirements-dev.txt ./

# Upgrade pip
RUN pip install --upgrade pip --no-cache-dir

# Install dependencies (combine into one layer)
RUN pip install --no-cache-dir -r requirements-main.txt && \
    pip install --no-cache-dir -r requirements-additional.txt && \
    pip install --no-cache-dir -r requirements-dev.txt

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p uploads/documents uploads/logos

# Expose port
EXPOSE 8000

# Correct module path
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]