import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.backends.tiktok import close_http_client
from bot.config import config
from bot.handlers import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)

async def main():
    bot = Bot(token=config.bot_token)
    dp = Dispatcher()

    dp.include_router(router)

    logging.info("Starting bot...")
    try:
        await dp.start_polling(bot)
    finally:
        logging.info("Shutting down bot session and resources...")
        await bot.session.close()
        await close_http_client()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped.")
