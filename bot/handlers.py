import os
import re
import logging
from typing import List
from aiogram import Router, F
from aiogram.types import Message, FSInputFile, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.utils.media_group import MediaGroupBuilder

from bot.config import config
from bot.utils import check_rate_limit, get_file_size_mb, compress_video, is_safe_url
from bot.downloader import process_download
from bot.i18n import t, get_language_keyboard, set_user_language

logger = logging.getLogger(__name__)
router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    lang_code = message.from_user.language_code
    text = t("welcome", user_id=user_id, user_language_code=lang_code)
    await message.answer(
        text,
        reply_markup=get_language_keyboard(),
        parse_mode="Markdown"
    )

@router.message(Command("lang", "language"))
async def cmd_lang(message: Message):
    user_id = message.from_user.id
    lang_code = message.from_user.language_code
    text = t("choose_lang", user_id=user_id, user_language_code=lang_code)
    await message.answer(
        text,
        reply_markup=get_language_keyboard(),
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("set_lang:"))
async def handle_set_language(callback: CallbackQuery):
    lang = callback.data.split(":")[1]
    user_id = callback.from_user.id
    set_user_language(user_id, lang)
    
    await callback.answer(t("lang_selected", lang=lang))
    
    new_text = f"{t('lang_selected', lang=lang)}\n\n{t('welcome', lang=lang)}"
    try:
        await callback.message.edit_text(
            new_text,
            reply_markup=get_language_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.debug(f"Could not edit message on language switch: {e}")

@router.message(F.text.regexp(r"https?://[^\s]+"))
async def handle_url(message: Message):
    user_id = message.from_user.id
    lang_code = message.from_user.language_code
    
    # Extract clean URL from text
    match = re.search(r"https?://[^\s]+", message.text)
    if not match:
        return
    url = match.group(0)

    # Validate URL against SSRF and unsupported schemes
    if not is_safe_url(url):
        await message.answer(t("unsafe_url", user_id=user_id, user_language_code=lang_code))
        return

    if not check_rate_limit(user_id, config.rate_limit_per_minute):
        await message.answer(t("rate_limit", user_id=user_id, user_language_code=lang_code))
        return

    status_msg = await message.answer(t("downloading", user_id=user_id, user_language_code=lang_code))
    files_to_cleanup: List[str] = []

    try:
        downloaded_result = await process_download(url)
        
        if not downloaded_result:
            await status_msg.edit_text(t("download_failed", user_id=user_id, user_language_code=lang_code))
            return

        # --- Handle Photo Carousel ---
        if isinstance(downloaded_result, list):
            files_to_cleanup.extend(downloaded_result)
            if not downloaded_result:
                await status_msg.edit_text(t("no_photos_found", user_id=user_id, user_language_code=lang_code))
                return

            if len(downloaded_result) == 1:
                await status_msg.edit_text(t("uploading_photo", user_id=user_id, user_language_code=lang_code))
                await message.answer_photo(photo=FSInputFile(downloaded_result[0]))
            else:
                await status_msg.edit_text(t("uploading_photos", user_id=user_id, user_language_code=lang_code))
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
            await status_msg.edit_text(t("video_not_found", user_id=user_id, user_language_code=lang_code))
            return
            
        file_size = get_file_size_mb(downloaded_path)
        final_path = downloaded_path
        
        if file_size > config.max_video_size_mb:
            await status_msg.edit_text(t("compressing", user_id=user_id, user_language_code=lang_code))
            compressed_path = downloaded_path.replace(".mp4", "_compressed.mp4")
            files_to_cleanup.append(compressed_path)
            
            success = await compress_video(downloaded_path, compressed_path)
            
            if success and os.path.exists(compressed_path):
                final_path = compressed_path
                if get_file_size_mb(final_path) > 50:
                    await status_msg.edit_text(t("too_large_after_compress", user_id=user_id, user_language_code=lang_code))
                    return
            else:
                await status_msg.edit_text(t("compress_failed", user_id=user_id, user_language_code=lang_code))
                return

        await status_msg.edit_text(t("uploading_video", user_id=user_id, user_language_code=lang_code))
        video_file = FSInputFile(final_path)
        await message.answer_video(video=video_file, supports_streaming=True)
        try:
            await status_msg.delete()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Handler error: {e}")
        try:
            await status_msg.edit_text(t("unexpected_error", user_id=user_id, user_language_code=lang_code))
        except Exception:
            pass
    finally:
        for path in set(files_to_cleanup):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.error(f"Failed to delete temp file {path}: {e}")