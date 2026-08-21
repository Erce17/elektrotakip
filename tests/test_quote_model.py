"""Teklif modeli ve ORM↔motor köprüsü testleri.

Motorun kendi testleri `test_quote_engine.py`'da. Burada sınanan şey farklı: kayıtlı
teklif motora doğru çevriliyor mu, fiyat gerçekten donuyor mu, kısıtlar tutuyor mu.
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app import quote_engine as motor
from app import quote_service
from app.models import (
    Category,
    Customer,
    Product,
    Quote,
    QuoteAdjustment,
    QuoteDefaults,
    QuoteItem,
    User,
)


def D(deger) -> Decimal:
    return Decimal(str(deger))


@pytest.fixture
def user(db_session):
    kullanici = User(email="teklif@test.com", password_hash="x")
    db_session.add(kullanici)
    db_session.commit()
    return kullanici


@pytest.fixture
def urun(db_session, user):
    kategori = Category(name="Kablo", user_id=user.id)
    db_session.add(kategori)
    db_session.flush()
    p = Product(
        name="NYA 2.5 mm²",
        brand="Öznur",
        category_id=kategori.id,
        unit_price=D("12.3456"),
        vat_rate=20,
        unit="Metre",
        currency="TRY",
        supplier_code="OZ-NYA-25",
    )
    db_session.add(p)
    db_session.commit()
    return p


def teklif_kur(db_session, user, kalemler=(), zincir=()):
    teklif = Quote(user_id=user.id, number="2026-001", items=list(kalemler),
                   adjustments=list(zincir))
    db_session.add(teklif)
    db_session.commit()
    return teklif


def basit_kalem(**kwargs) -> QuoteItem:
    kwargs.setdefault("name", "kalem")
    kwargs.setdefault("quantity", D(1))
    kwargs.setdefault("source_unit_price", kwargs.get("unit_price", D(100)))
    kwargs.setdefault("unit_price", D(100))
    return QuoteItem(**kwargs)


# =============================================================================
# Fiyatın donması
# =============================================================================


def test_katalog_fiyati_degisince_teklif_degismez(db_session, user, urun):
    """Kablo fiyatı bakıra ve dolara endeksli, günlük oynar.

    Ürünle canlı bağ kurulsaydı katalog güncellenince geçmiş teklifler kendiliğinden
    bozulurdu. Bu testin kırılması ürünün güvenilirliğinin bittiği yerdir.
    """
    kalem = quote_service.kalem_kur(urun, miktar=D(100))
    teklif = teklif_kur(db_session, user, [kalem])
    once = quote_service.hesapla(teklif).ara_toplam

    urun.unit_price = D("99.9999")
    db_session.commit()
    db_session.refresh(teklif)

    assert quote_service.hesapla(teklif).ara_toplam == once
    assert teklif.items[0].unit_price == D("12.3456")


def test_urun_silinse_de_teklif_hesaplanir(db_session, user, urun):
    kalem = quote_service.kalem_kur(urun, miktar=D(10))
    teklif = teklif_kur(db_session, user, [kalem])
    beklenen = quote_service.hesapla(teklif).genel_toplam

    teklif.items[0].product_id = None  # ürün silindiğinde kalacak hâl
    db_session.commit()
    assert quote_service.hesapla(teklif).genel_toplam == beklenen


def test_kalem_kur_kuru_ve_kaynak_fiyati_dondurur(db_session, user, urun):
    """Klemsan EURO veriyor; kur donmazsa aynı teklif ertesi gün başka rakam gösterir."""
    urun.currency = "EUR"
    db_session.commit()

    kalem = quote_service.kalem_kur(urun, miktar=D(1), kur=D("47.3000"))
    assert kalem.source_currency == "EUR"
    assert kalem.source_unit_price == D("12.3456")
    assert kalem.fx_rate == D("47.3000")
    assert kalem.unit_price == D("583.9469")  # 12,3456 × 47,3


def test_kalem_kur_tedarikci_kodunu_tasir(urun):
    """Entegrasyon sonradan gelecek; kod taşınmazsa o iş baştan yazmak demek."""
    assert quote_service.kalem_kur(urun, miktar=D(1)).supplier_code == "OZ-NYA-25"


# =============================================================================
# ORM → motor köprüsü
# =============================================================================


def test_kalem_iskonto_zinciri_sirayla_uygulanir(db_session, user):
    kalem = basit_kalem(unit_price=D(1000), source_unit_price=D(1000))
    kalem.adjustments = [
        QuoteAdjustment(position=0, kind=motor.ISKONTO_YUZDE, value=D(20)),
        QuoteAdjustment(position=1, kind=motor.ISKONTO_YUZDE, value=D(10)),
    ]
    teklif = teklif_kur(db_session, user, [kalem])
    assert quote_service.hesapla(teklif).ara_toplam == D("720.00")


def test_teklif_zinciri_position_sirasina_gore_uygulanir(db_session, user):
    """DB satır sırasını garanti etmez; sıra `position`'dan gelmeli."""
    kalem = basit_kalem(unit_price=D(1000), source_unit_price=D(1000))
    # Bilerek ters sırada ekleniyor.
    zincir = [
        QuoteAdjustment(position=1, kind=motor.EK_YUZDE, value=D(10), label="İşçilik",
                        scope=motor.KAPSAM_TUMU),
        QuoteAdjustment(position=0, kind=motor.ISKONTO_YUZDE, value=D(20),
                        scope=motor.KAPSAM_TUMU),
    ]
    teklif = teklif_kur(db_session, user, [kalem], zincir)
    sonuc = quote_service.hesapla(teklif)
    assert [z.ad for z in sonuc.zincir] == ["iskonto_yuzde", "İşçilik"]
    assert sonuc.ara_toplam == D("880.00")  # önce iskonto (800), sonra %10 işçilik


def test_iscilik_kalemi_iskontodan_muaf_kalir(db_session, user):
    kalemler = [
        basit_kalem(position=0, name="malzeme", unit_price=D(1000), source_unit_price=D(1000)),
        basit_kalem(position=1, name="işçilik", unit_price=D(500), source_unit_price=D(500),
                    kind=motor.ISCILIK, discountable=False),
    ]
    zincir = [QuoteAdjustment(position=0, kind=motor.ISKONTO_YUZDE, value=D(20))]
    teklif = teklif_kur(db_session, user, kalemler, zincir)
    assert quote_service.hesapla(teklif).ara_toplam == D("1300.00")


def test_varsayilan_kdv_isletme_ayarindan_gelir(db_session, user):
    db_session.add(QuoteDefaults(user_id=user.id, vat_rate=D(10)))
    db_session.commit()

    kalem = basit_kalem(unit_price=D(1000), source_unit_price=D(1000))
    zincir = [QuoteAdjustment(position=0, kind=motor.EK_TUTAR, value=D(100), label="Nakliye")]
    teklif = teklif_kur(db_session, user, [kalem], zincir)
    db_session.refresh(teklif)

    assert quote_service.hesapla(teklif).kalemler[-1].kdv_orani == D(10)


def test_bilesen_kalemi_ayri_satir_olarak_toplanmaz(db_session, user):
    """Anahtar/priz bileşen kararı verilmedi; alan bugün hesaba girmiyor.

    Bu test alanın varlığını değil, hesaba KARIŞMADIĞINI sabitliyor. Karar gelince
    burası bilinçli olarak değiştirilecek.
    """
    ana = basit_kalem(position=0, name="Priz", unit_price=D(684), source_unit_price=D(684))
    teklif = teklif_kur(db_session, user, [ana])

    bilesen = basit_kalem(position=1, name="Mekanizma", unit_price=D(472),
                          source_unit_price=D(472), quote_id=teklif.id,
                          parent_item_id=teklif.items[0].id)
    db_session.add(bilesen)
    db_session.commit()
    db_session.refresh(teklif)

    sonuc = quote_service.hesapla(teklif)
    assert len(sonuc.kalemler) == 1
    assert sonuc.ara_toplam == D("684.00")


# =============================================================================
# Şablondan zincir
# =============================================================================


def test_musteri_varsayilani_teklife_kopyalanir(db_session, user):
    """Kopyalanır, bağlanmaz: müşterinin varsayılanı değişince geçmiş teklif bozulmasın."""
    musteri = Customer(
        name="Akraba Elektrik",
        user_id=user.id,
        default_adjustments=[
            {"kind": motor.ISKONTO_YUZDE, "value": 20, "label": "Bayi"},
            {"kind": motor.ISKONTO_YUZDE, "value": 10, "label": "Ek"},
        ],
    )
    db_session.add(musteri)
    db_session.commit()

    kalem = basit_kalem(unit_price=D(1000), source_unit_price=D(1000))
    zincir = quote_service.sablondan_zincir(musteri.default_adjustments)
    teklif = teklif_kur(db_session, user, [kalem], zincir)
    assert quote_service.hesapla(teklif).ara_toplam == D("720.00")

    musteri.default_adjustments = []
    db_session.commit()
    db_session.refresh(teklif)
    assert quote_service.hesapla(teklif).ara_toplam == D("720.00")


def test_sablon_tanimsiz_anahtari_yutar(db_session):
    """Şablon JSON'u kullanıcı verisi; tanımadığımız anahtar hesabı patlatmamalı."""
    zincir = quote_service.sablondan_zincir(
        [{"kind": motor.ISKONTO_YUZDE, "value": 20, "uydurma_alan": 1}]
    )
    assert len(zincir) == 1
    assert zincir[0].value == D(20)


def test_sablon_eksik_satiri_atlanir():
    zincir = quote_service.sablondan_zincir([{"label": "eksik"}, {"kind": "iskonto_yuzde",
                                                                 "value": 5}])
    assert len(zincir) == 1


def test_sablon_bos_veya_none():
    assert quote_service.sablondan_zincir(None) == []
    assert quote_service.sablondan_zincir([]) == []


# =============================================================================
# Kısıtlar
# =============================================================================


def test_zincir_satiri_ya_tekliffe_ya_kaleme_ait(db_session, user):
    """Bir hesap adımı iki sahibi olamaz; ikisi de boş da kalamaz."""
    teklif = teklif_kur(db_session, user, [basit_kalem()])
    db_session.add(QuoteAdjustment(kind=motor.ISKONTO_YUZDE, value=D(10)))  # ikisi de boş
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        QuoteAdjustment(
            kind=motor.ISKONTO_YUZDE,
            value=D(10),
            quote_id=teklif.id,
            quote_item_id=teklif.items[0].id,  # ikisi birden
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_ayni_teklif_numarasi_ayni_versiyonda_tekrarlanamaz(db_session, user):
    teklif_kur(db_session, user, [basit_kalem()])
    db_session.add(Quote(user_id=user.id, number="2026-001", version=1))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_revizyon_ayni_numarayla_yeni_versiyon_acar(db_session, user):
    """Revizyon eskisini değiştirmez; ikisi yan yana durur."""
    ilk = teklif_kur(db_session, user, [basit_kalem(unit_price=D(1000),
                                                    source_unit_price=D(1000))])
    revizyon = Quote(
        user_id=user.id,
        number=ilk.number,
        version=2,
        parent_quote_id=ilk.id,
        items=[basit_kalem(unit_price=D(900), source_unit_price=D(900))],
    )
    db_session.add(revizyon)
    db_session.commit()

    assert quote_service.hesapla(ilk).ara_toplam == D("1000.00")
    assert quote_service.hesapla(revizyon).ara_toplam == D("900.00")
    assert ilk.revisions[0].id == revizyon.id


def test_teklif_silinince_kalem_ve_zincir_de_silinir(db_session, user):
    kalem = basit_kalem()
    kalem.adjustments = [QuoteAdjustment(position=0, kind=motor.ISKONTO_YUZDE, value=D(5))]
    zincir = [QuoteAdjustment(position=0, kind=motor.ISKONTO_YUZDE, value=D(10))]
    teklif = teklif_kur(db_session, user, [kalem], zincir)

    db_session.delete(teklif)
    db_session.commit()
    assert db_session.query(QuoteItem).count() == 0
    assert db_session.query(QuoteAdjustment).count() == 0


def test_gecerlilik_tarihi_saklanir(db_session, user):
    """Teklif dondurulmuş fiyat taşıyor; ne zamana kadar geçerli olduğu zorunlu bilgi."""
    teklif = teklif_kur(db_session, user, [basit_kalem()])
    teklif.valid_until = date(2026, 9, 5)
    db_session.commit()
    db_session.refresh(teklif)
    assert teklif.valid_until == date(2026, 9, 5)
