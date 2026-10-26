FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir faster-whisper==1.2.1 fastapi==0.115.6 uvicorn==0.34.0
WORKDIR /app
COPY app.py /app/app.py
ENV HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=/models/hf-cache OMP_NUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8090","--no-access-log"]
