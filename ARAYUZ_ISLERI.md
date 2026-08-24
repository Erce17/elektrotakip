# Arayüz işleri — 24 Ağustos 2026

Taslak: https://claude.ai/code/artifact/f95bb18f-2713-4747-b487-c5957da7c766
Yedi ekranın önce/sonra karşılaştırması. Önizlemeler gerçek HTML, "Tam boyut" ile 1:1 açılıyor.
Kaynak dosyalar: `~/Documents/ErceOS/.design/elektrotakip/` (her ekran ayrı `.dc.html`).

## Kural

Palet ve bileşen sözlüğü **değişmiyor**: aynı slate/blue ailesi, aynı `rounded-xl`, aynı
`shadow-sm`, sistem fontu. Bu bir yeniden tasarım değil. Değişen şey yerleşim, yoğunluk
ve hiyerarşi.

Taslakta uydurulmuş veritabanı alanı yok. "Sonra" ekranlarında görünen her şey mevcut
modelden geliyor (geçerliliğe kalan gün, kalem sayısı, müşterinin varsayılan iskonto
zinciri). Yeni migration gerektiren bir öneri yok.

## ŞİMDİ — gösterim engelleri ✅ tamamlandı (24.08.2026)

Dördü de yapıldı, 502 test geçiyor. Aşağıdaki tanımlar kayıt için duruyor; her
maddenin altında ne yapıldığı yazıyor.

Akrabaya ilk gösterim bunlardan sonra yapılacak. Tahmini yarım gün.

### 1. Kalem satırları salt okunur olsun ⭐ en önemli
`app/templates/partials/quote_body.html` — şu an her kalem satırından sonra ikinci bir
`<tr>` geliyor ve içinde beş kutuluk düzenleme formu **sürekli açık** duruyor. 15 kalemlik
teklifte ekranda 15 form, ~90 kutu var. Ekranı kullanılamaz yapan tek başına bu.

Desen zaten repoda çalışıyor: `app/templates/partials/catalog_rows.html:28` satırdaki
kalem ikonu `hx-get="/catalog/product/{id}/edit"` ile satırı düzenleme satırıyla
değiştiriyor (`catalog_edit_row.html`). Aynısı teklif kalemleri için kurulacak:
satır salt okunur, tıklanınca **tek satır** açılır, Kaydet / Vazgeç / Sil.

Aynı anda birden fazla satır açık olmasın.

> **Yapıldı.** Katalogdaki `closest tr` takası yerine açık kalem gövdenin bağlamında
> tutuluyor (`duzenlenen`): `GET /quotes/{id}/items/{item_id}/edit` gövdeyi o satır
> açık, `GET /quotes/{id}/body` kapalı döndürüyor. Sebep: kalem değişince toplam ve
> zincir de değişiyor, gövde zaten tek parça dönüyor — satır bazlı takas ikinci bir
> tazeleme yolu açardı ve iki satırı birden açık bırakabilirdi. Satırda kalem ikonu,
> açık satırda Kaydet / Vazgeç / Sil.

### 2. Genel toplam görsel olarak öne çıksın
`quote_body.html` toplamlar bölümü. Şu an genel toplam `text-lg font-bold`, yani "Para
Birimi" seçicisiyle neredeyse aynı ağırlıkta. Taslakta koyu blok içinde, 24px.

> **Yapıldı.** Tablodan çıkarıldı, altına `bg-slate-800` blok içinde `text-2xl`.

### 3. Hesap zinciri ekleme formu düğme arkasına
`quote_body.html` — zincir tablosunun altındaki yedi alanlı form (`kind`, `value`,
`label`, `scope`, `base`, `added_kind`, `vat_rate`) sürekli açık. "Adım ekle" düğmesi
olsun, tıklayınca açılsın. Alanlar ve davranış aynı kalıyor, sadece varsayılan kapalı.

> **Yapıldı.** `<details>` + "Adım ekle" özeti; bu ekranda JavaScript yok, açılır
> kapanır davranış için ek bağımlılık istemedi.

### 4. Müşterilerden `Bakiye` sütunu kalksın
`app/templates/partials/customer_rows.html` ve `customers.html`. `Customer.balance`
20 Ağustos'ta v1 kapsamından çıkarıldı ama sütun ekranda duruyor ve hepsi 0,00 görünüyor.
Gösterimde "burası ne" sorusu gelir ve cevabı yok.

Model alanını silme, sadece ekrandan kaldır (v2'de geri gelebilir).

> **Yapıldı.** `Customer.balance` modelde duruyor. Sütun boş bırakılmadı, adrese
> verildi: düzenleme satırı (`customer_edit_row.html`) zaten adres alanını taşıyordu,
> sütun sayısı da böyle örtüşüyor.

## SONRA — ilk gösterimden gelen geri bildirimden sonra

Bunlara şimdi girme. Hangi ekranın yeniden yazılacağını geri bildirim belirleyecek.

- Teklif ekranında sol sütundaki üç kartın dağıtılması ve sağ rayın kurulması
  (kalem ekleme aramaya, işçilik düğmeye, teklif bilgileri başlık çubuğuna)
- Ürün aramasının ayrıştırdığı parametreleri chip olarak göstermesi
- Katalog ve müşteri ekranlarında formların dialoga taşınması
- Katalogda "fiyatı 0" filtresi
- Ana panelin kalıp kalmayacağı
- Teklif çıktısına firma künyesi, kalem numarası, kaşe alanı
- Tailwind CDN'in çıkarılması (T10, v2'ye alınmıştı)

## Bunu değiştirebilecek şey

Akrabaya sorulacak altı sorunun cevapları bekleniyor. İkisi doğrudan bu ekranı etkiler:

- **İskonto müşteriye göre sabitse** kalem satırındaki iskonto kutusu oradan kalkar,
  müşteri seçilince gelir.
- **İşçilik metraj başına birim fiyatla hesaplanıyorsa** işçilik kalemi ayrı bir giriş
  biçimi ister.

Cevaplar gelmeden 1-4 maddeleri yapılabilir, ikisi de bu sorulardan bağımsız.
