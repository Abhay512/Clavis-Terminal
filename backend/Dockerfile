FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Kolkata

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# data/ and .env are bind-mounted at run time so recordings and the daily
# access token survive a rebuild.
RUN mkdir -p data/bars data/signals data/meta

EXPOSE 8000

CMD ["python", "main.py", "--api"]
