import asyncio
import logging
import yt_dlp
from typing import Optional

from bot.config import config

logger = logging.getLogger(__name__)

def _sync_yt_dlp_download(url: str, output_path: str, use_proxy: bool) -> bool:
    ydl_opts = {
            'outtmpl': output_path,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'cookiefile': '/home/botuser/app/cookies.txt',
            'extractor_args': {
                'youtube': ['player_client=android', 'player_client=default']
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
            }
        }
    
    if use_proxy:
        ydl_opts['proxy'] = config.warp_proxy_url

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
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