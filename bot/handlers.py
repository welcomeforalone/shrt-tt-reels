import asyncio
import logging
import os
import re
from collections.abc import Callable

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.media_group import MediaGroupBuilder

from bot.config import config
from bot.downloader import process_download
from bot.i18n import get_language_keyboard, get_translator, set_user_language, t
from bot.utils import check_rate_limit, compress_video, get_file_size_mb, is_safe_url

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    _ = get_translator(user.id if user else None, user.language_code if user else None)
    await message.answer(
        _("welcome"),
        reply_markup=get_language_keyboard(),
        parse_mode="Markdown"
    )


@router.message(Command("lang", "language"))
async def cmd_lang(message: Message):
    user = message.from_user
    _ = get_translator(user.id if user else None, user.language_code if user else None)
    await message.answer(
        _("choose_lang"),
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
        if callback.message:
            await callback.message.edit_text(
                new_text,
                reply_markup=get_language_keyboard(),
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.debug(f"Could not edit message on language switch: {e}")


async def _send_photo_carousel(
    message: Message,
    status_msg: Message,
    photos: list[str],
    _: Callable[..., str]
) -> None:
    """Отправляет набор фото альбомами (по 10 штук) или одиночным фото."""
    if len(photos) == 1:
        await status_msg.edit_text(_("uploading_photo"))
        await message.answer_photo(photo=FSInputFile(photos[0]))
    else:
        await status_msg.edit_text(_("uploading_photos"))
        chunk_size = config.album_chunk_size
        for i in range(0, len(photos), chunk_size):
            chunk = photos[i:i + chunk_size]
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


async def _send_video(
    message: Message,
    status_msg: Message,
    video_path: str,
    files_to_cleanup: list[str],
    _: Callable[..., str]
) -> None:
    """Проверяет размер видео, при необходимости сжимает и отправляет пользователю."""
    if not os.path.exists(video_path):
        await status_msg.edit_text(_("video_not_found"))
        return

    file_size = get_file_size_mb(video_path)
    final_path = video_path

    if file_size > config.max_video_size_mb:
        await status_msg.edit_text(_("compressing"))
        compressed_path = video_path.replace(".mp4", "_compressed.mp4")
        files_to_cleanup.append(compressed_path)

        success = await compress_video(video_path, compressed_path)

        if success and os.path.exists(compressed_path):
            final_path = compressed_path
            if get_file_size_mb(final_path) > config.telegram_max_size_mb:
                await status_msg.edit_text(_("too_large_after_compress"))
                return
        else:
            await status_msg.edit_text(_("compress_failed"))
            return

    await status_msg.edit_text(_("uploading_video"))
    await message.answer_video(video=FSInputFile(final_path), supports_streaming=True)
    try:
        await status_msg.delete()
    except Exception:
        pass


@router.message(F.text.regexp(r"https?://[^\s]+"))
async def handle_url(message: Message):
    user = message.from_user
    user_id = user.id if user else 0
    lang_code = user.language_code if user else None
    _ = get_translator(user_id, lang_code)

    # 1. Извлекаем чистый URL из текста
    match = re.search(r"https?://[^\s]+", message.text or "")
    if not match:
        return
    url = match.group(0)

    # 2. Rate limit ПЕРЕД любыми сетевыми и DNS операциями для защиты от флуда
    if not check_rate_limit(user_id, config.rate_limit_per_minute):
        await message.answer(_("rate_limit"))
        return

    # 3. Асинхронная проверка безопасности URL (SSRF, локальные IP, резолв в потоке)
    if not await is_safe_url(url):
        await message.answer(_("unsafe_url"))
        return

    status_msg = await message.answer(_("downloading"))
    files_to_cleanup: list[str] = []

    try:
        # 4. Общий таймаут на загрузку, чтобы зависший процесс не держал слот семафора
        try:
            downloaded_result = await asyncio.wait_for(
                process_download(url),
                timeout=config.download_timeout_seconds
            )
        except TimeoutError:
            logger.warning(f"Download timed out after {config.download_timeout_seconds}s for {url}")
            await status_msg.edit_text(_("download_timeout"))
            return

        if not downloaded_result:
            await status_msg.edit_text(_("download_failed"))
            return

        # 5. Обработка фото-карусели
        if isinstance(downloaded_result, list):
            files_to_cleanup.extend(downloaded_result)
            await _send_photo_carousel(message, status_msg, downloaded_result, _)
            return

        # 6. Обработка видеофайла
        files_to_cleanup.append(downloaded_result)
        await _send_video(message, status_msg, downloaded_result, files_to_cleanup, _)

    except Exception as e:
        logger.error(f"Handler error: {e}")
        try:
            await status_msg.edit_text(_("unexpected_error"))
        except Exception:
            pass
    finally:
        for path in set(files_to_cleanup):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    logger.error(f"Failed to delete temp file {path}: {e}")
