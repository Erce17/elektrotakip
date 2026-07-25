"""Müşteri erişim kontrolü ve veri izolasyonu.

customers.py'da izolasyon zaten doğruydu; bu testler require_user'a geçerken
davranışın bozulmadığını sabitler.
"""

import pytest

from app.models import Customer

MUSTERI_ADI = "Kadıköy Elektrik Ltd."


@pytest.fixture
def ahmet(db_session, make_user):
    user, token = make_user("ahmet@example.com")
    customer = Customer(name=MUSTERI_ADI, phone="5551112233", user_id=user.id)
    db_session.add(customer)
    db_session.commit()
    db_session.refresh(customer)
    return {"user": user, "token": token, "customer": customer}


@pytest.fixture
def mehmet(make_user):
    user, token = make_user("mehmet@example.com")
    return {"user": user, "token": token}


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/customers/"),
        ("POST", "/customers/"),
        ("GET", "/customers/1/edit"),
        ("GET", "/customers/1/row"),
        ("PUT", "/customers/1"),
        ("DELETE", "/customers/1"),
    ],
)
def test_giris_yapmadan_musteriye_erisilemez(client, method, path):
    response = client.request(method, path, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_baskasinin_musterisi_listede_gorunmez(client, login_as, ahmet, mehmet):
    login_as(mehmet["token"])
    response = client.get("/customers/")

    assert response.status_code == 200
    assert MUSTERI_ADI not in response.text


def test_baskasinin_musterisi_okunamaz(client, login_as, ahmet, mehmet):
    login_as(mehmet["token"])
    customer_id = ahmet["customer"].id

    assert client.get(f"/customers/{customer_id}/edit").status_code == 404
    assert client.get(f"/customers/{customer_id}/row").status_code == 404


def test_baskasinin_musterisi_silinemez(client, login_as, db_session, ahmet, mehmet):
    login_as(mehmet["token"])
    customer_id = ahmet["customer"].id

    client.delete(f"/customers/{customer_id}")

    assert db_session.query(Customer).filter(Customer.id == customer_id).first() is not None


def test_baskasinin_musterisi_guncellenemez(client, login_as, db_session, ahmet, mehmet):
    login_as(mehmet["token"])
    customer_id = ahmet["customer"].id

    response = client.put(f"/customers/{customer_id}", data={"name": "Sahte"})

    assert response.status_code == 404
    db_session.expire_all()
    assert db_session.query(Customer).filter(Customer.id == customer_id).first().name == MUSTERI_ADI


def test_musteri_giris_yapan_kullaniciya_yazilir(client, login_as, db_session, mehmet):
    login_as(mehmet["token"])

    client.post("/customers/", data={"name": "Yeni Müşteri"}, follow_redirects=False)

    customer = db_session.query(Customer).filter(Customer.name == "Yeni Müşteri").first()
    assert customer is not None
    assert customer.user_id == mehmet["user"].id


def test_sahibi_kendi_musterisine_erisebilir(client, login_as, ahmet):
    login_as(ahmet["token"])
    customer_id = ahmet["customer"].id

    assert MUSTERI_ADI in client.get("/customers/").text
    assert client.get(f"/customers/{customer_id}/edit").status_code == 200
    assert client.get(f"/customers/{customer_id}/row").status_code == 200
