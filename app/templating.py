"""Şablon motoru ve ortak filtreler.

Üç router da kendi Jinja2Templates nesnesini kuruyordu; filtre eklemek için
tek bir yer gerekiyor.
"""

from decimal import Decimal

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def turkce_fiyat(value, min_basamak: int = 2) -> str:
    """Fiyatı Türkçe yazımla döndürür: 1234.5 → '1.234,50'.

    Kolon 4 ondalık tutuyor. Kuruşun altındaki değerler (KM fiyatından bölünen
    ucuz malzemeler) iki basamakta '0,00' görünüyordu; bu yüzden anlamlı
    basamaklar varsa dörde kadar gösteriliyor.
    """
    if value is None:
        return "-"
    try:
        sayi = Decimal(str(value))
    except Exception:
        return str(value)

    basamak = min_basamak
    if sayi != sayi.quantize(Decimal("0.01")):
        basamak = 4

    metin = f"{sayi:,.{basamak}f}"                    # 1,234.5000
    return metin.replace(",", "X").replace(".", ",").replace("X", ".")


templates.env.filters["fiyat"] = turkce_fiyat
