@/Users/erce/.claude/thufir/IDENTITY.md

# Proje: Elektrotakip

## Ne bu
**Elektrik malzemecileri için teklif hazırlama aracı.** Katalog, stok ve müşteri kaydı
arkada durur; satın alınan şey tekliftir.

Çözdüğü acı, ilk müşterinin kendi cümlesiyle: *"müşteri bir işi sorduğunda Excel açıp
uzun hesap yapmam gerekiyordu, iskontosu vergisi işçiliği."*

⚠️ **Bu bir portföy projesi değil.** Erce'nin gelir hedefinin tek ayağı ve tarihli:
Ağustos motor, Eylül canlıya çıkış, **Ekim satış ayı.** Oyuncak değil, ciddiye al.
Ürün tanımı 08.08.2026'da değişti — ayrıntı ve kapsam kararları `PROGRESS.md` başında.

## Stack
FastAPI 0.137 · SQLAlchemy 2 · Alembic · PostgreSQL · Jinja2 + HTMX
JWT (httpOnly cookie) · bcrypt · uv (paket yönetimi) · Railway (deploy)

## Yapı
```
app/
├── main.py, config.py, database.py, security.py
├── dependencies.py, csrf.py, templating.py
├── quote_engine.py   → teklif hesap motoru (saf, DB bilmez)
├── quote_service.py  → ORM ↔ motor köprüsü
├── excel_import.py   → tedarikçi dosyası ayrıştırma (saf, DB bilmez)
├── models/    → user, customer, catalog (Category + Product), quote
├── routers/   → auth · catalog · customers   (teklif router'ı HENÜZ YOK)
└── templates/ → base, home, login, register, catalog, customers, partials/
alembic/       → migration'lar
```

## Kodun kökeni — okurken bunu bil
Bu proje büyük ölçüde **tarayıcıdan AI'ya sorulup kopyala-yapıştır** ile yazıldı.
Sonucu: parçalı yapı, bölümler arası tutarsız kalite, Erce'nin kendisinin de tam
okumadığı kod parçaları.

Pratik anlamı: **mevcut kodun arkasında bir niyet olduğunu varsayma.** Tuhaf gördüğün
bir şey bilinçli bir tasarım kararı değil, büyük ihtimalle başka bir bağlamdan
yapıştırılmış bir parça. Aşağıdaki "tasarım kararları" bölümü doğrulanmış olanları
listeler; onun dışında kalan her şey şüpheli sayılır.

Buna karşılık gördüğün her sorunu sessizce düzeltme. Önce listele, Erce önceliklendirsin.
Amaç kodun temizlenmesi kadar Erce'nin kendi projesini tanıması.

## Bilmen gereken tasarım kararları
- **Sahiplik zinciri:** `Product`'ın `user_id`'si **yok**. Sahiplik `Category` üzerinden
  gelir. Ürün sorguları `join(Category).filter(Category.user_id == current_user.id)`
  şeklinde olmalı. Bu bir eksiklik değil, bilinçli model.
- **Doğru kalıp `customers.py`'da.** Her route'ta auth kontrolü ve
  `filter(user_id == current_user.id)` izolasyonu var. Yeni modül yazarken şablon budur.
- **Teklif hesabı `quote_engine.py`'dan çıkmaz.** Motor bilinçli olarak DB/ORM/HTTP
  bilmiyor: girdi dataclass, çıktı dataclass. Sebebi bu projenin geçmişi — denetimde
  çıkan ciddi hataların hepsi hesap tarafındaydı ve arayüzden görünmüyordu. Route'a veya
  şablona hesap yazma; `quote_service.py` sadece çeviri yapar, kural içermez.
- **Hesap zinciri sabit formül değil, sıralı `QuoteAdjustment` listesi.** İskonto önce mi
  işçilik önce mi sorusunun cevabı işletmeye göre değişiyor. Yeni işletme kod değil ayar
  istesin. Sıra `position`'dan gelir.
- **Teklifte fiyat ve kur dondurulur**, katalogla canlı bağ kurulmaz. Kablo fiyatı bakıra
  ve dolara endeksli, günlük oynuyor; bağ kurulsaydı geçmiş teklifler kendiliğinden
  bozulurdu. Aynı gerekçeyle varsayılan iskonto zincirleri de **kopyalanır, bağlanmaz.**
- **Tedarikçi dosyası ayrıştırma `excel_import.py`'da**, router'da değil. Başlık satırını
  ve sütun adlarını kendisi tanır; sabit sütun sırası varsayma. Davranışların hepsi
  `tests/fixtures/tedarikci_listeleri/` altındaki **11 gerçek dosyadan** ölçüldü ve
  `test_supplier_files.py` ile sabitlendi. Ayrıştırmaya dokunacaksan önce o testleri koştur —
  uydurma fixture'la doğrulanmış sayma. Korunması gereken davranışlar: KM bazlı fiyatı
  metreye çevirme, Türkçe `1.200,50` ayrıştırma, mükerrer atlama, bölüm başlığını ürün
  saymama, üç para birimini çözme.
- **Sütun adı eşleştirmesi kelime bazlı olmalı, alt dize değil.** `"ad" in "ADET"` doğrudur
  ama istenen şey değildir; bu hata bir dosyada 699 ürünü sessizce attırmıştı.

## Kurallar
- Paket işlemleri `uv` ile (`pip` değil).
- Şema değişikliği = Alembic migration. Elle DB'ye dokunma.
- `.env` asla commit edilmez, içeriği loglanmaz.
- `git push` sormadan yapılmaz. Remote: `github.com/Erce17/elektrotakip`
- Test altyapısı (pytest + httpx) kurulu ama hiç test yok. Yeni yazdığın kritik
  mantığa test ekle.

---
Durum ve devam noktası için **PROGRESS.md**'yi oku.
