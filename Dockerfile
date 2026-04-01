FROM python:3.11-slim

WORKDIR /app

# System dependencies for playwright, lxml, and kaleido
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        chromium-driver \
        libglib2.0-0 \
        libnss3 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxrandr2 \
        libgbm1 \
        libasound2 \
        libpango-1.0-0 \
        libcairo2 \
        fonts-liberation \
        wget \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers (chromium only to keep image small)
RUN playwright install chromium

# Copy source
COPY . .

# Data directories (mounted as volumes in production)
RUN mkdir -p data/ohlcv data/company data/tickers data/predictions \
             data_us/ohlcv

EXPOSE 8501

# Default: run dashboard. Override CMD to run pipeline instead.
CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.address=0.0.0.0", "--server.port=8501"]
