FROM python:3.12-slim-bookworm

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "python-telegram-bot[webhooks]==22.8" "rapidocr-onnxruntime==1.2.3"
COPY src/ src/
COPY cli.py .
ENV PYTHONUNBUFFERED=1 OCR_ENGINE=rapidocr TZ=Asia/Jakarta
CMD ["python", "cli.py", "run-bot", "--webhook"]
