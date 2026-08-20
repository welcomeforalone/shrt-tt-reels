FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m botuser
USER botuser
WORKDIR /home/botuser/app

ENV PATH="/home/botuser/.local/bin:${PATH}"

COPY --chown=botuser:botuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=botuser:botuser bot/ ./bot/

CMD ["python", "-m", "bot.main"]