"""Teklif hesap motoru testleri.

Buradaki her test bir iş kuralını sabitliyor. Motor DB'siz olduğu için testler de
fixture istemiyor: girdi dataclass, çıktı dataclass.
"""

from decimal import Decimal

import pytest

from app.quote_engine import (
    DIGER,
    EK_TUTAR,
    EK_YUZDE,
    ISCILIK,
    ISKONTO_TUTAR,
    ISKONTO_YUZDE,
    KAPSAM_ISKONTOYA_TABI,
    KAPSAM_TUMU,
    TABAN_KALEM_TOPLAMI,
    TABAN_YURUYEN,
    Kalem,
    ZincirSatiri,
    dagit,
    hesapla,
    kur_uygula,
    kurusla,
)


def D(deger) -> Decimal:
    return Decimal(str(deger))


def kalem(fiyat, miktar=1, **kwargs) -> Kalem:
    kwargs.setdefault("ad", "kalem")
    return Kalem(miktar=D(miktar), birim_fiyat=D(fiyat), **kwargs)


# =============================================================================
# Kalem aşaması: zincirli iskonto
# =============================================================================


def test_zincirli_iskonto_carpimsaldir():
    """%20 sonra %10, %30 DEĞİL. 1000 → 720, 700 değil.

    Sektörün temel kuralı bu ve tek `iskonto_orani` alanıyla yapılan her tasarım
    burada yanlış rakam üretir.
    """
    sonuc = hesapla([kalem(1000, iskontolar=(D(20), D(10)))])
    assert sonuc.kalemler[0].net == D("720.00")


def test_tek_iskonto_toplamla_karistirilmiyor():
    tek = hesapla([kalem(1000, iskontolar=(D(30),))])
    zincir = hesapla([kalem(1000, iskontolar=(D(20), D(10)))])
    assert tek.kalemler[0].net == D("700.00")
    assert zincir.kalemler[0].net == D("720.00")
    assert tek.kalemler[0].net != zincir.kalemler[0].net


def test_iskonto_sirasi_kalem_icinde_sonucu_degistirmez():
    """Çarpma yer değiştirmeli: kalem içi zincirin sırası sonucu değiştirmez.

    Sıra teklif seviyesinde (iskonto/işçilik/nakliye arasında) önemli; kalemin kendi
    yüzde zincirinde değil. Bu ayrımı kayda geçiriyoruz.
    """
    a = hesapla([kalem(1000, iskontolar=(D(20), D(10)))])
    b = hesapla([kalem(1000, iskontolar=(D(10), D(20)))])
    assert a.kalemler[0].net == b.kalemler[0].net


def test_brut_ve_kalem_iskontosu_ayri_raporlanir():
    """'Liste 100 bin, size 62 bin' göstermek satışın kendisi — ikisi ayrı durmalı."""
    sonuc = hesapla([kalem(100000, iskontolar=(D(38),))])
    satir = sonuc.kalemler[0]
    assert satir.brut == D("100000.00")
    assert satir.kalem_iskontosu == D("38000.00")
    assert satir.net == D("62000.00")


def test_miktarli_kalem():
    sonuc = hesapla([kalem("12.3456", miktar=250)])
    assert sonuc.kalemler[0].brut == D("3086.40")


# =============================================================================
# KDV: satır bazında, satır bazında yuvarlanmış
# =============================================================================


def test_kdv_satir_bazinda_hesaplanir_karisik_oranda():
    """Karışık KDV oranlı tek teklifte tek oran yanlış rakam verir."""
    sonuc = hesapla(
        [
            kalem(1000, kdv_orani=D(20)),
            kalem(1000, kdv_orani=D(10)),
        ]
    )
    assert sonuc.kalemler[0].kdv == D("200.00")
    assert sonuc.kalemler[1].kdv == D("100.00")
    assert sonuc.kdv_toplami == D("300.00")
    assert sonuc.genel_toplam == D("2300.00")


def test_kdv_dagilimi_orana_gore_gruplanir():
    sonuc = hesapla(
        [
            kalem(1000, kdv_orani=D(20)),
            kalem(500, kdv_orani=D(20)),
            kalem(400, kdv_orani=D(10)),
        ]
    )
    assert sonuc.kdv_dagilimi[D(20)] == (D("1500.00"), D("300.00"))
    assert sonuc.kdv_dagilimi[D(10)] == (D("400.00"), D("40.00"))


def test_yuvarlama_half_even():
    """GİB: tam yarım değer en yakın çift sayıya gider. 0.125 → 0.12, 0.135 → 0.14."""
    assert kurusla(D("0.125")) == D("0.12")
    assert kurusla(D("0.135")) == D("0.14")
    assert kurusla(D("2.675")) == D("2.68")


def test_kdv_satir_bazinda_yuvarlandigi_icin_ara_toplam_uzerinden_hesapla_farkli():
    """Satır bazlı yuvarlama ara toplam üzerinden hesaptan sapabilir — kasıtlı.

    Muhasebe programı satır bazında yuvarlar; biz de öyle yaparız. Aksi hâlde
    e-faturada kuruş farkı çıkar.
    """
    kalemler = [kalem("0.055", kdv_orani=D(20)) for _ in range(3)]
    sonuc = hesapla(kalemler)
    # Her satır 0,06'ya yuvarlanır → matrah 0,18, KDV 3 × 0,01 = 0,03.
    assert sonuc.ara_toplam == D("0.18")
    assert sonuc.kdv_toplami == D("0.03")


# =============================================================================
# Zincir: sıra, kapsam, taban
# =============================================================================


def test_genel_iskonto_kalemlere_dagitilir_ve_kdv_dogru_kalir():
    """Genel iskonto ara toplamda beklemez; etkilediği kalemlere orantılı düşer.

    Aksi hâlde karışık KDV oranlı teklifte iskonto hangi orandan düşecek belirsizleşir.
    """
    sonuc = hesapla(
        [kalem(1000, kdv_orani=D(20)), kalem(1000, kdv_orani=D(10))],
        [ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(10), ad="Genel iskonto", kapsam=KAPSAM_TUMU)],
    )
    assert [k.net for k in sonuc.kalemler] == [D("900.00"), D("900.00")]
    assert sonuc.kalemler[0].kdv == D("180.00")
    assert sonuc.kalemler[1].kdv == D("90.00")
    assert sonuc.ara_toplam == D("1800.00")


def test_iscilik_iskontoya_girmez():
    """Sektörde işçilik iskontoya genelde girmez. Bayrak olmadan ilk teklifte hata çıkar."""
    sonuc = hesapla(
        [
            kalem(1000, ad="malzeme"),
            kalem(500, ad="işçilik", iskontoya_tabi=False, tur=ISCILIK),
        ],
        [ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(20), kapsam=KAPSAM_ISKONTOYA_TABI)],
    )
    assert sonuc.kalemler[0].net == D("800.00")
    assert sonuc.kalemler[1].net == D("500.00")  # dokunulmadı
    assert sonuc.ara_toplam == D("1300.00")


def test_kapsam_tumu_iscilige_de_vurur():
    sonuc = hesapla(
        [kalem(1000), kalem(500, iskontoya_tabi=False, tur=ISCILIK)],
        [ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(20), kapsam=KAPSAM_TUMU)],
    )
    assert sonuc.ara_toplam == D("1200.00")


def test_zincir_sirasi_sonucu_degistirir():
    """İskonto önce mi işçilik önce mi — sonuç değişir. Motorun varlık sebebi bu."""
    malzeme = [kalem(1000)]
    iskonto = ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(20), kapsam=KAPSAM_TUMU)
    iscilik = ZincirSatiri(
        tur=EK_YUZDE,
        deger=D(10),
        ad="İşçilik",
        kapsam=KAPSAM_TUMU,
        eklenen_tur=ISCILIK,
        eklenen_iskontoya_tabi=True,
    )

    once_iskonto = hesapla(malzeme, [iskonto, iscilik])
    once_iscilik = hesapla(malzeme, [iscilik, iskonto])

    # İskonto önce: 1000 → 800, sonra %10 işçilik = 80 → 880
    assert once_iskonto.ara_toplam == D("880.00")
    # İşçilik önce: 1000 + 100 = 1100, sonra %20 iskonto → 880... değil:
    # iskonto işçiliğe de vurduğu için 1100 × 0,8 = 880. Aynı çıkıyor, çünkü
    # her iki işlem de tüm tabana uygulanıyor. Farkı işçilik iskontodan muafken görürüz.
    assert once_iscilik.ara_toplam == D("880.00")

    muaf_iscilik = ZincirSatiri(
        tur=EK_YUZDE,
        deger=D(10),
        ad="İşçilik",
        kapsam=KAPSAM_TUMU,
        eklenen_tur=ISCILIK,
        eklenen_iskontoya_tabi=False,
    )
    iskonto_tabi = ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(20), kapsam=KAPSAM_ISKONTOYA_TABI)
    # İşçilik önce ve muaf: 1000 + 100 = 1100, iskonto sadece malzemeye → 800 + 100 = 900
    assert hesapla(malzeme, [muaf_iscilik, iskonto_tabi]).ara_toplam == D("900.00")
    # İskonto önce: 1000 → 800, işçilik 800'ün %10'u = 80 → 880
    assert hesapla(malzeme, [iskonto_tabi, muaf_iscilik]).ara_toplam == D("880.00")


def test_taban_kalem_toplami_onceki_iskontodan_etkilenmez():
    """'İşçilik liste tutarının %10'u' ile 'iskontolu tutarın %10'u' ayrı kurallar."""
    malzeme = [kalem(1000)]
    zincir_yuruyen = [
        ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(20), kapsam=KAPSAM_TUMU),
        ZincirSatiri(tur=EK_YUZDE, deger=D(10), ad="İşçilik", kapsam=KAPSAM_TUMU,
                     taban=TABAN_YURUYEN),
    ]
    zincir_liste = [
        ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(20), kapsam=KAPSAM_TUMU),
        ZincirSatiri(tur=EK_YUZDE, deger=D(10), ad="İşçilik", kapsam=KAPSAM_TUMU,
                     taban=TABAN_KALEM_TOPLAMI),
    ]
    assert hesapla(malzeme, zincir_yuruyen).ara_toplam == D("880.00")   # 800 + 80
    assert hesapla(malzeme, zincir_liste).ara_toplam == D("900.00")     # 800 + 100


def test_zincirli_genel_iskonto_de_carpimsal():
    sonuc = hesapla(
        [kalem(1000)],
        [
            ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(20)),
            ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(10)),
        ],
    )
    assert sonuc.ara_toplam == D("720.00")


def test_tutar_iskontosu():
    sonuc = hesapla([kalem(1000)], [ZincirSatiri(tur=ISKONTO_TUTAR, deger=D("150.50"))])
    assert sonuc.ara_toplam == D("849.50")


def test_iskonto_tabani_asamaz():
    """Taban aşılırsa satırlar negatife düşer ve teklif anlamsızlaşır. Sınırla."""
    sonuc = hesapla([kalem(100)], [ZincirSatiri(tur=ISKONTO_TUTAR, deger=D(500))])
    assert sonuc.ara_toplam == D("0.00")
    assert all(k.net >= 0 for k in sonuc.kalemler)


def test_ek_tutar_kendi_kdv_oraniyla_gelir():
    sonuc = hesapla(
        [kalem(1000, kdv_orani=D(20))],
        [ZincirSatiri(tur=EK_TUTAR, deger=D(2500), ad="Nakliye", kdv_orani=D(10),
                      eklenen_tur=DIGER)],
    )
    nakliye = sonuc.kalemler[-1]
    assert nakliye.ad == "Nakliye"
    assert nakliye.net == D("2500.00")
    assert nakliye.kdv == D("250.00")
    assert sonuc.kdv_toplami == D("450.00")


def test_ek_satirin_kdv_orani_verilmezse_varsayilan_kullanilir():
    sonuc = hesapla(
        [kalem(1000)],
        [ZincirSatiri(tur=EK_TUTAR, deger=D(100), ad="Nakliye")],
        varsayilan_kdv=D(10),
    )
    assert sonuc.kalemler[-1].kdv_orani == D(10)


def test_zincir_raporu_her_adimi_gosterir():
    """Kullanıcı 'bu rakam nereden çıktı' diye sorunca cevap verilebilmeli."""
    sonuc = hesapla(
        [kalem(1000)],
        [
            ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(20), ad="Bayi iskontosu"),
            ZincirSatiri(tur=EK_TUTAR, deger=D(150), ad="Nakliye"),
        ],
    )
    assert [(z.ad, z.taban_tutar, z.etki) for z in sonuc.zincir] == [
        ("Bayi iskontosu", D("1000.00"), D("-200.00")),
        ("Nakliye", D("800.00"), D("150.00")),
    ]


def test_zincir_iskontosu_kalem_bazinda_raporlanir():
    sonuc = hesapla(
        [kalem(1000), kalem(3000)],
        [ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(10), kapsam=KAPSAM_TUMU)],
    )
    assert sonuc.kalemler[0].zincir_iskontosu == D("100.00")
    assert sonuc.kalemler[1].zincir_iskontosu == D("300.00")


# =============================================================================
# Dağıtım: kuruş kaybı
# =============================================================================


def test_dagitim_kurus_kaybetmez():
    """Payları ayrı ayrı yuvarlarsan toplam hedeften sapar. Sapmamalı."""
    paylar = dagit(D("10.00"), [D(1), D(1), D(1)])
    assert sum(paylar) == D("10.00")
    assert sorted(paylar) == [D("3.33"), D("3.33"), D("3.34")]


def test_dagitim_agirliksizsa_sifir_doner():
    assert dagit(D(100), [D(0), D(0)]) == [D(0), D(0)]


def test_dagitim_bos_listede_patlamaz():
    assert dagit(D(100), []) == []


@pytest.mark.parametrize("kalem_sayisi", [3, 7, 11, 13])
def test_genel_iskontoda_toplam_tutarlidir(kalem_sayisi):
    """Kalemlerin toplamı her zaman teklifin toplamını vermeli."""
    kalemler = [kalem("33.33", miktar=7) for _ in range(kalem_sayisi)]
    sonuc = hesapla(
        kalemler, [ZincirSatiri(tur=ISKONTO_YUZDE, deger=D("7.5"), kapsam=KAPSAM_TUMU)]
    )
    assert sum(k.net for k in sonuc.kalemler) == sonuc.ara_toplam
    assert sum(k.kdv for k in sonuc.kalemler) == sonuc.kdv_toplami
    assert sonuc.ara_toplam + sonuc.kdv_toplami == sonuc.genel_toplam


def test_kalem_ara_toplami_zincirden_once_donar():
    sonuc = hesapla(
        [kalem(1000)], [ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(20), kapsam=KAPSAM_TUMU)]
    )
    assert sonuc.kalem_ara_toplami == D("1000.00")
    assert sonuc.ara_toplam == D("800.00")


# =============================================================================
# Sınır durumlar
# =============================================================================


def test_bos_teklif():
    sonuc = hesapla([])
    assert sonuc.ara_toplam == D(0)
    assert sonuc.genel_toplam == D(0)
    assert sonuc.kalemler == ()


def test_kalemsiz_teklifte_yuzde_iskonto_patlamaz():
    sonuc = hesapla([], [ZincirSatiri(tur=ISKONTO_YUZDE, deger=D(20))])
    assert sonuc.genel_toplam == D(0)


def test_sifir_fiyatli_kalem():
    """Liste fiyatı yerine 'Bilgi Alınız' gelen ürünler var; fiyatsız kalem geçebilir."""
    sonuc = hesapla([kalem(0, miktar=10), kalem(100)])
    assert sonuc.kalemler[0].net == D("0.00")
    assert sonuc.ara_toplam == D("100.00")


def test_sifir_kdv_orani():
    sonuc = hesapla([kalem(1000, kdv_orani=D(0))])
    assert sonuc.kdv_toplami == D("0.00")
    assert sonuc.genel_toplam == D("1000.00")


# =============================================================================
# Kur
# =============================================================================


def test_kur_uygula_dort_ondalik_korur():
    """Kuruşa yuvarlarsan ucuz malzemede miktarla çarpınca sapma büyür (KM→metre dersi)."""
    assert kur_uygula(D("0.0123"), D("42.1567")) == D("0.5185")


def test_kur_bir_ise_fiyat_degismez():
    assert kur_uygula(D("1234.5678"), D(1)) == D("1234.5678")


def test_euro_kalem_teklif_para_biriminde_hesaplanir():
    """Klemsan tamamen EURO. Kur kalemde donar, motor tek para biriminde çalışır."""
    birim = kur_uygula(D("12.50"), D("47.3000"))
    sonuc = hesapla([kalem(birim, miktar=100)])
    assert birim == D("591.2500")
    assert sonuc.kalemler[0].brut == D("59125.00")
