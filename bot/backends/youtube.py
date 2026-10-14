import os
import glob
import shutil
import asyncio
import logging
from typing import Optional
import yt_dlp

from bot.config import config

logger = logging.getLogger(__name__)

MASTER_COOKIE_FILE = "/home/botuser/app/cookies.txt"

def _sync_yt_dlp_download(url: str, output_path: str, use_proxy: bool) -> bool:
    # Убираем расширение для outtmpl, чтобы yt-dlp корректно смержил в .mp4
    base_path, _ = os.path.splitext(output_path)
    outtmpl_path = f"{base_path}.%(ext)s"
    temp_cookie_path = None

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'extractor_args': {
            'youtubepot-bgutilhttp': {
                'base_url': ['http://bgutil-pot:4416']
            }
        },
        'socket_timeout': 30,
        'max_filesize': 150 * 1024 * 1024,
        'quiet': False,
        'no_warnings': False,
        'outtmpl': outtmpl_path,
    }

    # Защита cookies.txt от гонки потоков: копируем во временный файл
    if os.path.exists(MASTER_COOKIE_FILE) and os.path.getsize(MASTER_COOKIE_FILE) > 0:
        temp_cookie_path = f"{base_path}_cookies.txt"
        try:
            shutil.copyfile(MASTER_COOKIE_FILE, temp_cookie_path)
            ydl_opts['cookiefile'] = temp_cookie_path
        except Exception as e:
            logger.warning(f"Failed to copy cookies file: {e}")

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

        # Проверяем, что итоговый файл действительно создан на диске
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

async def download_via_ytdlp(url: str, output_path: str, retries: int = 2) -> Optional[str]:
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