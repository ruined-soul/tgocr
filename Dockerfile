FROM python:3.11-slim

WORKDIR /app

# Install tesseract
RUN apt-get update && apt-get install -y tesseract-ocr libsm6 libxext6 libxrender-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Light mode: no unnecessary cache, minimal layers
ENV PYTHONUNBUFFERED=1
CMD ["python", "bot.py"]
