import os
import re
import logging
from typing import List
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.filters import CommandStart
from aiogram.utils.media_group import MediaGroupBuilder

from bot.config import config
from bot.utils import check_rate_limit, get_file_size_mb, compress_video, is_safe_url
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
    
    # Extract clean URL from text
    match = re.search(r"https?://[^\s]+", message.text)
    if not match:
        return
    url = match.group(0)

    # Validate URL against SSRF and unsupported schemes
    if not is_safe_url(url):
        await message.answer("❌ Invalid or forbidden URL.")
        return

    if not check_rate_limit(user_id, config.rate_limit_per_minute):
        await message.answer("Rate limit exceeded. Please wait a minute.")
        return

    status_msg = await message.answer("Downloading... ⏳")
    files_to_cleanup: List[str] = []

    try:
        downloaded_result = await process_download(url)
        
        if not downloaded_result:
            await status_msg.edit_text("❌ Failed to download. All backends failed (or API is temporarily down).")
            return

        # --- Handle Photo Carousel ---
        if isinstance(downloaded_result, list):
            files_to_cleanup.extend(downloaded_result)
            if not downloaded_result:
                await status_msg.edit_text("❌ No photos found to download.")
                return

            if len(downloaded_result) == 1:
                await status_msg.edit_text("Uploading photo to Telegram... 📤")
                await message.answer_photo(photo=FSInputFile(downloaded_result[0]))
            else:
                await status_msg.edit_text("Uploading photos to Telegram... 📤")
                chunk_size = 10
                for i in range(0, len(downloaded_result), chunk_size):
                    chunk = downloaded_result[i:i + chunk_size]
                    if len(chunk) == 1:
                        await message.answer_photo(photo=FSInputFile(chunk[0]))
                    else:
                        media_group = MediaGroupBuilder()
                        for photo_path in chunk:
                            media_group.add_photo(media=FSInputFile(photo_path))
                        await message.answer_media_group(media=media_group.build())

            try:
                await status_msg.delete()
            except Exception:
                pass
            return
        # -----------------------------

        # --- Handle Standard Video ---
        downloaded_path = downloaded_result
        files_to_cleanup.append(downloaded_path)
        
        if not os.path.exists(downloaded_path):
            await status_msg.edit_text("❌ Failed to download the video.")
            return
            
        file_size = get_file_size_mb(downloaded_path)
        final_path = downloaded_path
        
        if file_size > config.max_video_size_mb:
            await status_msg.edit_text("Video is large, compressing... 🗜️")
            compressed_path = downloaded_path.replace(".mp4", "_compressed.mp4")
            files_to_cleanup.append(compressed_path)
            
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
        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Handler error: {e}")
        try:
            await status_msg.edit_text("❌ An unexpected error occurred.")
        except Exception:
            pass
    finally:
        for path in set(files_to_cleanup):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.error(f"Failed to delete temp file {path}: {e}")