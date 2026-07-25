"""Birim normalleştirme ve KM → metre dönüşümü.

Yanlış birim doğrudan yanlış fiyat demek: KM listesindeki 850.000 TL, metre
fiyatı sanılırsa ürün milyonlarca liraya çıkıyor.
"""

from decimal import Decimal

import pytest

from app.models import Category, Product
from app.routers.catalog import normalize_unit
from tests.test_excel_import import yukle


@pytest.fixture
def kullanici(client, make_user, login_as):
    user, token = make_user("ahmet@example.com")
    login_as(token)
    return user


@pytest.mark.parametrize(
    "girdi,beklenen",
    [
        ("KM", "KM"), ("km", "KM"), ("Km.", "KM"), ("1000 m", "KM"), ("kilometre", "KM"),
        ("MT", "Metre"), ("mt.", "Metre"), ("metre", "Metre"), ("m", "Metre"),
        ("AD", "Adet"), ("adet", "Adet"), ("ADT", "Adet"),
        ("kutu", "Kutu"), ("PKT", "Paket"), ("kg", "Kg"),
        ("", ""), ("   ", ""),          # belirtilmemiş, 'Adet' ile karışmasın
        ("Rulo Başı", "Rulo Başı"),     # tanımadığımız yazım korunur
    ],
)
def test_birim_normallestirme(girdi, beklenen):
    assert normalize_unit(girdi) == beklenen


def fiyat_of(db_session, spec):
    return db_session.query(Product).filter(Product.technical_specs == spec).first()


def test_satirdaki_km_birimi_kutucuk_isaretsizken_de_cevrilir(client, db_session, kullanici):
    """Asıl 'milyon TL' hatası buydu: kutucuk unutulunca KM fiyatı metre fiyatı sanılıyordu."""
    yukle(client, [["Kablo", "3x2.5", "Öznur", "850.000,00", "KM"]])

    urun = fiyat_of(db_session, "3x2.5")
    assert urun.unit_price == Decimal("850.0000")
    assert urun.unit == "Metre"


def test_adet_bazli_satir_kutucuk_isaretliyken_bile_bolunmez(client, db_session, kullanici):
    """Karışık dosyada kutucuk işaretlenince anahtar/priz fiyatları kuruşa düşüyordu."""
    yukle(client, [
        ["Kablo", "3x2.5", "Öznur", "12.500,00", "Metre"],
        ["Anahtar", "16A", "Viko", "85,00", "Adet"],
        ["Buat", "10x10", "Viko", "40,00", "Kutu"],
    ], is_km_price=True)

    assert fiyat_of(db_session, "3x2.5").unit_price == Decimal("12.5000")
    assert fiyat_of(db_session, "16A").unit_price == Decimal("85.0000")
    assert fiyat_of(db_session, "16A").unit == "Adet"
    assert fiyat_of(db_session, "10x10").unit_price == Decimal("40.0000")


def test_kutucuk_birimi_belirtilmemis_satirlar_icin_calisir(client, db_session, kullanici):
    """Birim sütunu boş gelen KM listeleri için kutucuk hâlâ gerekli."""
    yukle(client, [["Kablo", "3x2.5", "Öznur", "12.500,00", None]], is_km_price=True)

    urun = fiyat_of(db_session, "3x2.5")
    assert urun.unit_price == Decimal("12.5000")
    assert urun.unit == "Metre"


def test_birim_yazimlari_tek_bicime_getirilir(client, db_session, kullanici):
    """'MT', 'mt.', 'metre' listede üç ayrı birim gibi görünmemeli."""
    yukle(client, [
        ["Kablo", "3x1.5", "Öznur", "10", "MT"],
        ["Kablo", "3x2.5", "Öznur", "20", "mt."],
        ["Kablo", "3x4", "Öznur", "30", "Metre"],
    ])

    birimler = {u.unit for u in db_session.query(Product).all()}
    assert birimler == {"Metre"}


def test_km_bolumunde_kurus_alti_deger_korunur(client, db_session, kullanici):
    """Numeric(10,2) ile 3,5 TL/km fiyatı 0,00'a yuvarlanıyordu."""
    yukle(client, [["Kablo", "0.5mm", "Öznur", "3,50", "KM"]])

    assert fiyat_of(db_session, "0.5mm").unit_price == Decimal("0.0035")


def test_sinir_disi_fiyat_ice_aktarmayi_cokertmez(client, db_session, kullanici):
    """Kolon sınırını aşan değer Postgres'te DataError veriyordu."""
    response = yukle(client, [
        ["Kablo", "3x2.5", "Öznur", "999999999999", "Metre"],
        ["Anahtar", "16A", "Viko", "85", "Adet"],
    ])

    assert response.status_code == 303
    assert "fiyatsiz=1" in response.headers["location"]
    # Ürün yine de giriyor, fiyatı düzeltilmek üzere 0
    assert fiyat_of(db_session, "3x2.5").unit_price == Decimal("0.0000")
    assert fiyat_of(db_session, "16A").unit_price == Decimal("85.0000")


# --- Elle ürün ekleme ----------------------------------------------------

def test_elle_eklerken_virgullu_fiyat_kabul_edilir(client, db_session, kullanici):
    """Form alanı type=number iken '1.200,50' reddediliyordu."""
    client.post("/catalog/category", data={"name": "Kablo"}, follow_redirects=False)
    kategori_id = db_session.query(Category).first().id

    response = client.post("/catalog/product", data={
        "brand": "Öznur", "technical_specs": "3x2.5",
        "category_id": kategori_id, "unit_price": "1.200,50", "unit": "mt",
    }, follow_redirects=False)

    assert response.status_code == 303
    urun = db_session.query(Product).first()
    assert urun.unit_price == Decimal("1200.5000")
    assert urun.unit == "Metre"  # birim burada da normalleşiyor


def test_elle_eklerken_okunamayan_fiyat_reddedilir(client, db_session, kullanici):
    client.post("/catalog/category", data={"name": "Kablo"}, follow_redirects=False)
    kategori_id = db_session.query(Category).first().id

    response = client.post("/catalog/product", data={
        "brand": "Öznur", "technical_specs": "3x2.5",
        "category_id": kategori_id, "unit_price": "fiyat sorunuz",
    }, follow_redirects=False)

    assert response.status_code == 400
    assert db_session.query(Product).count() == 0
