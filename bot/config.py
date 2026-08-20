from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    bot_token: str
    warp_proxy_url: str = "socks5://warp:1080"
    max_video_size_mb: int = 45
    rate_limit_per_minute: int = 5

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

config = Settings()