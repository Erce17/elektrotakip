"""Teklif çıktısı, revizyon ve işletme varsayılanları.

Kalem/zincir akışı `test_quotes_router.py`'da. Burada sınanan şey: çıktıda doğru
rakam çıkıyor mu, revizyon eskisini bozuyor mu, varsayılanlar teklife geçiyor mu.
"""

from decimal import Decimal

import pytest

from app.models import (
    Category,
    Customer,
    Product,
    Quote,
    QuoteAdjustment,
    QuoteDefaults,
    QuoteItem,
)


def D(deger) -> Decimal:
    return Decimal(str(deger))


@pytest.fixture
def kullanici(client, make_user, login_as):
    user, token = make_user("ciktici@example.com")
    login_as(token)
    return user


@pytest.fixture
def urun(db_session, kullanici):
    kategori = Category(name="Kablo", user_id=kullanici.id)
    db_session.add(kategori)
    db_session.flush()
    p = Product(name="NYA 2.5", category_id=kategori.id, unit_price=D("100"),
                vat_rate=20, unit="Metre", currency="TRY")
    db_session.add(p)
    db_session.commit()
    return p


def teklif_ac(client, title="Villa tesisatı", customer_id=""):
    cevap = client.post("/quotes", data={"title": title, "customer_id": customer_id},
                        follow_redirects=False)
    return int(cevap.headers["location"].rsplit("/", 1)[1])


# =============================================================================
# Yazdırılabilir çıktı
# =============================================================================


def test_ciktida_toplamlar_ekrandakiyle_ayni(client, db_session, kullanici, urun):
    """İki ekran aynı motoru çağırıyor; rakamların ayrışması mümkün olmamalı."""
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "10", "discounts": "20"})
    client.post(f"/quotes/{teklif_id}/adjustments",
                data={"kind": "ek_tutar", "value": "250", "label": "Nakliye"})

    cikti = client.get(f"/quotes/{teklif_id}/print")

    assert cikti.status_code == 200
    # 800 malzeme + 250 nakliye = 1050; KDV %20 → 210; toplam 1260
    assert "1.050,00" in cikti.text
    assert "1.260,00" in cikti.text
    assert "Nakliye" in cikti.text


def test_cikti_gezinme_ve_cdn_tasimaz(client, db_session, kullanici):
    """Kâğıda gezinme basılmamalı; yazdırma anında CDN beklemesi de olmamalı."""
    teklif_id = teklif_ac(client)
    cikti = client.get(f"/quotes/{teklif_id}/print").text

    assert "Ana Panel" not in cikti
    assert "cdn.tailwindcss.com" not in cikti
    assert "Çıkış Yap" not in cikti


def test_ciktida_musteri_bilgileri_var(client, db_session, kullanici):
    musteri = Customer(name="Akraba Elektrik", phone="0555 111 22 33",
                       address="Sanayi Sitesi No 5", user_id=kullanici.id)
    db_session.add(musteri)
    db_session.commit()

    teklif_id = teklif_ac(client, customer_id=str(musteri.id))
    cikti = client.get(f"/quotes/{teklif_id}/print").text

    assert "Akraba Elektrik" in cikti
    assert "0555 111 22 33" in cikti
    assert "Sanayi Sitesi No 5" in cikti


def test_ciktida_kdv_orana_gore_dokuluyor(client, db_session, kullanici):
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"name": "malzeme", "quantity": "1", "unit_price": "1000",
                      "vat_rate": "20"})
    client.post(f"/quotes/{teklif_id}/items",
                data={"name": "kitap", "quantity": "1", "unit_price": "1000",
                      "vat_rate": "10"})

    cikti = client.get(f"/quotes/{teklif_id}/print").text

    assert "KDV %20" in cikti
    assert "KDV %10" in cikti


def test_ciktida_gecerlilik_tarihi_yaziyor(client, db_session, kullanici):
    """Teklif dondurulmuş fiyat taşıyor; müşteri ne zamana kadar geçerli olduğunu görmeli."""
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}", data={"valid_until": "2026-09-30"},
                follow_redirects=False)

    cikti = client.get(f"/quotes/{teklif_id}/print").text
    assert "30.09.2026" in cikti
    assert "geçerlidir" in cikti


def test_baskasinin_teklifinin_ciktisi_alinamaz(client, db_session, make_user, login_as,
                                                 kullanici):
    teklif_id = teklif_ac(client)

    _, baska_token = make_user("baskasi@example.com")
    login_as(baska_token)

    assert client.get(f"/quotes/{teklif_id}/print").status_code == 404


def test_bos_teklifin_ciktisi_patlamaz(client, db_session, kullanici):
    teklif_id = teklif_ac(client)
    assert client.get(f"/quotes/{teklif_id}/print").status_code == 200


# =============================================================================
# Revizyon
# =============================================================================


def test_revizyon_eskisini_bozmaz(client, db_session, kullanici, urun):
    """Revizyon demonun en güçlü anı; eskisini değiştirseydi anlamı kalmazdı."""
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "10"})

    cevap = client.post(f"/quotes/{teklif_id}/revise", follow_redirects=False)
    yeni_id = int(cevap.headers["location"].rsplit("/", 1)[1])

    eski = db_session.get(Quote, teklif_id)
    yeni = db_session.get(Quote, yeni_id)

    assert yeni.id != eski.id
    assert yeni.number == eski.number
    assert yeni.version == 2
    assert yeni.parent_quote_id == eski.id
    assert len(eski.items) == 1 and len(yeni.items) == 1
    # Kalemler ayrı kayıtlar: birini değiştirmek diğerini etkilemiyor
    assert yeni.items[0].id != eski.items[0].id


def test_revizyonda_dondurulmus_fiyat_ve_kur_korunur(client, db_session, kullanici, urun):
    """Revizyon 'aynı işin yeni teklifi'; fiyat güncellemesi ayrı bir karar."""
    urun.currency = "EUR"
    db_session.commit()

    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "1", "fx_rate": "47,30"})

    urun.unit_price = D("999")  # katalog değişti
    db_session.commit()

    cevap = client.post(f"/quotes/{teklif_id}/revise", follow_redirects=False)
    yeni = db_session.get(Quote, int(cevap.headers["location"].rsplit("/", 1)[1]))

    kalem = yeni.items[0]
    assert kalem.source_currency == "EUR"
    assert kalem.source_unit_price == D("100")
    assert kalem.fx_rate == D("47.30")
    assert kalem.unit_price == D("4730.0000")


def test_revizyonda_zincir_de_kopyalanir(client, db_session, kullanici, urun):
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "10", "discounts": "20/10"})
    client.post(f"/quotes/{teklif_id}/adjustments",
                data={"kind": "iskonto_yuzde", "value": "5", "label": "Genel",
                      "scope": "tumu"})

    cevap = client.post(f"/quotes/{teklif_id}/revise", follow_redirects=False)
    yeni_id = int(cevap.headers["location"].rsplit("/", 1)[1])

    yeni = db_session.get(Quote, yeni_id)
    assert [a.value for a in yeni.adjustments] == [D(5)]
    assert [a.value for a in yeni.items[0].adjustments] == [D(20), D(10)]
    # Toplam ikisinde de aynı: 1000 → 720 → %5 → 684
    assert "684,00" in client.get(f"/quotes/{yeni_id}").text
    assert "684,00" in client.get(f"/quotes/{teklif_id}").text


def test_ucuncu_revizyon_versiyonu_dogru_artar(client, db_session, kullanici):
    ilk = teklif_ac(client)
    ikinci = int(client.post(f"/quotes/{ilk}/revise", follow_redirects=False)
                 .headers["location"].rsplit("/", 1)[1])
    # Revizyonun revizyonu değil, ilkinden tekrar revizyon açmak da 3 vermeli
    ucuncu = int(client.post(f"/quotes/{ilk}/revise", follow_redirects=False)
                 .headers["location"].rsplit("/", 1)[1])

    assert db_session.get(Quote, ikinci).version == 2
    assert db_session.get(Quote, ucuncu).version == 3


def test_revizyon_listede_ayri_satir_olarak_durur(client, db_session, kullanici):
    # Formdaki örnek metinle karışmasın diye ayırt edici bir başlık
    teklif_id = teklif_ac(client, "Depo aydınlatması")
    client.post(f"/quotes/{teklif_id}/revise", follow_redirects=False)

    sayfa = client.get("/quotes").text
    assert sayfa.count("Depo aydınlatması") == 2
    assert "rev 2" in sayfa


def test_baskasinin_teklifi_revize_edilemez(client, db_session, make_user, login_as,
                                            kullanici):
    teklif_id = teklif_ac(client)

    _, baska_token = make_user("baskasi@example.com")
    login_as(baska_token)
    client.post(f"/quotes/{teklif_id}/revise", follow_redirects=False)

    assert db_session.query(Quote).count() == 1


# =============================================================================
# İşletme varsayılanları
# =============================================================================


def test_ayarlar_sayfasi_teklif_id_sanilmaz(client, db_session, kullanici):
    """`/quotes/settings` route'u `/quotes/{id}`'den ÖNCE tanımlı olmalı."""
    cevap = client.get("/quotes/settings")

    assert cevap.status_code == 200
    assert "Teklif Varsayılanları" in cevap.text


def test_ayar_yoksa_ilk_bakista_olusur(client, db_session, kullanici):
    assert db_session.query(QuoteDefaults).count() == 0
    client.get("/quotes/settings")
    assert db_session.query(QuoteDefaults).count() == 1


def test_ayarlar_kaydedilir(client, db_session, kullanici):
    client.post("/quotes/settings",
                data={"currency": "EUR", "vat_rate": "10", "labor_vat_rate": "20",
                      "validity_days": "30"},
                follow_redirects=False)

    ayar = db_session.query(QuoteDefaults).one()
    assert ayar.currency == "EUR"
    assert ayar.vat_rate == D(10)
    assert ayar.validity_days == 30


def test_gecerlilik_gunu_en_az_bir(client, db_session, kullanici):
    """Sıfır gün geçerli teklif anlamsız; tarih bugünden geriye kaymamalı."""
    client.post("/quotes/settings", data={"validity_days": "0"}, follow_redirects=False)
    assert db_session.query(QuoteDefaults).one().validity_days == 1


def test_varsayilan_para_birimi_yeni_teklife_geciyor(client, db_session, kullanici):
    client.post("/quotes/settings", data={"currency": "USD"}, follow_redirects=False)
    teklif_id = teklif_ac(client)

    assert db_session.get(Quote, teklif_id).currency == "USD"


def test_varsayilan_gecerlilik_suresi_yeni_teklife_geciyor(client, db_session, kullanici):
    from datetime import date, timedelta

    client.post("/quotes/settings", data={"validity_days": "45"}, follow_redirects=False)
    teklif_id = teklif_ac(client)

    beklenen = date.today() + timedelta(days=45)
    assert db_session.get(Quote, teklif_id).valid_until == beklenen


def test_varsayilan_kdv_zincirin_ekledigi_satira_uygulanir(client, db_session, kullanici):
    client.post("/quotes/settings", data={"vat_rate": "10"}, follow_redirects=False)
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"name": "malzeme", "quantity": "1", "unit_price": "1000",
                      "vat_rate": "20"})
    # KDV oranı verilmeden ek satır: motor işletme varsayılanını kullanmalı
    client.post(f"/quotes/{teklif_id}/adjustments",
                data={"kind": "ek_tutar", "value": "100", "label": "Nakliye"})

    sayfa = client.get(f"/quotes/{teklif_id}").text
    assert "KDV %10" in sayfa


# --- Varsayılan zincir şablonu ---


def test_sablona_adim_eklenir_ve_yeni_teklife_kopyalanir(client, db_session, kullanici,
                                                          urun):
    """Asıl kazanç burada: iskontoyu bir kez tanımla, her teklifte hazır gelsin."""
    client.post("/quotes/settings/template",
                data={"kind": "iskonto_yuzde", "value": "20", "label": "Bayi",
                      "scope": "tumu"},
                follow_redirects=False)
    client.post("/quotes/settings/template",
                data={"kind": "iskonto_yuzde", "value": "10", "label": "Ek",
                      "scope": "tumu"},
                follow_redirects=False)

    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "10"})

    teklif = db_session.get(Quote, teklif_id)
    assert [a.value for a in teklif.adjustments] == [D(20), D(10)]
    # Çarpımsal: 1000 → 800 → 720
    assert "720,00" in client.get(f"/quotes/{teklif_id}").text


def test_sablon_degisince_gecmis_teklif_bozulmaz(client, db_session, kullanici, urun):
    """Şablon kopyalanır, bağlanmaz — donmuş fiyat kararının aynısı."""
    client.post("/quotes/settings/template",
                data={"kind": "iskonto_yuzde", "value": "20", "scope": "tumu"},
                follow_redirects=False)
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "10"})

    client.post("/quotes/settings/template/0/delete", follow_redirects=False)

    assert "800,00" in client.get(f"/quotes/{teklif_id}").text


def test_musterinin_zinciri_isletme_sablonunu_yener(client, db_session, kullanici, urun):
    """Müşteriye özel oran varsa işletme varsayılanı devreye girmemeli."""
    client.post("/quotes/settings/template",
                data={"kind": "iskonto_yuzde", "value": "20", "scope": "tumu"},
                follow_redirects=False)
    musteri = Customer(
        name="Özel müşteri", user_id=kullanici.id,
        default_adjustments=[{"kind": "iskonto_yuzde", "value": 40, "scope": "tumu"}],
    )
    db_session.add(musteri)
    db_session.commit()

    teklif_id = teklif_ac(client, customer_id=str(musteri.id))
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "10"})

    assert [a.value for a in db_session.get(Quote, teklif_id).adjustments] == [D(40)]
    assert "600,00" in client.get(f"/quotes/{teklif_id}").text


def test_sablon_adimi_silinir_ve_sira_yeniden_numaralanir(client, db_session, kullanici):
    for deger in ("10", "20", "30"):
        client.post("/quotes/settings/template",
                    data={"kind": "iskonto_yuzde", "value": deger},
                    follow_redirects=False)

    client.post("/quotes/settings/template/1/delete", follow_redirects=False)

    sablon = db_session.query(QuoteDefaults).one().adjustment_template
    assert [s["value"] for s in sablon] == ["10", "30"]
    assert [s["position"] for s in sablon] == [0, 1]


def test_bilinmeyen_sablon_adimi_eklenmez(client, db_session, kullanici):
    client.post("/quotes/settings/template",
                data={"kind": "uydurma", "value": "5"}, follow_redirects=False)

    assert db_session.query(QuoteDefaults).one().adjustment_template == []


def test_olmayan_sablon_satiri_silinmeye_calisilirsa_patlamaz(client, db_session, kullanici):
    cevap = client.post("/quotes/settings/template/99/delete", follow_redirects=False)
    assert cevap.status_code == 303


def test_ayarlar_kullaniciya_ozel(client, db_session, make_user, login_as, kullanici):
    client.post("/quotes/settings", data={"currency": "EUR"}, follow_redirects=False)

    _, baska_token = make_user("baskasi@example.com")
    login_as(baska_token)
    client.get("/quotes/settings")

    ayarlar = {a.user_id: a.currency for a in db_session.query(QuoteDefaults).all()}
    assert len(ayarlar) == 2
    assert ayarlar[kullanici.id] == "EUR"
    assert ayarlar[kullanici.id + 1] == "TRY"


def test_giris_yapmadan_ayarlara_erisilemez(raw_client):
    cevap = raw_client.get("/quotes/settings", follow_redirects=False)
    assert cevap.status_code in (302, 303, 307, 401, 403)


# =============================================================================
# Temizlik
# =============================================================================


def test_revizyon_silinince_kalemleri_de_gider(client, db_session, kullanici, urun):
    teklif_id = teklif_ac(client)
    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "1", "discounts": "20"})
    cevap = client.post(f"/quotes/{teklif_id}/revise", follow_redirects=False)
    yeni_id = int(cevap.headers["location"].rsplit("/", 1)[1])

    client.post(f"/quotes/{yeni_id}/delete", follow_redirects=False)

    assert db_session.query(Quote).count() == 1
    assert db_session.query(QuoteItem).count() == 1
    assert db_session.query(QuoteAdjustment).count() == 1


def test_ilk_surum_silinince_revizyonu_silinmez(client, db_session, kullanici, urun):
    """Revizyon ayrı bir tekliftir, alt kayıt değil.

    `delete-orphan` cascade'i konulduğunda 1. sürümü silmek 2. sürümü de
    götürüyordu — kullanıcı eskisini temizlerken en güncel teklifini kaybederdi.
    """
    ilk = teklif_ac(client, "Depo aydınlatması")
    client.post(f"/quotes/{ilk}/items",
                data={"product_id": str(urun.id), "quantity": "10"})
    cevap = client.post(f"/quotes/{ilk}/revise", follow_redirects=False)
    revizyon_id = int(cevap.headers["location"].rsplit("/", 1)[1])

    client.post(f"/quotes/{ilk}/delete", follow_redirects=False)

    kalan = db_session.query(Quote).one()
    assert kalan.id == revizyon_id
    assert kalan.version == 2
    assert kalan.parent_quote_id is None  # köksüz kaldı, silinmedi
    assert len(kalan.items) == 1
    assert client.get(f"/quotes/{revizyon_id}").status_code == 200
