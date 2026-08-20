import httpx
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

async def download_via_tikwm(url: str, output_path: str) -> Optional[str]:
    logger.info("Trying tikwm API for TikTok")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://www.tikwm.com/api/", 
                data={"url": url, "hd": 1}
            )
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("code") == 0 and "data" in data and "play" in data["data"]:
                video_url = data["data"]["play"]
                
                video_resp = await client.get(video_url)
                video_resp.raise_for_status()
                
                with open(output_path, "wb") as f:
                    f.write(video_resp.content)
                return output_path
    except Exception as e:
        logger.warning(f"tikwm API failed: {e}")
    return None