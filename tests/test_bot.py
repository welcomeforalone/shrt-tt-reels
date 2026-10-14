import os
import tempfile

from bot.downloader import detect_platform
from bot.i18n import get_translator, get_user_language, t
from bot.utils import (
    check_rate_limit,
    get_file_size_mb,
    is_safe_url,
    is_safe_url_sync,
    reset_rate_limits,
)


class TestUrlSafety:
    """Тесты проверки безопасности URL (SSRF, локальные сети, схемы)."""

    def test_safe_valid_urls(self):
        valid_urls = [
            "https://www.tiktok.com/@user/video/123456",
            "https://vm.tiktok.com/ZM8rX1234/",
            "https://www.instagram.com/reel/CxY1234567/",
            "https://youtu.be/dQw4w9WgXcQ",
            "https://www.youtube.com/shorts/12345678901",
        ]
        for url in valid_urls:
            assert is_safe_url_sync(url) is True, f"Expected safe for {url}"

    def test_blocked_schemes(self):
        unsafe_schemes = [
            "ftp://example.com/file.mp4",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "data:text/plain;base64,SGVsbG8=",
            "gopher://evil.com",
            "",
            "not-a-url",
        ]
        for url in unsafe_schemes:
            assert is_safe_url_sync(url) is False, f"Expected unsafe scheme for {url}"

    def test_blocked_internal_and_private_hosts(self):
        blocked_urls = [
            "http://localhost:8080/test",
            "http://127.0.0.1:8000/",
            "http://192.168.1.1/admin",
            "http://10.0.0.5/api",
            "http://172.16.0.2/",
            "http://warp:1080/",
            "http://bgutil-pot:4416/",
            "http://bot:8080/",
            "http://service.local/",
            "http://server.internal/",
            "http://router.lan/",
        ]
        for url in blocked_urls:
            assert is_safe_url_sync(url) is False, f"Expected blocked host for {url}"

    def test_unresolvable_domain_rejected(self):
        # Домен, которого заведомо не существует, должен возвращать False, а не True
        nonexistent_url = "http://this-domain-definitely-does-not-exist-8374921.org/video"
        assert is_safe_url_sync(nonexistent_url) is False

    def test_async_is_safe_url(self):
        import asyncio
        assert asyncio.run(is_safe_url("https://www.tiktok.com/@user/video/123")) is True
        assert asyncio.run(is_safe_url("http://127.0.0.1:8080")) is False
        assert asyncio.run(is_safe_url("file:///etc/passwd")) is False


class TestPlatformDetection:
    """Тесты роутинга платформ по имени хоста (защита от URL query injection)."""

    def test_detect_tiktok(self):
        assert detect_platform("https://www.tiktok.com/@creator/video/12345") == "tiktok"
        assert detect_platform("https://vm.tiktok.com/ZM812345/") == "tiktok"
        assert detect_platform("https://vt.tiktok.com/ZS12345/") == "tiktok"
        assert detect_platform("https://v.douyin.com/iabc123/") == "tiktok"

    def test_detect_instagram(self):
        assert detect_platform("https://www.instagram.com/reel/Cxxxxxx/") == "instagram"
        assert detect_platform("https://instagram.com/p/Cyyyyyy/") == "instagram"
        assert detect_platform("https://instagr.am/reel/Czzzzzz/") == "instagram"

    def test_detect_youtube(self):
        assert detect_platform("https://www.youtube.com/shorts/12345678901") == "youtube"
        assert detect_platform("https://youtu.be/12345678901") == "youtube"
        assert detect_platform("https://m.youtube.com/watch?v=12345678901") == "youtube"

    def test_detect_spoofed_query_params(self):
        # Попытка обмануть детектор через параметры запроса или поддомены
        assert detect_platform("https://evil.com/?x=tiktok.com") == "other"
        assert detect_platform("https://evil.com/?url=https://instagram.com") == "other"
        assert detect_platform("https://tiktok.com.evil.com/video") == "other"
        assert detect_platform("https://youtube.com.attacker.com/watch") == "other"


class TestRateLimiter:
    """Тесты ограничения частоты запросов (скользящее окно)."""

    def setup_method(self):
        reset_rate_limits()

    def test_rate_limit_allows_under_quota(self):
        user_id = 99901
        limit = 3
        assert check_rate_limit(user_id, limit) is True
        assert check_rate_limit(user_id, limit) is True
        assert check_rate_limit(user_id, limit) is True

    def test_rate_limit_blocks_exceeded(self):
        user_id = 99902
        limit = 2
        assert check_rate_limit(user_id, limit) is True
        assert check_rate_limit(user_id, limit) is True
        assert check_rate_limit(user_id, limit) is False  # 3-й запрос блокируется


class TestI18n:
    """Тесты локализации и определения языка пользователя."""

    def test_default_and_fallback(self):
        # Английский по умолчанию
        assert get_user_language(user_id=123456789, user_language_code="de") == "en"
        # Автоопределение для русскоязычных локалей
        assert get_user_language(user_id=123456789, user_language_code="ru") == "ru"
        assert get_user_language(user_id=123456789, user_language_code="be") == "ru"
        assert get_user_language(user_id=123456789, user_language_code="uk") == "ru"

    def test_translations_keys(self):
        assert "welcome" in t("welcome", lang="en").lower()
        assert "Добро пожаловать" in t("welcome", lang="ru")
        assert t("downloading", lang="en") == "Downloading... ⏳"
        assert t("downloading", lang="ru") == "Скачиваю... ⏳"

    def test_get_translator_helper(self):
        _ = get_translator(user_id=None, user_language_code="ru")
        assert _("downloading") == "Скачиваю... ⏳"


class TestUtilsHelpers:
    """Тесты вспомогательных утилит."""

    def test_get_file_size_mb(self):
        assert get_file_size_mb("nonexistent_file_path.xyz") == 0.0

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"x" * (1024 * 1024))  # 1 MB
            temp_path = f.name

        try:
            size_mb = get_file_size_mb(temp_path)
            assert 0.99 <= size_mb <= 1.01
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
