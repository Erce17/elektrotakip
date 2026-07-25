"""Katalog erişim kontrolü ve veri izolasyonu.

Denetimde bulunan iki açığı sabitler:
  - /catalog/* route'ları giriş yapmadan erişilebiliyordu
  - ürün sorguları sadece Product.id ile yapıldığı için başkasının ürünü
    okunabiliyor/silinebiliyordu (IDOR)
"""

import pytest

from app.models import Category, Product

# Şablonlarda geçmeyen bir marka: "bu metin sayfada var mı" kontrolü yanlış
# pozitif vermesin diye özellikle seçildi.
MARKA = "Zeta"


@pytest.fixture
def ahmet(db_session, make_user):
    """Bir kategori ve bir ürün sahibi kullanıcı."""
    user, token = make_user("ahmet@example.com")
    category = Category(name="Kablo", user_id=user.id)
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)

    product = Product(
        name=f"{MARKA} 3x2.5 Kablo",
        brand=MARKA,
        technical_specs="3x2.5",
        category_id=category.id,
        unit_price=100,
        unit="Metre",
    )
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    return {"user": user, "token": token, "category": category, "product": product}


@pytest.fixture
def mehmet(make_user):
    """Ahmet'in verisine erişmeye çalışan ikinci kullanıcı."""
    user, token = make_user("mehmet@example.com")
    return {"user": user, "token": token}


# --- Giriş zorunluluğu ---------------------------------------------------

@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/catalog/"),
        ("GET", "/catalog/search"),
        ("GET", "/catalog/download-template"),
        ("POST", "/catalog/category"),
        ("POST", "/catalog/product"),
        ("POST", "/catalog/import-excel"),
        ("GET", "/catalog/product/1"),
        ("GET", "/catalog/product/1/edit"),
        ("PUT", "/catalog/product/1"),
        ("DELETE", "/catalog/product/1"),
    ],
)
def test_giris_yapmadan_katalog_erisilemez(client, method, path):
    response = client.request(method, path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_htmx_isteginde_yonlendirme_hx_redirect_ile_gelir(client):
    """Satır içine login sayfası basılmasın diye HTMX'e 401 + HX-Redirect döner."""
    response = client.delete(
        "/catalog/product/1",
        headers={"HX-Request": "true"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert response.headers["HX-Redirect"] == "/login"


def test_gecersiz_token_ile_erisilemez(client, login_as):
    login_as("uydurma.token.degeri")
    response = client.get("/catalog/", follow_redirects=False)
    assert response.status_code == 303


# --- Veri izolasyonu -----------------------------------------------------

def test_baskasinin_urunu_listede_gorunmez(client, login_as, ahmet, mehmet):
    login_as(mehmet["token"])
    response = client.get("/catalog/")

    assert response.status_code == 200
    assert MARKA not in response.text


def test_baskasinin_urunu_aramada_cikmaz(client, login_as, ahmet, mehmet):
    login_as(mehmet["token"])
    assert MARKA not in client.get("/catalog/search", params={"q": MARKA}).text

    # Sahibi arayınca bulabiliyor olmalı — filtre fazla geniş kesmiş olmasın
    login_as(ahmet["token"])
    assert MARKA in client.get("/catalog/search", params={"q": MARKA}).text


def test_baskasinin_urunu_okunamaz(client, login_as, ahmet, mehmet):
    login_as(mehmet["token"])
    product_id = ahmet["product"].id

    assert client.get(f"/catalog/product/{product_id}").status_code == 404
    assert client.get(f"/catalog/product/{product_id}/edit").status_code == 404


def test_baskasinin_urunu_silinemez(client, login_as, db_session, ahmet, mehmet):
    login_as(mehmet["token"])
    product_id = ahmet["product"].id

    response = client.delete(f"/catalog/product/{product_id}")

    assert response.status_code == 200  # HTMX'e boş gövde döner
    assert db_session.query(Product).filter(Product.id == product_id).first() is not None


def test_baskasinin_urunu_guncellenemez(client, login_as, db_session, ahmet, mehmet):
    login_as(mehmet["token"])
    product_id = ahmet["product"].id

    response = client.put(
        f"/catalog/product/{product_id}",
        data={"brand": "Sahte", "category_id": ahmet["category"].id, "unit_price": "1"},
    )

    assert response.status_code == 404
    db_session.expire_all()
    assert db_session.query(Product).filter(Product.id == product_id).first().brand == MARKA


def test_baskasinin_kategorisine_urun_eklenemez(client, login_as, db_session, ahmet, mehmet):
    login_as(mehmet["token"])

    response = client.post(
        "/catalog/product",
        data={
            "brand": "Sahte",
            "technical_specs": "1x1",
            "category_id": ahmet["category"].id,
            "unit_price": 50,
        },
        follow_redirects=False,
    )

    assert response.status_code == 404
    assert db_session.query(Product).count() == 1


def test_kategori_giris_yapan_kullaniciya_yazilir(client, login_as, db_session, mehmet):
    """Eskiden user_id=1 hardcoded'dı; kategori her zaman ilk kullanıcıya gidiyordu."""
    login_as(mehmet["token"])

    client.post("/catalog/category", data={"name": "Anahtar"})

    category = db_session.query(Category).filter(Category.name == "Anahtar").first()
    assert category is not None
    assert category.user_id == mehmet["user"].id


def test_sahibi_kendi_urunune_erisebilir(client, login_as, ahmet):
    """İzolasyon fazla sıkı olup sahibini de kesmesin."""
    login_as(ahmet["token"])
    product_id = ahmet["product"].id

    assert client.get("/catalog/").status_code == 200
    assert client.get(f"/catalog/product/{product_id}").status_code == 200
    assert client.get(f"/catalog/product/{product_id}/edit").status_code == 200
