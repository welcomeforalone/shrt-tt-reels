import os
import logging
from typing import Optional, Union, List
import httpx

logger = logging.getLogger(__name__)

_http_client: Optional[httpx.AsyncClient] = None

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
            timeout=httpx.Timeout(20.0, connect=10.0),
            follow_redirects=True,
        )
    return _http_client

async def close_http_client():
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None

async def download_via_tikwm(url: str, output_path: str) -> Optional[Union[str, List[str]]]:
    logger.info("Trying tikwm API for TikTok")
    saved_paths: List[str] = []
    try:
        client = get_http_client()
        resp = await client.post(
            "https://www.tikwm.com/api/", 
            data={"url": url, "hd": 1}
        )
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("code") == 0 and "data" in data:
            # 1. Handle Photo Carousel
            if "images" in data["data"]:
                logger.info("Detected TikTok photo carousel")
                for i, img_url in enumerate(data["data"]["images"]):
                    img_resp = await client.get(img_url)
                    img_resp.raise_for_status()
                    img_path = output_path.replace(".mp4", f"_{i}.jpg")
                    with open(img_path, "wb") as f:
                        f.write(img_resp.content)
                    saved_paths.append(img_path)
                return saved_paths
                
            # 2. Handle Standard Video
            elif "play" in data["data"]:
                video_url = data["data"]["play"]
                video_resp = await client.get(video_url)
                video_resp.raise_for_status()
                with open(output_path, "wb") as f:
                    f.write(video_resp.content)
                return output_path
    except Exception as e:
        logger.warning(f"tikwm API failed: {e}")
        # Clean up any partially saved files to prevent disk leaks
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