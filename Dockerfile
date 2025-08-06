FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg libflac-dev libjpeg-dev libmagic-dev git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "--workers=3", "--worker-class=gevent", "--bind=0.0.0.0:5000", "run:app"]
