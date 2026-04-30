FROM python:3.13.3-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# - gcc + libpq-dev: diperlukan oleh psycopg2 (PostgreSQL driver)
# - curl: diperlukan oleh curl-cffi
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Buat virtual environment di dalam container
RUN python -m venv /app/.venv

# Aktifkan venv untuk semua perintah selanjutnya
ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# Install dependencies ke dalam venv
# Copy requirements terlebih dahulu agar layer di-cache Docker (lebih cepat rebuild)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy seluruh source code
COPY . .

# Jalankan bot
CMD ["python", "main.py"]
