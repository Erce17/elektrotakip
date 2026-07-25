from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_access_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Cookie'deki token'ı okur, geçerliyse kullanıcıyı döner. Yoksa None.

    Yetkisiz durumu hata değil None ile bildirir; sadece "giriş yapılmışsa farklı
    göster" tipi yerlerde kullan. Korunması gereken route'larda require_user kullan.
    """
    token = request.cookies.get("access_token")
    if not token:
        return None
    user_id = decode_access_token(token)
    if not user_id:
        return None
    # Token'daki sub bizim ürettiğimiz bir id olmalı; değilse token sahtedir.
    try:
        user_id = int(user_id)
    except ValueError:
        return None
    return db.query(User).filter(User.id == user_id).first()


def require_user(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> User:
    """Giriş zorunlu. Yetkisizse route hiç çalışmaz, kullanıcı /login'e gider.

    Böylece korumayı her route'ta elle yazmak gerekmez; dependency'yi eklemeyi
    unutmak dışında açık kalmaz.
    """
    if user is not None:
        return user

    # HTMX isteğinde gövde bir tablo satırına yazılacağı için normal yönlendirme
    # login sayfasını satırın içine gömer; HX-Redirect tarayıcının tamamını taşır.
    if request.headers.get("HX-Request"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum gerekli",
            headers={"HX-Redirect": "/login"},
        )
    raise HTTPException(
        status_code=status.HTTP_303_SEE_OTHER,
        detail="Oturum gerekli",
        headers={"Location": "/login"},
    )