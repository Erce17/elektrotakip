"""Teklif hesap motoru — saf hesap katmanı.

Burada veritabanı, ORM, HTTP yok. Girdi dataclass, çıktı dataclass. Sebebi bu projenin
kendi geçmişi: denetimde çıkan ciddi hataların hepsi hesap tarafındaydı ve hiçbiri
arayüzden görünmüyordu. Hesap DB'den ayrı durursa testi ucuz, kırılması görünür olur.

İki aşamalı çalışır:

1. **Kalem aşaması.** Her kalem kendi zincirli iskontosunu yer, kuruşa yuvarlanır.
2. **Zincir aşaması.** Teklif seviyesindeki satırlar (genel iskonto, işçilik, nakliye…)
   `sira` düzeninde tek tek uygulanır. Sıra sonucu değiştirir; sabit formül yok.

Zincir satırındaki iskonto ara toplama değil, **etkilediği kalemlere orantılı dağıtılır.**
Sebebi GİB: KDV satır bazında hesaplanır ve satır bazında yuvarlanır. Genel iskontoyu
ara toplamda tutup KDV'yi sonda hesaplarsan karışık KDV oranlı teklifte muhasebeyle
uyuşmayan rakam çıkar.

Yuvarlama her yerde `ROUND_HALF_EVEN`, iki ondalık (kuruş). Tam yarım değerler en yakın
çift sayıya gider — e-fatura kuralı budur.
"""

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, ROUND_HALF_EVEN, Decimal

# --- Kalem türleri -----------------------------------------------------------
# İşçiliğin ayrı tür olması raporlama içindir; iskontoya girip girmemesini tür değil
# kalemin `iskontoya_tabi` bayrağı belirler. Sektörde işçilik genelde girmez ama
# "girmez" bir varsayılandır, kural değil.
MALZEME = "malzeme"
ISCILIK = "iscilik"
DIGER = "diger"

# --- Zincir satırı türleri ---------------------------------------------------
ISKONTO_YUZDE = "iskonto_yuzde"
ISKONTO_TUTAR = "iskonto_tutar"
EK_YUZDE = "ek_yuzde"      # örn. "malzemenin %15'i işçilik"
EK_TUTAR = "ek_tutar"      # örn. "nakliye 2.500 TL"

# --- Zincir satırının tabanı -------------------------------------------------
# Yüzde neyin üzerinden hesaplanacak.
TABAN_YURUYEN = "yuruyen"              # o ana kadar oluşmuş tutar (zincirli iskonto)
TABAN_KALEM_TOPLAMI = "kalem_toplami"  # kalem aşaması sonucu, sonrakilerden etkilenmez

# --- Zincir satırının kapsamı ------------------------------------------------
KAPSAM_ISKONTOYA_TABI = "iskontoya_tabi"  # sadece `iskontoya_tabi` kalemler
KAPSAM_TUMU = "tumu"                      # işçilik dahil her kalem

KURUS = Decimal("0.01")
YUZ = Decimal(100)


def kurusla(deger: Decimal) -> Decimal:
    """Kuruşa yuvarlar. ROUND_HALF_EVEN: tam yarım en yakın çift sayıya gider (GİB)."""
    return deger.quantize(KURUS, rounding=ROUND_HALF_EVEN)


# =============================================================================
# Girdi
# =============================================================================


@dataclass(frozen=True)
class Kalem:
    """Teklif kalemi. Fiyat teklif anında **dondurulmuş** olarak gelir.

    Motor kataloğa bakmaz: kablo fiyatı bakır ve dolara endeksli, günlük oynar.
    Ürünle canlı bağ kurulursa katalog fiyatı değişince geçmiş teklifler kendiliğinden
    bozulur. `birim_fiyat` teklifin para biriminde, kur uygulanmış hâlde verilir.
    """

    ad: str
    miktar: Decimal
    birim_fiyat: Decimal
    kdv_orani: Decimal = Decimal(20)
    # Zincirli iskonto: %20 sonra %5, %25 DEĞİL. Sırayla çarpımsal uygulanır.
    iskontolar: tuple[Decimal, ...] = ()
    iskontoya_tabi: bool = True
    tur: str = MALZEME


@dataclass(frozen=True)
class ZincirSatiri:
    """Teklif seviyesinde, sırası önemli tek bir hesap adımı.

    Sabit formül yerine sıralı satır listesi kurulmasının sebebi: iskonto önce mi
    işçilik önce mi sorusunun cevabı işletmeye göre değişiyor ve sonucu değiştiriyor.
    Yeni işletme kod değil, ayar istesin.
    """

    tur: str
    deger: Decimal
    ad: str = ""
    taban: str = TABAN_YURUYEN
    kapsam: str = KAPSAM_ISKONTOYA_TABI
    # Sadece ek satırlarında anlamlı: eklenen kalemin KDV oranı.
    kdv_orani: Decimal | None = None
    # Eklenen kalem kendisinden SONRAKİ iskontolara girsin mi. İşçilik için False.
    eklenen_iskontoya_tabi: bool = False
    # Eklenen kalemin türü; raporlamada işçiliği malzemeden ayırmak için.
    eklenen_tur: str = DIGER


# =============================================================================
# Çıktı
# =============================================================================


@dataclass(frozen=True)
class KalemSonuc:
    ad: str
    tur: str
    miktar: Decimal
    birim_fiyat: Decimal
    brut: Decimal              # miktar × birim fiyat
    kalem_iskontosu: Decimal   # kalemin kendi zincirinden düşen
    zincir_iskontosu: Decimal  # teklif seviyesi iskontodan bu kaleme düşen pay
    net: Decimal               # KDV matrahı
    kdv_orani: Decimal
    kdv: Decimal
    toplam: Decimal            # net + kdv
    iskontoya_tabi: bool


@dataclass(frozen=True)
class ZincirSonuc:
    """Bir zincir adımının ne yaptığı. Teklif çıktısında satır satır gösterilir."""

    ad: str
    tur: str
    deger: Decimal
    taban_tutar: Decimal  # yüzdenin üzerinden hesaplandığı tutar
    etki: Decimal         # negatif = indirim, pozitif = ekleme


@dataclass(frozen=True)
class TeklifSonuc:
    kalemler: tuple[KalemSonuc, ...]
    zincir: tuple[ZincirSonuc, ...]
    kalem_ara_toplami: Decimal  # zincir uygulanmadan önceki net toplam
    ara_toplam: Decimal         # zincir sonrası, KDV hariç
    kdv_toplami: Decimal
    genel_toplam: Decimal
    # KDV oranı → (matrah, kdv). E-faturada oran bazlı döküm isteniyor.
    kdv_dagilimi: dict[Decimal, tuple[Decimal, Decimal]] = field(default_factory=dict)


# =============================================================================
# Dağıtım
# =============================================================================


def dagit(tutar: Decimal, agirliklar: list[Decimal]) -> list[Decimal]:
    """`tutar`ı ağırlıklara orantılı dağıtır, kuruş kaybetmeden.

    Her payı ayrı ayrı yuvarlayıp toplarsan sonuç hedeften birkaç kuruş sapar ve
    teklifin toplamı kalemlerin toplamını tutmaz. Bu yüzden aşağı yuvarlanır, artan
    kuruşlar en büyük ondalık artığı olan kalemlere birer birer dağıtılır
    (largest remainder). Çıktının toplamı her zaman tam olarak `tutar`dır.
    """
    toplam_agirlik = sum(agirliklar)
    if toplam_agirlik <= 0 or tutar == 0:
        return [Decimal(0) for _ in agirliklar]

    paylar = []
    artiklar = []
    for agirlik in agirliklar:
        tam = tutar * agirlik / toplam_agirlik
        asagi = tam.quantize(KURUS, rounding=ROUND_DOWN)
        paylar.append(asagi)
        artiklar.append(tam - asagi)

    kalan = int(((tutar - sum(paylar)) / KURUS).to_integral_value())
    # Artığı büyük olandan başlayarak birer kuruş ekle.
    for indeks in sorted(range(len(paylar)), key=lambda i: artiklar[i], reverse=True)[:kalan]:
        paylar[indeks] += KURUS
    return paylar


# =============================================================================
# Hesap
# =============================================================================


@dataclass
class _Satir:
    """Hesap sırasında değişen iç kayıt. Dışarı `KalemSonuc` olarak çıkar."""

    ad: str
    tur: str
    miktar: Decimal
    birim_fiyat: Decimal
    brut: Decimal
    kalem_iskontosu: Decimal
    baslangic_net: Decimal  # kalem aşaması sonucu; TABAN_KALEM_TOPLAMI bunu kullanır
    net: Decimal
    kdv_orani: Decimal
    iskontoya_tabi: bool


def _kalem_neti(kalem: Kalem) -> tuple[Decimal, Decimal]:
    """Kalemin brütünü ve kendi zincirinden sonraki netini döner."""
    brut = kurusla(kalem.miktar * kalem.birim_fiyat)
    net = brut
    for oran in kalem.iskontolar:
        net = net * (Decimal(1) - oran / YUZ)
    return brut, kurusla(net)


def _uygun(satirlar: list[_Satir], kapsam: str) -> list[int]:
    if kapsam == KAPSAM_TUMU:
        return list(range(len(satirlar)))
    return [i for i, s in enumerate(satirlar) if s.iskontoya_tabi]


def hesapla(
    kalemler: list[Kalem],
    zincir: list[ZincirSatiri] | None = None,
    varsayilan_kdv: Decimal = Decimal(20),
) -> TeklifSonuc:
    """Kalemleri ve sıralı zinciri işleyip teklif toplamlarını üretir.

    `zincir` verildiği sırayla uygulanır; sıralama çağıranın işidir (DB tarafında
    `sira` kolonu). Motor sırayı yeniden düzenlemez, çünkü sıra bir iş kararıdır.
    """
    zincir = zincir or []

    # 1. Kalem aşaması
    satirlar: list[_Satir] = []
    for kalem in kalemler:
        brut, net = _kalem_neti(kalem)
        satirlar.append(
            _Satir(
                ad=kalem.ad,
                tur=kalem.tur,
                miktar=kalem.miktar,
                birim_fiyat=kalem.birim_fiyat,
                brut=brut,
                kalem_iskontosu=brut - net,
                baslangic_net=net,
                net=net,
                kdv_orani=kalem.kdv_orani,
                iskontoya_tabi=kalem.iskontoya_tabi,
            )
        )

    kalem_ara_toplami = sum((s.net for s in satirlar), Decimal(0))
    kalem_sayisi = len(satirlar)  # zincirin eklediği satırları ayırt etmek için

    # 2. Zincir aşaması
    zincir_sonuclari: list[ZincirSonuc] = []
    for adim in zincir:
        indeksler = _uygun(satirlar, adim.kapsam)
        if adim.taban == TABAN_KALEM_TOPLAMI:
            taban = sum((satirlar[i].baslangic_net for i in indeksler), Decimal(0))
        else:
            taban = sum((satirlar[i].net for i in indeksler), Decimal(0))

        if adim.tur in (ISKONTO_YUZDE, ISKONTO_TUTAR):
            ham = taban * adim.deger / YUZ if adim.tur == ISKONTO_YUZDE else adim.deger
            # İskonto tabanı aşarsa satırlar negatife düşerdi. Tabanla sınırla.
            tutar = min(kurusla(ham), max(taban, Decimal(0)))
            paylar = dagit(tutar, [satirlar[i].net for i in indeksler])
            for indeks, pay in zip(indeksler, paylar):
                satirlar[indeks].net -= pay
            etki = -tutar
        else:
            ham = taban * adim.deger / YUZ if adim.tur == EK_YUZDE else adim.deger
            tutar = kurusla(ham)
            satirlar.append(
                _Satir(
                    ad=adim.ad or adim.tur,
                    tur=adim.eklenen_tur,
                    miktar=Decimal(1),
                    birim_fiyat=tutar,
                    brut=tutar,
                    kalem_iskontosu=Decimal(0),
                    baslangic_net=tutar,
                    net=tutar,
                    kdv_orani=adim.kdv_orani if adim.kdv_orani is not None else varsayilan_kdv,
                    iskontoya_tabi=adim.eklenen_iskontoya_tabi,
                )
            )
            etki = tutar

        zincir_sonuclari.append(
            ZincirSonuc(
                ad=adim.ad or adim.tur,
                tur=adim.tur,
                deger=adim.deger,
                taban_tutar=taban,
                etki=etki,
            )
        )

    # 3. KDV — satır bazında, satır bazında yuvarlanmış (GİB)
    kalem_sonuclari: list[KalemSonuc] = []
    kdv_dagilimi: dict[Decimal, tuple[Decimal, Decimal]] = {}
    for sira, satir in enumerate(satirlar):
        net = kurusla(satir.net)
        kdv = kurusla(net * satir.kdv_orani / YUZ)
        # Zincirden gelen satırların kendi "kalem iskontosu" yok; farkı zincir yarattı.
        zincir_iskontosu = satir.baslangic_net - net if sira < kalem_sayisi else Decimal(0)
        kalem_sonuclari.append(
            KalemSonuc(
                ad=satir.ad,
                tur=satir.tur,
                miktar=satir.miktar,
                birim_fiyat=satir.birim_fiyat,
                brut=satir.brut,
                kalem_iskontosu=satir.kalem_iskontosu,
                zincir_iskontosu=zincir_iskontosu,
                net=net,
                kdv_orani=satir.kdv_orani,
                kdv=kdv,
                toplam=net + kdv,
                iskontoya_tabi=satir.iskontoya_tabi,
            )
        )
        onceki_matrah, onceki_kdv = kdv_dagilimi.get(satir.kdv_orani, (Decimal(0), Decimal(0)))
        kdv_dagilimi[satir.kdv_orani] = (onceki_matrah + net, onceki_kdv + kdv)

    ara_toplam = sum((k.net for k in kalem_sonuclari), Decimal(0))
    kdv_toplami = sum((k.kdv for k in kalem_sonuclari), Decimal(0))

    return TeklifSonuc(
        kalemler=tuple(kalem_sonuclari),
        zincir=tuple(zincir_sonuclari),
        kalem_ara_toplami=kalem_ara_toplami,
        ara_toplam=ara_toplam,
        kdv_toplami=kdv_toplami,
        genel_toplam=ara_toplam + kdv_toplami,
        kdv_dagilimi=kdv_dagilimi,
    )


def kur_uygula(birim_fiyat: Decimal, kur: Decimal) -> Decimal:
    """Kaynak para birimindeki fiyatı teklif para birimine çevirir.

    Kur teklif anında dondurulur ve kalemde saklanır (`QuoteItem.fx_rate`). Klemsan
    tamamen EURO, Grup Arge aynı dosyada TL ve USD veriyor; kur donmazsa aynı teklif
    ertesi gün başka rakam gösterir.

    Yuvarlama burada kuruşa değil dört basamağa yapılır: birim fiyat kuruşa
    yuvarlanırsa ucuz malzemede miktarla çarpınca sapma büyür (KM→metre dersi).
    """
    return (birim_fiyat * kur).quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN)
