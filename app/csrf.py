"""CSRF koruması — çift gönderim (double submit) yöntemi.

Sorun: tarayıcı, başka bir siteden gelen isteklere de bizim cookie'lerimizi
otomatik ekler. Saldırganın sayfasındaki gizli bir form /catalog/product'a POST
atarsa, kullanıcı giriş yapmış olduğu için istek geçerli görünür.

Çözüm: oturum cookie'siyle birlikte ikinci bir rastgele değer üretiriz. Bu değer
hem cookie'de durur hem de her formun içine gömülür. İstek geldiğinde ikisinin
eşit olması beklenir. Saldırganın sayfası bizim cookie'mizi okuyamaz (aynı köken
değil), dolayısıyla forma doğru değeri yazamaz.

Token JS'e hiç açılmıyor — sunucu şablona kendisi bastığı için cookie httpOnly
kalabiliyor.
"""

import secrets

from fastapi import Request, Response, status
from fastapi.exceptions import HTTPException

COOKIE_NAME = "csrf_token"
FORM_FIELD = "csrf_token"      # normal formlar gizli input ile gönderir
HEADER_NAME = "X-CSRF-Token"   # HTMX istekleri başlıkla gönderir

# Gövdeyi değiştirmeyen metotlar korumadan muaf
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def set_cookie(response: Response, token: str, secure: bool) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=secure,
        samesite="lax",
    )


async def verify_csrf(request: Request) -> None:
    """Durum değiştiren her istekte token'ı doğrular.

    main.py'da uygulama geneli dependency olarak bağlı; route'a tek tek
    eklenmediği için unutulma ihtimali yok.
    """
    if request.method in SAFE_METHODS:
        return

    cookie_token = request.cookies.get(COOKIE_NAME)
    if not cookie_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token bulunamadı. Sayfayı yenileyip tekrar dene.",
        )

    sent_token = request.headers.get(HEADER_NAME)
    if not sent_token:
        # Form gövdesi: burada okunması sorun değil, Starlette sonucu request
        # üzerinde önbelleğe alır; route aynı gövdeyi tekrar okuyabiliyor.
        form = await request.form()
        sent_token = form.get(FORM_FIELD)

    # compare_digest: karşılaştırma süresinden token sızmasın
    if not sent_token or not secrets.compare_digest(str(sent_token), cookie_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF doğrulaması başarısız. Sayfayı yenileyip tekrar dene.",
        )
