FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data

WORKDIR /app

# ----- deps -----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ----- app code -----
COPY . .

# ----- volume for JSON “DB” -----
VOLUME ["/app/data"]

EXPOSE 8456
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8456"]
