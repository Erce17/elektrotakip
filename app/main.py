from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from app import csrf
from app.config import settings
from app.database import get_db
from app.templating import templates
from app.dependencies import require_user
from app.models import Category, Customer, Product, Quote, User
from app.routers import auth, catalog, customers, quotes


# CDN'e bağlı olmayan CSP direktifleri. `script-src`/`style-src` T10'da (Tailwind
# CDN'in çıkarılması) eklenecek; o gün hedef şu:
#     default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:
CSP_DIREKTIFLERI = "; ".join([
    # `<base>` etiketi enjekte edilip tüm göreli bağlantılar saldırganın
    # sunucusuna çevrilemesin.
    "base-uri 'none'",
    # Sayfadaki form başka bir siteye gönderilemez: giriş formuna sokulan bir
    # `action` ile parola dışarı postalanamaz.
    "form-action 'self'",
    # X-Frame-Options'ın modern karşılığı; ikisi birden duruyor çünkü eski
    # tarayıcılar yalnızca birincisini biliyor.
    "frame-ancestors 'none'",
    # Flash/applet kalıntısı; bedava kapanıyor.
    "object-src 'none'",
])


# CSRF doğrulaması uygulama geneli: route'a tek tek eklenmediği için unutulamaz
app = FastAPI(title="ElektroTakip", dependencies=[Depends(csrf.verify_csrf)])

app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(customers.router)
app.include_router(quotes.router)


@app.middleware("http")
async def guvenlik_basliklari(request: Request, call_next):
    """Tarayıcıya uygulanacak asgari kısıtları söyler.

    - `X-Frame-Options: DENY` — sayfa başka sitenin iframe'ine gömülemez.
      Gömülebilseydi saldırgan teklif ekranını görünmez bir çerçevede açıp
      kullanıcıya "Sil" düğmesine bastırabilirdi (clickjacking).
    - `X-Content-Type-Options: nosniff` — yüklenen Excel'i tarayıcı kendi
      tahminiyle HTML sayıp çalıştırmasın.
    - `Referrer-Policy` — teklif id'si üçüncü sitelere referrer ile sızmasın.

    CSP kısmi: `script-src`/`style-src` bilerek **yok**. Tailwind CDN tarayıcıda
    çalışan bir derleyici (CSS'i çalışma anında üretip `<style>` olarak enjekte
    ediyor) ve `quote_print.html`'de bir `onclick` var; ikisi de `unsafe-inline`
    isterdi. `script-src 'unsafe-inline'` yazmak CSP'nin engellemek için var
    olduğu şeye izin vermek demek — başlık durur, koruma olmaz. Yanlış güven
    eksik korumadan kötü, o yüzden konmadı. Bkz. CSP_DIREKTIFLERI.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", CSP_DIREKTIFLERI)
    if settings.cookie_secure:
        # Yalnızca HTTPS'te anlamlı; lokalde http'yi kilitlemesin.
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


@app.middleware("http")
async def csrf_cookie(request: Request, call_next):
    """Her istekte bir CSRF token'ı hazır eder ve cookie'de yoksa yerleştirir.

    Şablonlar token'a request.state.csrf_token ile ulaşır; doğrulama işini
    csrf.verify_csrf yapar.
    """
    token = request.cookies.get(csrf.COOKIE_NAME) or csrf.generate_token()
    request.state.csrf_token = token

    response = await call_next(request)

    if request.cookies.get(csrf.COOKIE_NAME) != token:
        csrf.set_cookie(response, token, secure=settings.cookie_secure)
    return response



@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    # Ürünün sahibi kategorisi üzerinden belli olur, bu yüzden join gerekiyor
    urun_sayisi = (
        db.query(Product)
        .join(Category)
        .filter(Category.user_id == user.id)
        .count()
    )
    musteri_sayisi = db.query(Customer).filter(Customer.user_id == user.id).count()
    teklif_sayisi = db.query(Quote).filter(Quote.user_id == user.id).count()

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "user": user,
            "urun_sayisi": urun_sayisi,
            "musteri_sayisi": musteri_sayisi,
            "teklif_sayisi": teklif_sayisi,
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/db-health")
def db_health(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1")).scalar()
    return {"database": "ok", "result": result}
