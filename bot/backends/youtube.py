import asyncio
import glob
import logging
import os
import shutil

import yt_dlp

from bot.config import config

logger = logging.getLogger(__name__)


def _get_cookie_file_path() -> str | None:
    """Находит файл cookies, если он существует и не пустой."""
    candidates = [
        config.cookies_file_path,
        "/home/botuser/app/cookies.txt",
        "cookies.txt",
    ]
    for path in candidates:
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
    return None


def _sync_yt_dlp_download(url: str, output_path: str, use_proxy: bool) -> bool:
    base_path, _ = os.path.splitext(output_path)
    outtmpl_path = f"{base_path}.%(ext)s"
    temp_cookie_path = None

    def _filter_duration(info_dict, *, incomplete):
        duration = info_dict.get('duration')
        if duration and duration > config.max_youtube_duration_seconds:
            return f"Video duration ({duration}s) exceeds max limit of {config.max_youtube_duration_seconds}s"
        return None

    # Ограничиваем разрешение до 1080p и отдаем приоритет mp4/h264,
    # чтобы избежать загрузки 4K/AV1, которые перегружают CPU при сжатии
    ydl_opts = {
        'format': (
            'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/'
            'bestvideo[height<=1080]+bestaudio/'
            'best[height<=1080]/'
            'best'
        ),
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'extractor_args': {
            'youtubepot-bgutilhttp': {
                'base_url': ['http://bgutil-pot:4416']
            }
        },
        'socket_timeout': 30,
        'max_filesize': 150 * 1024 * 1024,
        'match_filter': _filter_duration,
        'quiet': False,
        'no_warnings': False,
        'outtmpl': outtmpl_path,
    }

    # Изоляция cookies: копируем во временный файл для защиты от гонок потоков
    master_cookie = _get_cookie_file_path()
    if master_cookie:
        temp_cookie_path = f"{base_path}_cookies.txt"
        try:
            shutil.copyfile(master_cookie, temp_cookie_path)
            ydl_opts['cookiefile'] = temp_cookie_path
            logger.info(f"Loaded cookies from {master_cookie} ({os.path.getsize(master_cookie)} bytes)")
        except Exception as e:
            logger.warning(f"Failed to copy cookies file: {e}")
    else:
        logger.info("No cookies file found or file is empty; continuing without cookies")

    if use_proxy:
        ydl_opts['proxy'] = getattr(config, 'warp_proxy_url', 'socks5://warp:1080')

    def _cleanup_partial_files():
        for f in glob.glob(f"{glob.escape(base_path)}.*"):
            if f != temp_cookie_path and os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if not os.path.exists(output_path):
            _cleanup_partial_files()
            return False

        return True
    except Exception as e:
        logger.warning(f"yt-dlp failed (proxy={use_proxy}): {e}")
        _cleanup_partial_files()
        return False
    finally:
        if temp_cookie_path and os.path.exists(temp_cookie_path):
            try:
                os.remove(temp_cookie_path)
            except Exception as e:
                logger.warning(f"Failed to remove temp cookie file {temp_cookie_path}: {e}")


async def download_via_ytdlp(url: str, output_path: str, retries: int = 2) -> str | None:
    """
    Загружает медиа через yt-dlp.
    Сначала пытается через прокси WARP с повторами, а в случае неудачи — напрямую.
    """
    logger.info("Trying yt-dlp via WARP proxy")

    for attempt in range(retries):
        success = await asyncio.to_thread(_sync_yt_dlp_download, url, output_path, True)
        if success:
            return output_path

        logger.info(f"Retrying yt-dlp WARP... attempt {attempt + 1}")
        await asyncio.sleep(2 ** attempt)

    logger.info("Trying yt-dlp WITHOUT proxy as last resort")
    success = await asyncio.to_thread(_sync_yt_dlp_download, url, output_path, False)
    if success:
        return output_path

    return None
