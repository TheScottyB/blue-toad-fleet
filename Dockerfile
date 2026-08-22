# Cloud Run's container contract is linux/amd64. An ARM-only image will not
# deploy. Custom containers are not upgraded by the managed Python runtime
# table — this FROM line is the production interpreter.
FROM --platform=linux/amd64 python:3.14-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PYTHONPATH=/app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn src.server:app --host 0.0.0.0 --port ${PORT:-8080}"]
