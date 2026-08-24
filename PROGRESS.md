# PROGRESS — Elektrotakip

> Thufir bu dosyayı her oturum sonunda üzerine yazar. Oturum açılışında **önce burası okunur.**

**Takvim: Ağustos motor · Eylül canlıya çıkış · Ekim satış ayı.** Kayma lüksü yok.

---

## Son oturum
**Tarih:** 2026-08-24 (Thufir)
**Yapılan:** İki iş. (1) `ARAYUZ_ISLERI.md`'deki **"ŞİMDİ — gösterim engelleri"** dördü de
kapatıldı. (2) **Güvenlik borcu kapatıldı** — G6, G7 ve denetimde çıkan dört madde daha.
Commit `2adb57d` → `6331406`.
**Test:** 531 geçiyor (33 yeni test).

> ⚠️ **Push edilmedi** — `3276966`'dan `6331406`'ya kadar yerelde bekliyor.

### Güvenlik borcu — kapandı

| Açık | Ne yapıldı |
|---|---|
| **G6** `python-jose` bakımsız, CVE'li | `PyJWT`'ye geçildi. Algoritma `decode`'da açıkça veriliyor (`alg: none` ve HMAC/RSA karıştırma kapalı), `exp` zorunlu — süresiz token geçmiyor |
| **G7** parola politikası yok | En az 10 karakter; bcrypt'in 72 bayt sessiz kırpması açıkça reddediliyor. Karakter çeşidi **dayatılmıyor** — büyük harf+rakam+sembol kuralı pratikte `Parola1!` üretiyor, uzunluk aynı işi daha dürüst yapıyor |
| Girişte deneme sınırı yoktu | Hesap bazlı 5/15dk, IP bazlı 20/15dk, kayıt 5/saat. Kilit **doğrulamadan önce** bakılıyor, yoksa sınır kaba kuvveti durdurmuyor |
| E-posta normalize edilmiyordu | `Ali@X.com` ile `ali@x.com` iki ayrı hesap oluyordu ve kullanıcı kaydolduğu adresle giriş yapamıyordu |
| Kullanıcı var/yok zamanlamadan sızıyordu | Kullanıcı yokken de bir kukla bcrypt doğrulaması koşuyor |
| Güvenlik başlığı yoktu | `X-Frame-Options: DENY` (clickjacking), `nosniff`, `Referrer-Policy`, HTTPS'te HSTS |
| Zayıf `SECRET_KEY` mümkündü | 32 karakterden kısa veya örnek değer uygulamayı açtırmıyor |
| `logout` cookie'leri bırakıyordu | `access_token` ve `csrf_token` kurulumdaki niteliklerle siliniyor |

**Bilerek yapılmayanlar — ikisi de karar bekliyor:**
- **E-posta doğrulaması (G7'nin ikinci yarısı).** Gönderim servisi seçimi Erce'nin;
  onsuz sahte adresle kayıt mümkün.
- **CSP başlığı.** Tailwind CDN'den çekildiği ve satır içi stil kullanıldığı sürece
  konulacak CSP ya ekranı bozar ya `unsafe-inline` ile anlamsız olur. T10 (CDN'in
  çıkarılması) yapıldığında `app/main.py`'daki başlık middleware'ine eklenmeli.

**Deneme sayacının kabul edilmiş zayıflığı:** süreç belleğinde duruyor. Süreç yeniden
başlarsa sıfırlanır, birden fazla instance açılırsa her biri kendi sayacını tutar.
İkincisi olduğu gün paylaşılan sayaca (Redis) taşınmalı — `app/rate_limit.py` başında
yazılı.

### Bu oturumda ne değişti

1. **Kalem satırları salt okunur.** Her kalemin altında sürekli açık duran beş kutuluk
   form kalktı (15 kalemlik teklifte ~90 kutu ediyordu). Satırda kalem ikonu var;
   `GET /quotes/{id}/items/{item_id}/edit` gövdeyi o satır açık, `GET /quotes/{id}/body`
   kapalı döndürüyor. Açık satır **gövdenin bağlamında** (`duzenlenen`) tutuluyor, bu
   yüzden aynı anda birden fazla satır açılamıyor. Katalogdaki `closest tr` takası
   seçilmedi: kalem değişince toplam ve zincir de değişiyor, gövde zaten tek parça
   dönüyor — satır takası ikinci bir tazeleme yolu açardı.
2. **Genel toplam** tablodan çıkıp koyu blok içinde `text-2xl` oldu.
3. **Zincir ekleme formu** `<details>` arkasına alındı; ekranda JavaScript yok, ek
   bağımlılık gerekmedi.
4. **Müşteri listesindeki `Bakiye` sütunu** kalktı (v1 kapsamı dışı, hepsi 0,00
   görünüyordu). Model alanı duruyor. Sütun boş bırakılmadı, adrese verildi —
   `customer_edit_row.html` zaten adres alanını taşıyordu, sütunlar böyle örtüşüyor.

**Sıradaki adım: akrabaya ilk gösterim.** `ARAYUZ_ISLERI.md`'nin "SONRA" başlığındaki
işlere gösterim geri bildirimi gelmeden girilmeyecek; hangi ekranın yeniden yazılacağını
o belirleyecek. Altı sorunun ikisi (müşteriye sabit iskonto, metraj başına işçilik)
teklif ekranını doğrudan etkiliyor.

---

## Önceki oturum
**Tarih:** 2026-08-21/22 (Thufir)
**Yapılan:** Beş iş: **teklif motoru**, **içe aktarma**, **teklif ekranı**, **ürün arama**,
**şablon güçlendirme.** Commit `de10755` → `3276966`.
**Test:** 498 geçiyor (oturum başında 144).

> ⚠️ **Push edilmedi** — `3276966` ve `9baabad` yerelde bekliyor.

> **Ağustos'un üç haftalık planı kapandı.** 08.08'de "1. hafta motor, 2. hafta ekran,
> 3. hafta katalog + kablo parametreli arama" denmişti; dördü de bitti.
> **Kalan: güvenlik borcu + canlıya çıkış + gerçek kullanıcıyla deneme.**

### Ne kuruldu

| Dosya | İş |
|---|---|
| `app/quote_engine.py` | Saf hesap katmanı. DB/ORM/HTTP bilmez, girdi-çıktı dataclass |
| `app/quote_service.py` | ORM ↔ motor köprüsü. Hesap mantığı burada değil |
| `app/models/quote.py` | `Quote` · `QuoteItem` · `QuoteAdjustment` · `QuoteDefaults` |
| `app/excel_import.py` | Tedarikçi dosyası ayrıştırma. Saf, DB bilmez |
| `app/product_search.py` | Parametre ayrıştırma + arama. Saf, sahiplik filtresini bilmez |
| `app/routers/quotes.py` | Teklif ekranı. Route'ta tek bir çarpma yok |
| `alembic/.../2bd390383d15` | Teklif tabloları. Postgres'te upgrade→downgrade→upgrade doğrulandı |
| `alembic/.../254add4c7164` | Ürün parametre kolonları. Hepsi nullable |

| Test dosyası | Kapsam |
|---|---|
| `test_quote_engine.py` | 36 — iş kuralları, fixture'sız |
| `test_quote_model.py` | 19 — model, köprü, kısıtlar |
| `test_supplier_files.py` | 118 — 11 gerçek tedarikçi dosyası |
| `test_quotes_router.py` | 37 — erişim kontrolü, kalem/zincir akışı |
| `test_quotes_output.py` | 31 — çıktı, revizyon, varsayılanlar |
| `test_product_search.py` | 80 — parametre ayrıştırma, yanlış pozitifler, arama |
| `test_template_import.py` | 35 — şablon, şablonla içe aktarma, KDV |

### Motorun tasarım kararları (bunlar artık kod)

1. **Hesap zinciri sabit formül değil, sıralı satır listesi.** `QuoteAdjustment`:
   tipi (`iskonto_yuzde`/`iskonto_tutar`/`ek_yuzde`/`ek_tutar`), tabanı, kapsamı ve
   `position`'ı olan tek bir adım. Sıra sonucu değiştirir; motor sırayı düzenlemez.
2. **Zincirli iskonto çarpımsal.** %20 sonra %10 → 720, 700 değil. Test sabitledi.
3. **Genel iskonto ara toplamda beklemez**, etkilediği kalemlere orantılı dağıtılır
   (largest remainder — kuruş kaybı yok, kalem toplamı her zaman teklif toplamını verir).
   Sebebi GİB: KDV satır bazında hesaplanır ve satır bazında yuvarlanır.
4. **`Decimal` + `ROUND_HALF_EVEN`** her yerde.
5. **Fiyat ve kur teklif anında dondurulur.** Kalemde `source_currency` +
   `source_unit_price` + `fx_rate` + çevrilmiş `unit_price` birden durur. Katalogla
   canlı bağ yok — testle sabitlendi (`test_katalog_fiyati_degisince_teklif_degismez`).
6. **`QuoteItem.discountable`** — işçilik iskontoya girmesin diye. Tür değil bayrak
   karar veriyor; "girmez" bir varsayılan, kural değil.
7. **Varsayılan/istisna ayrımı:** `QuoteDefaults` (işletme) + `Customer.default_adjustments`
   (müşteri). İkisi de **şablon**: teklife kopyalanır, bağlanmaz. Sonradan değişince
   geçmiş teklif bozulmaz.
8. **`QuoteAdjustment` tek tabloda iki yerde:** `quote_item_id` dolu → kalem zinciri,
   `quote_id` dolu → teklif seviyesi. CHECK kısıtı tam olarak birinin dolu olmasını zorluyor.
9. **Revizyon:** `version` + `parent_quote_id`. `(user_id, number, version)` unique.
   Revizyon eskisini değiştirmez, yan yana durur.

### Yan değişiklikler
- `Product.currency` (TRY/USD/EUR) ve `Product.supplier_code` eklendi.
- `Customer.default_adjustments` (JSON şablon) eklendi.
- Migration'da elle düzeltilen iki şey: dolu tabloya NOT NULL kolon için
  `server_default`, ve yabancı anahtar index'leri. Autogenerate ikisini de kaçırır.

### ⚠️ Bilerek yapılmayanlar
- **Router ve ekran yok.** Bugünün kapsamı model + hesap katmanıydı.
- **Bileşen (anahtar/priz) hesaba girmiyor.** `QuoteItem.parent_item_id` alanı duruyor
  ama `quote_service.hesapla` bileşen satırlarını atlıyor —
  `test_bilesen_kalemi_ayri_satir_olarak_toplanmaz` bunu sabitliyor. Karar gelince
  bilinçli olarak değiştirilecek.
- **Kalem seviyesinde tutar iskontosu** motora girmiyor (yalnız yüzde). Tabloda alan var.
- **Kademeli iskonto** (miktar eşiği + oran tablosu) yok. Zincir satırı olarak sonradan
  eklenebilir, model buna kapalı değil.
- **Tevkifat** v1 kapsam dışı (karar 08.08).

---

# PAKET A — içe aktarma (21.08, bitti)

Eski akış "tedarikçi dosyası aktar" değil **"bizim şablonu doldur"**du: sabit sütun
sırası (0,1,2,3,4), `workbook.active` ile tek sheet, openpyxl olduğu için `.xls` yok.

**`app/excel_import.py`** — saf ayrıştırma katmanı, DB/ORM/HTTP bilmez. Router artık
yalnızca kayıtları ürüne çeviriyor ve mükerrer/sahiplik kurallarını uyguluyor.

| Sorun | Çözüm | Ölçüm |
|---|---|---|
| Başlık satırı sabit değil | Puanlayarak bulunuyor | 1. (6 dosya), 2. (Sezgin, Tense), 3. (Kael), 5. (Erse) satır |
| Sütun adları çeşitli | Addan tanıma + kelime bazlı gevşek eşleşme | kod 7, fiyat 6 farklı isim |
| Fiyat sütunu tarihle adlandırılıyor | Türkçe ay adı + yıl kalıbı | `2026 ŞUBAT`, `2024 KASIM LİSTE FİYATI` |
| `.xls` açılamıyor | `xlrd` eklendi | Kael gerçek BIFF8 |
| Tek sheet okunuyordu | Tüm sayfalar | Grup Arge 10, Molwex 2, Erse 2 |
| Fiyatsız sayfa | Atlanıyor **ve adıyla raporlanıyor** | Molwex 'Tüm Kodlar' |
| Bölüm başlıkları ürün sayılıyordu | Fiyat hücresi boşsa başlık | Kael, Sezgin, Tense, Grup Arge |
| Para birimi | Üç yoldan çözülüyor | ayrı sütun · `TL/km` içinden · 'BİRİM' diye açılmış USD sütunu (Sezgin) |
| Kimliksiz satır | Ürün sayılmıyor | Viko'da PDF çevrim artığı |

**Sonuç: 11 dosyanın 11'i okunuyor, ~13.600 satır.** Mükerrer tespiti artık tedarikçi
koduna dayanıyor (`Product.supplier_code`); kod yoksa eski kalıba (özellik + marka) düşüyor.
Kategori seçimi: grup sütunu → sayfa adı → `Diğer`. `Sayfa1` gibi Excel'in kendi verdiği
adlar elenir.

### İki hata testlerle yakalandı — ikisi de sessiz veri kaybıydı
1. **Alt dize eşleşmesi felaketti.** `'ADET'` içinde `"ad"`, `'Turuncu'` içinde `"urun"`,
   `'KODLAMA MALZEMESİ'` içinde `"kod"` geçiyor. Molwex'te **699 ürün** başlık sanılıp
   atılmıştı. Eşleşme kelime bazlı olunca düzeldi.
2. **Ürün adı boş = bölüm başlığı sanmak.** Viko'da **822 satırın** adı boş ama fiyatı
   geçerli. Ayırt edici ölçüt ad değil, fiyat hücresinin sayıya çevrilebilmesi.

### Bilerek yapılmayanlar
- ~~Kablo parametreli ayrıştırma yok~~ → ✅ aynı oturumda yapıldı, aşağıya bak.
- ~~Şablon 5 sütun, ham dosyadan zayıf~~ → ✅ 22.08'de düzeltildi, aşağıya bak.
- **Marka sütunu gerçek dosyalarda yok.** Alan tanınıyor ama 11 dosyanın hiçbirinde
  geçmiyor; ürünlerin `brand`'i boş kalıyor.
- **İki seviyeli paketleme** (`Kutudaki Adet` + `Kolideki Adet`) okunuyor ama ürüne
  yazılmıyor — modelde karşılığı yok.
- **Ruff'ta 4 uyarı duruyor**, ikisi boş `pass` migration'da (T8, v2'ye kesildi).
  Fixture'daki tek seferlik PDF script'leri `pyproject.toml`'da ruff'tan hariç tutuldu.

---

# TEKLİF EKRANI (21.08, bitti)

**`app/routers/quotes.py`** — route'ta tek bir çarpma yok. Hesabın tamamı
`quote_engine`'de kalıyor; ekran sadece giriş alıp motorun çıktısını gösteriyor.
Kalıp `customers.py`'dan: koruma route imzasında, izolasyon her sorguda.

| Ekran | İş |
|---|---|
| `/quotes` | Liste + teklif açma. Toplamlar motordan |
| `/quotes/{id}` | Kalem ekleme (katalogdan/elle), zincir düzenleme, canlı toplam |
| `/quotes/{id}/print` | Yazdırılabilir çıktı |
| `/quotes/settings` | İşletme varsayılanları + varsayılan zincir şablonu |

### Kararlar
- **Teklif numarası otomatik** (`2026-001`), kullanıcı içinde tekil, revizyonlar aynı
  numarayı paylaşıyor. Boşluk aranıyor — sayaç tutmaktan basit ve silinen numarayı
  geri kazandırıyor.
- **İskonto zinciri tek kutuya `20/10` yazımıyla giriliyor.** Sektörde böyle
  konuşuluyor ("yirmi bölü on"); her kademe için ayrı kutu doldurmak yavaşlatırdı.
- **Zincir sırası ekranda ↑↓ ile değiştirilebiliyor** ve her adımın tabanı + etkisi
  satır satır gösteriliyor. "Bu rakam nereden çıktı" sorusu cevaplanabilmeli.
- **Her mutasyon gövdenin tamamını yeniden çiziyor** (`partials/quote_body.html`).
  Bir kalemin iskontosu teklifin toplamını da değiştiriyor; kısmi güncellemede biri
  unutulunca ekranda yanlış rakam kalırdı.
- **Motor çıktısı ↔ DB kalemi eşleştirmesi router'da açık** (`kalem_ciftleri`),
  şablonda indeks sayılmıyor. `quote_service.hesaba_giren_kalemler` filtreyi tek
  yerde tutuyor.
- **Yazdırma çıktısı `base.html`'i genişletmiyor.** Gezinme kâğıda basılmamalı ve
  Tailwind CDN'i yazdırma anında ağa bağlanıp çıktıyı stilsiz bastırabilir; stil
  dosyanın içinde. **PDF kütüphanesi yok** — tarayıcının "PDF kaydet" akışı yeterli.
- **Revizyon** aynı numarayı taşıyor, versiyonu artıyor, eskisi dokunulmadan duruyor.
  Kalemler dondurulmuş fiyat ve kurla kopyalanıyor: revizyon "aynı işin yeni teklifi",
  fiyat güncellemesi ayrı bir karar.
- **`/quotes/settings` route'u `/{quote_id}`'den ÖNCE tanımlı.** FastAPI yolları tanım
  sırasına göre eşleştiriyor; sonra olsaydı "settings" bir teklif id'si sanılırdı.

### Yakalanan sessiz veri kaybı
**`Quote.revisions` ilişkisinde `delete-orphan` cascade vardı.** 1. sürümü silmek 2. ve
3. sürümü de götürüyordu — kullanıcı eskisini temizlerken en güncel teklifini
kaybederdi. Cascade kaldırıldı: revizyon köksüz kalıyor (`parent_quote_id` NULL) ama
silinmiyor. Revizyon ayrı bir tekliftir, alt kayıt değil.

### Bilerek yapılmayanlar
- **Ürün arama yok.** Katalogdan kalem eklerken ilk 500 ürün bir `select` içinde
  listeleniyor. ✅ **Bu oturumda çözüldü** — aşağıdaki "ürün arama" bölümü.
- **Kur elle giriliyor.** Otomatik kur çekme yok; teklif anında dondurma çalışıyor.
- **Teklif durumu (`status`) kullanılmıyor.** Alan var, ekranda yok — "gönderildi /
  kabul edildi" takibi v1 kapsamında değil.
- **Kalemin sırası değiştirilemiyor** (zincirin sırası değiştirilebiliyor).
- **CSV/Excel dışa aktarım yok.** 08.08'de "entegrasyon kapısı" için istenmişti;
  `supplier_code` taşınıyor ama dışa aktarım yazılmadı.

---

# ÜRÜN ARAMA (21.08, bitti)

**`app/product_search.py`** — saf katman, DB bilmez. Sorgu kurucu SQLAlchemy ifadesi
üretiyor ama **sahiplik filtresini bilmiyor**: onu çağıran koyar, yoksa unutulduğu
yerde açık oluşur.

Teklif ekranındaki ürün seçimi ilk 500 ürünü basan bir açılır listeydi. Artık sahada
konuşulduğu gibi aranıyor:

| Yazılan | Anlaşılan |
|---|---|
| `3x2.5 NYY` | 3 damar + 2,5 mm² + adı NYY'ye uyanlar |
| `5x16 bakır` | 5 damar + 16 mm² + iletken bakır |
| `2.5-6 mm2 nya` | kesit 2,5–6 arası + metin "nya" |
| `OZ-003` | tedarikçi kodu |
| `klemens` | sadece metin |

`Product`'a `cross_section` · `core_count` · `conductor` · `insulation` · `sheathed`
eklendi. **Ayrı kolon** tercih edildi (EAV/JSON değil): alanlar az sayıda, sayısal ve
aralık sorgusu istiyor, index'lenebilir ve okunur kalıyor. Hepsi nullable — çıkarılamayan
parametre NULL kalır ve ürün metinle bulunmaya devam eder.

### Ölçüm ayrıştırıcının şeklini belirledi
- **Çıplak `NxM` kalıbı çoğunlukla YANLIŞ POZİTİF.** Viko'da ürün kodu (`926Y5X01`),
  Klemsan'da kontak değeri (`2x8A/250VAC`) ve fiziksel ölçü (`96x96mm`, `5x20`),
  Tense'de ekran boyutu (`3x20 mm`). Viko'da 532, Klemsan'da 496 satır bu kalıbı
  içeriyor ve **hiçbiri kablo değil.** Kesit yalnızca `mm²` bağlamından ya da dosyanın
  kendi kesit sütunundan okunuyor.
- **Öznur'da kesit ürün adında değil, ayrı `Kesit (mm2)` sütununda** ve sahada konuşulan
  yazımı birebir taşıyor: `4x25`, `2x1.5`, `3x25+16`. O sütun tanındı; `+16` faz dışı
  iletken olduğu için damar sayısına katılmıyor ("3x25+16" sahada üç damarlı).
- **Molwex'te `0.5-1.5 mm²` bir aralık** — pabucun hizmet ettiği kablo aralığı, ürünün
  kendi kesiti değil. Kesit yazılmıyor, `kesit_araligi_mi` ile işaretleniyor.

**Sonuç:** Öznur (kablo tedarikçisi) 1673 satırın 1673'ünde kesit, 1547'sinde damar.
Erse 298 satır. Kablo olmayan altı dosyada **sıfır** kesit uydurulmuyor.

### Yakalanan iki sessiz veri kaybı
1. **`mm\s*[²2]` kalıbı `"mm 200/5"` metninde eşleşiyordu** — Tense'in akım trafosunu
   30 damarlı 10 mm² kablo sanıyordu. Boşluklu biçim artık yalnızca gerçek `²` kabul
   ediyor; bitişik `mm2` güvenli ama ardından rakam gelmemeli.
2. **Mükerrer kimliği parametreleri içermiyordu.** Öznur'un 1673 satırında tedarikçi
   kodu yok ve ürün adı tekrar ediyor; ürünleri ayıran şey kesit. **1614 satır mükerrer
   sanılıp atılıyordu, kablo kataloğu 59 ürüne iniyordu.** Kimliğe `cross_section` ve
   `core_count` girdi → 1505 ayrı ürün.

Ürün adı artık kesiti taşıyor (`... 2x1.5 mm²`) — aynı ad onlarca satırda tekrar edince
liste okunmuyordu.

**`/catalog/reparse-parameters`** — parametre alanları eklenmeden önce aktarılmış
katalogları kurtarma yolu. Yalnızca parametresi boş olanlara dokunur, elle girilmiş
değeri ezmez.

### Bilerek yapılmayanlar
- **Kablo tipi kodu yalıtıma çevrilmiyor.** `NYA`/`NYM` = PVC, `N2XH` = XLPE gibi
  eşlemeler yapılmadı; Öznur'un adlarında PVC/Cu yazmıyor, bu yüzden o dosyada
  iletken/yalıtım boş kalıyor. Metin aramasıyla bulunuyorlar.
- **Kesit aralığı arananla kesişmiyor.** Molwex'in `0.5-1.5 mm²` pabucu "1.5 mm²"
  aramasında çıkmaz. `section_min`/`section_max` kolonları gerekirdi; v1 kapsamında
  değil — kullanıcının ihtiyacı kablo, pabuç aralığı değil.
- **Kablo dışı parametreler yok** (amper, kutup sayısı, IP sınıfı). Aşağıdaki açık soru.

---

# ŞABLON GÜÇLENDİRME (22.08, bitti)

**Bulgu:** Kendi indirilebilir şablonumuz gerçek tedarikçi dosyasından **daha zayıf**
girdiydi. Ham dosyadan kesit, tedarikçi kodu ve para birimi çıkıyordu; 5 sütunluk
şablondan (Kategori · Teknik Özellik · Marka · Birim Fiyat · Birim) hiçbiri çıkmıyordu.

Erce 21.08 gecesi tedarikçi dosyalarını bu şablon biçimine çevirmiş
(`oznur_sablon.xlsx`, `viko_tl_sablon.xlsx`) — kategori ve marka ham dosyadan daha
temiz gelmiş, **ama kesit açıklama metnine çıplak sayı olarak gömülmüş:**
`'H07V-U (NYA) 450/750 V (CPR Class: Eca) 2.5'`. Ölçüldü: **1673 kablonun hiçbiri
kesitle aranamıyordu.**

**Çözüm parser'ı gevşetmek değildi.** Serbest metinde çıplak sayıyı kesit saymak
Viko'da 532, Klemsan'da 496 satırı kablo yapardı. Kesit kendi sütununda olunca başlık
bağlamı garanti ediyor ve `4x25` yazımı güvenli oluyor.

**Şablona dört sütun eklendi:** `Stok Kodu` · `Kesit` · `Para Birimi` · `KDV %`.
Bir test şablonu üreten yer ile okuyan yerin ayrışmadığını sabitliyor.

### Yan işler
- **İçe aktarma KDV'yi okuyor** — T6'nın yarısı kapandı. `%20`, `20`, `0,20` hepsi 20;
  0 ile 1 arası değer kesirli yazım sayılıp yüzle çarpılıyor. Reddetmek `0,10` için
  sessizce %20 yazardı, yani yanlış rakam. Tam `0` meşru (KDV'siz ürün var).
- **Katalog listesi sabit `₺` yazıyordu.** Para birimi artık ürün bazlı — Klemsan
  tamamen EURO veriyor, liste yanlış birim gösteriyordu. Kesit, iletken, yalıtım ve
  KDV de listede görünüyor: kullanıcı içe aktarmanın ne çıkardığını görebilmeli.
- **Öznur PDF çevrimi** (Erce'nin düzeltmesi): kesit bazen `4X25` diye büyük harfle
  geçiyordu, regex yalnızca küçük `x` kabul ediyordu.

### Açık
`tests/fixtures/.../oznur_sablon.xlsx` ve `viko_tl_sablon.xlsx` **eski 5 sütunlu
biçimde ve git'e eklenmedi.** Yeni şablonla yeniden üretilirlerse kesitleri de girer;
ham dosyalar zaten çalıştığı için zorunlu değil. Karar Erce'de.

---

## Sırada

**1. Güvenlik borcu — ✅ 24.08'de kapatıldı.** Kalan tek madde e-posta doğrulaması ve o
Erce'nin servis kararını bekliyor. Canlıya çıkarken hâlâ ortam değişkeni olarak verilmeli:
`SECRET_KEY` (32+ karakter, yoksa uygulama açılmıyor) ve `COOKIE_SECURE=true`.

**2. Canlıya çıkış (Eylül).** Railway trial bitmiş. T10 (Tailwind CDN'den çekiliyor,
üretim için önerilmiyor) v2'ye kesilmişti ama yazdırma çıktısında zaten CDN
kullanılmıyor; teklif ekranı CDN'e bağlı.

**3. Gerçek kullanıcıyla ilk deneme — ARTIK MÜMKÜN.** Uçtan uca akış çalışıyor:
tedarikçi Excel'i içeri, ürün araması, teklif, yazdırma. Akrabaya gösterilebilir.
Aşağıdaki 5 soru bu denemede kendiliğinden cevaplanır.

**Öneri (Thufir):** sıralamayı bu şekilde yapma. **Önce 3, sonra 1-2.** Gerekçe:
güvenlik borcu canlıya çıkmadan kapatılmalı ama denemeyi kendi makinende yapabilirsin
ve gerçek kullanıcı geri bildirimi hangi ekranın yeniden yazılacağını belirler.
Güvenliği önce kapatıp sonra ekranı baştan yazmak iki kez iş demek. Karar sende.

---

## ⏰ Erce'nin yapacağı — motor bunları bekliyor değil ama ince ayarı bunlar belirleyecek

**Akrabaya sorulacak, hâlâ sorulmadı.** Önerilen ve kabul edilen yol: Excel istemek
yerine **eski bir teklif örneği istemek** — tek belge 7 sorunun beşini birden cevaplıyor
(kalem yapısı, arama ifadeleri, iskonto zinciri, işçilik, KDV yeri, revizyon görünümü).

1. Kaç kademe iskonto, tipik oranlar ne?
2. İskonto müşteriye göre sabit mi, her teklifte yeniden mi belirleniyor?
3. İşçilik nasıl hesaplanıyor: yüzde mi, metraj başına birim mi, götürü mü?
4. İşçiliğe iskonto uygulanıyor mu?
5. Fiyat neye göre veriliyor (güncel liste / kur)? Teklif kaç gün geçerli?
6. Aynı işin ikinci-üçüncü teklifi oluyor mu, eskisi saklanıyor mu?

> 6. sorunun modele etkisi kapandı: versiyonlama zaten kuruldu.
> 1-5 motoru değiştirmez, **varsayılanları** (`QuoteDefaults`) doldurur.

### 🔑 Anahtar/priz — KARAR VERİLDİ (21.08)

Viko listesi üç fiyat veriyor: `Mekanizma 472,00 + Düğme/Kapak 212,00 = Toplam 684,00`,
çerçeve **ayrıca** fiyatlı. Perakendede iç ve dış ayrı satılıyor.

**Erce'nin kararı: şimdilik ayrı kalemler olarak kalsın. Sonrasında "set olarak ekle"
seçeneği gelecek.**

Motora yansıması: bugünkü davranış zaten bu — her bileşen kendi kalemi, kendi iskonto
grubuyla. `QuoteItem.parent_item_id` alanı duruyor ve hesaba girmiyor;
`test_bilesen_kalemi_ayri_satir_olarak_toplanmaz` bunu sabitliyor.

"Set olarak ekle" geldiğinde yapılacak iş: ekranda bir set tanımı seçilince üç kalemi
birden ekleyen bir giriş kolaylığı. Mekanizma ve kapağın iskonto grubu farklı
olabildiği için **toplama yine erken yapılmayacak** — set bir giriş kolaylığı,
hesap birimi değil.

---

## Karar durumu (bağlayıcı)

| Konu | Karar | Tarih |
|---|---|---|
| Ürün tanımı | Teklif hazırlama aracı. Stok takip değil | 08.08 |
| Stok adet takibi | ❌ v1'den çıktı — müşteride muhasebe programı var | 20.08 |
| `Customer.balance` | ❌ v1'den çıktı, aynı gerekçe | 20.08 |
| Katalog | Müşterinin verisi. Kurulan şey **içe aktarma ve ayrıştırma** | 20.08 |
| Teklif versiyonlama | ✅ v1'de var, kuruldu | 21.08 |
| Teklif modülü | Yeni router olacak, katalog altına sıkıştırılmayacak | 08.08 |
| Teklif çıktısı | İlk sürümde yazdırılabilir HTML yeterli, PDF sonra | 26.07 |
| Kesildi (v2) | Y2 kategori silme/düzenleme · T8 migration zinciri · T10 Tailwind CDN | 08.08 |
| Entegrasyon | Kod yok. Sadece `supplier_code` + CSV/Excel dışa aktarım kapısı | 08.08 |

---

## Veri durumu
- **11 gerçek tedarikçi fiyat listesi:** `tests/fixtures/tedarikci_listeleri/`, ~11.000 satır.
  9'u doğrudan Excel, 2'si PDF'ten çevrildi (`_pdf2xlsx_*.py` — **tek seferlik script'ler,
  ürüne girmez**, her PDF'in sayfa düzenine özel; ruff bunlara takılıyor, bilerek).
  ⚠️ **Bu klasör henüz git'e eklenmedi (1,1 MB, gerçek tedarikçi fiyat verisi).
  Commit edilsin mi, `.gitignore`'a mı girsin — karar Erce'de.**
- Parametre envanteri Erce'nin vault'unda: `🏰 300-Projects/Elektrotakip Urun Parametreleri.md`
- DB'de 3 kullanıcı. Eski 66 ürün 26.07'de silindi (birim belirsizdi),
  `yedek_urunler_2026-07-26.csv` olarak dışa aktarıldı, git'e dahil değil.
- Boş `Kablo` kategorisi (id=1, user_id=1) duruyor.

### Dosyalardan ölçülen, motoru bağlayan girdiler (tahmin değil)
1. **Üç para birimi:** Klemsan tamamen EURO · Grup Arge aynı dosyada TL+USD ·
   Viko'da anahtar-priz TL, LED ve şalt USD. → `Product.currency` eklendi, kur donduruluyor.
2. **Birim aynı ürün tipinde bile değişiyor:** Öznur kablo `TL/km`, Erse `TL/m`,
   Molwex `ADET`+`MT` karışık. → Satır bazlı birim kararı doğru, öyle kalsın.
3. **Fiyat yerine metin:** `Bilgi Alınız` (Tense), `FİYAT SORUNUZ`,
   `KDV DAHİL NET FİYAT` (Grup Arge). → Fiyatsız ürün akışı gerçek.
4. **Liste fiyatlarında iskonto/KDV bilgisi YOK.** Viko'nun 69 sayfasında 0 eşleşme.
   → İskonto zinciri tamamen kullanıcının verisi. Mevcut tasarım doğru.
5. **İki seviyeli paketleme:** `Kutudaki Adet` + `Kolideki Adet` ayrı sütunlar (Viko, Klemsan).

---

## Sektör araştırması — motoru bağlayan bulgular (referans, hepsi koda girdi)

| Bulgu | Ürüne yansıması | Durum |
|---|---|---|
| **Zincirli iskonto çarpımsaldır:** 1.000'e %20+%10 → **720**, %30 → 700 | Sırayla uygulanır | ✅ |
| **Liste fiyatı bilinçli şişik**, iş iskonto oranı üzerinden döner. Bayi %15-25, distribütör %25-35 | Net fiyat kaydeden model yanlış. Liste + zincir ayrı saklanır. "Liste 100 bin, size 62 bin" satışın kendisi | ✅ |
| **Dört iskonto türü aynı anda:** satır · kademeli · zincirleme · genel | Ayrı satır tipleri | ✅ (kademeli hariç) |
| **İşçilik ayrı kalem grubu, genelde iskontoya GİRMEZ** | `discountable` bayrağı | ✅ |
| **Kablo fiyatı bakır (LME) ve dolara endeksli, günlük oynar** | Teklif dondurulur, `valid_until` zorunlu | ✅ |
| **GİB e-fatura satır bazında yuvarlar**, tam 5'te en yakın çift sayıya | `Decimal` + `ROUND_HALF_EVEN`, satır bazında | ✅ |
| **Tevkifat (yapım işleri 4/10)**, eşik KDV dahil 5 milyon TL | v1 kapsam dışı, yapı esnek kaldı | ⏸ |

---

## Kablo parametreleri — ✅ 21.08'de yapıldı

> Aşağıdaki analiz 26 Temmuz'da yazıldı ve **uygulandı.** Ne yapıldığı yukarıdaki
> "ÜRÜN ARAMA" bölümünde; burası kararın gerekçesi olarak duruyor. Tek fark:
> ayrıştırıcı serbest metinde çıplak `NxM` kalıbına güvenmiyor, çünkü ölçümde
> bu kalıbın çoğunlukla kablo değil ürün kodu/kontak değeri olduğu çıktı.

### Sorun
`technical_specs` tek bir uzun metin, parametreler ayrıştırılmamış:
```
PVC İzoleli, Kılıfsız, Tek Damarlı, Tek Telli Bakır İletkenli | TS EN 50525-2-31 | CPR: Eca | 2.5 mm² | Ambalaj: R100
```
Sonuçları: (a) kesit sayı olmadığı için `2.5–6 mm² arası` filtre yapılamıyor, "3x2.5 bakır"
gibi sahada konuşulan ifadeyle bulunamıyor; (b) ürün adı `marka + technical_specs +
kategori` olarak derlendiği için liste okunmuyor; (c) `Ambalaj: R100 / M1000` bilgisi
görmezden geliniyor (M1000 = 1000 m makara, fiyat birimiyle ilişkili olabilir).

### Önerilen çözüm (Erce onaylarsa)
Metin korunur, karar veren parametreler ayrı kolonlara çıkar: `cross_section` (Numeric, mm²) ·
`core_count` (Integer) · `conductor` (bakır/alüminyum) · `insulation` (PVC/XLPE) ·
`sheathed` (Boolean). İçe aktarmada bir ayrıştırıcı bunları metinden çıkarır, çıkaramadığı
satır sayısını raporlar. Ürün adı kısalır (`Öznur NYA 2.5 mm² Bakır`).

Ayrı kolon tercih edildi (EAV/JSON değil): alanlar az sayıda, sayısal ve aralık sorgusu
istiyor; index'lenebilir ve okunur kalıyor.

**Açık soru:** kablo dışı ürünlerde ayırt edici parametreler (anahtar/priz/sigortada amper,
kutup sayısı, IP sınıfı) — aynı yapı onlara da kurulsun mu, şimdilik sadece kablo mu?

**Açık kalan:** kablo dışı ürünlerde ayırt edici parametreler (anahtar/priz/sigortada
amper, kutup sayısı, IP sınıfı). Kablo tarafı bitti; bunlar gerçek kullanıcı denemesinde
ihtiyaç çıkarsa eklenir. Yapı aynı kalıpla genişliyor: ölç, ayrı kolon, testle sabitle.

---

## Test durumu
`uv run pytest` → **498 test.** Bellekte SQLite ile koşuyor, PostgreSQL gerekmiyor.

| Dosya | Kapsam |
|---|---|
| `test_quote_engine.py` | Hesap zinciri, KDV, yuvarlama, dağıtım, kur (36) |
| `test_quote_model.py` | Model, ORM↔motor köprüsü, fiyat donması, kısıtlar (19) |
| `test_quotes_router.py` | Teklif ekranı: erişim kontrolü, kalem/zincir akışı (37) |
| `test_quotes_output.py` | Yazdırma çıktısı, revizyon, işletme varsayılanları (31) |
| `test_product_search.py` | Parametre ayrıştırma, yanlış pozitifler, arama, yeniden ayrıştırma (80) |
| `test_template_import.py` | Şablonun kendisi, şablonla içe aktarma, KDV, katalog listesi (35) |
| `test_supplier_files.py` | 11 gerçek tedarikçi dosyası: ayrıştırma + uçtan uca içe aktarma (116) |
| `test_catalog_isolation.py` | Erişim kontrolü + IDOR |
| `test_customers_isolation.py` | Müşteri izolasyonu |
| `test_csrf.py` | CSRF |
| `test_excel_import.py` | Mükerrer, bozuk girdi, boş satır (kendi şablonumuz) |
| `test_units.py` | KM dönüşümü, birim normalleştirme, kolon sınırı |
| `test_parse_price.py` | Fiyat ayrıştırma ve Türkçe gösterim |
| `test_home.py` | Ana panel sayıları, gezinme |

---

## Öğrenilenler
| Konu | Ne öğrenildi | Tarih |
|---|---|---|
| Sır yönetimi | `.env.example` bir şablondur, gerçek değer taşımaz. | 25.07 |
| Auth tasarımı | Yetkisizde `None` dönen dependency, korumayı her route'ta elle yazmayı zorunlu kılar; bir yerde unutulunca açık oluşur. Doğrusu hata fırlatan zorunlu dependency. | 26.07 |
| Sahiplik zinciri | Ürünün `user_id`'si olmadığı için her sorgu `join(Category)` ister. Tek yardımcıya toplamak açığın tekrar açılmasını engelliyor. | 26.07 |
| Testin anı | Çalışan koda dokunmadan önce test yaz. | 26.07 |
| Fixture zinciri | Test fixture'ı, test edilen korumayı sessizce sağlayabilir. | 26.07 |
| Ayrıştırma kararı | `parse_price` "anlamadım" için `None` döner; kararı fonksiyonun içine gömmek iki farklı kopya doğurmuştu. | 26.07 |
| Para tipi | Para `float` ile tutulmaz. Ondalık basamak sayısı da bir tasarım kararı. | 26.07 |
| **Hesabı DB'den ayırmak** | `quote_engine` ORM bilmediği için 36 test fixture'sız koşuyor ve saniyenin altında bitiyor. Hesap mantığı route'a girseydi her kural için HTTP isteği kurmak gerekirdi. | 21.08 |
| **Orantılı dağıtım** | Payları ayrı ayrı yuvarlarsan toplam hedeften sapar ve teklif toplamı kalemlerin toplamını tutmaz. Largest remainder ile aşağı yuvarlayıp artan kuruşları dağıtmak gerekiyor. | 21.08 |
| **Autogenerate'e güvenme** | Dolu tabloya NOT NULL kolon eklerken `server_default` koymaz (migration patlar) ve yabancı anahtarlara index koymaz. `alembic check` sürüklenmeyi yakalıyor. | 21.08 |
| **Şablon ≠ bağ** | Müşterinin varsayılan iskontosu teklife **kopyalanır.** Bağlansaydı varsayılan değişince geçmiş teklifler kendiliğinden bozulurdu — donmuş fiyat kararının aynısı. | 21.08 |
| **Alt dize ≠ kelime** | Sütun adı tanırken `"ad" in "ADET"` doğrudur ama istenen şey değildir. Kısa anahtarlarla alt dize araması Molwex'te 699 yanlış pozitif verdi; kelime bazlı eşleşmede 0. Eşleştirme kelime sınırında yapılmalı. | 21.08 |
| **Gerçek dosya = testin kendisi** | Ayrıştırıcıyı 11 gerçek dosyaya karşı koşturmak iki sessiz veri kaybını (Molwex 699, Viko 822 satır) anında gösterdi. Uydurma fixture ikisini de kaçırırdı: ikisi de "beklenmedik ama gerçek" veriden çıktı. | 21.08 |
| **Sayaç, sessiz atlamadan iyidir** | Ayrıştırıcı kaç satırı neden atladığını sayıyor (bölüm başlığı, tekrar eden başlık, kimliksiz, fiyatı okunamayan). "Neden bu kadar az ürün geldi" sorusu ancak böyle cevaplanıyor — ve iki hatayı da bu sayaçlar ele verdi. | 21.08 |
| **Cascade bir iş kararıdır** | `delete-orphan` "bu kayıt onsuz anlamsız" demek. Revizyon öyle değil: ayrı bir tekliftir. Cascade konulunca 1. sürümü silmek en güncel teklifi götürüyordu. İlişki kurarken "silinince ne olmalı" sorusu ayrıca sorulmalı. | 21.08 |
| **Şablonda indeks sayma** | Motorun çıktısıyla DB kayıtlarını indeks üzerinden eşleştirmek, iki listenin filtresi ayrıştığı gün sessizce kayar. Eşleştirme veriyi üreten yerde açıkça kurulmalı — şablon sadece göstermeli. | 21.08 |
| **Yol sırası eşleştirmeyi belirler** | FastAPI yolları tanım sırasına göre eşleştiriyor. `/quotes/settings`, `/quotes/{quote_id}`'den sonra tanımlansaydı "settings" bir id sanılıp 422 dönerdi. Sabit yollar parametreli olanlardan önce gelmeli. | 21.08 |
| **Kalıp bağlamdan güç alır** | Aynı `NxM` kalıbı serbest metinde çöp, "Kesit (mm2)" sütununda güvenilir — çünkü sütun başlığı bağlamı garanti ediyor. Ayrıştırıcı verinin nereden geldiğini bilmeli; her yere aynı regex'i uygulamak Viko'da 532 ürün kodunu kablo yapardı. | 21.08 |
| **Mükerrer kimliği ürünü ayıran şeyi içermeli** | Öznur'da ad tekrar ediyor, ürünleri ayıran kesit. Kimlik (kategori+özellik+marka) olduğu için 1614 satır mükerrer sanılıp atıldı. "Bu iki kaydı ne ayırır" sorusu kimlik kurulurken sorulmalı. | 21.08 |

---

## Vault özeti (Olric'e taşınacak)
**Elektrotakip artık uçtan uca çalışıyor: tedarikçi Excel'i içeri, teklif dışarı.**
Ağustos'un üç haftalık planı tek oturumda kapandı; 144 testten **463 teste** çıkıldı.

**Teklif motoru** — ürünün satılan parçası: sıralı ve yeniden düzenlenebilir hesap
zinciri, çarpımsal iskonto, satır bazında GİB uyumlu KDV yuvarlaması, kuruş kaybetmeyen
orantılı iskonto dağıtımı, teklif anında dondurulan fiyat ve döviz kuru, revizyon
versiyonlaması. Hesap katmanı veritabanından tamamen ayrı durduğu için testleri
fixture'sız koşuyor.

**İçe aktarma** gerçek tedarikçi dosyalarını yiyor: başlık satırını ve sütun adlarını
kendisi tanıyor, çoklu sayfa ve eski `.xls` okuyor, bölüm başlıklarını ürün sanmıyor,
üç para birimini çözüyor. 11 gerçek dosyanın 11'i okunuyor (~13.600 satır).

**Teklif ekranı** motoru kullanıcının önüne koydu: katalogdan veya elle kalem, "20/10"
yazımıyla iskonto zinciri, sırası ↑↓ ile değiştirilebilen hesap zinciri, canlı toplam,
yazdırılabilir çıktı, revizyon ve işletme varsayılanları. Ekranda tek bir hesap satırı
yok — her rakam motordan geliyor.

**Ürün arama** kablo parametrelerini ayrıştırdı ve sahada konuşulan ifadeyi anlıyor:
"3x2.5 NYY", "5x16 bakır", "2.5-6 mm² arası". Öznur'un 1673 kablosunun tamamında kesit
çıkarılıyor; kablo olmayan altı dosyada sıfır yanlış pozitif.

**Testler bu oturumda beş sessiz veri kaybı yakaladı.** İkisi sütun eşleştirmesinde
(Molwex'te 699, Viko'da 822 ürün atılıyordu), biri ORM cascade'inde (eski teklifi silmek
en güncel revizyonu götürüyordu), biri regex'te (akım trafosu kablo sanılıyordu), biri
mükerrer kimliğinde (Öznur'un kablo kataloğu 1673 satırdan 59 ürüne iniyordu). Hiçbiri
arayüzden görünmüyordu; hepsini gerçek dosyalarla ölçüm ortaya çıkardı.

Anahtar/priz bileşen sorusu karara bağlandı: şimdilik ayrı kalemler, ileride "set olarak
ekle" kolaylığı.

**22.08 eki:** kendi indirilebilir şablonumuz gerçek tedarikçi dosyasından daha zayıf
girdi çıktı — kesit, tedarikçi kodu ve para birimi taşımıyordu, dolayısıyla şablonla
yüklenen kablo kataloğu aranamıyordu. Şablona dört sütun eklendi ve içe aktarma ürün
bazlı KDV'yi de okumaya başladı.

**Sıradaki iş artık ürün değil, çıkış.** Güvenlik borcu (parola politikası,
`python-jose` → `PyJWT`), Eylül canlıya çıkış ve **akrabaya ilk gösterim** — uçtan uca
akış çalıştığı için bu artık mümkün. Thufir'in önerisi: gösterimi güvenlik borcundan
önce yap, çünkü geri bildirim hangi ekranın yeniden yazılacağını belirler.
