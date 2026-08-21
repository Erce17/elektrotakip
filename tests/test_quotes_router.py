"""Teklif ekranı: erişim kontrolü, kalem/zincir akışı, ekrandaki rakamlar.

Motorun kendi testleri `test_quote_engine.py`'da, model köprüsü
`test_quote_model.py`'da. Burada sınanan şey farklı: route doğru kalemi kuruyor mu,
başkasının teklifine erişilebiliyor mu, ekranda çıkan rakam motorun dediği mi.
"""

from decimal import Decimal

import pytest

from app.models import Category, Customer, Product, Quote, QuoteAdjustment, QuoteItem


def D(deger) -> Decimal:
    return Decimal(str(deger))


@pytest.fixture
def kullanici(client, make_user, login_as):
    user, token = make_user("teklifci@example.com")
    login_as(token)
    return user


@pytest.fixture
def urun(db_session, kullanici):
    kategori = Category(name="Kablo", user_id=kullanici.id)
    db_session.add(kategori)
    db_session.flush()
    p = Product(
        name="NYA 2.5 mm²",
        category_id=kategori.id,
        unit_price=D("100"),
        vat_rate=20,
        unit="Metre",
        currency="TRY",
    )
    db_session.add(p)
    db_session.commit()
    return p


def teklif_ac(client, title="Villa tesisatı", customer_id=""):
    cevap = client.post(
        "/quotes",
        data={"title": title, "customer_id": customer_id},
        follow_redirects=False,
    )
    assert cevap.status_code == 303
    return int(cevap.headers["location"].rsplit("/", 1)[1])


# =============================================================================
# Erişim kontrolü
# =============================================================================


def test_giris_yapmadan_teklifler_gorunmez(raw_client):
    cevap = raw_client.get("/quotes", follow_redirects=False)
    assert cevap.status_code in (302, 303, 307, 401, 403)


def test_baskasinin_teklifi_gorunmez(client, db_session, make_user, login_as, kullanici):
    teklif_id = teklif_ac(client)

    _, baska_token = make_user("baskasi@example.com")
    login_as(baska_token)

    assert client.get(f"/quotes/{teklif_id}").status_code == 404
    # Listede de görünmemeli
    assert "Villa tesisatı" not in client.get("/quotes").text


def test_baskasinin_teklifine_kalem_eklenemez(client, db_session, make_user, login_as, kullanici):
    teklif_id = teklif_ac(client)

    _, baska_token = make_user("baskasi@example.com")
    login_as(baska_token)
    cevap = client.post(
        f"/quotes/{teklif_id}/items",
        data={"name": "sızma", "unit_price": "1", "quantity": "1"},
    )

    assert cevap.status_code == 404
    assert db_session.query(QuoteItem).count() == 0


def test_baskasinin_teklifi_silinemez(client, db_session, make_user, login_as, kullanici):
    teklif_id = teklif_ac(client)

    _, baska_token = make_user("baskasi@example.com")
    login_as(baska_token)
    client.post(f"/quotes/{teklif_id}/delete", follow_redirects=False)

    assert db_session.query(Quote).count() == 1


def test_baska_kullanicinin_urunu_kaleme_alinamaz(
    client, db_session, make_user, login_as, kullanici, urun
):
    """Ürünün sahibi kategorisi üzerinden belli; teklif tarafında da doğrulanmalı."""
    _, baska_token = make_user("baskasi@example.com")
    login_as(baska_token)
    baska_teklif = teklif_ac(client)

    cevap = client.post(
        f"/quotes/{baska_teklif}/items",
        data={"product_id": str(urun.id), "quantity": "5"},
    )

    assert cevap.status_code == 404
    assert db_session.query(QuoteItem).count() == 0


# =============================================================================
# Teklif açma
# =============================================================================


def test_teklif_numarasi_otomatik_ve_artan(client, db_session, kullanici):
    teklif_ac(client, "birinci")
    teklif_ac(client, "ikinci")

    numaralar = sorted(q.number for q in db_session.query(Quote).all())
    assert len(numaralar) == 2
    assert numaralar[0].endswith("-001")
    assert numaralar[1].endswith("-002")


def test_iki_kullanici_ayni_numarayi_kullanabilir(
    client, db_session, make_user, login_as, kullanici
):
    """Numara kullanıcıya görünen kimlik; tekillik kullanıcı içinde."""
    teklif_ac(client, "benim")

    _, baska_token = make_user("baskasi@example.com")
    login_as(baska_token)
    teklif_ac(client, "onun")

    numaralar = [q.number for q in db_session.query(Quote).all()]
    assert numaralar[0] == numaralar[1]


def test_silinen_numara_geri_kazanilir(client, db_session, kullanici):
    ilk = teklif_ac(client, "birinci")
    client.post(f"/quotes/{ilk}/delete", follow_redirects=False)
    teklif_ac(client, "ikinci")

    assert db_session.query(Quote).one().number.endswith("-001")


def test_musterinin_varsayilan_zinciri_teklife_kopyalanir(client, db_session, kullanici):
    """Kopyalanır, bağlanmaz: müşterinin varsayılanı değişince geçmiş teklif bozulmasın."""
    musteri = Customer(
        name="Akraba Elektrik",
        user_id=kullanici.id,
        default_adjustments=[
            {"kind": "iskonto_yuzde", "value": 20, "label": "Bayi"},
            {"kind": "iskonto_yuzde", "value": 10, "label": "Ek"},
        ],
    )
    db_session.add(musteri)
    db_session.commit()

    teklif_id = teklif_ac(client, "villa", customer_id=str(musteri.id))
    teklif = db_session.get(Quote, teklif_id)

    assert [a.value for a in teklif.adjustments] == [D(20), D(10)]

    musteri.default_adjustments = []
    db_session.commit()
    assert len(db_session.get(Quote, teklif_id).adjustments) == 2


def test_gecerlilik_tarihi_varsayilandan_gelir(client, db_session, kullanici):
    """Teklif dondurulmuş fiyat taşıyor; ne zamana kadar geçerli olduğu zorunlu."""
    teklif_id = teklif_ac(client)
    assert db_session.get(Quote, teklif_id).valid_until is not None


def test_baska_kullanicinin_musterisi_teklife_baglanmaz(
    client, db_session, make_user, login_as, kullanici
):
    baska, baska_token = make_user("baskasi@example.com")
    musteri = Customer(name="Onun müşterisi", user_id=baska.id)
    db_session.add(musteri)
    db_session.commit()

    teklif_id = teklif_ac(client, "villa", customer_id=str(musteri.id))
    assert db_session.get(Quote, teklif_id).customer_id is None


# =============================================================================
# Kalemler
# =============================================================================


def test_katalogdan_kalem_eklenir_ve_fiyat_donar(client, db_session, kullanici, urun):
    teklif_id = teklif_ac(client)
    cevap = client.post(
        f"/quotes/{teklif_id}/items",
        data={"product_id": str(urun.id), "quantity": "10"},
    )
    assert cevap.status_code == 200

    kalem = db_session.query(QuoteItem).one()
    assert kalem.unit_price == D("100.0000")
    assert kalem.product_id == urun.id

    # Katalog fiyatı değişse teklif değişmiyor
    urun.unit_price = D("999")
    db_session.commit()
    assert "1.000,00" in client.get(f"/quotes/{teklif_id}").text


def test_kurlu_kalem_teklif_para_biriminde_donar(client, db_session, kullanici, urun):
    """Klemsan EURO veriyor; kur donmazsa aynı teklif ertesi gün başka rakam gösterir."""
    urun.currency = "EUR"
    db_session.commit()

    teklif_id = teklif_ac(client)
    client.post(
        f"/quotes/{teklif_id}/items",
        data={"product_id": str(urun.id), "quantity": "1", "fx_rate": "47,30"},
    )

    kalem = db_session.query(QuoteItem).one()
    assert kalem.source_currency == "EUR"
    assert kalem.source_unit_price == D("100")
    assert kalem.fx_rate == D("47.30")
    assert kalem.unit_price == D("4730.0000")


def test_kalem_iskonto_zinciri_carpimsal_uygulanir(client, db_session, kullanici, urun):
    """'20/10' yazımı sektörde böyle konuşuluyor. Sonuç 720, 700 değil."""
    teklif_id = teklif_ac(client)
    client.post(
        f"/quotes/{teklif_id}/items",
        data={"product_id": str(urun.id), "quantity": "10", "discounts": "20/10"},
    )

    assert "720,00" in client.get(f"/quotes/{teklif_id}").text


def test_elle_kalem_eklenir(client, db_session, kullanici):
    teklif_id = teklif_ac(client)
    client.post(
        f"/quotes/{teklif_id}/items",
        data={"name": "Kablo çekimi", "quantity": "1", "unit_price": "1.500,50",
              "kind": "diger"},
    )

    kalem = db_session.query(QuoteItem).one()
    assert kalem.name == "Kablo çekimi"
    assert kalem.unit_price == D("1500.5000")
    assert kalem.discountable is True


def test_iscilik_kalemi_iskontoya_tabi_degil_eklenir(client, db_session, kullanici):
    """Sektörde işçiliğe iskonto genelde uygulanmıyor; varsayılan bunu yansıtıyor."""
    teklif_id = teklif_ac(client)
    client.post(
        f"/quotes/{teklif_id}/items",
        data={"name": "İşçilik", "quantity": "1", "unit_price": "500", "kind": "iscilik"},
    )

    kalem = db_session.query(QuoteItem).one()
    assert kalem.kind == "iscilik"
    assert kalem.discountable is False


def test_adsiz_elle_kalem_reddedilir(client, db_session, kullanici):
    teklif_id = teklif_ac(client)
    cevap = client.post(f"/quotes/{teklif_id}/items", data={"name": "  ", "unit_price": "5"})

    assert cevap.status_code == 400
    assert db_session.query(QuoteItem).count() == 0


def test_kalem_guncellenir(client, db_session, kullanici, urun):
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "10"})
    kalem = db_session.query(QuoteItem).one()

    client.post(
        f"/quotes/{teklif_id}/items/{kalem.id}",
        data={"quantity": "20", "unit_price": "50", "discounts": "10",
              "discountable": "true"},
    )
    db_session.refresh(kalem)

    assert kalem.quantity == D(20)
    assert kalem.unit_price == D("50")
    assert [a.value for a in kalem.adjustments] == [D(10)]
    # 20 × 50 = 1000, %10 iskonto → 900
    assert "900,00" in client.get(f"/quotes/{teklif_id}").text


def test_kalem_guncellemede_zincir_bastan_kurulur(client, db_session, kullanici, urun):
    """Kısmi güncelleme sırayı bozardı; eski satırlar silinip yeniden yazılıyor."""
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "1", "discounts": "20/10/5"})
    kalem = db_session.query(QuoteItem).one()
    assert len(kalem.adjustments) == 3

    client.post(f"/quotes/{teklif_id}/items/{kalem.id}", data={"discounts": "15"})
    db_session.refresh(kalem)

    assert [a.value for a in kalem.adjustments] == [D(15)]
    assert db_session.query(QuoteAdjustment).count() == 1


def test_kalem_silinir(client, db_session, kullanici, urun):
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "1"})
    kalem = db_session.query(QuoteItem).one()

    cevap = client.request("DELETE", f"/quotes/{teklif_id}/items/{kalem.id}")

    assert cevap.status_code == 200
    assert db_session.query(QuoteItem).count() == 0


def test_kalem_silinince_kendi_iskonto_zinciri_de_silinir(client, db_session, kullanici, urun):
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "1", "discounts": "20/10"})
    kalem = db_session.query(QuoteItem).one()

    client.request("DELETE", f"/quotes/{teklif_id}/items/{kalem.id}")

    assert db_session.query(QuoteAdjustment).count() == 0


# =============================================================================
# Hesap zinciri
# =============================================================================


def test_zincire_genel_iskonto_eklenir(client, db_session, kullanici, urun):
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "10"})
    client.post(
        f"/quotes/{teklif_id}/adjustments",
        data={"kind": "iskonto_yuzde", "value": "20", "label": "Bayi", "scope": "tumu"},
    )

    assert "800,00" in client.get(f"/quotes/{teklif_id}").text


def test_bilinmeyen_zincir_adimi_reddedilir(client, db_session, kullanici):
    teklif_id = teklif_ac(client)
    cevap = client.post(
        f"/quotes/{teklif_id}/adjustments", data={"kind": "uydurma", "value": "5"}
    )

    assert cevap.status_code == 400
    assert db_session.query(QuoteAdjustment).count() == 0


def test_iscilik_zincir_adimi_olarak_eklenir(client, db_session, kullanici, urun):
    """'Malzemenin %10'u işçilik' kalıbı: ek satır, kendi KDV oranıyla."""
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "10"})
    client.post(
        f"/quotes/{teklif_id}/adjustments",
        data={"kind": "ek_yuzde", "value": "10", "label": "İşçilik", "scope": "tumu",
              "added_kind": "iscilik", "vat_rate": "20"},
    )

    sayfa = client.get(f"/quotes/{teklif_id}").text
    assert "İşçilik" in sayfa
    # 1000 + 100 = 1100
    assert "1.100,00" in sayfa


def test_zincir_sirasi_degistirilebilir_ve_sonuc_degisir(client, db_session, kullanici, urun):
    """Sıranın değiştirilebilir olması ürünün varlık sebebi.

    İskonto sadece malzemeye uygulanıyorsa:
    - işçilik önce, iskonto sonra → 1000×0,8 + 100 = 900
    - iskonto önce, işçilik sonra → 800 + 80 = 880
    """
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "10"})

    client.post(
        f"/quotes/{teklif_id}/adjustments",
        data={"kind": "ek_yuzde", "value": "10", "label": "İşçilik",
              "scope": "tumu", "added_kind": "iscilik"},
    )
    client.post(
        f"/quotes/{teklif_id}/adjustments",
        data={"kind": "iskonto_yuzde", "value": "20", "label": "Bayi",
              "scope": "iskontoya_tabi"},
    )
    assert "900,00" in client.get(f"/quotes/{teklif_id}").text

    # İskontoyu yukarı taşı: artık işçilik iskontolu tutarın yüzdesi
    iskonto = (
        db_session.query(QuoteAdjustment)
        .filter(QuoteAdjustment.label == "Bayi")
        .one()
    )
    client.post(
        f"/quotes/{teklif_id}/adjustments/{iskonto.id}/move", data={"yon": "up"}
    )

    assert "880,00" in client.get(f"/quotes/{teklif_id}").text


def test_zincir_ucundan_disari_tasinmaz(client, db_session, kullanici):
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/adjustments",
                data={"kind": "iskonto_yuzde", "value": "20"})
    adim = db_session.query(QuoteAdjustment).one()

    client.post(f"/quotes/{teklif_id}/adjustments/{adim.id}/move", data={"yon": "up"})
    db_session.refresh(adim)
    assert adim.position == 0

    client.post(f"/quotes/{teklif_id}/adjustments/{adim.id}/move", data={"yon": "down"})
    db_session.refresh(adim)
    assert adim.position == 0


def test_zincir_adimi_silinir(client, db_session, kullanici):
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/adjustments",
                data={"kind": "iskonto_yuzde", "value": "20"})
    adim = db_session.query(QuoteAdjustment).one()

    client.request("DELETE", f"/quotes/{teklif_id}/adjustments/{adim.id}")

    assert db_session.query(QuoteAdjustment).count() == 0


def test_zincir_adimi_baska_teklife_ait_degilse_silinmez(
    client, db_session, kullanici, urun
):
    birinci = teklif_ac(client, "birinci")
    ikinci = teklif_ac(client, "ikinci")
    client.post(f"/quotes/{birinci}/adjustments",
                data={"kind": "iskonto_yuzde", "value": "20"})
    adim = db_session.query(QuoteAdjustment).one()

    client.request("DELETE", f"/quotes/{ikinci}/adjustments/{adim.id}")

    assert db_session.query(QuoteAdjustment).count() == 1


# =============================================================================
# Ekrandaki rakamlar
# =============================================================================


def test_karisik_kdv_orani_ekranda_ayri_dokuluyor(client, db_session, kullanici):
    """Karışık KDV oranlı teklifte tek satır yanlış rakam verir; e-fatura da oran ister."""
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"name": "malzeme", "quantity": "1", "unit_price": "1000",
                      "vat_rate": "20"})
    client.post(f"/quotes/{teklif_id}/items",
                data={"name": "kitap", "quantity": "1", "unit_price": "1000",
                      "vat_rate": "10"})

    sayfa = client.get(f"/quotes/{teklif_id}").text
    assert "KDV %20" in sayfa
    assert "KDV %10" in sayfa
    assert "2.300,00" in sayfa  # 2000 + 200 + 100


def test_bos_teklif_ekrani_patlamaz(client, db_session, kullanici):
    teklif_id = teklif_ac(client)
    cevap = client.get(f"/quotes/{teklif_id}")

    assert cevap.status_code == 200
    assert "Henüz kalem yok" in cevap.text


def test_liste_teklif_toplamini_gosterir(client, db_session, kullanici, urun):
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "10"})

    sayfa = client.get("/quotes").text
    assert "Villa tesisatı" in sayfa
    assert "1.200,00" in sayfa  # 1000 + %20 KDV


def test_teklif_bilgileri_guncellenir(client, db_session, kullanici):
    teklif_id = teklif_ac(client)
    client.post(
        f"/quotes/{teklif_id}",
        data={"title": "Yeni ad", "currency": "EUR", "valid_until": "2026-09-30",
              "notes": "peşin"},
        follow_redirects=False,
    )

    teklif = db_session.get(Quote, teklif_id)
    assert teklif.title == "Yeni ad"
    assert teklif.currency == "EUR"
    assert teklif.valid_until.isoformat() == "2026-09-30"
    assert teklif.notes == "peşin"


def test_para_birimi_degismesi_kalem_fiyatini_bozmaz(client, db_session, kullanici, urun):
    """Teklif kendi kopyasının sahibi; para birimi etiketi fiyatı çevirmez."""
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "10"})

    client.post(f"/quotes/{teklif_id}", data={"currency": "EUR"}, follow_redirects=False)

    assert db_session.query(QuoteItem).one().unit_price == D("100.0000")


def test_teklif_silinince_kalemler_de_silinir(client, db_session, kullanici, urun):
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "1", "discounts": "20"})

    client.post(f"/quotes/{teklif_id}/delete", follow_redirects=False)

    assert db_session.query(Quote).count() == 0
    assert db_session.query(QuoteItem).count() == 0
    assert db_session.query(QuoteAdjustment).count() == 0


def test_ana_panel_teklif_sayisini_gosterir(client, db_session, kullanici):
    teklif_ac(client)
    teklif_ac(client, "ikinci")

    sayfa = client.get("/").text
    assert "Teklifler" in sayfa
    assert "Bu modül henüz yazılmadı" not in sayfa


def test_bilesen_kalemi_ekrandaki_eslesmeyi_kaydirmaz(client, db_session, kullanici, urun):
    """Motorun çıktısı ile DB kalemleri indeks üzerinden eşleştirilmemeli.

    Motor bileşen kalemlerini atlıyor, `quote.items` atlamıyor. İndeks sayılsaydı
    araya bir bileşen girdiği anda silme düğmeleri yanlış kaleme bağlanırdı — yani
    kullanıcı A'yı silmek isteyip B'yi silerdi. Anahtar/priz kararı "şimdilik ayrı
    kalemler" olduğu için bu alan bugün kullanılmıyor; test kaymanın olmadığını
    sabitliyor.
    """
    import re

    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"name": "birinci", "quantity": "1", "unit_price": "100"})
    client.post(f"/quotes/{teklif_id}/items",
                data={"name": "ikinci", "quantity": "1", "unit_price": "200"})
    birinci, ikinci = db_session.query(QuoteItem).order_by(QuoteItem.position).all()

    # Birinci kalemin bileşeni: hesaba girmiyor, ekranda da satırı olmamalı
    db_session.add(QuoteItem(
        quote_id=teklif_id, parent_item_id=birinci.id, position=1,
        name="bilesen", quantity=D(1), source_unit_price=D(50), unit_price=D(50),
    ))
    db_session.commit()

    sayfa = client.get(f"/quotes/{teklif_id}").text
    silme_sirasi = re.findall(rf'hx-delete="/quotes/{teklif_id}/items/(\d+)"', sayfa)

    assert "bilesen" not in sayfa
    assert silme_sirasi == [str(birinci.id), str(ikinci.id)]


def test_zincirin_ekledigi_satirin_silme_dugmesi_yok(client, db_session, kullanici):
    """İşçilik zincirden geliyorsa kalem satırı DB'de yok; silme düğmesi çıkmamalı."""
    import re

    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"name": "malzeme", "quantity": "1", "unit_price": "1000"})
    client.post(f"/quotes/{teklif_id}/adjustments",
                data={"kind": "ek_tutar", "value": "250", "label": "Nakliye"})

    sayfa = client.get(f"/quotes/{teklif_id}").text
    kalem = db_session.query(QuoteItem).one()

    assert "Nakliye" in sayfa
    assert re.findall(rf'hx-delete="/quotes/{teklif_id}/items/(\d+)"', sayfa) == [str(kalem.id)]
