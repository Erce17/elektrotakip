from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError, validate_email
from sqlalchemy.orm import Session

from app import csrf, rate_limit
from app.config import settings
from app.database import get_db
from app.templating import templates
from app.models import User
from app.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    eposta_normalize,
    hash_password,
    kukla_dogrula,
    parola_hatasi,
    verify_password,
)

router = APIRouter()


def eposta_gecerli(eposta: str) -> bool:
    try:
        validate_email(eposta)
    except (ValidationError, ValueError):
        return False
    return True


def _hata(request: Request, sayfa: str, mesaj: str, eposta: str = "") -> HTMLResponse:
    """Hatalı formu geri çizer. E-postayı geri veriyoruz, parolayı asla."""
    return templates.TemplateResponse(
        request, sayfa, {"error": mesaj, "eposta": eposta}, status_code=400
    )


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html")


@router.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ip = rate_limit.istemci_ip(request)
    if rate_limit.kayit_siniri.kilitli_mi(ip):
        return _hata(request, "register.html", "Çok fazla kayıt denemesi. Sonra tekrar dene.")

    eposta = eposta_normalize(email)
    if not eposta_gecerli(eposta):
        return _hata(request, "register.html", "Geçerli bir e-posta adresi gir.", email)

    hata = parola_hatasi(password, eposta)
    if hata:
        return _hata(request, "register.html", hata, eposta)

    existing = db.query(User).filter(User.email == eposta).first()
    if existing:
        return _hata(request, "register.html", "Bu e-posta zaten kayıtlı.", eposta)

    user = User(email=eposta, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    rate_limit.kayit_siniri.basarisiz(ip)  # başarılı kayıt da kotadan düşer
    return RedirectResponse(url="/login", status_code=303)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    eposta = eposta_normalize(email)
    ip = rate_limit.istemci_ip(request)

    # Kilit doğrulamadan önce bakılıyor: kilitliyken parola hiç denenmiyor.
    if rate_limit.giris_siniri.kilitli_mi(eposta) or rate_limit.ip_siniri.kilitli_mi(ip):
        kalan = max(
            rate_limit.giris_siniri.kalan_dakika(eposta),
            rate_limit.ip_siniri.kalan_dakika(ip),
        )
        return _hata(
            request,
            "login.html",
            f"Çok fazla hatalı deneme. {kalan} dakika sonra tekrar dene.",
            eposta,
        )

    user = db.query(User).filter(User.email == eposta).first()
    if user is None:
        # Kullanıcı yokken de bcrypt maliyeti ödeniyor; cevap süresi
        # "bu e-posta kayıtlı mı" sorusunu ele vermesin.
        kukla_dogrula()

    if user is None or not verify_password(password, user.password_hash):
        rate_limit.giris_siniri.basarisiz(eposta)
        rate_limit.ip_siniri.basarisiz(ip)
        # Tek ve aynı mesaj: hangisinin yanlış olduğu söylenmiyor.
        return _hata(request, "login.html", "E-posta veya şifre hatalı.", eposta)

    rate_limit.giris_siniri.sifirla(eposta)
    rate_limit.ip_siniri.sifirla(ip)

    token = create_access_token(user.id)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # token ömrüyle aynı kalsın
        path="/",
    )
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    # Nitelikler kurulumdakiyle aynı verilmeli: tarayıcı cookie'yi ada değil
    # (ad, alan, yol) üçlüsüne göre siliyor, eşleşmezse eski cookie kalıyordu.
    response.delete_cookie(
        "access_token", path="/", httponly=True,
        secure=settings.cookie_secure, samesite="lax",
    )
    # CSRF token'ı da yenilensin: çıkıştan sonra aynı token'la devam edilmesin.
    response.delete_cookie(
        csrf.COOKIE_NAME, path="/", httponly=True,
        secure=settings.cookie_secure, samesite="lax",
    )
    return response
