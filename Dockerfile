# macDiag - MB W221/X164 OBD-II web tool
# Image carries ONLY code + a small seed dataset. The real data (CBF library,
# ecu_db.sqlite, unlock_db.json) lives in the mounted /data volume so it can be
# extended later without rebuilding the image.
FROM python:3.11-slim

WORKDIR /app

# Python deps
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Application code
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY tools/ /app/tools/

# Seed dataset (used to populate an empty /data volume on first run)
COPY docker/seed/ /app/seed/
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Data lives in the volume; paths point there (see ecu_db.py / unlock.py / varcoding.py)
ENV MACDIAG_MODE=sim \
    MACDIAG_DB_PATH=/data/ecu_db.sqlite \
    MACDIAG_UNLOCK_DB=/data/unlock_db.json \
    MACDIAG_CBF_DIR=/data/cbf \
    MACDIAG_CFF_DIR=/data/cff \
    MACDIAG_VSG_DIR=/data/vsg \
    PYTHONUNBUFFERED=1

VOLUME ["/data"]
EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
