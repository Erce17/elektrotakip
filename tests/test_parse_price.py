"""Fiyat ayrıştırma.

Bu mantık daha önce hem Excel içe aktarmada hem ürün güncellemede ayrı ayrı
yazılmıştı ve ikisi birbirinden farklıydı (biri boşluk temizliyor, diğeri
temizlemiyordu). Tek fonksiyona indirildi; bu testler gerçek kullanımdan gelen
davranışları sabitler.
"""

import pytest

from app.routers.catalog import parse_price


@pytest.mark.parametrize(
    "girdi,beklenen",
    [
        # Türkçe format: nokta binlik ayracı, virgül ondalık
        ("1.200,50", 1200.50),
        ("1.200.000,00", 1200000.00),
        ("850,75", 850.75),
        # İngilizce/düz format
        ("1200.50", 1200.50),
        ("1200", 1200.0),
        # Excel hücresi zaten sayı olarak gelebilir
        (1200.5, 1200.5),
        (1200, 1200.0),
        # Kullanıcı birim ve boşluk yazıyor
        ("850 TL", 850.0),
        ("1.200,50 TL", 1200.50),
        (" 850 ", 850.0),
        ("850tl", 850.0),
    ],
)
def test_gecerli_fiyatlar(girdi, beklenen):
    assert parse_price(girdi) == pytest.approx(beklenen)


@pytest.mark.parametrize("girdi", [None, "", "   ", "fiyat sorunuz", "abc"])
def test_anlasilmayan_girdi_none_doner(girdi):
    """None dönmesi önemli: çağıran taraf 0'a mı düşsün eski değerde mi kalsın kendi karar verir."""
    assert parse_price(girdi) is None
