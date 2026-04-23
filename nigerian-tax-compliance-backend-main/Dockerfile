FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y `
    gcc `
    g++ `
    libpq-dev `
    poppler-utils `
    tesseract-ocr `
    libgl1 `
    libglib2.0-0 `
    && rm -rf /var/lib/apt/lists/*
COPY requirements-main.txt requirements-additional.txt ./
RUN pip install --upgrade pip --no-cache-dir
RUN pip install --no-cache-dir -r requirements-main.txt && `
    pip install --no-cache-dir -r requirements-additional.txt
COPY . .
RUN mkdir -p uploads/documents uploads/logos
RUN chmod +x start.sh
EXPOSE 8000
CMD ["./start.sh"]
