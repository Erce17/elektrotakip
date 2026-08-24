"""Giriş denemesi sınırı — kaba kuvvetle parola tahminini yavaşlatır.

Sorun: `/login` sınırsız denemeye açıktı. 10 karakterlik parola politikası
tahmin uzayını büyütüyor ama tek başına yetmiyor; saniyede yüzlerce deneme
yapabilen bir saldırgan için asıl fren deneme sayısıdır.

Sayaç **süreç belleğinde** duruyor. Bilerek: v1 tek Railway instance'ında
koşuyor ve Redis eklemek bugünkü riske göre fazla. Sınırın iki bilinen zayıflığı
var, ikisi de kabul edildi:
  - Süreç yeniden başlarsa sayaçlar sıfırlanır.
  - Birden fazla instance açılırsa her biri kendi sayacını tutar.
İkincisi olduğu gün burası paylaşılan bir sayaca (Redis) taşınmalı.
"""

import time
from collections import defaultdict


class DenemeSiniri:
    """Kayan pencere: son `pencere` saniyede en fazla `azami` başarısız deneme."""

    def __init__(self, azami: int, pencere: int):
        self.azami = azami
        self.pencere = pencere
        self._denemeler: dict[str, list[float]] = defaultdict(list)

    def _temizle(self, anahtar: str, simdi: float) -> list[float]:
        taze = [t for t in self._denemeler[anahtar] if simdi - t < self.pencere]
        self._denemeler[anahtar] = taze
        return taze

    def kilitli_mi(self, anahtar: str) -> bool:
        return len(self._temizle(anahtar, time.monotonic())) >= self.azami

    def basarisiz(self, anahtar: str) -> None:
        simdi = time.monotonic()
        self._temizle(anahtar, simdi).append(simdi)

    def sifirla(self, anahtar: str) -> None:
        """Başarılı girişten sonra çağrılır: doğru parolayı bilen cezalandırılmaz."""
        self._denemeler.pop(anahtar, None)

    def kalan_dakika(self, anahtar: str) -> int:
        denemeler = self._temizle(anahtar, time.monotonic())
        if not denemeler:
            return 0
        gecen = time.monotonic() - min(denemeler)
        return max(1, int((self.pencere - gecen) // 60) + 1)


# Hesap bazlı: belirli bir e-postaya parola denemesi.
giris_siniri = DenemeSiniri(azami=5, pencere=15 * 60)

# IP bazlı: e-posta değiştirerek hesap sınırını dolaşmayı engeller. Aynı ofisten
# birkaç kişi giriş yapabilsin diye hesap sınırından belirgin şekilde gevşek.
ip_siniri = DenemeSiniri(azami=20, pencere=15 * 60)

# Kayıt: tek IP'den hesap yağdırılmasın.
kayit_siniri = DenemeSiniri(azami=5, pencere=60 * 60)


def istemci_ip(request) -> str:
    """Railway proxy arkasında gerçek IP `X-Forwarded-For`'un ilk değerinde.

    Başlık istemciden geliyor, yani taklit edilebilir; sınırı dolaşmak isteyen
    kendine sahte IP yazabilir. Bu yüzden IP sınırı tek başına değil, hesap
    sınırıyla birlikte duruyor — hesap sınırı e-postaya bağlı ve taklit edilemez.
    """
    iletilen = request.headers.get("x-forwarded-for")
    if iletilen:
        return iletilen.split(",")[0].strip()
    return request.client.host if request.client else "bilinmiyor"


def hepsini_sifirla() -> None:
    """Testler arası sızıntıyı önler; üretimde çağrılmıyor."""
    for sinir in (giris_siniri, ip_siniri, kayit_siniri):
        sinir._denemeler.clear()
