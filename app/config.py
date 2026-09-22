from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str

    # Local disk storage
    STORAGE_DIR: str = "./storage"
    MAX_STORAGE_MB: int = 500

    MAX_IMPORT_SIZE_MB: int = 100

    CORS_ORIGINS: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
