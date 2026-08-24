"""Parola saklama, oturum token'ı ve parola politikası.

JWT kütüphanesi `PyJWT`. Önceki `python-jose` bakımsız ve bilinen açıkları vardı;
imza algoritması `decode`'da açıkça veriliyor ki token'ın kendi başlığındaki `alg`
dinlenmesin ("alg: none" ve HMAC/RSA karıştırma saldırıları buradan geçer).
"""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 gün

# bcrypt parolanın ilk 72 baytından fazlasını sessizce atar. Sessiz kırpma yerine
# politika bunu açıkça reddediyor.
PAROLA_EN_AZ = 10
PAROLA_EN_COK_BAYT = 72

# Kullanıcı bulunamadığında da bir bcrypt doğrulaması koşsun diye duruyor.
# Yoksa "kullanıcı yok" cevabı gözle görülür şekilde daha hızlı dönüyor ve
# saldırgan hangi e-postaların kayıtlı olduğunu ölçerek çıkarabiliyor.
_KUKLA_HASH = "$2b$12$NoQmTkTOa7iyRk6ck/YX2.7iICNyXidjx8kuVJVbL1HL/hoVflpl."


def hash_password(password: str) -> str:
    """Düz şifreyi alıp hash'ini döner. Veritabanına bu saklanır."""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Girilen şifre, saklanan hash ile uyuşuyor mu?"""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except ValueError:
        # Bozuk/elle düzenlenmiş hash: doğrulama başarısız sayılır, patlamaz.
        return False


def kukla_dogrula() -> None:
    """Kullanıcı yokken de bcrypt maliyetini öder — cevap süresi ayırt etmesin."""
    verify_password("kullanilmayan-sabit-parola", _KUKLA_HASH)


def eposta_normalize(eposta: str) -> str:
    """Kayıt ve girişte aynı biçime indirger.

    Normalize edilmeseydi `Ali@X.com` ile `ali@x.com` iki ayrı hesap olurdu ve
    kullanıcı kaydolduğu adresle giriş yapamazdı. Türkçe klavyede `İ` küçültmesi
    dile bağlı; `casefold` yerine ASCII `lower` yeterli çünkü e-posta zaten ASCII.
    """
    return eposta.strip().lower()


def parola_hatasi(parola: str, eposta: str = "") -> str | None:
    """Politikaya uymayan parolanın kullanıcıya gösterilecek gerekçesi; uygunsa None.

    Uzunluk merkezli, karakter çeşidi dayatmayan bir politika seçildi. Büyük harf +
    rakam + sembol zorunluluğu pratikte `Parola1!` üretiyor: kurala uyar, tahmini
    kolaydır. Uzunluk aynı işi daha dürüst yapıyor.
    """
    if len(parola) < PAROLA_EN_AZ:
        return f"Parola en az {PAROLA_EN_AZ} karakter olmalı."
    if len(parola.encode("utf-8")) > PAROLA_EN_COK_BAYT:
        return f"Parola en fazla {PAROLA_EN_COK_BAYT} bayt olabilir."
    if parola.strip() == "":
        return "Parola yalnızca boşluktan oluşamaz."
    if len(set(parola)) == 1:
        return "Parola tek bir karakterin tekrarı olamaz."
    if eposta and parola.lower() == eposta_normalize(eposta):
        return "Parola e-posta adresiyle aynı olamaz."
    return None


def create_access_token(subject: str) -> str:
    """Kullanıcı için imzalı bir JWT token üretir. subject genelde user id."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """Token'ı çözer ve içindeki user id'yi (sub) döner. Geçersizse None."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            # Süresiz token kabul edilmesin: `exp` yoksa token geçersiz sayılır.
            options={"require": ["exp", "sub"]},
        )
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
