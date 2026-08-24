from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Oturum token'larının tamamı bu anahtarla imzalanıyor. Tahmin edilebilir bir
# anahtar, herkesin kendine istediği kullanıcının token'ını üretebilmesi demek —
# yani parola katmanı tamamen atlanır. Kısa/örnek değerler açılışta reddediliyor.
SECRET_KEY_EN_AZ = 32
ORNEK_SECRET_KEYLER = {
    "<buraya-rastgele-uzun-string>",
    "changeme",
    "secret",
    "supersecretkey",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    secret_key: str

    @field_validator("secret_key")
    @classmethod
    def anahtar_yeterince_guclu(cls, deger: str) -> str:
        if deger.strip().lower() in ORNEK_SECRET_KEYLER or len(deger) < SECRET_KEY_EN_AZ:
            # Değerin kendisi mesaja konmuyor: hata izleri loga düşüyor.
            raise ValueError(
                f"SECRET_KEY en az {SECRET_KEY_EN_AZ} karakter ve örnek değerlerden "
                "farklı olmalı. Üret: python -c "
                "\"import secrets; print(secrets.token_urlsafe(64))\""
            )
        return deger

    # Üretimde true olmalı: token cookie'si sadece HTTPS üzerinden gider.
    # Lokalde http://localhost ile çalışıldığı için varsayılan false.
    cookie_secure: bool = False


settings = Settings() 