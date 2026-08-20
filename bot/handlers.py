import os
import logging
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import CommandStart

from bot.config import config
from bot.utils import check_rate_limit, get_file_size_mb, compress_video
from bot.downloader import process_download

logger = logging.getLogger(__name__)
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Send me a link from TikTok, Instagram Reels, or YouTube Shorts, "
        "and I will download it without a watermark."
    )

@router.message(F.text.regexp(r"https?://[^\s]+"))
async def handle_url(message: Message):
    user_id = message.from_user.id
    url = message.text.strip()
    
    if not check_rate_limit(user_id, config.rate_limit_per_minute):
        await message.answer("Rate limit exceeded. Please wait a minute.")
        return

    status_msg = await message.answer("Downloading... ⏳")
    downloaded_path = None
    compressed_path = None

    try:
        downloaded_path = await process_download(url)
        
        if not downloaded_path or not os.path.exists(downloaded_path):
            await status_msg.edit_text("❌ Failed to download the video. All backends failed.")
            return
            
        file_size = get_file_size_mb(downloaded_path)
        final_path = downloaded_path
        
        if file_size > config.max_video_size_mb:
            await status_msg.edit_text("Video is large, compressing... 🗜️")
            compressed_path = downloaded_path.replace(".mp4", "_compressed.mp4")
            success = await compress_video(downloaded_path, compressed_path)
            
            if success and os.path.exists(compressed_path):
                final_path = compressed_path
                if get_file_size_mb(final_path) > 50:
                    await status_msg.edit_text("❌ Video is still too large for Telegram after compression.")
                    return
            else:
                await status_msg.edit_text("❌ Failed to compress video.")
                return

        await status_msg.edit_text("Uploading to Telegram... 📤")
        video_file = FSInputFile(final_path)
        await message.answer_video(video=video_file)
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Handler error: {e}")
        await status_msg.edit_text("❌ An unexpected error occurred.")
    finally:
        # Guaranteed cleanup
        for path in [downloaded_path, compressed_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.error(f"Failed to delete temp file {path}: {e}")