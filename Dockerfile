FROM python:3.12-slim

# Установка системных зависимостей (ffmpeg для компрессии видео)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Создание и переключение на непривилегированного пользователя для безопасности
RUN useradd -m -u 1000 botuser
USER botuser
WORKDIR /home/botuser/app

ENV PATH="/home/botuser/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Установка Python-зависимостей
COPY --chown=botuser:botuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY --chown=botuser:botuser bot/ ./bot/

CMD ["python", "-m", "bot.main"]