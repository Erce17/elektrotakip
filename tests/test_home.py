"""Ana panel ve sayfa gezinmesi."""

import pytest

from app.models import Category, Customer, Product


@pytest.fixture
def ahmet(db_session, make_user, login_as):
    user, token = make_user("ahmet@example.com")
    login_as(token)

    category = Category(name="Kablo", user_id=user.id)
    db_session.add(category)
    db_session.commit()
    db_session.refresh(category)
    db_session.add_all([
        Product(name="A", category_id=category.id, unit_price=1),
        Product(name="B", category_id=category.id, unit_price=2),
    ])
    db_session.add(Customer(name="Kadıköy Elektrik", user_id=user.id))
    db_session.commit()
    return user


def test_giris_yapmadan_ana_panel_login_e_yonlendirir(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_ana_panel_gercek_sayilari_gosterir(client, ahmet):
    """Kutular eskiden sabit metindi ('Ürünler eklenecek')."""
    response = client.get("/")

    assert response.status_code == 200
    assert ahmet.email in response.text
    # 2 ürün, 1 müşteri
    assert ">2<" in response.text
    assert ">1<" in response.text


def test_ana_panel_sayilari_kullaniciya_ozel(client, login_as, make_user, ahmet):
    _, mehmet_token = make_user("mehmet@example.com")
    login_as(mehmet_token)

    response = client.get("/")

    assert response.status_code == 200
    assert "henüz malzeme yok" in response.text
    assert "henüz müşteri yok" in response.text


@pytest.mark.parametrize("path", ["/", "/catalog/", "/customers/"])
def test_her_sayfada_gezinme_linkleri_var(client, ahmet, path):
    """Eskiden müşteriler sayfasına ancak URL yazarak gidiliyordu."""
    response = client.get(path)

    assert response.status_code == 200
    assert 'href="/catalog"' in response.text
    assert 'href="/customers"' in response.text


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_giris_sayfalarinda_gezinme_yok(client, path):
    response = client.get(path)

    assert response.status_code == 200
    assert 'href="/customers"' not in response.text
