import asyncio
import ipaddress
import logging
import os
import socket
import time
from urllib.parse import urlparse

from bot.config import config

logger = logging.getLogger(__name__)

# Базовая защита от SSRF: блокировка имен внутренних сервисов Docker и локальных TLD
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


def _is_ip_private_or_restricted(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Проверяет, относится ли IP к приватным, loopback или спец-диапазонам."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_and_check_domain(hostname: str) -> bool:
    """
    Синхронная проверка резолва домена.
    Возвращает False, если домен не резолвится или указывает на приватный/локальный IP.
    """
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        if not addr_info:
            return False
        for item in addr_info:
            ip_str = item[4][0]
            ip = ipaddress.ip_address(ip_str)
            if _is_ip_private_or_restricted(ip):
                return False
        return True
    except (socket.gaierror, socket.herror, ValueError, OSError):
        # Если домен невозможно разрешить, считаем его небезопасным/невалидным
        return False


def is_safe_url_sync(url: str) -> bool:
    """
    Синхронная проверка URL на базовую безопасность (SSRF, локальные IP, схема).
    Удобно для тестов и синхронного вызова.
    """
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

        # Если в URL указан прямой IP-адрес
        try:
            ip = ipaddress.ip_address(hostname)
            return not _is_ip_private_or_restricted(ip)
        except ValueError:
            # Имя хоста — доменное имя, резолвим его
            return _resolve_and_check_domain(hostname)
    except Exception:
        return False


async def is_safe_url(url: str, timeout: float = 3.0) -> bool:
    """
    Асинхронная проверка безопасности URL.
    Резолв DNS выносится в отдельный поток (asyncio.to_thread) с таймаутом,
    чтобы не блокировать основной event loop бота при медленном или зависшем DNS.
    """
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

        # Проверка прямого IP
        try:
            ip = ipaddress.ip_address(hostname)
            return not _is_ip_private_or_restricted(ip)
        except ValueError:
            # Резолвим домен в отдельном потоке с таймаутом
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(_resolve_and_check_domain, hostname),
                    timeout=timeout
                )
            except (TimeoutError, Exception):
                return False
    except Exception:
        return False


# Ограничение частоты запросов (Rate Limiting)
_rate_limits: dict[int, list[float]] = {}


def check_rate_limit(user_id: int, max_requests: int) -> bool:
    """Проверяет скользящее окно запросов пользователя за последние 60 секунд."""
    current_time = time.time()
    user_times = _rate_limits.get(user_id, [])

    # Оставляем только запросы за последнюю минуту
    valid_times = [t for t in user_times if current_time - t < 60]

    if not valid_times:
        _rate_limits.pop(user_id, None)
    else:
        _rate_limits[user_id] = valid_times

    # Периодическая очистка устаревших пользователей при разрастании словаря
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


def reset_rate_limits() -> None:
    """Очищает историю запросов (используется в тестах)."""
    _rate_limits.clear()


# Семафоры для ограничения конкурентных тяжелых операций
_download_semaphore: asyncio.Semaphore | None = None
_ffmpeg_semaphore: asyncio.Semaphore | None = None


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


async def get_video_duration(file_path: str) -> float | None:
    """Определяет длительность видео в секундах через ffprobe."""
    try:
        process = await asyncio.create_subprocess_exec(
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
        if process.returncode == 0:
            val = stdout.decode().strip()
            return float(val)
    except Exception as e:
        logger.debug(f"Could not get duration via ffprobe: {e}")
    return None


async def compress_video(input_path: str, output_path: str) -> bool:
    """
    Сжимает видео через FFmpeg с адаптивным расчетом битрейта под лимит Telegram (50 МБ).
    Включает таймаут (180 сек) и удаление незавершенного файла при ошибке.
    """
    logger.info(f"Compressing video {input_path}")
    async with get_ffmpeg_semaphore():
        try:
            # Рассчитываем битрейт на основе длительности видео
            target_mb = min(config.telegram_max_size_mb - 4, 46)
            duration = await get_video_duration(input_path)

            maxrate_str = "2M"
            bufsize_str = "4M"
            if duration and duration > 0:
                target_bits = target_mb * 8 * 1024 * 1024
                calculated_kbps = int((target_bits / duration) / 1000)
                # Ограничиваем битрейт диапазоном 400k..2500k
                clamped_kbps = max(400, min(calculated_kbps, 2500))
                maxrate_str = f"{clamped_kbps}k"
                bufsize_str = f"{clamped_kbps * 2}k"
                logger.info(f"Duration: {duration:.1f}s -> calculated maxrate: {maxrate_str}")

            process = await asyncio.create_subprocess_exec(
                'ffmpeg', '-y', '-i', input_path,
                '-vcodec', 'libx264',
                '-preset', 'veryfast',
                '-crf', '28',
                '-maxrate', maxrate_str,
                '-bufsize', bufsize_str,
                '-vf', "scale=-2:'min(1280,ih)'",
                '-stats',
                '-acodec', 'copy', output_path
            )

            try:
                await asyncio.wait_for(process.wait(), timeout=180)
                return process.returncode == 0
            except TimeoutError:
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
    """Возвращает размер файла в мегабайтах."""
    if not os.path.exists(file_path):
        return 0.0
    return os.path.getsize(file_path) / (1024 * 1024)
