FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app

ARG ACPS_COMMUNITY_TAG=v2.2.0
RUN python -m pip install --no-cache-dir \
    "https://github.com/AIP-PUB/ACPs-community/archive/refs/tags/${ACPS_COMMUNITY_TAG}.zip#subdirectory=acps-sdk" \
    cryptography \
    jcs

COPY src /app/src

EXPOSE 8010

CMD ["python", "-m", "uvicorn", "evidence_mesh.leader_app:app", "--host", "0.0.0.0", "--port", "8010"]
