import logging

from bot.backends.youtube import download_via_ytdlp

logger = logging.getLogger(__name__)


async def download_via_instagram(url: str, output_path: str) -> str | None:
    """
    Загрузка Instagram Reels и видео.
    Использует yt-dlp с проксированием через Cloudflare WARP,
    так как официальный API требует авторизации, а бесплатные парсеры нестабильны.
    """
    logger.info("Downloading Instagram media via yt-dlp (WARP proxy)")
    return await download_via_ytdlp(url, output_path)
