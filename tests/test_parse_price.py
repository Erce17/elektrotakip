"""Fiyat ayrıştırma ve gösterimi.

Tedarikçi listeleri tek formatta gelmiyor. Buradaki her satır gerçek bir yazım
biçimi; yanlış ayrıştırma doğrudan yanlış fiyat demek.
"""

from decimal import Decimal

import pytest

from app.routers.catalog import parse_price, quantize_price
from app.templating import turkce_fiyat


@pytest.mark.parametrize(
    "girdi,beklenen",
    [
        # Hem nokta hem virgül: sondaki ondalık ayracıdır
        ("1.200,50", "1200.50"),
        ("1.200.000,00", "1200000.00"),
        ("1,200.50", "1200.50"),        # İngilizce binlik virgül
        ("1,234,567.89", "1234567.89"),
        # Sadece virgül: ondalık (Türkçe varsayılan)
        ("850,75", "850.75"),
        ("0,85", "0.85"),
        # Sadece nokta: 3 hane → binlik, değilse ondalık
        ("1.200", "1200"),
        ("1.234.567", "1234567"),
        ("1200.50", "1200.50"),
        ("1200.5", "1200.5"),
        ("0.500", "0.5"),               # tam kısım 0 → ondalık
        # Ayraçsız
        ("1200", "1200"),
        ("850 TL", "850"),
        ("1.200,50 TL", "1200.50"),
        ("1.200,50 ₺", "1200.50"),
        (" 850 ", "850"),
        ("850tl", "850"),
        # Excel hücresi sayı olarak gelebilir
        (1200.5, "1200.5"),
        (1200, "1200"),
        (Decimal("1200.50"), "1200.50"),
    ],
)
def test_gecerli_fiyatlar(girdi, beklenen):
    assert parse_price(girdi) == Decimal(beklenen)


@pytest.mark.parametrize("girdi", [None, "", "   ", "fiyat sorunuz", "abc", True, False])
def test_anlasilmayan_girdi_none_doner(girdi):
    """None dönmesi önemli: çağıran taraf 0'a mı düşsün eski değerde mi kalsın kendi karar verir."""
    assert parse_price(girdi) is None


def test_sonuc_decimal_float_degil():
    """Para değerinde float yuvarlama hatası biriktirir; kolon da Numeric."""
    assert isinstance(parse_price("1.200,50"), Decimal)


def test_binlik_ayraci_bin_kat_hata_uretmiyor():
    """'1.200' eskiden 1,2 oluyordu — sessiz 1000 kat sapma."""
    assert parse_price("1.200") == Decimal("1200")


def test_quantize_dort_basamaga_yuvarlar():
    assert quantize_price(Decimal("12.34567")) == Decimal("12.3457")
    assert quantize_price(Decimal("0.00004")) == Decimal("0.0000")


# --- Gösterim ------------------------------------------------------------

@pytest.mark.parametrize(
    "deger,beklenen",
    [
        (Decimal("1234.5"), "1.234,50"),
        (Decimal("1200"), "1.200,00"),
        (Decimal("0.85"), "0,85"),
        (Decimal("1234567.89"), "1.234.567,89"),
        # Kuruşun altı: iki basamakta '0,00' görünüyordu
        (Decimal("0.0035"), "0,0035"),
        (Decimal("12.3457"), "12,3457"),
        (None, "-"),
    ],
)
def test_turkce_fiyat_gosterimi(deger, beklenen):
    assert turkce_fiyat(deger) == beklenen
