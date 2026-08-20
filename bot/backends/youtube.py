import asyncio
import logging
import os
from typing import Optional
import yt_dlp

from bot.config import config

logger = logging.getLogger(__name__)

def _sync_yt_dlp_download(url: str, output_path: str, use_proxy: bool) -> bool:
    # Убираем расширение для outtmpl, чтобы yt-dlp корректно смержил в .mp4
    base_path, _ = os.path.splitext(output_path)
    outtmpl_path = f"{base_path}.%(ext)s"

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'cookiefile': '/home/botuser/app/cookies.txt',
        'extractor_args': {
            'youtubepot-bgutilhttp': {
                'base_url': ['http://bgutil-pot:4416']
            }
        },
        'quiet': False,
        'no_warnings': False,
        'outtmpl': outtmpl_path,
    }
    
    if use_proxy:
        ydl_opts['proxy'] = getattr(config, 'warp_proxy_url', 'socks5://warp:1080')

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        # Проверяем, что итоговый файл действительно создан на диске
        return os.path.exists(output_path)
    except Exception as e:
        logger.warning(f"yt-dlp failed (proxy={use_proxy}): {e}")
        return False

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