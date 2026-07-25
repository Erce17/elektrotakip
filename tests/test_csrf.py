"""CSRF koruması.

`raw_client` token taşımaz — yani başka bir siteden gelen sahte isteği taklit
eder. `client` ise tarayıcı gibi token'ı taşır.
"""

import pytest

from app import csrf
from app.models import Category, Customer, Product

YAZMA_ISTEKLERI = [
    ("POST", "/login"),
    ("POST", "/register"),
    ("POST", "/logout"),
    ("POST", "/catalog/category"),
    ("POST", "/catalog/product"),
    ("POST", "/catalog/import-excel"),
    ("PUT", "/catalog/product/1"),
    ("DELETE", "/catalog/product/1"),
    ("POST", "/customers/"),
    ("PUT", "/customers/1"),
    ("DELETE", "/customers/1"),
]


@pytest.fixture
def ahmet(db_session, make_user, login_as, raw_client):
    """Giriş yapmış kullanıcı — CSRF kontrolünün auth'tan bağımsız çalıştığını görmek için."""
    user, token = make_user("ahmet@example.com")
    login_as(token)

    category = Category(name="Kablo", user_id=user.id)
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    product = Product(name="Zeta Kablo", category_id=category.id, unit_price=100)
    customer = Customer(name="Kadıköy Elektrik", user_id=user.id)
    db_session.add_all([product, customer])
    db_session.commit()
    db_session.refresh(product)
    db_session.refresh(customer)
    return {"user": user, "category": category, "product": product, "customer": customer}


@pytest.mark.parametrize("method,path", YAZMA_ISTEKLERI)
def test_tokensiz_yazma_istegi_reddedilir(raw_client, method, path):
    response = raw_client.request(method, path, follow_redirects=False)
    assert response.status_code == 403


@pytest.mark.parametrize("method,path", YAZMA_ISTEKLERI)
def test_yanlis_token_reddedilir(raw_client, method, path):
    raw_client.get("/login")  # cookie'yi al ama başka bir değer gönder
    response = raw_client.request(
        method, path, headers={csrf.HEADER_NAME: "baska-bir-token"}, follow_redirects=False
    )
    assert response.status_code == 403


def test_giris_yapmis_kullanici_da_tokensiz_yazamaz(raw_client, ahmet):
    """Oturum açık olmak yetmez — CSRF saldırısında kurbanın oturumu zaten açıktır."""
    response = raw_client.delete(f"/catalog/product/{ahmet['product'].id}")
    assert response.status_code == 403


def test_tokensiz_istek_veriyi_degistirmez(raw_client, db_session, ahmet):
    raw_client.delete(f"/catalog/product/{ahmet['product'].id}")
    raw_client.delete(f"/customers/{ahmet['customer'].id}")

    assert db_session.query(Product).count() == 1
    assert db_session.query(Customer).count() == 1


def test_okuma_istekleri_token_istemez(raw_client):
    """GET korumadan muaf: gövdeyi değiştirmiyor."""
    assert raw_client.get("/login").status_code == 200
    assert raw_client.get("/register").status_code == 200


def test_token_cookie_ilk_istekte_yerlesir(raw_client):
    response = raw_client.get("/login")

    assert csrf.COOKIE_NAME in response.cookies
    # Token JS'e açılmıyor: sunucu şablona kendisi basıyor
    assert "httponly" in response.headers["set-cookie"].lower()


def test_token_istekler_arasinda_degismez(raw_client):
    """Her istekte yenilenseydi iki sekmeli kullanımda formlar bozulurdu."""
    ilk = raw_client.get("/login").cookies[csrf.COOKIE_NAME]
    raw_client.get("/register")

    assert raw_client.cookies[csrf.COOKIE_NAME] == ilk


def test_form_alanindaki_token_da_kabul_edilir(raw_client, db_session, make_user, login_as):
    """Normal formlar başlık değil gizli input gönderir."""
    _, user_token = make_user("ahmet@example.com")
    login_as(user_token)
    raw_client.get("/catalog/")
    csrf_token = raw_client.cookies[csrf.COOKIE_NAME]

    response = raw_client.post(
        "/catalog/category",
        data={"name": "Anahtar", csrf.FORM_FIELD: csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert db_session.query(Category).filter(Category.name == "Anahtar").first() is not None


def test_token_sayfalara_basiliyor(client, make_user, login_as):
    """Şablon token'ı basmazsa koruma kullanıcıyı da kilitler — bu test onu yakalar."""
    _, user_token = make_user("ahmet@example.com")
    login_as(user_token)
    csrf_token = client.cookies[csrf.COOKIE_NAME]

    for path in ["/", "/catalog/", "/customers/", "/login", "/register"]:
        html = client.get(path).text
        assert csrf_token in html, f"{path} sayfasında CSRF token'ı yok"
