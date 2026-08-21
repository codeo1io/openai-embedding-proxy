FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app \
    && mkdir -p /data \
    && chown app:app /data

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./

USER app

EXPOSE 18473

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "18473", "--no-server-header"]
