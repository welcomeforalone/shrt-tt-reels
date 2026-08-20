import os
import time
import asyncio
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

# Basic rate limiting: user_id -> list of timestamps
_rate_limits = defaultdict(list)

def check_rate_limit(user_id: int, max_requests: int) -> bool:
    current_time = time.time()
    user_times = _rate_limits[user_id]
    
    # Remove timestamps older than 60 seconds
    _rate_limits[user_id] = [t for t in user_times if current_time - t < 60]
    
    if len(_rate_limits[user_id]) >= max_requests:
        return False
        
    _rate_limits[user_id].append(current_time)
    return True

async def compress_video(input_path: str, output_path: str) -> bool:
    logger.info(f"Compressing video {input_path}")
    process = await asyncio.create_subprocess_exec(
            'ffmpeg', '-y', '-i', input_path,
            '-vcodec', 'libx264', '-crf', '28', '-preset', 'ultrafast', # Изменили faster на ultrafast
            '-acodec', 'copy', output_path,
        )
    await process.wait()
    return process.returncode == 0

def get_file_size_mb(file_path: str) -> float:
    if not os.path.exists(file_path):
        return 0.0
    return os.path.getsize(file_path) / (1024 * 1024)