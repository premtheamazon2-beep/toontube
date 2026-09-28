FROM python:3.11-slim

# ffmpeg for video assembly, fontconfig + Tamil/Latin fonts for subtitle burn-in
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg fontconfig fonts-lohit-taml fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

ENV PORT=10000
EXPOSE 10000

# 1 worker (jobs run in background threads within it), generous timeout since
# a request can trigger a long-running video-generation thread.
CMD gunicorn -w 1 --threads 8 -b 0.0.0.0:$PORT --timeout 600 app:app
