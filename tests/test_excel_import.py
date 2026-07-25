"""Excel içe aktarma.

Mantık gerçek kullanımdan çıkmış: KM bazlı fiyatın metreye çevrilmesi, Türkçe
sayı formatı ve mükerrer atlama. Bu testler o davranışları sabitler; ayrıca
bozuk girdide 500 dönmediğini doğrular.
"""

import io

import openpyxl
import pytest

from app.models import Category, Product

BASLIKLAR = ["Kategori", "Teknik Özellik", "Marka", "Birim Fiyat", "Birim"]


def excel_dosyasi(satirlar, basliklar=BASLIKLAR):
    """Verilen satırlardan bellekte bir .xlsx üretir."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(basliklar)
    for satir in satirlar:
        ws.append(satir)
    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


def yukle(client, satirlar, is_km_price=False):
    data = {"is_km_price": "true"} if is_km_price else {}
    return client.post(
        "/catalog/import-excel",
        files={"file": ("liste.xlsx", excel_dosyasi(satirlar), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data=data,
        follow_redirects=False,
    )


@pytest.fixture
def kullanici(client, make_user, login_as):
    user, token = make_user("ahmet@example.com")
    login_as(token)
    return user


# --- Temel akış ----------------------------------------------------------

def test_satirlar_kategorisiyle_birlikte_aktarilir(client, db_session, kullanici):
    response = yukle(client, [
        ["Kablo", "3x2.5", "Öznur", "1.200,50", "Metre"],
        ["Anahtar", "16A", "Viko", "85", "Adet"],
    ])

    assert response.status_code == 303
    assert "eklendi=2" in response.headers["location"]

    assert db_session.query(Product).count() == 2
    # Kategoriler otomatik oluşur ve yükleyen kullanıcıya yazılır
    kategoriler = db_session.query(Category).all()
    assert {k.name for k in kategoriler} == {"Kablo", "Anahtar"}
    assert all(k.user_id == kullanici.id for k in kategoriler)

    kablo = db_session.query(Product).filter(Product.brand == "Öznur").first()
    assert float(kablo.unit_price) == pytest.approx(1200.50)
    assert kablo.name == "Öznur 3x2.5 Kablo"


def test_km_bazli_fiyat_metreye_cevrilir(client, db_session, kullanici):
    """1000 metrelik liste fiyatı metre birim fiyatına döner."""
    yukle(client, [["Kablo", "3x2.5", "Öznur", "12.500,00", "KM"]], is_km_price=True)

    urun = db_session.query(Product).first()
    assert float(urun.unit_price) == pytest.approx(12.5)
    assert urun.unit == "Metre"


def test_mukerrer_satirlar_atlanir(client, db_session, kullanici):
    """Aynı kategori + özellik + marka ikinci kez eklenmez."""
    yukle(client, [["Kablo", "3x2.5", "Öznur", "100", "Metre"]])
    response = yukle(client, [
        ["Kablo", "3x2.5", "Öznur", "999", "Metre"],   # zaten var
        ["Kablo", "3x1.5", "Öznur", "80", "Metre"],    # yeni
    ])

    assert "eklendi=1" in response.headers["location"]
    assert "atlandi=1" in response.headers["location"]
    assert db_session.query(Product).count() == 2
    # Mükerrer satır mevcut fiyatı ezmemeli
    assert float(db_session.query(Product).filter(Product.technical_specs == "3x2.5").first().unit_price) == 100


def test_ayni_dosyadaki_mukerrer_satir_da_atlanir(client, db_session, kullanici):
    """Commit edilmemiş satırları DB sorgusu görmediği için ayrıca takip ediliyor."""
    response = yukle(client, [
        ["Kablo", "3x2.5", "Öznur", "100", "Metre"],
        ["Kablo", "3x2.5", "Öznur", "100", "Metre"],
    ])

    assert "eklendi=1" in response.headers["location"]
    assert db_session.query(Product).count() == 1


def test_bos_satirlar_atlanir(client, db_session, kullanici):
    response = yukle(client, [
        ["Kablo", "3x2.5", "Öznur", "100", "Metre"],
        [None, None, None, None, None],
    ])

    assert "eklendi=1" in response.headers["location"]
    assert db_session.query(Product).count() == 1


def test_okunamayan_fiyat_sifirlanir_ve_raporlanir(client, db_session, kullanici):
    """Satır atılmaz — ürün girsin, kullanıcı fiyatı sonra düzeltsin."""
    response = yukle(client, [["Kablo", "3x2.5", "Öznur", "fiyat sorunuz", "Metre"]])

    assert "fiyatsiz=1" in response.headers["location"]
    urun = db_session.query(Product).first()
    assert float(urun.unit_price) == 0


def test_eksik_kategori_diger_olur(client, db_session, kullanici):
    yukle(client, [[None, "3x2.5", "Öznur", "100", "Metre"]])

    assert db_session.query(Category).first().name == "Diğer"


# --- Bozuk girdi ---------------------------------------------------------

def test_xlsx_olmayan_dosya_reddedilir(client, db_session, kullanici):
    response = client.post(
        "/catalog/import-excel",
        files={"file": ("liste.csv", io.BytesIO(b"a,b,c"), "text/csv")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "hata=" in response.headers["location"]
    assert db_session.query(Product).count() == 0


def test_bozuk_xlsx_500_dondurmez(client, db_session, kullanici):
    """Eskiden openpyxl hatası doğrudan 500'e çıkıyordu."""
    response = client.post(
        "/catalog/import-excel",
        files={"file": ("liste.xlsx", io.BytesIO(b"bu bir excel dosyasi degil"), "application/vnd.ms-excel")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "hata=" in response.headers["location"]
    assert db_session.query(Product).count() == 0


def test_bos_dosya_reddedilir(client, kullanici):
    response = client.post(
        "/catalog/import-excel",
        files={"file": ("liste.xlsx", io.BytesIO(b""), "application/vnd.ms-excel")},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "hata=" in response.headers["location"]


def test_sadece_baslik_iceren_dosya_hata_vermez(client, db_session, kullanici):
    response = yukle(client, [])

    assert response.status_code == 303
    assert "eklendi=0" in response.headers["location"]
    assert db_session.query(Product).count() == 0


# --- İzolasyon -----------------------------------------------------------

def test_ayni_isimli_kategori_baska_kullaniciya_yazilmaz(client, db_session, make_user, login_as, kullanici):
    """Ahmet'in 'Kablo' kategorisi varken Mehmet yüklerse kendi kategorisi açılır."""
    yukle(client, [["Kablo", "3x2.5", "Öznur", "100", "Metre"]])

    _, mehmet_token = make_user("mehmet@example.com")
    login_as(mehmet_token)
    yukle(client, [["Kablo", "3x1.5", "Hes", "80", "Metre"]])

    kablo_kategorileri = db_session.query(Category).filter(Category.name == "Kablo").all()
    assert len(kablo_kategorileri) == 2
    assert {k.user_id for k in kablo_kategorileri} == {kullanici.id, kullanici.id + 1}
