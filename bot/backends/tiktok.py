import logging
import os

import httpx

from bot.config import config

logger = logging.getLogger(__name__)

_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=True,
        )
    return _http_client


async def close_http_client():
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


async def download_via_tikwm(url: str, output_path: str) -> str | list[str] | None:
    """
    Загружает контент из TikTok через неофициальный API tikwm.com.
    Поддерживает видео без водяных знаков (потоковая загрузка с лимитом размера)
    и фото-карусели.
    """
    logger.info("Trying tikwm API for TikTok")
    saved_paths: list[str] = []
    max_video_bytes = config.max_tikwm_video_size_mb * 1024 * 1024

    try:
        client = get_http_client()
        resp = await client.post(
            "https://www.tikwm.com/api/",
            data={"url": url, "hd": 1}
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") == 0 and "data" in data:
            # 1. Фото-карусель
            if "images" in data["data"]:
                logger.info("Detected TikTok photo carousel")
                for i, img_url in enumerate(data["data"]["images"]):
                    img_path = output_path.replace(".mp4", f"_{i}.jpg")
                    async with client.stream("GET", img_url) as img_resp:
                        img_resp.raise_for_status()
                        with open(img_path, "wb") as f:
                            async for chunk in img_resp.aiter_bytes(chunk_size=65536):
                                f.write(chunk)
                    saved_paths.append(img_path)
                return saved_paths

            # 2. Обычное видео: читаем потоком (stream), не загружая весь файл в RAM
            elif "play" in data["data"]:
                video_url = data["data"]["play"]
                async with client.stream("GET", video_url) as video_resp:
                    video_resp.raise_for_status()

                    # Проверяем заголовок Content-Length, если передан
                    content_len = video_resp.headers.get("content-length")
                    if content_len and int(content_len) > max_video_bytes:
                        logger.warning(
                            f"TikWM video too large: {content_len} bytes (limit {max_video_bytes})"
                        )
                        return None

                    bytes_written = 0
                    with open(output_path, "wb") as f:
                        async for chunk in video_resp.aiter_bytes(chunk_size=65536):
                            bytes_written += len(chunk)
                            if bytes_written > max_video_bytes:
                                logger.warning(
                                    f"TikWM video exceeded max limit of {max_video_bytes} bytes"
                                )
                                raise ValueError("TikWM video exceeded maximum size limit")
                            f.write(chunk)

                return output_path
    except Exception as e:
        logger.warning(f"tikwm API failed: {e}")
        # Очищаем частично сохраненные файлы при сбое
        for path in saved_paths:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except Exception:
                pass
    return None
