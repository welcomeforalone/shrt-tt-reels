import re
import os
import uuid
import logging
from typing import Optional, Union, List

from bot.backends.tiktok import download_via_tikwm
from bot.backends.instagram import download_via_public_api
from bot.backends.youtube import download_via_ytdlp

logger = logging.getLogger(__name__)

class PlatformDetect:
    TIKTOK = r"tiktok\.com|vm\.tiktok\.com"
    INSTAGRAM = r"instagram\.com"
    YOUTUBE = r"youtube\.com|youtu\.be"

async def process_download(url: str) -> Optional[Union[str, List[str]]]:
    temp_filename = f"/tmp/{uuid.uuid4().hex}.mp4"
    
    try:
        if re.search(PlatformDetect.TIKTOK, url, re.IGNORECASE):
            logger.info("Detected TikTok")
            result = await download_via_tikwm(url, temp_filename)
            
            # Prevent crashing yt-dlp with unsupported photo URLs
            if not result and "/photo/" not in url:
                result = await download_via_ytdlp(url, temp_filename)
            return result
            
        elif re.search(PlatformDetect.INSTAGRAM, url, re.IGNORECASE):
            logger.info("Detected Instagram")
            result = await download_via_public_api(url, temp_filename)
            if not result:
                result = await download_via_ytdlp(url, temp_filename)
            return result
            
        elif re.search(PlatformDetect.YOUTUBE, url, re.IGNORECASE):
            logger.info("Detected YouTube")
            return await download_via_ytdlp(url, temp_filename)
            
        else:
            logger.info("Platform not explicitly supported, fallback to yt-dlp")
            return await download_via_ytdlp(url, temp_filename)
            
    except Exception as e:
        logger.error(f"Error in chain of responsibility: {e}")
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
        return None