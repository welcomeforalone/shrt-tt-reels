import json
import logging
import os

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.config import config

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {"en", "ru"}
DEFAULT_LANGUAGE = "en"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": (
            "👋 **Welcome!**\n\n"
            "Send me a link from **TikTok**, **Instagram Reels**, or **YouTube Shorts**, "
            "and I will download it in high quality without watermarks!\n\n"
            "🌐 You can change the language anytime using the buttons below or with /lang."
        ),
        "choose_lang": "🌐 Choose your language / Выберите язык:",
        "lang_selected": "✅ Language set to English!",
        "rate_limit": "⏳ Rate limit exceeded. Please wait a minute.",
        "unsafe_url": "❌ Invalid or forbidden URL.",
        "downloading": "Downloading... ⏳",
        "download_failed": "❌ Failed to download. All backends failed (or API is temporarily down).",
        "video_not_found": "❌ Failed to download the video.",
        "uploading_photos": "Uploading photos to Telegram... 📤",
        "uploading_photo": "Uploading photo to Telegram... 📤",
        "no_photos_found": "❌ No photos found to download.",
        "compressing": "Video is large, compressing... 🗜️",
        "too_large_after_compress": "❌ Video is still too large for Telegram after compression.",
        "compress_failed": "❌ Failed to compress video.",
        "uploading_video": "Uploading to Telegram... 📤",
        "download_timeout": "⏳ Download timed out. Please try again later.",
        "unexpected_error": "❌ An unexpected error occurred.",
    },
    "ru": {
        "welcome": (
            "👋 **Добро пожаловать!**\n\n"
            "Отправьте мне ссылку на **TikTok**, **Instagram Reels** или **YouTube Shorts**, "
            "и я скачаю видео в высоком качестве без водяных знаков!\n\n"
            "🌐 Вы можете изменить язык в любой момент кнопками ниже или командой /lang."
        ),
        "choose_lang": "🌐 Выберите язык / Choose your language:",
        "lang_selected": "✅ Язык переключен на русский!",
        "rate_limit": "⏳ Превышен лимит запросов. Пожалуйста, подождите минуту.",
        "unsafe_url": "❌ Недопустимая или небезопасная ссылка.",
        "downloading": "Скачиваю... ⏳",
        "download_failed": "❌ Не удалось скачать. Все сервисы временно недоступны или ссылка не поддерживается.",
        "video_not_found": "❌ Не удалось сохранить видеофайл.",
        "uploading_photos": "Загружаю фото в Telegram... 📤",
        "uploading_photo": "Загружаю фото в Telegram... 📤",
        "no_photos_found": "❌ Не удалось найти фото для скачивания.",
        "compressing": "Видео слишком большое, сжимаю... 🗜️",
        "too_large_after_compress": "❌ Видео всё ещё превышает лимит Telegram (50 МБ) даже после сжатия.",
        "compress_failed": "❌ Ошибка при сжатии видео.",
        "uploading_video": "Отправляю видео в Telegram... 📤",
        "download_timeout": "⏳ Время ожидания скачивания истекло. Пожалуйста, попробуйте позже.",
        "unexpected_error": "❌ Произошла непредвиденная ошибка.",
    },
}

# In-memory storage for user language preferences: user_id -> "en" | "ru"
_user_langs: dict[int, str] = {}

def _load_user_langs() -> None:
    path = config.user_langs_path
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                for uid_str, lang in data.items():
                    try:
                        if lang in SUPPORTED_LANGUAGES:
                            _user_langs[int(uid_str)] = lang
                    except (ValueError, TypeError):
                        continue
        logger.info(f"Loaded {len(_user_langs)} user language preferences from {path}")
    except Exception as e:
        logger.warning(f"Could not load user language preferences from {path}: {e}")

def _save_user_langs() -> None:
    path = config.user_langs_path
    if not path:
        return
    try:
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        # Convert int keys to str for JSON serialization
        data = {str(uid): lang for uid, lang in _user_langs.items()}
        temp_path = f"{path}.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, path)
    except Exception as e:
        logger.warning(f"Failed to save user languages to disk ({path}): {e}. Continuing with in-memory storage.")

# Load saved preferences at module startup
_load_user_langs()

def get_user_language(user_id: int | None, user_language_code: str | None = None) -> str:
    if user_id is not None and user_id in _user_langs:
        return _user_langs[user_id]

    if user_language_code:
        code = user_language_code.lower().strip()
        if code.startswith("ru") or code.startswith("be") or code.startswith("uk"):
            return "ru"

    return DEFAULT_LANGUAGE

def set_user_language(user_id: int, lang: str) -> None:
    if lang in SUPPORTED_LANGUAGES:
        _user_langs[user_id] = lang
        _save_user_langs()

def t(
    key: str,
    user_id: int | None = None,
    lang: str | None = None,
    fallback_lang: str = DEFAULT_LANGUAGE,
    user_language_code: str | None = None
) -> str:
    chosen_lang = lang
    if not chosen_lang and (user_id is not None or user_language_code is not None):
        chosen_lang = get_user_language(user_id, user_language_code)
    elif not chosen_lang:
        chosen_lang = fallback_lang

    lang_dict = TRANSLATIONS.get(chosen_lang, TRANSLATIONS[DEFAULT_LANGUAGE])
    return lang_dict.get(key, TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key))

def get_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🇺🇸 English", callback_data="set_lang:en"),
                InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang:ru"),
            ]
        ]
    )


def get_translator(user_id: int | None = None, user_language_code: str | None = None):
    """Возвращает функцию перевода, зафиксированную для конкретного пользователя."""
    return lambda key, **kwargs: t(key, user_id=user_id, user_language_code=user_language_code, **kwargs)
