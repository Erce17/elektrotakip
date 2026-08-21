"""11 gerçek tedarikçi dosyasıyla ayrıştırıcı testleri.

Bu testler uydurma dosya kullanmıyor. Sebebi 26 Temmuz dersinin aynısı: tahminle
yazılan parser ilk farklı dosyada kırılır. Buradaki her beklenti dosyadan ölçüldü.

Dosyalar `tests/fixtures/tedarikci_listeleri/` altında ve git'e dahil — testler
başka makinede de koşabilsin diye.
"""

import pathlib
from decimal import Decimal

import pytest

from app.excel_import import (
    OkunamadiHatasi,
    normalize_currency,
    oku,
    sayfa_adi_kategori_olur_mu,
    sutun_tipi,
    sutunlari_esle,
)

FIXTURE_DIZINI = pathlib.Path(__file__).parent / "fixtures" / "tedarikci_listeleri"

# Dosya → (en az kaç satır okunmalı, beklenen para birimleri)
# Sayılar ölçüldü; alt sınır olarak yazılıyor ki tedarikçi listeyi büyütürse
# test kendiliğinden kırılmasın, ama veri kaybı olursa kırılsın.
DOSYALAR = {
    "Erse_agustos_2025_fiyat_listesi.xlsx": (600, set()),
    "Grup-Arge-Fiyat-Listesi-2026.xlsx": (500, {"TRY", "USD"}),
    "KLEMSAN-KASIM-2024-FIYAT-LISTESI-V2.xlsx": (3600, {"EUR"}),
    "Kael_subat_2026_fiyat_listesi.xls": (400, set()),
    "Molwex_Subat_2026_Fiyat-Listesi.xlsx": (2200, {"TRY", "USD"}),
    "Oznur_Kablo_Haziran_2026_PDFten.xlsx": (1600, {"TRY"}),
    "POFACO-MART-2025-EXCEL.xlsx": (250, set()),
    "Sezgin_Ocak_2026_Fiyat_Listesi.xlsx": (850, {"TRY", "USD"}),
    "Viko_Panasonic_2026-2_PDFten.xlsx": (2400, {"TRY", "USD"}),
    "tense_subat_2026_fiyat_listesi.xlsx": (750, set()),
}


def dosya_oku(ad: str):
    yol = FIXTURE_DIZINI / ad
    if not yol.exists():
        pytest.skip(f"fixture yok: {ad}")
    return oku(yol.read_bytes(), ad)


# =============================================================================
# Hepsi okunabiliyor mu
# =============================================================================


@pytest.mark.parametrize("ad,beklenti", DOSYALAR.items())
def test_gercek_dosya_okunuyor(ad, beklenti):
    """11 dosyanın 11'i de ürün üretmeli. Eskiden 1'i (.xls) hiç açılamıyordu."""
    asgari, _ = beklenti
    sonuc = dosya_oku(ad)
    assert len(sonuc.satirlar) >= asgari, (
        f"{ad}: {len(sonuc.satirlar)} satır okundu, en az {asgari} bekleniyordu"
    )


@pytest.mark.parametrize("ad,beklenti", DOSYALAR.items())
def test_para_birimleri_dogru_taninmis(ad, beklenti):
    """Klemsan tamamen EURO, Grup Arge aynı dosyada TL ve USD veriyor."""
    _, beklenen = beklenti
    sonuc = dosya_oku(ad)
    bulunan = {k.para_birimi for k in sonuc.satirlar if k.para_birimi}
    assert bulunan == beklenen


@pytest.mark.parametrize("ad", DOSYALAR)
def test_okunan_her_satirin_kimligi_var(ad):
    """Kodu da adı da açıklaması da boş bir satır ürün olamaz — bölüm başlığıdır."""
    sonuc = dosya_oku(ad)
    kimliksiz = [k for k in sonuc.satirlar if not (k.kod or k.ad or k.aciklama)]
    assert kimliksiz == []


@pytest.mark.parametrize("ad", DOSYALAR)
def test_okunan_fiyatlar_makul(ad):
    """Negatif fiyat ya da absürt büyük değer ayrıştırma hatasının işaretidir."""
    sonuc = dosya_oku(ad)
    for kayit in sonuc.satirlar:
        if kayit.fiyat is None:
            continue
        assert kayit.fiyat >= 0, f"{ad} r{kayit.satir_no}: negatif fiyat"
        assert kayit.fiyat < Decimal(10) ** 9, f"{ad} r{kayit.satir_no}: {kayit.fiyat}"


# =============================================================================
# Başlık satırı sabit değil
# =============================================================================


def test_baslik_birinci_satirda():
    sonuc = dosya_oku("POFACO-MART-2025-EXCEL.xlsx")
    assert [s.baslik_satiri for s in sonuc.sayfalar] == [1]


def test_baslik_ikinci_satirda():
    """Sezgin'de 1. satır tamamen boş."""
    sonuc = dosya_oku("Sezgin_Ocak_2026_Fiyat_Listesi.xlsx")
    assert sonuc.sayfalar[0].baslik_satiri == 2


def test_baslik_ucuncu_satirda():
    """Kael'de 1. satır boş, 2. satır firma adı."""
    sonuc = dosya_oku("Kael_subat_2026_fiyat_listesi.xls")
    assert sonuc.sayfalar[0].baslik_satiri == 3


def test_baslik_besinci_satirda():
    """Erse'nin 'Baskı Formatı' sayfasında 4 satır başlık/bölüm var."""
    sonuc = dosya_oku("Erse_agustos_2025_fiyat_listesi.xlsx")
    baski = next(s for s in sonuc.sayfalar if s.ad == "Baskı Formatı")
    assert baski.baslik_satiri == 5


# =============================================================================
# Eski format
# =============================================================================


def test_xls_dosyasi_okunuyor():
    """Kael gerçek BIFF8 `.xls`; openpyxl açamıyor, eskiden tamamen reddediliyordu."""
    sonuc = dosya_oku("Kael_subat_2026_fiyat_listesi.xls")
    assert len(sonuc.satirlar) > 400
    assert sonuc.satirlar[0].kod == "SUPER SVC"
    assert sonuc.satirlar[0].fiyat == Decimal("57523")


# =============================================================================
# Çoklu sayfa
# =============================================================================


def test_tum_sayfalar_okunuyor():
    """Grup Arge 10 sayfa; eskiden `workbook.active` ile sadece 1'i okunuyordu."""
    sonuc = dosya_oku("Grup-Arge-Fiyat-Listesi-2026.xlsx")
    assert len(sonuc.sayfalar) == 10
    assert all(s.baslik_satiri == 1 for s in sonuc.sayfalar)
    # Tek sayfa okunsaydı ~36 satır gelirdi.
    assert len(sonuc.satirlar) > 400


def test_fiyatsiz_sayfa_atlanir_ve_raporlanir():
    """Molwex'in 'Tüm Kodlar' sayfası gerçek ama fiyat tutmuyor.

    Sessizce atlamak yerine adıyla raporlanıyor: kullanıcı 'neden bu kadar az
    ürün geldi' sorusunun cevabını görebilsin.
    """
    sonuc = dosya_oku("Molwex_Subat_2026_Fiyat-Listesi.xlsx")
    assert sonuc.atlanan_sayfalar == ["Tüm Kodlar"]
    assert all(k.sayfa == "Fiyat Listesi" for k in sonuc.satirlar)


# =============================================================================
# Bölüm başlıkları
# =============================================================================


def test_bolum_basliklari_urun_sayilmaz():
    """Kael'de 'DİNAMİK KOMPANZASYON' bir bölüm başlığı, fiyat hücresi boş."""
    sonuc = dosya_oku("Kael_subat_2026_fiyat_listesi.xls")
    kodlar = {k.kod for k in sonuc.satirlar}
    assert "DİNAMİK KOMPANZASYON" not in kodlar
    assert sonuc.sayfalar[0].bolum_basligi > 0


def test_urun_adi_bos_ama_fiyati_gecerli_satir_korunur():
    """Viko'da 822 satırın ürün adı boş, fiyatı geçerli.

    Bu satırları bölüm başlığı saymak veri kaybıydı — ayırt edici ölçüt ad değil,
    fiyat hücresinin sayıya çevrilebilmesi.
    """
    sonuc = dosya_oku("Viko_Panasonic_2026-2_PDFten.xlsx")
    adsiz = [k for k in sonuc.satirlar if not k.ad and k.kod and k.fiyat]
    assert len(adsiz) > 500
    assert adsiz[0].grup == "Çerçeveler"


def test_tekrar_eden_baslik_satirlari_atlanir():
    """Erse'nin 'Baskı Formatı' sayfasında başlık defalarca yeniden yazılmış."""
    sonuc = dosya_oku("Erse_agustos_2025_fiyat_listesi.xlsx")
    baski = next(s for s in sonuc.sayfalar if s.ad == "Baskı Formatı")
    assert baski.tekrar_eden_baslik > 0
    assert "KOD NO" not in {k.kod for k in sonuc.satirlar}


def test_urun_satirlari_baslik_sanilmaz():
    """'ADET', 'Turuncu', 'KODLAMA MALZEMESİ' başlık kelimeleri içeriyor.

    Alt dize araması bunları başlık sanıp Molwex'te 699 ürünü atıyordu; eşleşme
    kelime bazlı olunca düzeldi. Bu testin kırılması o hatanın geri gelmesidir.
    """
    sonuc = dosya_oku("Molwex_Subat_2026_Fiyat-Listesi.xlsx")
    sayfa = next(s for s in sonuc.sayfalar if s.ad == "Fiyat Listesi")
    assert sayfa.tekrar_eden_baslik == 0
    assert len(sonuc.satirlar) > 2200


def test_fiyat_yerine_metin_gelen_satir_urun_olarak_kalir():
    """Tense'de 'Bilgi Alınız' yazan satırlar gerçek ürün, fiyatı sonra girilecek."""
    sonuc = dosya_oku("tense_subat_2026_fiyat_listesi.xlsx")
    fiyatsiz = [k for k in sonuc.satirlar if k.fiyat is None]
    assert fiyatsiz
    assert sonuc.sayfalar[0].fiyat_okunamadi == len(fiyatsiz)
    assert all(k.kod for k in fiyatsiz)


# =============================================================================
# Para birimi ve birim
# =============================================================================


def test_para_birimi_ayri_sutundan():
    sonuc = dosya_oku("KLEMSAN-KASIM-2024-FIYAT-LISTESI-V2.xlsx")
    assert all(k.para_birimi == "EUR" for k in sonuc.satirlar)


def test_para_birimi_birim_sutununun_icinden():
    """Öznur `TL/km` yazıyor: soldaki para birimi, sağdaki birim."""
    sonuc = dosya_oku("Oznur_Kablo_Haziran_2026_PDFten.xlsx")
    ilk = sonuc.satirlar[0]
    assert ilk.para_birimi == "TRY"
    assert ilk.birim == "KM"


def test_birim_diye_acilmis_sutun_aslinda_para_birimi():
    """Sezgin'in 'BİRİM' sütununda 'USD' yazıyor — birim değil kur bilgisi."""
    sonuc = dosya_oku("Sezgin_Ocak_2026_Fiyat_Listesi.xlsx")
    usd = [k for k in sonuc.satirlar if k.para_birimi == "USD"]
    assert usd
    assert all(k.birim == "" for k in usd)


def test_ayni_dosyada_iki_para_birimi():
    """Grup Arge aynı dosyada TL ve USD veriyor; tek dosya = tek para birimi değil."""
    sonuc = dosya_oku("Grup-Arge-Fiyat-Listesi-2026.xlsx")
    assert {k.para_birimi for k in sonuc.satirlar} == {"TRY", "USD"}


@pytest.mark.parametrize(
    "ham,beklenen",
    [
        ("TL", "TRY"), ("tl", "TRY"), ("₺", "TRY"),
        ("USD", "USD"), ("$", "USD"), ("Dolar", "USD"),
        ("EURO", "EUR"), ("eur", "EUR"), ("€", "EUR"),
        ("", ""), ("ABC", ""), ("Adet", ""),
    ],
)
def test_para_birimi_normallestirme(ham, beklenen):
    assert normalize_currency(ham) == beklenen


# =============================================================================
# Sütun tanıma
# =============================================================================


@pytest.mark.parametrize(
    "baslik",
    ["STOK KODU", "Referans", "KOD NO", "Malz. Kodu", "ÜRÜN KODU", "Sipariş Kodu",
     "Stok Kodu"],
)
def test_kod_sutununun_yedi_adi(baslik):
    """PROGRESS'te sayılan yedi yazım; hepsi aynı alana gitmeli."""
    assert sutun_tipi(baslik)[0] == "kod"


@pytest.mark.parametrize(
    "baslik",
    ["2026 ŞUBAT", "BİRİM FİYAT(t/m)", "2024 KASIM LİSTE FİYATI", "LİSTE FİYATI",
     "Liste Fiyat", "FİYAT"],
)
def test_fiyat_sutununun_alti_adi(baslik):
    assert sutun_tipi(baslik)[0] == "fiyat"


def test_doviz_sutunu_fiyat_sanilmaz():
    """Klemsan'ın 'Fiyat Listesi Döviz Cinsi' başlığı 'fiyat' içeriyor ama fiyat değil."""
    assert sutun_tipi("Fiyat Listesi Döviz Cinsi")[0] == "para_birimi"


def test_kisa_fiyat_basligi_uzun_olani_yener():
    """Viko'da hem 'Fiyat' hem 'Tum Fiyatlar', Öznur'da 'Fiyat' ve 'Fiyat (ham)' var."""
    esleme = sutunlari_esle(["Siparis Kodu", "Urun Adi", "Fiyat", "Tum Fiyatlar"])
    assert esleme["fiyat"] == 2


def test_turkce_buyuk_i_harfi_eslesir():
    """`str.lower()` 'İ' harfini Türkçe kurallarına göre çevirmez; katlama şart."""
    assert sutun_tipi("FİYAT")[0] == "fiyat"
    assert sutun_tipi("fiyat")[0] == "fiyat"
    assert sutun_tipi("Fıyat") is not None


def test_taninmayan_baslik_none_doner():
    assert sutun_tipi("Kesit (mm2)") is None
    assert sutun_tipi("") is None
    assert sutun_tipi(None) is None


def test_fiyat_sutunu_yoksa_baslik_bulunmaz():
    """Fiyat sütunu olmayan sayfa kataloğa giremez; yarım veri almaktan iyisi budur."""
    sonuc = oku_bellekten([["Kod", "Ad", "Açıklama"], ["A1", "ürün", "not"]])
    assert sonuc.sayfalar[0].baslik_satiri is None
    assert sonuc.satirlar == []


# =============================================================================
# Sayfa adından kategori
# =============================================================================


@pytest.mark.parametrize("ad", ["Sheet", "Sheet1", "Sayfa1", "sayfa", "Tablo1"])
def test_excelin_verdigi_sayfa_adi_kategori_olmaz(ad):
    assert not sayfa_adi_kategori_olur_mu(ad)


@pytest.mark.parametrize("ad", ["OZNUR HAZIRAN 2026", "ÜRÜNLER", "Fiyat Listesi"])
def test_anlamli_sayfa_adi_kategori_olur(ad):
    assert sayfa_adi_kategori_olur_mu(ad)


# =============================================================================
# Bozuk girdi
# =============================================================================


def oku_bellekten(satirlar, dosya_adi="test.xlsx"):
    """Bellekte .xlsx üretip ayrıştırır."""
    import io

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for satir in satirlar:
        ws.append(satir)
    akis = io.BytesIO()
    wb.save(akis)
    return oku(akis.getvalue(), dosya_adi)


def test_bozuk_dosya_okunamadi_hatasi_verir():
    with pytest.raises(OkunamadiHatasi):
        oku(b"bu bir excel dosyasi degil", "liste.xlsx")


def test_bozuk_xls_okunamadi_hatasi_verir():
    with pytest.raises(OkunamadiHatasi):
        oku(b"bu da degil", "liste.xls")


def test_bos_sayfa_patlamaz():
    sonuc = oku_bellekten([])
    assert sonuc.satirlar == []


def test_sadece_baslik_iceren_sayfa():
    sonuc = oku_bellekten([["Stok Kodu", "Stok Adı", "Fiyat"]])
    assert sonuc.sayfalar[0].baslik_satiri == 1
    assert sonuc.satirlar == []


# =============================================================================
# Uçtan uca: gerçek dosya → katalog
# =============================================================================


@pytest.fixture
def kullanici(client, make_user, login_as):
    user, token = make_user("tedarikci@example.com")
    login_as(token)
    return user


def yukle_gercek(client, ad: str):
    yol = FIXTURE_DIZINI / ad
    if not yol.exists():
        pytest.skip(f"fixture yok: {ad}")
    tur = ("application/vnd.ms-excel" if ad.endswith(".xls")
           else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    return client.post(
        "/catalog/import-excel",
        files={"file": (ad, yol.read_bytes(), tur)},
        follow_redirects=False,
    )


def test_klemsan_dosyasi_katalogda_euro_urun_olusturur(client, db_session, kullanici):
    """Eskiden sabit sütun sırası beklendiği için bu dosya anlamsız veri üretiyordu."""
    from app.models import Product

    cevap = yukle_gercek(client, "KLEMSAN-KASIM-2024-FIYAT-LISTESI-V2.xlsx")
    assert cevap.status_code == 303
    assert "hata=" not in cevap.headers["location"]

    urunler = db_session.query(Product).all()
    assert len(urunler) > 3000
    assert {u.currency for u in urunler} == {"EUR"}
    assert all(u.supplier_code for u in urunler)


def test_xls_dosyasi_artik_reddedilmiyor(client, db_session, kullanici):
    from app.models import Product

    cevap = yukle_gercek(client, "Kael_subat_2026_fiyat_listesi.xls")
    assert "hata=" not in cevap.headers["location"]
    assert db_session.query(Product).count() > 400


def test_coklu_sayfa_tek_yuklemede_aktarilir(client, db_session, kullanici):
    """Grup Arge'nin 10 sayfası da girmeli; kategoriler sayfa adından gelmez, grup yok."""
    from app.models import Category, Product

    yukle_gercek(client, "Grup-Arge-Fiyat-Listesi-2026.xlsx")

    assert db_session.query(Product).count() > 400
    # Grup sütunu yok, sayfa adları anlamlı → her sayfa kendi kategorisi olur
    kategoriler = {k.name for k in db_session.query(Category).all()}
    assert "KONDANSATÖR" in kategoriler
    assert len(kategoriler) == 10


def test_atlanan_sayfa_kullaniciya_raporlanir(client, db_session, kullanici):
    cevap = yukle_gercek(client, "Molwex_Subat_2026_Fiyat-Listesi.xlsx")
    assert "atlanan_sayfalar=" in cevap.headers["location"]


def test_karisik_para_birimi_urun_bazinda_saklanir(client, db_session, kullanici):
    """Grup Arge aynı dosyada TL ve USD veriyor; tek dosya = tek para birimi değil."""
    from app.models import Product

    yukle_gercek(client, "Grup-Arge-Fiyat-Listesi-2026.xlsx")
    assert {p.currency for p in db_session.query(Product).all()} == {"TRY", "USD"}


def test_oznur_km_fiyati_metreye_cevrilir(client, db_session, kullanici):
    """Dosya `TL/km` diyor; kutucuk işaretlenmese de satır bazlı çevrilmeli.

    'Milyon TL' şikâyetinin kaynağı buydu: 18.410 TL/km = 18,41 TL/m.
    """
    from app.models import Product

    yukle_gercek(client, "Oznur_Kablo_Haziran_2026_PDFten.xlsx")

    urun = (
        db_session.query(Product)
        .filter(Product.technical_specs.like("H05V-U (NYA) 300/500%"))
        .first()
    )
    assert urun.unit == "Metre"
    assert urun.unit_price == Decimal("18.4100")
    assert urun.currency == "TRY"


def test_ayni_dosya_ikinci_kez_yuklenirse_mukerrer_eklenmez(client, db_session, kullanici):
    from app.models import Product

    yukle_gercek(client, "POFACO-MART-2025-EXCEL.xlsx")
    ilk = db_session.query(Product).count()

    cevap = yukle_gercek(client, "POFACO-MART-2025-EXCEL.xlsx")
    assert db_session.query(Product).count() == ilk
    assert f"eklendi=0&atlandi={ilk}" in cevap.headers["location"]


def test_fiyatsiz_urunler_raporlanir(client, db_session, kullanici):
    """Tense'de 'Bilgi Alınız' yazan satırlar ürün olarak girer, fiyatı 0 kalır."""
    from app.models import Product

    cevap = yukle_gercek(client, "tense_subat_2026_fiyat_listesi.xlsx")
    assert "fiyatsiz=" in cevap.headers["location"]
    assert "fiyatsiz=0" not in cevap.headers["location"]
    assert db_session.query(Product).filter(Product.unit_price == 0).count() > 0


@pytest.mark.parametrize("ad", list(DOSYALAR))
def test_her_gercek_dosya_hatasiz_aktarilir(client, db_session, kullanici, ad):
    """11 dosyanın 11'i de 500 vermeden, hata mesajı üretmeden kataloğa girmeli."""
    from app.models import Product

    cevap = yukle_gercek(client, ad)
    assert cevap.status_code == 303
    assert "hata=" not in cevap.headers["location"]
    assert db_session.query(Product).count() > 0
