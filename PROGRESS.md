# PROGRESS — Elektrotakip

> Thufir bu dosyayı her oturum sonunda üzerine yazar. Oturum açılışında **önce burası okunur.**

## Son oturum
**Tarih:** 2026-07-26 (Thufir)
**Yapılanlar:** Denetim raporlandı, kritik güvenlik açığı kapatıldı, katalog auth ve veri
izolasyonuna bağlandı, Excel içe aktarma sağlamlaştırıldı, proje geneli tutarlılık
temizliği yapıldı. Test altyapısı ilk kez çalışır durumda: **68 test geçiyor.**

Commit'ler: `244e7ff` (SECRET_KEY) · `be5db5a` (katalog auth+izolasyon) ·
`0344c06` (Excel) · `8c72e92` (temizlik). İlki push edildi, **son üçü henüz push edilmedi.**

## Kapatılanlar
- **SECRET_KEY sızıntısı (kritik).** `.env`'deki anahtar rotasyona sokuldu, `.env.example`
  placeholder'a çevrildi. `.env` git geçmişinde hiç yok, temiz. Railway canlı olmadığı
  için (trial bitmiş) orada yapılacak bir şey yok — **canlıya çıkarken `SECRET_KEY` ve
  `COOKIE_SECURE=true` ortam değişkeni olarak verilmeli.**
- **Katalog auth'suzdu.** `require_user` dependency'si eklendi (`app/dependencies.py`):
  koruma artık route imzasında, gövdede değil. Yetkisizde 303 → `/login`, HTMX isteğinde
  401 + `HX-Redirect`. `catalog.py` ve `customers.py` aynı kalıpta.
- **`user_id=1` hardcode'u ve IDOR.** Ürün erişimi `user_products` / `get_owned_product` /
  `get_owned_category` yardımcılarına toplandı; sahiplik zinciri (Product → Category →
  user) tek yerde. Kategori değiştirme de kontrol ediliyor.
- **Excel içe aktarma.** Uzantı/boyut/boş dosya kontrolü, bozuk dosyada 500 yerine mesaj,
  sonuç özeti (eklenen/atlanan/fiyatı okunamayan) sayfada gösteriliyor, tek commit
  (yarım içe aktarma yok), aynı dosyadaki mükerrerler de yakalanıyor.
- **Fiyat ayrıştırma** iki farklı kopyadan tek `parse_price`'a indi; anlaşılmazsa `None`
  döner, ne yapılacağına çağıran karar verir.
- **Gezinme.** Linkler `base.html`'e taşındı, her sayfadan Katalog/Müşteriler erişilebilir.
  Ana panel sabit metin yerine gerçek ürün/müşteri sayısını gösteriyor.
- **Ölü kod:** kök `main.py` ve `app/schemas.py` silindi.
- **Cookie `secure`** bayrağı eklendi, `COOKIE_SECURE` ile ayarlanıyor.

## Şu an nerede kaldık
Denetim listesindeki kritik ve yüksek maddeler bitti. Kalanlar aşağıda, önceliklendirilmiş.

### Sırada (denetimden kalan, önem sırasıyla)
1. **G4 — CSRF koruması yok.** `samesite=lax` POST'u kısmen korur, HTMX'in PUT/DELETE
   isteklerini korumaz. Tek gerçek güvenlik açığı olarak bu kaldı.
2. **G7 — parola politikası ve e-posta doğrulaması yok.** Tek karakterlik parola kabul
   ediliyor. `schemas.py` bunun içindi ama kullanılmadığı için silindi; doğrulama
   `auth.py`'a yazılmalı.
3. **G6 — `python-jose` bakımsız,** bilinen CVE'leri var. `PyJWT`'ye geçiş küçük iş.
4. **Y2 — kategori silme/düzenleme yok.** Ekleme var, gerisi yok.
5. **T6 — `vat_rate`** modelde ve ekleme formunda var ama listede görünmüyor,
   güncellemede yok. Teklif/fatura için KDV lazım olacak.
6. **T7 — `Customer.balance`** modelde var, hiçbir yerde kullanılmıyor. Ya cari hesap
   ekranı yazılacak ya alan kaldırılacak.
7. **T8 — migration zinciri kirli.** İki boş (`pass`) migration, bir tanesinin adı
   yaptığı işi anlatmıyor. Zincir çalışıyor, sadece okunaksız. Düşük öncelik.
8. **T10 — Tailwind CDN'den çekiliyor,** üretim için önerilmiyor.
9. **Y4 — teklif/fatura modülü** hiç yok. Ana panelde placeholder duruyor.

## Test durumu
`uv run pytest` → 68 test. Bellekte SQLite ile koşuyor, PostgreSQL gerekmiyor.
- `test_catalog_isolation.py` — erişim kontrolü + IDOR (26)
- `test_excel_import.py` — KM çevrimi, Türkçe sayı formatı, mükerrer, bozuk girdi (12)
- `test_customers_isolation.py` — müşteri izolasyonu (12)
- `test_home.py` — ana panel sayıları, gezinme (8)
- `test_parse_price.py` — fiyat ayrıştırma (10)

## Açık sorular / kararlar
- Katalog auth'u eklendiğinden `user_id=1` ile yazılmış eski dev verisi artık kimseye
  görünmüyor olabilir. Erce'nin lokal DB'sinde ne durumda, temizlensin mi?
- Teklif/fatura modülü yeni bir router mı, katalog altında mı?
- `Customer.balance` kalacak mı?

## Öğrenilenler
| Konu | Ne öğrenildi | Tarih |
|---|---|---|
| Sır yönetimi | `.env.example` bir şablondur, gerçek değer taşımaz. Üretilen anahtar doğrudan `.env`'e yazılır, örnek dosyaya placeholder konur. | 2026-07-25 |
| Auth tasarımı | Yetkisizde `None` dönen dependency, korumayı her route'ta elle yazmayı zorunlu kılar; bir yerde unutulunca açık oluşur. Doğrusu hata fırlatan zorunlu bir dependency: koruma imzada durur, unutulamaz. | 2026-07-26 |
| Sahiplik zinciri | Ürünün `user_id`'si olmadığı için her sorgu `join(Category)` ister. Bunu her route'ta tekrar yazmak yerine tek yardımcıya toplamak, açığın tekrar açılmasını engelliyor. | 2026-07-26 |
| Test yazmanın anı | İzolasyon düzeltmesiyle birlikte yazılan test, düzeltmenin kendisinden değerli: aynı açığın tekrar açılmasını engelliyor. | 2026-07-26 |

## Vault özeti (Olric'e taşınacak)
Elektrotakip denetimi tamamlandı ve kritik bulgular kapatıldı. Sızmış JWT anahtarı
rotasyona sokuldu; katalog modülü tamamen auth'suz ve veri izolasyonsuzdu, bağlandı
(IDOR dahil). Excel içe aktarma sağlamlaştırıldı. Proje ilk kez test kapsamına girdi:
68 test. Kalan en önemli açık CSRF koruması.
