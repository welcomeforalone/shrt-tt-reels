import os
import time
import socket
import asyncio
import logging
import ipaddress
from urllib.parse import urlparse
from typing import Optional

from bot.config import config

logger = logging.getLogger(__name__)

# SSRF Protection: Block internal hostnames and private/local IPs
BLOCKED_HOSTNAMES = {
    "localhost",
    "warp",
    "warp_proxy",
    "bgutil-pot",
    "bgutil_pot",
    "bot",
    "tiktok_downloader_bot",
}

BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".lan")

def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        hostname = hostname.lower().strip(".")
        if hostname in BLOCKED_HOSTNAMES or any(hostname.endswith(s) for s in BLOCKED_SUFFIXES):
            return False

        # Check if the hostname is a direct IP address
        try:
            ip = ipaddress.ip_address(hostname)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                return False
        except ValueError:
            # Hostname is a domain name, resolve to check DNS targets
            try:
                addr_info = socket.getaddrinfo(hostname, None)
                for item in addr_info:
                    ip_str = item[4][0]
                    ip = ipaddress.ip_address(ip_str)
                    if (
                        ip.is_private
                        or ip.is_loopback
                        or ip.is_link_local
                        or ip.is_reserved
                        or ip.is_multicast
                        or ip.is_unspecified
                    ):
                        return False
            except (socket.gaierror, socket.herror, ValueError):
                pass

        return True
    except Exception:
        return False

# Rate limiting: user_id -> list of timestamps (cleaned up to prevent memory leak)
_rate_limits: dict[int, list[float]] = {}

def check_rate_limit(user_id: int, max_requests: int) -> bool:
    current_time = time.time()
    user_times = _rate_limits.get(user_id, [])

    # Remove timestamps older than 60 seconds
    valid_times = [t for t in user_times if current_time - t < 60]

    # Clean up empty user entry from dictionary to prevent memory leak
    if not valid_times:
        _rate_limits.pop(user_id, None)
    else:
        _rate_limits[user_id] = valid_times

    # Periodic sweep if dictionary grows large
    if len(_rate_limits) > 500:
        stale_users = [
            uid for uid, times in _rate_limits.items()
            if not times or current_time - times[-1] >= 60
        ]
        for uid in stale_users:
            _rate_limits.pop(uid, None)

    if len(valid_times) >= max_requests:
        return False

    if user_id not in _rate_limits:
        _rate_limits[user_id] = []
    _rate_limits[user_id].append(current_time)
    return True

# Concurrency Semaphores
_download_semaphore: Optional[asyncio.Semaphore] = None
_ffmpeg_semaphore: Optional[asyncio.Semaphore] = None

def get_download_semaphore() -> asyncio.Semaphore:
    global _download_semaphore
    if _download_semaphore is None:
        _download_semaphore = asyncio.Semaphore(config.max_concurrent_downloads)
    return _download_semaphore

def get_ffmpeg_semaphore() -> asyncio.Semaphore:
    global _ffmpeg_semaphore
    if _ffmpeg_semaphore is None:
        _ffmpeg_semaphore = asyncio.Semaphore(config.max_concurrent_compressions)
    return _ffmpeg_semaphore

async def compress_video(input_path: str, output_path: str) -> bool:
    logger.info(f"Compressing video {input_path}")
    async with get_ffmpeg_semaphore():
        try:
            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-y', '-i', input_path,
                '-vcodec', 'libx264', 
                '-preset', 'veryfast',             # Баланс скорости и качества
                '-crf', '28', 
                '-maxrate', '2M',                  # Жесткий лимит битрейта, чтобы не превысить 50 МБ
                '-bufsize', '4M',
                '-vf', "scale=-2:'min(1280,ih)'",  # Уменьшаем до 720x1280 (HD), если видео больше
                '-stats',
                '-acodec', 'copy', output_path
            )
            try:
                await asyncio.wait_for(process.wait(), timeout=180)
                return process.returncode == 0
            except asyncio.TimeoutError:
                logger.error(f"FFmpeg compression timed out for {input_path}")
                try:
                    process.kill()
                    await process.wait()
                except Exception:
                    pass
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except Exception:
                        pass
                return False
        except Exception as e:
            logger.error(f"FFmpeg execution failed: {e}")
            return False

def get_file_size_mb(file_path: str) -> float:
    if not os.path.exists(file_path):
        return 0.0
    return os.path.getsize(file_path) / (1024 * 1024)