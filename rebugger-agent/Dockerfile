FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy


WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgstreamer-gl1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    libenchant-2-2 \
    libsecret-1-0 \
    libhyphen0 \
    man-db \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium

COPY . .

RUN mkdir -p data uploads

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]