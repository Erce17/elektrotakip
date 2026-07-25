from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    secret_key: str

    # Üretimde true olmalı: token cookie'si sadece HTTPS üzerinden gider.
    # Lokalde http://localhost ile çalışıldığı için varsayılan false.
    cookie_secure: bool = False


settings = Settings() 