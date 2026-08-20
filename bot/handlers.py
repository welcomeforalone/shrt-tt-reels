import os
import logging
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import CommandStart
from aiogram.utils.media_group import MediaGroupBuilder

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
        downloaded_result = await process_download(url)
        
        if not downloaded_result:
            await status_msg.edit_text("❌ Failed to download. All backends failed (or API is temporarily down).")
            return
            
        # --- Handle Photo Carousel ---
        if isinstance(downloaded_result, list):
            await status_msg.edit_text("Uploading photos to Telegram... 📤")
            media_group = MediaGroupBuilder()
            for photo_path in downloaded_result:
                media_group.add_photo(media=FSInputFile(photo_path))
            
            await message.answer_media_group(media=media_group.build())
            await status_msg.delete()
            
            for photo_path in downloaded_result:
                if os.path.exists(photo_path):
                    os.remove(photo_path)
            return
        # -----------------------------

        # --- Handle Standard Video ---
        downloaded_path = downloaded_result
        if not os.path.exists(downloaded_path):
            await status_msg.edit_text("❌ Failed to download the video.")
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
        await message.answer_video(video=video_file, supports_streaming=True)
        await status_msg.delete()

    except Exception as e:
        logger.error(f"Handler error: {e}")
        await status_msg.edit_text("❌ An unexpected error occurred.")
    finally:
        for path in [downloaded_path, compressed_path]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.error(f"Failed to delete temp file {path}: {e}")