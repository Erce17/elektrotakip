"""ORM ile hesap motoru arasındaki ince katman.

`quote_engine` bilinçli olarak DB bilmiyor. Bu dosya ORM nesnelerini motorun girdisine
çevirir ve şablonları (müşteri/işletme varsayılanı) gerçek zincir satırlarına kopyalar.
Hesap mantığı buraya yazılmaz — buraya yazılan her satır testsiz kalır.
"""

from decimal import Decimal

from app import quote_engine as motor
from app.models import Quote, QuoteAdjustment, QuoteItem


def _ondalik(deger, varsayilan: Decimal = Decimal(0)) -> Decimal:
    """Numeric kolonları SQLite'ta bazen float/int, Postgres'te Decimal döner."""
    if deger is None:
        return varsayilan
    return deger if isinstance(deger, Decimal) else Decimal(str(deger))


def _kalem_iskontolari(item: QuoteItem) -> tuple[Decimal, ...]:
    """Kalemin kendi zincirinden sadece yüzde iskontoları alır.

    Kalem seviyesinde tutar iskontosu (`iskonto_tutar`) v1'de desteklenmiyor: liste
    fiyatı + oran zinciri kalıbı sektörde yüzdeyle dönüyor. Tabloda alan var, motora
    girmiyor — desteklenince burası genişler.
    """
    return tuple(
        _ondalik(a.value)
        for a in sorted(item.adjustments, key=lambda a: a.position)
        if a.kind == motor.ISKONTO_YUZDE
    )


def kalem_girdisi(item: QuoteItem) -> motor.Kalem:
    return motor.Kalem(
        ad=item.name,
        miktar=_ondalik(item.quantity, Decimal(1)),
        birim_fiyat=_ondalik(item.unit_price),
        kdv_orani=_ondalik(item.vat_rate, Decimal(20)),
        iskontolar=_kalem_iskontolari(item),
        iskontoya_tabi=bool(item.discountable),
        tur=item.kind,
    )


def zincir_girdisi(adjustment: QuoteAdjustment) -> motor.ZincirSatiri:
    return motor.ZincirSatiri(
        tur=adjustment.kind,
        deger=_ondalik(adjustment.value),
        ad=adjustment.label or "",
        taban=adjustment.base,
        kapsam=adjustment.scope,
        kdv_orani=None if adjustment.vat_rate is None else _ondalik(adjustment.vat_rate),
        eklenen_iskontoya_tabi=bool(adjustment.added_discountable),
        eklenen_tur=adjustment.added_kind,
    )


def hesapla(quote: Quote) -> motor.TeklifSonuc:
    """Kayıtlı teklifi hesaplar. DB'ye yazmaz, sadece okur."""
    varsayilan_kdv = Decimal(20)
    if quote.owner is not None and quote.owner.quote_defaults is not None:
        varsayilan_kdv = _ondalik(quote.owner.quote_defaults.vat_rate, varsayilan_kdv)

    kalemler = [
        kalem_girdisi(i)
        for i in sorted(quote.items, key=lambda i: i.position)
        if i.parent_item_id is None  # bileşenler bugün ayrı kalem olarak girmiyor
    ]
    # `quote.adjustments` yalnızca teklif seviyesini taşır; kalem zinciri kalemin
    # kendi `adjustments`'ında ve `kalem_girdisi` içinde uygulanıyor.
    zincir = [zincir_girdisi(a) for a in sorted(quote.adjustments, key=lambda a: a.position)]
    return motor.hesapla(kalemler, zincir, varsayilan_kdv=varsayilan_kdv)


# --- Şablondan zincir kurma --------------------------------------------------

# Şablon satırında izin verilen anahtarlar. Beyaz liste, çünkü JSON kullanıcı verisi:
# tanımadığımız anahtar geçerse `QuoteAdjustment(**sablon)` patlar.
SABLON_ALANLARI = frozenset(
    {
        "position",
        "label",
        "kind",
        "value",
        "base",
        "scope",
        "vat_rate",
        "added_discountable",
        "added_kind",
    }
)


def sablondan_zincir(sablon: list[dict] | None) -> list[QuoteAdjustment]:
    """Varsayılan zincir şablonunu gerçek `QuoteAdjustment` satırlarına çevirir.

    Kopyalanır, bağlanmaz: müşterinin varsayılanı sonradan değişse geçmiş teklif
    kendiliğinden bozulmasın. Teklif bir kez kurulduktan sonra kendi zincirinin sahibi.
    """
    satirlar = []
    for sira, ham in enumerate(sablon or []):
        alanlar = {k: v for k, v in ham.items() if k in SABLON_ALANLARI}
        if "kind" not in alanlar or "value" not in alanlar:
            continue  # eksik şablon satırı sessizce atlanır; hesabı bozmasın
        alanlar.setdefault("position", sira)
        alanlar["value"] = _ondalik(alanlar["value"])
        satirlar.append(QuoteAdjustment(**alanlar))
    return satirlar


def kalem_kur(
    urun,
    miktar: Decimal,
    kur: Decimal = Decimal(1),
    iskontolar: tuple[Decimal, ...] = (),
) -> QuoteItem:
    """Katalog ürününden teklif kalemi üretir; fiyatı ve kuru dondurur.

    `product_id` sadece izlenebilirlik için taşınır. Hesap ondan okumaz — ürün silinse
    veya fiyatı değişse teklif olduğu gibi durur.
    """
    kaynak_fiyat = _ondalik(urun.unit_price)
    return QuoteItem(
        product_id=urun.id,
        supplier_code=getattr(urun, "supplier_code", None),
        name=urun.name,
        unit=urun.unit or "Adet",
        quantity=miktar,
        source_currency=urun.currency or "TRY",
        source_unit_price=kaynak_fiyat,
        fx_rate=kur,
        unit_price=motor.kur_uygula(kaynak_fiyat, kur),
        vat_rate=_ondalik(urun.vat_rate, Decimal(20)),
        adjustments=[
            QuoteAdjustment(position=sira, kind=motor.ISKONTO_YUZDE, value=oran)
            for sira, oran in enumerate(iskontolar)
        ],
    )
