import asyncio
import logging
from aiogram import Bot, Dispatcher

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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())