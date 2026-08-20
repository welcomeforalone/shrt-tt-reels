import httpx
import logging
from typing import Optional, Union, List

logger = logging.getLogger(__name__)

async def download_via_tikwm(url: str, output_path: str) -> Optional[Union[str, List[str]]]:
    logger.info("Trying tikwm API for TikTok")
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
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
                    saved_paths = []
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
    return None