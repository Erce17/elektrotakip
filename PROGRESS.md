# PROGRESS — Elektrotakip

> Thufir bu dosyayı her oturum sonunda üzerine yazar. Oturum açılışında **önce burası okunur.**

## Son oturum
**Tarih:** 2026-07-26 (Thufir)
**Yapılanlar:** Tam kod denetimi yapıldı, kritik bulgular kapatıldı. Sırasıyla: sızmış
`SECRET_KEY` rotasyonu, katalog auth + veri izolasyonu, Excel içe aktarmanın
sağlamlaştırılması, tutarlılık/arayüz temizliği, CSRF koruması, fiyat–birim–veri tipi
düzeltmeleri. **144 test geçiyor** (oturum başında sıfır test vardı).

`main` push edilmiş durumda, unpushed commit yok.

## ⚠️ Yarın ilk iş: kablo parametreleri
Erce gerçek tedarikçi kataloglarını ve aşağıdaki soruların cevaplarını getirecek.
**Cevaplar gelmeden ayrıştırıcı yazma** — tahminle yazılan parser ilk farklı dosyada kırılır.

### Sorun
`technical_specs` tek bir uzun metin ve içindeki parametreler ayrıştırılmamış:
```
PVC İzoleli, Kılıfsız, Tek Damarlı, Tek Telli Bakır İletkenli | TS EN 50525-2-31 | CPR: Eca | 2.5 mm² | Ambalaj: R100
```
Sonuçları: (a) kesit sayı olmadığı için `2.5–6 mm² arası` gibi filtre yapılamıyor,
"3x2.5 bakır" gibi sahada konuşulan ifadeyle bulunamıyor; (b) ürün adı
`marka + technical_specs + kategori` olarak derlendiği için liste okunmuyor;
(c) `Ambalaj: R100 / M1000` bilgisi tamamen görmezden geliniyor (M1000 = 1000 m makara,
fiyat birimiyle ilişkili olabilir).

### Önerilen çözüm (Erce onaylarsa)
`technical_specs` metni korunur, karar veren parametreler ayrı kolonlara çıkarılır:
`cross_section` (Numeric, mm²) · `core_count` (Integer) · `conductor` (bakır/alüminyum) ·
`insulation` (PVC/XLPE) · `sheathed` (Boolean). İçe aktarmada bir ayrıştırıcı bunları
metinden çıkarır, çıkaramadığı satır sayısını Excel özetindeki gibi raporlar.
Ürün adı kısaltılır (`Öznur NYA 2.5 mm² Bakır`), uzun metin ayrı sütunda kalır.

Ayrı kolon tercih edildi (EAV veya JSON değil): alanlar az sayıda, sayısal ve aralık
sorgusu istiyor; index'lenebilir ve okunur kalıyor.

### Erce'den beklenenler
1. **3-5 gerçek tedarikçi Excel'i** — özellikle Öznur dışı ve düzensiz olanlar. En kritik olan bu.
2. **Sahada kullanılan arama ifadeleri** — müşteri "3x2.5 NYY" mi diyor, "5x16 bakır" mı?
3. **Kablo dışı ürünlerde ayırt edici parametreler** (anahtar/priz/sigortada amper, kutup
   sayısı, IP sınıfı) — aynı yapı onlara da kurulsun mu, şimdilik sadece kablo mu?

## Veri durumu
- **Eski 66 ürün silindi** (Erce'nin kararı: birimlerinin metre mi km mi olduğu artık
  hatırlanmıyordu, yarın gerçek kataloglar yüklenecek). Silmeden önce
  `yedek_urunler_2026-07-26.csv` olarak dışa aktarıldı — proje kökünde, git'e dahil değil
  (`.gitignore`'da `yedek_*.csv`).
- Boş kalan `Kablo` kategorisi (id=1, user_id=1) duruyor. Gerçek kataloglar yüklenirken
  gerekirse silinir.
- DB'de 3 kullanıcı var.

## Bu oturumda kapatılanlar
- **SECRET_KEY sızıntısı (kritik).** Rotasyona sokuldu, `.env.example` placeholder oldu.
  `.env` git geçmişinde hiç yok. Railway trial bitmiş, canlı değil — **canlıya çıkarken
  `SECRET_KEY` ve `COOKIE_SECURE=true` ortam değişkeni olarak verilmeli.**
- **Katalog auth'suzdu ve izolasyonsuzdu.** `require_user` dependency'si eklendi: koruma
  route imzasında, gövdede değil, unutulamaz. `user_id=1` hardcode'u ve IDOR kapatıldı;
  sahiplik zinciri `user_products` / `get_owned_product` / `get_owned_category`'de toplandı.
- **Excel içe aktarma.** Uzantı/boyut/boş dosya kontrolü, bozuk dosyada 500 yerine mesaj,
  sonuç özeti, tek commit (yarım içe aktarma yok), aynı dosyadaki mükerrerler.
- **CSRF koruması.** Çift gönderim; doğrulama uygulama geneli dependency olduğu için
  route'a eklemek gerekmiyor. Token httpOnly cookie'de, şablona sunucu basıyor,
  HTMX tarafı `base.html`'deki tek `hx-headers` ile çözüldü.
- **Fiyat ayrıştırma.** `1.200` → 1,2 (1000 kat sapma), `1.200.000` → okunamıyor,
  `1,200.50` → 1,2005 hatalarının üçü de düzeltildi. `float` yerine `Decimal`.
- **Birim.** KM → metre dönüşümü satır bazlı oldu. Satır `KM` diyorsa kutucuk işaretsiz
  olsa da çevriliyor; adet bazlı satırlar kutucuk işaretliyken bile bölünmüyor.
  `MT`/`mt.`/`metre` tek biçime getiriliyor. **"Milyon TL" probleminin kaynağı buydu.**
- **Para veri tipi.** `Numeric(10,2)` → `Numeric(12,4)` (migration `a096f2c15539`).
  İki ondalıkta KM fiyatı metreye bölününce ucuz malzeme `0,00`'a yuvarlanıyordu.
  Kolon sınırını aşan değer artık 500 yerine raporlanıyor.
- **Tutarlılık.** `customers.py` da `require_user` kalıbında; gezinme `base.html`'e taşındı;
  ana panel gerçek sayıları gösteriyor; `Jinja2Templates` tek nesnede (`app/templating.py`)
  ve `fiyat` filtresi orada; ölü kod (`schemas.py`, kök `main.py`) silindi.

## Sırada (kablo işinden sonra)
1. **G7 — parola politikası ve e-posta doğrulaması yok.** Tek karakterlik parola kabul ediliyor.
2. **G6 — `python-jose` bakımsız**, bilinen CVE'leri var. `PyJWT`'ye geçiş küçük iş.
3. **Y2 — kategori silme/düzenleme yok.**
4. **T6 — `vat_rate`** modelde ve ekleme formunda var, listede görünmüyor, güncellemede yok.
5. **T7 — `Customer.balance`** modelde var, hiçbir yerde kullanılmıyor.
6. **T8 — migration zinciri kirli** (iki boş `pass` migration, adı işini anlatmayan bir tane).
7. **T10 — Tailwind CDN'den çekiliyor**, üretim için önerilmiyor.
8. **Y4 — teklif/fatura modülü** yok; ana panelde placeholder duruyor.

## Test durumu
`uv run pytest` → 144 test. Bellekte SQLite ile koşuyor, PostgreSQL gerekmiyor.
- `test_catalog_isolation.py` — erişim kontrolü + IDOR
- `test_customers_isolation.py` — müşteri izolasyonu
- `test_csrf.py` — CSRF (token'sız/yanlış token/form alanı/şablona basılma)
- `test_excel_import.py` — mükerrer, bozuk girdi, boş satır
- `test_units.py` — KM dönüşümü, birim normalleştirme, kolon sınırı
- `test_parse_price.py` — fiyat ayrıştırma ve Türkçe gösterim
- `test_home.py` — ana panel sayıları, gezinme

## Açık sorular / kararlar
- Kablo parametreleri: yukarıdaki üç madde.
- Teklif/fatura modülü yeni bir router mı, katalog altında mı?
- `Customer.balance` kalacak mı, kaldırılacak mı?

## Öğrenilenler
| Konu | Ne öğrenildi | Tarih |
|---|---|---|
| Sır yönetimi | `.env.example` bir şablondur, gerçek değer taşımaz. | 2026-07-25 |
| Auth tasarımı | Yetkisizde `None` dönen dependency, korumayı her route'ta elle yazmayı zorunlu kılar; bir yerde unutulunca açık oluşur. Doğrusu hata fırlatan zorunlu dependency: koruma imzada durur. | 2026-07-26 |
| Sahiplik zinciri | Ürünün `user_id`'si olmadığı için her sorgu `join(Category)` ister. Tek yardımcıya toplamak açığın tekrar açılmasını engelliyor. | 2026-07-26 |
| Testin anı | Çalışan koda dokunmadan önce test yaz. `customers.py` refactor'ü bu sırayla yapıldı. | 2026-07-26 |
| Fixture zinciri | Test fixture'ı, test edilen korumayı sessizce sağlayabilir. CSRF testleri `login_as` üzerinden token'ı da alıyordu; `raw_client`'a ayrıldı. | 2026-07-26 |
| Ayrıştırma kararı | `parse_price` "anlamadım" için `None` döner; 0 mı yazılacak eski değer mi korunacak kararı çağırana ait. Kararı fonksiyonun içine gömmek iki farklı kopya doğurmuştu. | 2026-07-26 |
| Para tipi | Para `float` ile tutulmaz; `Decimal` + `Numeric`. Ondalık basamak sayısı da bir tasarım kararı: 2 basamak KM→metre bölümünde veriyi siliyordu. | 2026-07-26 |

## Vault özeti (Olric'e taşınacak)
Elektrotakip denetimi tamamlandı ve tüm kritik/yüksek bulgular kapatıldı: sızmış JWT
anahtarı rotasyonu, katalogun auth ve veri izolasyonuna bağlanması (IDOR dahil), CSRF
koruması, Excel içe aktarmanın sağlamlaştırılması. Fiyat ayrıştırmada 1000 kat sapmaya
yol açan hata ve "milyon TL" şikâyetinin kaynağı olan KM/metre birim karışıklığı
düzeltildi; para kolonu `Numeric(12,4)`e çıkarıldı. Proje sıfırdan 144 teste ulaştı.
Sıradaki iş kablo parametrelerinin yapılandırılması — Erce gerçek tedarikçi kataloglarıyla
dönecek.
