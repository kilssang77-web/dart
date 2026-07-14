FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl wget \
    # Playwright / Chromium system deps
    libasound2 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libgbm1 libglib2.0-0 libnspr4 libnss3 \
    libpango-1.0-0 libpangocairo-1.0-0 \
    libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 \
    libxdamage1 libxext6 libxfixes3 libxi6 libxrandr2 \
    libxrender1 libxss1 libxtst6 libxkbcommon0 libxshmfence1 \
    ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

COPY . .

CMD ["python", "main.py"]
