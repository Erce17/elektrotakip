# PROGRESS — Elektrotakip

> Thufir bu dosyayı her oturum sonunda üzerine yazar. Oturum açılışında **önce burası okunur.**

## Son oturum
**Tarih:** 2026-07-25 (Olric, kod yazılmadı — denetim brifingi hazırlandı)
**Yapılanlar:** Erce projenin nasıl yazıldığını açıkladı: kodun büyük kısmı tarayıcıdan
AI'ya sorulup kopyala-yapıştır ile eklenmiş. Sonuç parçalı bir yapı, tutarsız kalite ve
Erce'nin kendisinin de tam okumadığı bölümler. Bu oturumun çıktısı kod değil, **görev
tanımının değişmesi**: sıradaki iş "katalog auth'unu bağla" değil, **kod tabanının baştan
okunup denetlenmesi.**

**Düzeltme:** Bu dosyanın önceki sürümü "henüz push edilmedi" diyordu. Yanlış.
`main`, `origin/main` ile senkron, unpushed commit yok. Repo public.

## ⚠️ Açık güvenlik açığı — her şeyden önce
**`.env.example` içindeki `SECRET_KEY`, `.env`'deki gerçek anahtarın birebir aynısı ve
bu dosya git'te takipli, public repo'da yayında.**

Etki: JWT imzalama anahtarı sızmış. Anahtarı bilen biri istediği `user_id` için geçerli
token üretir, parola bilmeden herhangi bir hesap olarak oturum açar. Auth katmanının
tamamı bypass edilebilir durumda.

Yapılacaklar (sıra önemli):
1. Yeni `SECRET_KEY` üret, `.env`'e yaz.
2. `.env.example` içindeki değeri placeholder ile değiştir (`<rastgele-uzun-string>`),
   commit et.
3. Erce'ye sor: aynı anahtar Railway ortam değişkenlerinde de duruyor mu? Duruyorsa
   orası da güncellenmeli.
4. Git geçmişinden temizlemek opsiyoneldir — anahtar zaten ifşa olduğu için asıl çözüm
   rotasyon. Erce isterse repo geçici olarak private'a alınabilir.

Bu iş bitmeden başka bir şeye geçme.

## Şu an nerede kaldık — görev: tam kod denetimi
Proje 15 Python dosyası / ~1100 satır. Tek oturumda okunabilir boyutta.
`app/routers/catalog.py` 270 satırla en şişkin dosya ve kuşkunun merkezi.

Denetimi şu sırayla yap, her bölüm sonunda bulguları listele — **düzeltmeye hemen girme,
önce tam resim çıksın.** Erce hangilerinin düzeltileceğine bakıp karar verecek.

1. **Güvenlik** (öncelik) — auth akışı, token üretimi/doğrulaması, cookie bayrakları
   (httpOnly/secure/samesite), parola hash'leme, SQL enjeksiyonu, yetkisiz veri erişimi.
2. **Veri izolasyonu** — her route gerçekten `current_user`'a filtreliyor mu. Bilinen
   açık: `catalog.py` içinde `user_id=1` hardcoded, `get_current_user` bağlı değil.
   Doğru kalıp `customers.py`'da; şablon olarak onu al.
3. **Tutarlılık** — kopyala-yapıştır kaynaklı çelişkiler: aynı işi iki farklı şekilde
   yapan yerler, ölü kod, kullanılmayan import, birbirini tutmayan isimlendirme,
   hata yönetiminin olduğu/olmadığı yerler.
4. **Yarım kalmış işler** — Erce'nin bildiği iki tanesi: **CSV/Excel içe aktarma yarım**
   ve **arayüz kötü**. Bunları teyit et, başka yarım kalanı varsa bul.

## Bilinen eksikler (Erce'nin kendi tespiti)
- **CSV okuma yarım yamalak.** `catalog.py` içindeki içe aktarma mantığı. Not: bu kodun
  bazı davranışları gerçek kullanım ihtiyacından geliyor (KM→metre fiyat çevrimi, Türkçe
  `1.200,50` sayı formatı, mükerrer atlama). Yeniden yazarken bu davranışları koru.
- **Arayüz kötü.** Jinja2 + HTMX şablonları. Şimdilik teşhis yeter, elden geçirme ayrı iş.
- **Hiç test yok.** pytest + httpx kurulu ama tek test yazılmamış.

## Sıradaki adım
1. `SECRET_KEY` rotasyonu ve `.env.example` temizliği (yukarıdaki bölüm).
2. Kod denetimi — dört başlık, bulgular listesi. Düzeltme yok, rapor var.
3. Erce bulguları önceliklendirir.
4. Ondan sonra: katalog auth'u + veri izolasyonu, sonra ilk testler.
5. Daha sonrası: CSV içe aktarmanın tamamlanması · arayüz · teklif/fatura üretimi.

## Açık sorular / kararlar
- Aynı `SECRET_KEY` Railway'de kullanılıyor mu? (Erce'ye sorulacak)
- Repo public kalsın mı, denetim bitene kadar private mı olsun? (Erce'ye sorulacak)
- Katalog auth'u eklendikten sonra mevcut `user_id=1` verisi ne olacak? Migration mı,
  elle temizlik mi, yoksa dev verisi olduğu için önemsiz mi?
- Teklif/fatura modülü yeni bir router mı yoksa katalog altında mı yaşayacak?

## Öğrenilenler
| Konu | Ne öğrenildi | Tarih |
|---|---|---|
| Sır yönetimi | `.env.example` bir şablondur, gerçek değer taşımaz. Üretilen anahtar doğrudan `.env`'e yazılır, örnek dosyaya placeholder konur. | 2026-07-25 |

## Vault özeti (Olric'e taşınacak)
Denetim henüz yapılmadı. Olric tarafından tespit edilen açık: public repo'da sızmış
JWT `SECRET_KEY`. Görev tanımı "auth tamamlama"dan "tam kod denetimi"ne çevrildi.
