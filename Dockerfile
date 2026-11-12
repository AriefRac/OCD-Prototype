FROM python:3.12-slim-bookworm

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "python-telegram-bot[webhooks]==22.8" "rapidocr-onnxruntime==1.2.3" "onnxruntime==1.31.1"
COPY src/ src/
COPY cli.py .
ENV PYTHONUNBUFFERED=1 OCR_ENGINE=rapidocr TZ=Asia/Jakarta
ENV ORT_INTRA_OP_NUM_THREADS=1 ORT_INTER_OP_NUM_THREADS=1 OPENCV_FOR_THREADS_NUM=1 OPENBLAS_NUM_THREADS=1
CMD ["python", "cli.py", "run-bot", "--webhook"]
