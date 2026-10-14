import logging
import os
import tempfile
import uuid
from urllib.parse import urlsplit

from bot.backends.instagram import download_via_instagram
from bot.backends.tiktok import download_via_tikwm
from bot.backends.youtube import download_via_ytdlp
from bot.utils import get_download_semaphore

logger = logging.getLogger(__name__)


def detect_platform(url: str) -> str:
    """
    Определяет платформу по имени хоста (hostname), чтобы избежать атак вида
    https://evil.com/?x=tiktok.com.
    Возвращает: 'tiktok', 'instagram', 'youtube' или 'other'.
    """
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").lower().strip(".")
    except Exception:
        return "other"

    if not hostname:
        return "other"

    # TikTok домены (tiktok.com, vm.tiktok.com, vt.tiktok.com, douyin.com)
    if hostname == "tiktok.com" or hostname.endswith(".tiktok.com") or hostname.endswith(".douyin.com"):
        return "tiktok"

    # Instagram домены (instagram.com, instagr.am)
    if hostname == "instagram.com" or hostname.endswith(".instagram.com") or hostname == "instagr.am":
        return "instagram"

    # YouTube домены (youtube.com, youtu.be)
    if hostname == "youtube.com" or hostname.endswith(".youtube.com") or hostname == "youtu.be":
        return "youtube"

    return "other"


async def process_download(url: str) -> str | list[str] | None:
    """
    Маршрутизирует ссылку на соответствующий бэкенд загрузки
    и возвращает путь к сохраненному файлу или список путей (для фотоальбомов).
    """
    temp_dir = tempfile.gettempdir()
    temp_filename = os.path.join(temp_dir, f"{uuid.uuid4().hex}.mp4")
    platform = detect_platform(url)

    logger.info(f"Routing URL to backend. Platform: {platform}")

    async with get_download_semaphore():
        try:
            if platform == "tiktok":
                result = await download_via_tikwm(url, temp_filename)
                # Если tikwm не справился и это не фотоальбом (yt-dlp падает на фото-ссылках TikTok)
                if not result and "/photo/" not in url:
                    logger.info("TikWM returned no result, attempting yt-dlp fallback")
                    result = await download_via_ytdlp(url, temp_filename)
                return result

            elif platform == "instagram":
                return await download_via_instagram(url, temp_filename)

            elif platform == "youtube":
                return await download_via_ytdlp(url, temp_filename)

            else:
                logger.info(f"Unrecognized platform for {url}, falling back to yt-dlp")
                return await download_via_ytdlp(url, temp_filename)

        except Exception as e:
            logger.error(f"Download execution error: {e}")
            if os.path.exists(temp_filename):
                try:
                    os.remove(temp_filename)
                except Exception:
                    pass
            return None
