"""Ürün parametresi ayrıştırma ve arama.

Beklentiler 11 gerçek tedarikçi dosyasından ölçüldü. Özellikle **yanlış pozitif
testleri** önemli: çıplak `NxM` kalıbı bu dosyalarda çoğunlukla kablo değil ürün kodu,
kontak değeri veya fiziksel ölçü anlamına geliyor.
"""

import pathlib
from decimal import Decimal

import pytest

from app.excel_import import oku
from app.models import Category, Product
from app.product_search import (
    arama_terimini_coz,
    kesit_sutununu_coz,
    parametreleri_coz,
    urun_ara,
)

FIXTURE_DIZINI = pathlib.Path(__file__).parent / "fixtures" / "tedarikci_listeleri"


def D(deger) -> Decimal:
    return Decimal(str(deger))


# =============================================================================
# Kesit ve damar — serbest metinden
# =============================================================================


@pytest.mark.parametrize(
    "metin,kesit,damar",
    [
        ("CCTV-AL 1 COAX+2X0,22 mm2", D("0.22"), 2),
        ("DT-8 DIAPHONE 8x0,22 mm2", D("0.22"), 8),
        ("NYA 3x2,5 mm² bakır", D("2.5"), 3),
        ("3x2.5 mm2", D("2.5"), 3),
        ("0.5 mm², izoleli yüksük", D("0.5"), None),
        ("2,5 mm² tek damarlı", D("2.5"), None),
    ],
)
def test_kesit_ve_damar_metinden_okunur(metin, kesit, damar):
    p = parametreleri_coz(metin)
    assert p.cross_section == kesit
    assert p.core_count == damar


# --- Yanlış pozitifler: hepsi gerçek dosyalardan -----------------------------


@pytest.mark.parametrize(
    "metin",
    [
        "926Y5X01 Anahtar 12 384",              # Viko: ürün kodu
        "909080X4 Dörtlü Çerçeve 1 20",         # Viko: ürün kodu
        "REL 110V DC WIDE TYPE 2x8A/250VAC",    # Klemsan: kontak değeri
        "IP66 SILICONE COVER (96x96mm)",        # Klemsan: fiziksel ölçü
        "PYK 4S (5x20) BEJ",                    # Klemsan: fiziksel ölçü
        "96x96mm Enerji Analizörü",             # Tense: ekran boyutu
        "7 Kademe 3x20 mm 7 Segment Display",   # Tense: ekran boyutu
    ],
)
def test_kablo_olmayan_carpim_isaretleri_kesit_sanilmaz(metin):
    """`NxM` tek başına kesit değil. Kesit için `mm²` bağlamı şart."""
    p = parametreleri_coz(metin)
    assert p.cross_section is None
    assert p.core_count is None


def test_mm_bosluk_rakam_kesit_sanilmaz():
    """Tense'in '30X10 mm 200/5 Akım Trafosu' satırı akım trafosu, kablo değil.

    `mm\\s*[²2]` yazılmıştı ve "mm" + boşluk + "2" olarak eşleşip bu satırı
    30 damarlı 10 mm² kablo sanıyordu. Boşluklu biçimde artık yalnızca gerçek `²`
    kabul ediliyor.
    """
    p = parametreleri_coz("30X10 mm 200/5 Mühürsüz Delikli Akım Trafosu, Class 0.5,2.5VA")
    assert p.cross_section is None
    assert p.core_count is None


def test_kesit_araligi_kesit_olarak_yazilmaz():
    """Molwex'te '0.5-1.5 mm²' pabucun hizmet ettiği aralık, ürünün kendi kesiti değil.

    0,5 yazmak yanlış olurdu: 1,5 mm² arayan kullanıcı bu pabucu bulamazdı ve
    0,5 arayan yanlış eşleşme alırdı.
    """
    p = parametreleri_coz("0.5-1.5 mm², tam izoleli faston - dişi kablo pabucu")
    assert p.cross_section is None
    assert p.kesit_araligi_mi is True


def test_absurt_kesit_reddedilir():
    p = parametreleri_coz("9999 mm2")
    assert p.cross_section is None


# =============================================================================
# Kesit sütunu
# =============================================================================


@pytest.mark.parametrize(
    "ham,kesit,damar",
    [
        ("2.5", D("2.5"), None),
        ("1", D(1), None),
        ("4x25", D(25), 4),
        ("5x16", D(16), 5),
        ("2x1.5", D("1.5"), 2),
        ("3x25+16", D(25), 3),      # +16 nötr/toprak, damara katılmıyor
        ("3x50+25", D(50), 3),
        ("", None, None),
        ("   ", None, None),
        ("bilgi yok", None, None),
    ],
)
def test_kesit_sutunu_okunur(ham, kesit, damar):
    """Öznur'un kesit sütunu sahada konuşulan yazımı birebir taşıyor."""
    assert kesit_sutununu_coz(ham) == (kesit, damar)


def test_kesit_sutunu_metinden_okunana_tercih_edilir():
    """Öznur'da ad 5 satırda birebir aynı; ayırt eden şey sütun."""
    p = parametreleri_coz("H07V-U (NYA) 450/750 V", kesit_metni="4x25")
    assert p.cross_section == D(25)
    assert p.core_count == 4


# =============================================================================
# İletken, yalıtım, kılıf
# =============================================================================


@pytest.mark.parametrize(
    "metin,beklenen",
    [
        ("COAXIAL RG 6/U-6 Cu/Cu PVC", "bakır"),
        ("Tek Telli Bakır İletkenli", "bakır"),
        ("ALPEK alüminyum iletken", "alüminyum"),
        ("Klemens", None),
    ],
)
def test_iletken_taninir(metin, beklenen):
    assert parametreleri_coz(metin).conductor == beklenen


def test_iki_iletken_varsa_soldaki_kazanir():
    """Erse'nin koaksiyellerinde 'Cu/Al' ikisi birden geçiyor; kastedilen iç iletken."""
    assert parametreleri_coz("COAXIAL RG 6/U-4 Cu/Al Class C PVC").conductor == "bakır"


@pytest.mark.parametrize(
    "metin,beklenen",
    [
        ("N2XH XLPE izoleli", "XLPE"),
        ("COAXIAL RG 6 HFFR", "HFFR"),
        ("CAT-6 U/UTP LSZH", "LSZH"),
        ("PVC İzoleli, Kılıfsız", "PVC"),
        ("COAXIAL RG 6/U-6 Cu/Cu PE", "PE"),
        ("Klemens", None),
    ],
)
def test_yalitim_taninir(metin, beklenen):
    assert parametreleri_coz(metin).insulation == beklenen


def test_xlpe_pe_olarak_okunmaz():
    """'XLPE' içinde 'PE' geçiyor; uzun kalıp önce denenmeli."""
    assert parametreleri_coz("N2XH XLPE").insulation == "XLPE"


@pytest.mark.parametrize(
    "metin,beklenen",
    [
        ("PVC İzoleli, Kılıfsız, Tek Damarlı", False),
        ("PVC İzoleli, Kılıflı", True),
        ("Klemens", None),
    ],
)
def test_kilif_taninir(metin, beklenen):
    assert parametreleri_coz(metin).sheathed is beklenen


def test_bos_metin_bos_parametre():
    p = parametreleri_coz("", "")
    assert p.bos_mu
    assert p.cross_section is None


# =============================================================================
# Arama terimi ayrıştırma
# =============================================================================


def test_sahada_konusulan_ifade_anlasilir():
    """PROGRESS'teki asıl gereksinim: müşteri '3x2.5 NYY' diyor."""
    t = arama_terimini_coz("3x2.5 NYY")
    assert t.core_count == 3
    assert t.cross_section == D("2.5")
    assert t.metin == "NYY"


def test_iletken_kelimesi_hem_filtre_hem_metin_kalir():
    """'PVC' hem parametre hem ürün adının parçası olabiliyor; metinden atılmıyor."""
    t = arama_terimini_coz("5x16 bakır")
    assert t.core_count == 5
    assert t.cross_section == D(16)
    assert t.conductor == "bakır"
    assert "bakır" in t.metin


def test_kesit_araligi_aranabilir():
    """'2.5–6 mm² arası' filtresi bu işin baştaki gerekçesiydi."""
    t = arama_terimini_coz("2.5-6 mm2 nya")
    assert t.kesit_min == D("2.5")
    assert t.kesit_max == D(6)
    assert t.cross_section is None
    assert "nya" in t.metin


def test_tek_kesit_aranabilir():
    t = arama_terimini_coz("2,5 mm2")
    assert t.cross_section == D("2.5")
    assert t.core_count is None


def test_sadece_metin():
    t = arama_terimini_coz("klemens")
    assert not t.parametreli_mi
    assert t.metin == "klemens"


def test_bos_arama():
    t = arama_terimini_coz("")
    assert not t.parametreli_mi
    assert t.metin == ""
    assert arama_terimini_coz("   ").metin == ""


def test_ters_aralik_yok_sayilir():
    t = arama_terimini_coz("6-2.5")
    assert t.kesit_min is None


# =============================================================================
# Gerçek dosyalarla ölçüm
# =============================================================================


def dosya_kayitlari(ad: str):
    yol = FIXTURE_DIZINI / ad
    if not yol.exists():
        pytest.skip(f"fixture yok: {ad}")
    return oku(yol.read_bytes(), ad).satirlar


def test_oznur_tum_kablolarda_kesit_cikariliyor():
    """Öznur kablo tedarikçisi; kesit çıkmazsa bu işin anlamı yok.

    Kesit sütunu okunmadan önce 1673 satırın 0'ında kesit vardı.
    """
    kayitlar = dosya_kayitlari("Oznur_Kablo_Haziran_2026_PDFten.xlsx")
    parametreler = [
        parametreleri_coz(k.ad, k.aciklama, kesit_metni=k.kesit) for k in kayitlar
    ]
    kesitli = [p for p in parametreler if p.cross_section is not None]
    damarli = [p for p in parametreler if p.core_count is not None]

    assert len(kesitli) == len(kayitlar)      # hepsi
    assert len(damarli) > len(kayitlar) * 0.9  # tek damarlılarda damar yazmıyor


def test_erse_kablolarinda_kesit_cikariliyor():
    kayitlar = dosya_kayitlari("Erse_agustos_2025_fiyat_listesi.xlsx")
    kesitli = [
        k for k in kayitlar
        if parametreleri_coz(k.ad, k.aciklama, kesit_metni=k.kesit).cross_section is not None
    ]
    assert len(kesitli) > 250


@pytest.mark.parametrize(
    "ad",
    [
        "Viko_Panasonic_2026-2_PDFten.xlsx",
        "KLEMSAN-KASIM-2024-FIYAT-LISTESI-V2.xlsx",
        "Sezgin_Ocak_2026_Fiyat_Listesi.xlsx",
        "tense_subat_2026_fiyat_listesi.xlsx",
        "Kael_subat_2026_fiyat_listesi.xls",
        "POFACO-MART-2025-EXCEL.xlsx",
    ],
)
def test_kablo_olmayan_dosyalarda_kesit_uydurulmuyor(ad):
    """Bu dosyalarda kablo yok. Kesit çıkması ayrıştırma hatasıdır.

    Viko'da 532, Klemsan'da 496 satır `NxM` kalıbı içeriyor — hiçbiri kablo değil.
    """
    kayitlar = dosya_kayitlari(ad)
    kesitli = [
        k for k in kayitlar
        if parametreleri_coz(k.ad, k.aciklama, kesit_metni=k.kesit).cross_section is not None
    ]
    assert kesitli == [], f"{ad}: {len(kesitli)} satırda kesit uyduruldu"


# =============================================================================
# Sorgu — uçtan uca
# =============================================================================


@pytest.fixture
def kullanici(client, make_user, login_as):
    user, token = make_user("aramaci@example.com")
    login_as(token)
    return user


@pytest.fixture
def katalog(db_session, kullanici):
    """Küçük ama gerçekçi bir katalog: farklı kesit, damar ve iletken."""
    kategori = Category(name="Kablo", user_id=kullanici.id)
    db_session.add(kategori)
    db_session.flush()

    def urun(ad, kesit, damar, iletken=None, kod=None, fiyat="10"):
        return Product(
            name=ad, category_id=kategori.id, unit_price=D(fiyat), unit="Metre",
            currency="TRY", technical_specs=ad, supplier_code=kod,
            cross_section=D(kesit) if kesit else None, core_count=damar,
            conductor=iletken,
        )

    urunler = [
        urun("NYA 3x2.5 bakır", "2.5", 3, "bakır", "OZ-001"),
        urun("NYY 3x2.5 bakır", "2.5", 3, "bakır", "OZ-002"),
        urun("NYA 5x16 bakır", "16", 5, "bakır", "OZ-003"),
        urun("NYY 4x25 alüminyum", "25", 4, "alüminyum", "OZ-004"),
        urun("NYA 1x4 bakır", "4", None, "bakır", "OZ-005"),
        urun("Klemens 12'li", None, None, None, "KL-001"),
    ]
    db_session.add_all(urunler)
    db_session.commit()
    return urunler


def test_damar_ve_kesit_birlikte_daraltir(db_session, kullanici, katalog):
    sorgu = db_session.query(Product).join(Category)
    sonuc = urun_ara(sorgu, Product, "3x2.5")
    assert {u.name for u in sonuc} == {"NYA 3x2.5 bakır", "NYY 3x2.5 bakır"}


def test_metin_parametreyle_birlikte_daraltir(db_session, kullanici, katalog):
    """'3x2.5 NYY' yazınca kesiti tutan her şey değil, adı da NYY olan çıkmalı."""
    sorgu = db_session.query(Product).join(Category)
    sonuc = urun_ara(sorgu, Product, "3x2.5 NYY")
    assert [u.name for u in sonuc] == ["NYY 3x2.5 bakır"]


def test_kesit_araligi_daraltir(db_session, kullanici, katalog):
    sorgu = db_session.query(Product).join(Category)
    sonuc = urun_ara(sorgu, Product, "2.5-6 mm2")
    assert {u.name for u in sonuc} == {"NYA 3x2.5 bakır", "NYY 3x2.5 bakır", "NYA 1x4 bakır"}


def test_tedarikci_kodu_ile_bulunur(db_session, kullanici, katalog):
    sorgu = db_session.query(Product).join(Category)
    assert [u.name for u in urun_ara(sorgu, Product, "OZ-003")] == ["NYA 5x16 bakır"]


def test_parametresi_olmayan_urun_metinle_bulunur(db_session, kullanici, katalog):
    """Ayrıştırılamamış ürün kaybolmamalı."""
    sorgu = db_session.query(Product).join(Category)
    assert [u.name for u in urun_ara(sorgu, Product, "klemens")] == ["Klemens 12'li"]


def test_kelime_sirasi_onemli_degil(db_session, kullanici, katalog):
    sorgu = db_session.query(Product).join(Category)
    assert [u.name for u in urun_ara(sorgu, Product, "bakır NYY")] == ["NYY 3x2.5 bakır"]


def test_limit_uygulanir(db_session, kullanici, katalog):
    sorgu = db_session.query(Product).join(Category)
    assert len(urun_ara(sorgu, Product, "NY", limit=2)) == 2


# =============================================================================
# Ekranlar
# =============================================================================


def test_katalog_aramasi_parametre_anliyor(client, db_session, kullanici, katalog):
    cevap = client.get("/catalog/search", params={"q": "3x2.5 NYY"})

    assert cevap.status_code == 200
    assert "NYY 3x2.5" in cevap.text
    assert "5x16" not in cevap.text


def test_teklif_ekraninda_urun_aranir(client, db_session, kullanici, katalog):
    teklif_id = int(
        client.post("/quotes", data={"title": "villa"}, follow_redirects=False)
        .headers["location"].rsplit("/", 1)[1]
    )

    cevap = client.get(f"/quotes/{teklif_id}/product-search", params={"q": "5x16"})

    assert cevap.status_code == 200
    assert "NYA 5x16" in cevap.text
    assert "3x2.5" not in cevap.text


def test_teklif_ekrani_acilirken_urun_basmiyor(client, db_session, kullanici, katalog):
    """Eski açılır liste 500 ürün gönderiyordu; Klemsan tek başına 3.694 ürün veriyor."""
    teklif_id = int(
        client.post("/quotes", data={"title": "villa"}, follow_redirects=False)
        .headers["location"].rsplit("/", 1)[1]
    )

    sayfa = client.get(f"/quotes/{teklif_id}").text

    assert "Klemens 12'li" not in sayfa
    assert "NYA 5x16" not in sayfa
    assert "Aramak için yaz" in sayfa


def test_bos_aramada_sonuc_yok(client, db_session, kullanici, katalog):
    teklif_id = int(
        client.post("/quotes", data={"title": "villa"}, follow_redirects=False)
        .headers["location"].rsplit("/", 1)[1]
    )
    cevap = client.get(f"/quotes/{teklif_id}/product-search", params={"q": "   "})
    assert "NYA" not in cevap.text


def test_baskasinin_urunu_teklif_aramasinda_gorunmez(
    client, db_session, make_user, login_as, kullanici, katalog
):
    _, baska_token = make_user("baskasi@example.com")
    login_as(baska_token)
    teklif_id = int(
        client.post("/quotes", data={"title": "onun"}, follow_redirects=False)
        .headers["location"].rsplit("/", 1)[1]
    )

    cevap = client.get(f"/quotes/{teklif_id}/product-search", params={"q": "NYA"})

    assert "NYA" not in cevap.text
    assert cevap.status_code == 200


def test_baskasinin_teklifinde_arama_yapilamaz(
    client, db_session, make_user, login_as, kullanici
):
    teklif_id = int(
        client.post("/quotes", data={"title": "benim"}, follow_redirects=False)
        .headers["location"].rsplit("/", 1)[1]
    )

    _, baska_token = make_user("baskasi@example.com")
    login_as(baska_token)

    assert client.get(f"/quotes/{teklif_id}/product-search",
                      params={"q": "NYA"}).status_code == 404


def test_aramadan_kalem_eklenebilir(client, db_session, kullanici, katalog):
    """Arama sonucundaki her satır doğrudan kalem ekleyen bir form."""
    from app.models import QuoteItem

    teklif_id = int(
        client.post("/quotes", data={"title": "villa"}, follow_redirects=False)
        .headers["location"].rsplit("/", 1)[1]
    )
    urun = next(u for u in katalog if u.name == "NYA 5x16 bakır")

    client.post(f"/quotes/{teklif_id}/items",
                data={"product_id": str(urun.id), "quantity": "100"})

    assert db_session.query(QuoteItem).one().name == "NYA 5x16 bakır"


# =============================================================================
# İçe aktarmada parametre çıkarma
# =============================================================================


def test_ice_aktarmada_parametreler_yaziliyor(client, db_session, kullanici):
    """Ürün ne zaman girdiyse o zaman aranabilir olmalı."""
    yol = FIXTURE_DIZINI / "Oznur_Kablo_Haziran_2026_PDFten.xlsx"
    if not yol.exists():
        pytest.skip("fixture yok")

    client.post(
        "/catalog/import-excel",
        files={"file": (yol.name, yol.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )

    kesitli = db_session.query(Product).filter(Product.cross_section.isnot(None)).count()
    toplam = db_session.query(Product).count()
    assert toplam > 0
    assert kesitli == toplam


def test_ice_aktarilan_katalogda_arama_calisiyor(client, db_session, kullanici):
    yol = FIXTURE_DIZINI / "Oznur_Kablo_Haziran_2026_PDFten.xlsx"
    if not yol.exists():
        pytest.skip("fixture yok")

    client.post(
        "/catalog/import-excel",
        files={"file": (yol.name, yol.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )

    sorgu = db_session.query(Product).join(Category)
    sonuc = urun_ara(sorgu, Product, "3x2.5", limit=100)
    assert sonuc
    assert all(u.core_count == 3 and u.cross_section == D("2.5") for u in sonuc)


def test_yeniden_ayristirma_bos_parametreleri_dolduruyor(client, db_session, kullanici):
    """Parametre alanları eklenmeden önce aktarılmış katalogları kurtarma yolu."""
    kategori = Category(name="Kablo", user_id=kullanici.id)
    db_session.add(kategori)
    db_session.flush()
    db_session.add(Product(
        name="NYA 3x2,5 mm2 bakır", technical_specs="PVC İzoleli, Kılıfsız, 3x2,5 mm2",
        category_id=kategori.id, unit_price=D(10), unit="Metre", currency="TRY",
    ))
    db_session.commit()

    cevap = client.post("/catalog/reparse-parameters", follow_redirects=False)

    assert "guncellendi=1" in cevap.headers["location"]
    urun = db_session.query(Product).one()
    assert urun.cross_section == D("2.5")
    assert urun.core_count == 3
    assert urun.conductor == "bakır"
    assert urun.insulation == "PVC"
    assert urun.sheathed is False


def test_yeniden_ayristirma_mevcut_degeri_ezmez(client, db_session, kullanici):
    """Elle girilmiş ya da dosyadan gelen kesit korunmalı."""
    kategori = Category(name="Kablo", user_id=kullanici.id)
    db_session.add(kategori)
    db_session.flush()
    db_session.add(Product(
        name="NYA 3x2,5 mm2", technical_specs="3x2,5 mm2", category_id=kategori.id,
        unit_price=D(10), unit="Metre", currency="TRY", cross_section=D("99"),
    ))
    db_session.commit()

    client.post("/catalog/reparse-parameters", follow_redirects=False)

    assert db_session.query(Product).one().cross_section == D("99")


def test_yeniden_ayristirma_baskasinin_urunune_dokunmaz(
    client, db_session, make_user, login_as, kullanici
):
    baska, baska_token = make_user("baskasi@example.com")
    kategori = Category(name="Kablo", user_id=baska.id)
    db_session.add(kategori)
    db_session.flush()
    db_session.add(Product(
        name="NYA 3x2,5 mm2", technical_specs="3x2,5 mm2", category_id=kategori.id,
        unit_price=D(10), unit="Metre", currency="TRY",
    ))
    db_session.commit()

    client.post("/catalog/reparse-parameters", follow_redirects=False)

    assert db_session.query(Product).one().cross_section is None


def test_kesitle_ayrilan_urunler_mukerrer_sanilmaz(client, db_session, kullanici):
    """Öznur'un 1673 satırında tedarikçi kodu yok ve ürün adı tekrar ediyor.

    Ürünleri ayıran şey kesit. Parametreler mükerrer kimliğine girmediğinde 1673
    satırın 1614'ü mükerrer sanılıp atılıyordu — kablo kataloğunun tamamı 59 ürüne
    iniyordu. Bu testin kırılması o veri kaybının geri gelmesidir.
    """
    yol = FIXTURE_DIZINI / "Oznur_Kablo_Haziran_2026_PDFten.xlsx"
    if not yol.exists():
        pytest.skip("fixture yok")

    cevap = client.post(
        "/catalog/import-excel",
        files={"file": (yol.name, yol.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )

    assert "eklendi=1" in cevap.headers["location"]
    assert db_session.query(Product).count() > 1500


def test_urun_adi_kesiti_tasiyor(client, db_session, kullanici):
    """Aynı ad onlarca satırda tekrar edince liste okunmuyordu."""
    yol = FIXTURE_DIZINI / "Oznur_Kablo_Haziran_2026_PDFten.xlsx"
    if not yol.exists():
        pytest.skip("fixture yok")

    client.post(
        "/catalog/import-excel",
        files={"file": (yol.name, yol.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )

    adlar = [u.name for u in db_session.query(Product).limit(400)]
    assert any("mm²" in a for a in adlar)
    assert any("2x1.5 mm²" in a for a in adlar)
    # Aynı ad artık her satırda tekrar etmiyor
    assert len(set(adlar)) > 200


def test_ayni_dosya_ikinci_kez_yuklenirse_hepsi_atlanir(client, db_session, kullanici):
    """Kimlik genişledi ama mükerrer tespiti hâlâ çalışmalı."""
    yol = FIXTURE_DIZINI / "Oznur_Kablo_Haziran_2026_PDFten.xlsx"
    if not yol.exists():
        pytest.skip("fixture yok")

    dosya = yol.read_bytes()
    tur = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    client.post("/catalog/import-excel", files={"file": (yol.name, dosya, tur)},
                follow_redirects=False)
    ilk = db_session.query(Product).count()

    cevap = client.post("/catalog/import-excel", files={"file": (yol.name, dosya, tur)},
                        follow_redirects=False)

    assert "eklendi=0" in cevap.headers["location"]
    assert db_session.query(Product).count() == ilk
