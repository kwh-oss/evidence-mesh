FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src

EXPOSE 8010

CMD ["python", "-m", "uvicorn", "evidence_mesh.leader_app:app", "--host", "0.0.0.0", "--port", "8010"]
