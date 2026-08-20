FROM python:3.12-slim

# Установка системных зависимостей под root
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Создание и переключение на непривилегированного пользователя
RUN useradd -m botuser
USER botuser
WORKDIR /home/botuser/app

ENV PATH="/home/botuser/.local/bin:${PATH}"

# Установка Python-зависимостей
COPY --chown=botuser:botuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY --chown=botuser:botuser bot/ ./bot/

CMD ["python", "-m", "bot.main"]