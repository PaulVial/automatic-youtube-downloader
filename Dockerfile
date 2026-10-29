FROM denoland/deno:bin-2.9.7 AS deno
FROM mwader/static-ffmpeg:9.0.2 AS ffmpeg

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Deno : runtime JavaScript dont yt-dlp a besoin pour YouTube.
COPY --from=deno /deno /usr/local/bin/deno
COPY --from=ffmpeg /ffmpeg /ffprobe /usr/local/bin/

RUN useradd --create-home app
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY automatic_youtube_downloader ./automatic_youtube_downloader

USER app
ENTRYPOINT ["python", "-m", "automatic_youtube_downloader"]
