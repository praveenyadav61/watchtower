FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WATCHTOWER_DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -m unittest discover -s tests \
    && rm -rf /app/tests /app/output /app/logs \
    && useradd --create-home --uid 10001 watchtower \
    && mkdir -p /data/logs /data/output \
    && chmod +x /app/run_container.sh \
    && chown -R watchtower:watchtower /app /data

USER watchtower

ENTRYPOINT ["/app/run_container.sh"]
