"""Ürün parametresi ayrıştırma ve arama — saf katman.

Burada DB yok: girdi metin, çıktı dataclass. Sorgu kurucular SQLAlchemy ifadesi
üretiyor ama oturum bilmiyor.

**Neden var:** `technical_specs` tek bir uzun metin ve içindeki parametreler
ayrıştırılmamıştı. Sonucu: kesit sayı olmadığı için "2.5–6 mm² arası" filtresi
yapılamıyor, sahada konuşulan `3x2.5 NYY` ifadesiyle ürün bulunamıyordu. Teklif
ekranındaki ürün seçimi de bu yüzden 500 kayıtlık bir açılır listeydi — Klemsan tek
başına 3.694 ürün veriyor.

**Ölçüm, ayrıştırıcının şeklini belirledi.** 11 gerçek dosyada sayıldı:

- Çıplak `NxM` kalıbı **çoğunlukla yanlış pozitif.** Viko'da ürün kodu (`926Y5X01`),
  Klemsan'da kontak değeri (`2x8A/250VAC`) ve fiziksel ölçü (`96x96mm`, `5x20`),
  Tense'de ekran boyutu (`3x20 mm`). Bu yüzden kesit **yalnızca `mm²` bağlamından**
  ya da dosyanın kendi kesit sütunundan okunuyor.
- Öznur'da kesit **ürün adında değil, ayrı `Kesit (mm2)` sütununda.** Ad 5 satırda
  birebir aynı; sütun okunmazsa ürünler ayırt edilemiyor.
- Erse'de kesit adın içinde ve çeşitli: `2X0,22 mm2`, `8x0,22 mm2`, `4x2x23 AWG`.
- Molwex'te `0.5-1.5 mm²` bir **aralık** — pabucun hizmet ettiği kablo aralığı.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# --- İletken ----------------------------------------------------------------
BAKIR = "bakır"
ALUMINYUM = "alüminyum"

# --- Yalıtım ----------------------------------------------------------------
# Sıra önemli: 'XLPE' içinde 'PE' geçiyor, uzun olan önce denenmeli.
YALITIM_KALIPLARI = (
    ("XLPE", r"\bXLPE\b"),
    ("HFFR", r"\bHFFR\b"),
    ("LSZH", r"\bLSZH\b|\bLS0H\b"),
    ("PVC", r"\bPVC\b"),
    ("PE", r"\bPE\b"),
    ("Silikon", r"silikon"),
)

ILETKEN_KALIPLARI = (
    (BAKIR, r"\bCu\b|bakir|bakır"),
    (ALUMINYUM, r"\bAl\b|aluminyum|alüminyum"),
)

# Kesit yalnızca `mm²` bağlamında güvenilir. `mm` (kare olmadan) fiziksel ölçüdür:
# Klemsan'ın '96x96mm' kutu ölçüsü, Tense'in '3x20 mm' ekranı.
#
# ⚠️ Boşluklu biçimde yalnızca gerçek `²` kabul ediliyor. `mm\s*[²2]` yazılmıştı ve
# Tense'in '30X10 mm 200/5 Akım Trafosu' metninde "mm" + boşluk + "2" olarak eşleşip
# akım trafosunu 30 damarlı 10 mm² kablo sanıyordu. Bitişik `mm2` ise güvenli, ama
# ardından başka rakam gelmemeli.
_MM2 = r"mm(?:\s*²|2(?![0-9]))"

# '3x2,5 mm²' → 3 damar, 2,5 mm². '4x2x23 AWG' gibi mm²'siz kalıplar eşleşmiyor.
DAMAR_KESIT = re.compile(
    rf"(?<![\d,.])(\d{{1,2}})\s*[x×*]\s*(\d{{1,4}}(?:[.,]\d{{1,3}})?)\s*{_MM2}",
    re.IGNORECASE,
)

# Aralık: '0,5-1,5 mm²'. Pabucun hizmet ettiği kablo aralığı; ürünün kendi kesiti
# değil. Kesit olarak yazmak yanlış olurdu, o yüzden ayrıca yakalanıp atlanıyor.
KESIT_ARALIGI = re.compile(
    rf"(\d{{1,4}}(?:[.,]\d{{1,3}})?)\s*-\s*(\d{{1,4}}(?:[.,]\d{{1,3}})?)\s*{_MM2}",
    re.IGNORECASE,
)

# Tek kesit: '2,5 mm²'.
TEK_KESIT = re.compile(
    rf"(?<![\d,.\-x×*])(\d{{1,4}}(?:[.,]\d{{1,3}})?)\s*{_MM2}",
    re.IGNORECASE,
)

KILIFSIZ = re.compile(r"kılıfsız|kilifsiz", re.IGNORECASE)
KILIFLI = re.compile(r"kılıflı|kilifli", re.IGNORECASE)

# Kesit için makul üst sınır. Bunun üstündeki bir sayı mm² bağlamında görünse bile
# ayrıştırma hatasıdır (tarih, kod, fiyat kırıntısı).
MAKUL_KESIT_UST = Decimal(1000)
MAKUL_DAMAR_UST = 61  # piyasadaki en kalın çok damarlı kablolar ~61 damar


@dataclass(frozen=True)
class Parametreler:
    """Metinden çıkarılan ürün parametreleri. Çıkarılamayanlar None kalır."""

    cross_section: Decimal | None = None
    core_count: int | None = None
    conductor: str | None = None
    insulation: str | None = None
    sheathed: bool | None = None
    # Kesit tek değer değil aralıksa (pabuç) kesit yazılmıyor; sebebi bilinsin diye
    # ayrıca işaretleniyor.
    kesit_araligi_mi: bool = False

    @property
    def bos_mu(self) -> bool:
        return not any(
            (
                self.cross_section is not None,
                self.core_count is not None,
                self.conductor,
                self.insulation,
                self.sheathed is not None,
            )
        )


def _ondalik(ham: str) -> Decimal | None:
    """'2,5' ve '2.5' aynı sayı. Kesitte binlik ayracı olmaz, virgül ondalıktır."""
    try:
        return Decimal(ham.replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def _ilk_eslesen(metin: str, kaliplar) -> str | None:
    """Kalıplardan metinde en SOLDA geçeni döner.

    Sol taraf önemli: Erse'nin koaksiyel kablolarında `Cu/Al` ikisi birden geçiyor
    ve kastedilen iç iletken, yani soldaki.
    """
    en_iyi = None
    for etiket, kalip in kaliplar:
        eslesme = re.search(kalip, metin, re.IGNORECASE)
        if eslesme is None:
            continue
        if en_iyi is None or eslesme.start() < en_iyi[0]:
            en_iyi = (eslesme.start(), etiket)
    return en_iyi[1] if en_iyi else None


# Kesit sütunundaki ifade: '2.5', '4x25', '3x25+16' (3 faz 25 + 16 nötr/toprak).
# Sahada konuşulan yazım birebir bu. Sütun başlığı zaten mm² olduğunu söylediği için
# burada `NxM` güvenilir — yanlış pozitif riski yalnızca serbest metinde vardı.
KESIT_SUTUNU = re.compile(
    r"^\s*(?:(\d{1,2})\s*[x×*]\s*)?(\d{1,4}(?:[.,]\d{1,3})?)"
)


def kesit_sutununu_coz(ham: str) -> tuple[Decimal | None, int | None]:
    """Kesit sütunundaki değeri `(kesit, damar sayısı)` olarak okur.

    '2.5' → (2.5, None) · '4x25' → (25, 4) · '3x25+16' → (25, 3).
    `+16` faz dışı iletken (nötr/toprak); damar sayısına katılmıyor çünkü sahada
    "3x25+16" üç damarlı diye konuşuluyor.
    """
    if not ham or not str(ham).strip():
        return (None, None)
    eslesme = KESIT_SUTUNU.match(str(ham))
    if eslesme is None:
        return (None, None)

    damar = int(eslesme.group(1)) if eslesme.group(1) else None
    kesit = _ondalik(eslesme.group(2))
    if damar is not None and not 0 < damar <= MAKUL_DAMAR_UST:
        damar = None
    if kesit is not None and not 0 < kesit <= MAKUL_KESIT_UST:
        kesit = None
    return (kesit, damar)


def parametreleri_coz(*metinler: str, kesit_metni: str = "") -> Parametreler:
    """Ürün metinlerinden parametreleri çıkarır.

    `kesit_metni` dosyanın kendi kesit sütunundan gelir ve metinden okunana **tercih
    edilir.** Öznur böyle: kesit adda değil ayrı sütunda ve ad 5 satırda birebir aynı.
    """
    kesit, damar_sutunundan = kesit_sutununu_coz(kesit_metni)

    metin = " ".join(m for m in metinler if m)
    if not metin.strip():
        return Parametreler(cross_section=kesit, core_count=damar_sutunundan)

    cross_section = kesit
    core_count = damar_sutunundan
    aralik_mi = False

    damar_eslesme = DAMAR_KESIT.search(metin)
    if damar_eslesme:
        damar = int(damar_eslesme.group(1))
        okunan = _ondalik(damar_eslesme.group(2))
        if core_count is None and 0 < damar <= MAKUL_DAMAR_UST:
            core_count = damar
        if cross_section is None and okunan is not None and 0 < okunan <= MAKUL_KESIT_UST:
            cross_section = okunan
    elif cross_section is None:
        if KESIT_ARALIGI.search(metin):
            # Aralık ürünün kendi kesiti değil; boş bırakılıyor ama işaretleniyor.
            aralik_mi = True
        else:
            tek = TEK_KESIT.search(metin)
            if tek:
                okunan = _ondalik(tek.group(1))
                if okunan is not None and 0 < okunan <= MAKUL_KESIT_UST:
                    cross_section = okunan

    sheathed = None
    if KILIFSIZ.search(metin):
        sheathed = False
    elif KILIFLI.search(metin):
        sheathed = True

    return Parametreler(
        cross_section=cross_section,
        core_count=core_count,
        conductor=_ilk_eslesen(metin, ILETKEN_KALIPLARI),
        insulation=_ilk_eslesen(metin, YALITIM_KALIPLARI),
        sheathed=sheathed,
        kesit_araligi_mi=aralik_mi,
    )


# =============================================================================
# Arama terimi ayrıştırma
# =============================================================================

# Sahada konuşulan ifade: "3x2.5 NYY", "5x16 bakır", "2.5-6 mm² arası".
# Arama kutusuna yazılanı bu kalıplara göre bölüp geri kalanını metin araması
# olarak kullanıyoruz.

ARAMA_DAMAR_KESIT = re.compile(
    r"(?<![\d,.])(\d{1,2})\s*[x×*]\s*(\d{1,4}(?:[.,]\d{1,3})?)(?![\d,.])"
)
ARAMA_ARALIK = re.compile(
    r"(?<![\d,.])(\d{1,4}(?:[.,]\d{1,3})?)\s*-\s*(\d{1,4}(?:[.,]\d{1,3})?)(?![\d,.])"
)
ARAMA_KESIT = re.compile(
    rf"(?<![\d,.\-x×*])(\d{{1,4}}(?:[.,]\d{{1,3}})?)\s*{_MM2}", re.IGNORECASE
)


@dataclass(frozen=True)
class AramaTerimi:
    """Kullanıcının yazdığı aramanın ayrıştırılmış hâli."""

    metin: str = ""                      # kalan serbest metin
    core_count: int | None = None
    cross_section: Decimal | None = None
    kesit_min: Decimal | None = None
    kesit_max: Decimal | None = None
    conductor: str | None = None
    insulation: str | None = None

    @property
    def parametreli_mi(self) -> bool:
        return any(
            (
                self.core_count is not None,
                self.cross_section is not None,
                self.kesit_min is not None,
                self.conductor,
                self.insulation,
            )
        )


def arama_terimini_coz(ham: str) -> AramaTerimi:
    """Arama kutusundaki ifadeyi parametre + serbest metne böler.

    Örnekler:
        '3x2.5 NYY'      → 3 damar, 2,5 mm², metin 'NYY'
        '2.5-6 mm2 nya'  → kesit 2,5–6 arası, metin 'nya'
        '5x16 bakır'     → 5 damar, 16 mm², iletken bakır, metin ''
        'klemens'        → sadece metin

    Serbest metin ile parametre birlikte kullanılıyor: kullanıcı "3x2.5" yazınca
    kesitle eşleşen her şey değil, aynı zamanda yazdığı isme uyanlar çıkmalı.
    """
    if not ham or not ham.strip():
        return AramaTerimi()

    kalan = ham.strip()
    core_count = cross_section = kesit_min = kesit_max = None

    # 1. Damar x kesit — en belirgin kalıp, önce o tüketilir.
    eslesme = ARAMA_DAMAR_KESIT.search(kalan)
    if eslesme:
        damar = int(eslesme.group(1))
        kesit = _ondalik(eslesme.group(2))
        if 0 < damar <= MAKUL_DAMAR_UST:
            core_count = damar
        if kesit is not None and 0 < kesit <= MAKUL_KESIT_UST:
            cross_section = kesit
        kalan = kalan[: eslesme.start()] + " " + kalan[eslesme.end():]

    # 2. Aralık: '2.5-6'
    if cross_section is None:
        eslesme = ARAMA_ARALIK.search(kalan)
        if eslesme:
            alt, ust = _ondalik(eslesme.group(1)), _ondalik(eslesme.group(2))
            if alt is not None and ust is not None and alt <= ust:
                kesit_min, kesit_max = alt, ust
                kalan = kalan[: eslesme.start()] + " " + kalan[eslesme.end():]

    # 3. Tek kesit: '2.5 mm²'
    if cross_section is None and kesit_min is None:
        eslesme = ARAMA_KESIT.search(kalan)
        if eslesme:
            kesit = _ondalik(eslesme.group(1))
            if kesit is not None and 0 < kesit <= MAKUL_KESIT_UST:
                cross_section = kesit
                kalan = kalan[: eslesme.start()] + " " + kalan[eslesme.end():]

    iletken = _ilk_eslesen(kalan, ILETKEN_KALIPLARI)
    yalitim = _ilk_eslesen(kalan, YALITIM_KALIPLARI)

    # İletken/yalıtım kelimelerini metinden çıkarmıyoruz: 'PVC' hem parametre hem
    # ürün adının parçası olabiliyor ve metin araması onu da bulmalı.
    kalan = re.sub(r"\bmm\s*[²2]\b", " ", kalan, flags=re.IGNORECASE)
    kalan = " ".join(kalan.split())

    return AramaTerimi(
        metin=kalan,
        core_count=core_count,
        cross_section=cross_section,
        kesit_min=kesit_min,
        kesit_max=kesit_max,
        conductor=iletken,
        insulation=yalitim,
    )


# =============================================================================
# Sorgu kurma
# =============================================================================


def sorguyu_daralt(sorgu, model, terim: AramaTerimi):
    """Ayrıştırılmış arama terimini SQLAlchemy sorgusuna çevirir.

    Oturum bilmiyor: hazır bir `Query` alıp filtre ekliyor. Sahiplik/izolasyon
    filtresini çağıran koyar — bu fonksiyon onu bilmemeli, yoksa unutulduğu yerde
    açık oluşur.

    Parametre ve metin **birlikte** daraltıyor: kullanıcı "3x2.5 NYY" yazdığında
    kesiti tutan her şey değil, adı da NYY'ye uyanlar çıkmalı.
    """
    if terim.core_count is not None:
        sorgu = sorgu.filter(model.core_count == terim.core_count)

    if terim.cross_section is not None:
        sorgu = sorgu.filter(model.cross_section == terim.cross_section)
    elif terim.kesit_min is not None:
        sorgu = sorgu.filter(
            model.cross_section >= terim.kesit_min,
            model.cross_section <= terim.kesit_max,
        )

    # İletken/yalıtım yalnızca ayrıştırılabilmiş ürünleri elemesin diye NULL'a da
    # izin veriliyor: parametresi çıkarılamamış ürün metinle bulunmaya devam etmeli.
    if terim.conductor:
        sorgu = sorgu.filter(
            (model.conductor == terim.conductor) | (model.conductor.is_(None))
        )
    if terim.insulation:
        sorgu = sorgu.filter(
            (model.insulation == terim.insulation) | (model.insulation.is_(None))
        )

    if terim.metin:
        # Her kelime ayrı ayrı aranıyor: "nya kablo" yazınca kelimelerin sırası
        # ürün adındakiyle aynı olmak zorunda kalmasın.
        for kelime in terim.metin.split():
            kalip = f"%{kelime}%"
            sorgu = sorgu.filter(
                model.name.ilike(kalip)
                | model.brand.ilike(kalip)
                | model.technical_specs.ilike(kalip)
                | model.supplier_code.ilike(kalip)
            )
    return sorgu


def urun_ara(sorgu, model, ham_terim: str, limit: int = 50):
    """Arama kutusundaki ifadeyle ürünleri daraltıp sıralı olarak döner."""
    terim = arama_terimini_coz(ham_terim)
    sorgu = sorguyu_daralt(sorgu, model, terim)
    return (
        sorgu.order_by(model.core_count.asc(), model.cross_section.asc(), model.name.asc())
        .limit(limit)
        .all()
    )
