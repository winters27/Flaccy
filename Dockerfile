FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    ffmpeg libflac-dev libjpeg-dev libmagic-dev git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY OrpheusDL /app/OrpheusDL
COPY app /app/app
COPY scripts /app/scripts
COPY run.py /app/
COPY gunicorn.conf.py /app/

RUN chmod +x /app/scripts/*.sh

EXPOSE 5000

# Use sync workers instead of gevent for better threading compatibility
CMD ["gunicorn", "--config", "gunicorn.conf.py", "run:app"]
