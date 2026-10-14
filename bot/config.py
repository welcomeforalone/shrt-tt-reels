from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    bot_token: str = ""
    warp_proxy_url: str = "socks5://warp:1080"
    max_video_size_mb: int = 45
    rate_limit_per_minute: int = 5
    max_concurrent_downloads: int = 3
    max_concurrent_compressions: int = 2

config = Settings()