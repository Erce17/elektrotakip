# PROGRESS — Elektrotakip

> Thufir bu dosyayı her oturum sonunda üzerine yazar. Oturum açılışında **önce burası okunur.**

**Takvim: Ağustos motor · Eylül canlıya çıkış · Ekim satış ayı.** Kayma lüksü yok.

---

## Son oturum
**Tarih:** 2026-08-21 (Thufir)
**Yapılan:** PAKET B (teklif motoru) **ve** PAKET A (içe aktarma) bitti.
Commit `de10755`, `e96ac90`, `fac73ca`. `main` push edilmiş durumda.
**Test:** 314 geçiyor (oturum başında 144).

### Ne kuruldu

| Dosya | İş |
|---|---|
| `app/quote_engine.py` | Saf hesap katmanı. DB/ORM/HTTP bilmez, girdi-çıktı dataclass |
| `app/quote_service.py` | ORM ↔ motor köprüsü. Hesap mantığı burada değil |
| `app/models/quote.py` | `Quote` · `QuoteItem` · `QuoteAdjustment` · `QuoteDefaults` |
| `alembic/.../2bd390383d15` | Migration. Postgres'te upgrade→downgrade→upgrade doğrulandı |
| `tests/test_quote_engine.py` | 36 test — iş kuralları |
| `tests/test_quote_model.py` | 18 test — model, köprü, kısıtlar |

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
- **Kablo parametreli ayrıştırma yok** (kesit, damar sayısı, iletken). 3. hafta işi,
  aşağıda duruyor.
- **Marka sütunu gerçek dosyalarda yok.** Alan tanınıyor ama 11 dosyanın hiçbirinde
  geçmiyor; ürünlerin `brand`'i boş kalıyor.
- **İki seviyeli paketleme** (`Kutudaki Adet` + `Kolideki Adet`) okunuyor ama ürüne
  yazılmıyor — modelde karşılığı yok.
- **Ruff'ta 4 uyarı duruyor**, ikisi boş `pass` migration'da (T8, v2'ye kesildi).
  Fixture'daki tek seferlik PDF script'leri `pyproject.toml`'da ruff'tan hariç tutuldu.

---

## Sırada

**1. Teklif router + ekranı** (2. hafta işi): teklif oluşturma, kalem ekleme, zincir
düzenleme, yazdırılabilir HTML çıktı. Motor hazır, bağlanmayı bekliyor.

**3. Kablo parametreli arama** (3. hafta): aşağıdaki "kablo parametreleri" bölümü.

**4. Güvenlik borcu — canlıya çıkmadan zorunlu:**
- **G7** parola politikası + e-posta doğrulaması yok. Tek karakterlik parola kabul ediliyor.
- **G6** `python-jose` bakımsız, bilinen CVE'leri var. `PyJWT`'ye geçiş küçük iş.
- Canlıya çıkarken `SECRET_KEY` ve `COOKIE_SECURE=true` ortam değişkeni olarak verilmeli.

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

## Kablo parametreleri — 3. hafta işi

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

---

## Test durumu
`uv run pytest` → **314 test.** Bellekte SQLite ile koşuyor, PostgreSQL gerekmiyor.

| Dosya | Kapsam |
|---|---|
| `test_quote_engine.py` | Hesap zinciri, KDV, yuvarlama, dağıtım, kur (36) |
| `test_quote_model.py` | Model, ORM↔motor köprüsü, fiyat donması, kısıtlar (18) |
| `test_catalog_isolation.py` | Erişim kontrolü + IDOR |
| `test_customers_isolation.py` | Müşteri izolasyonu |
| `test_csrf.py` | CSRF |
| `test_supplier_files.py` | 11 gerçek tedarikçi dosyası: ayrıştırma + uçtan uca içe aktarma (116) |
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

---

## Vault özeti (Olric'e taşınacak)
Elektrotakip'te iki paket birden bitti. **Teklif motoru** yazıldı — ürünün satılan parçası
artık var: sıralı ve yeniden düzenlenebilir hesap zinciri, çarpımsal iskonto, satır bazında
GİB uyumlu KDV yuvarlaması, kuruş kaybetmeyen orantılı iskonto dağıtımı, teklif anında
dondurulan fiyat ve döviz kuru, revizyon versiyonlaması. Hesap katmanı veritabanından
tamamen ayrı durduğu için testleri fixture'sız koşuyor.

**İçe aktarma** artık gerçek tedarikçi dosyalarını yiyor: başlık satırını ve sütun adlarını
kendisi tanıyor, çoklu sayfa ve eski `.xls` okuyor, bölüm başlıklarını ürün sanmıyor, üç
farklı para birimini çözüyor. 11 gerçek dosyanın 11'i okunuyor (~13.600 satır) ve dosyalar
teste dahil edildi. Bu testler iki sessiz veri kaybını yakaladı: bir sütun adı eşleşmesi
hatası Molwex'te 699, bir bölüm başlığı kuralı Viko'da 822 ürünü atıyordu.

Proje 144 testten **314 teste** çıktı. Anahtar/priz bileşen sorusu karara bağlandı: şimdilik
ayrı kalemler, ileride "set olarak ekle" kolaylığı. Sıradaki iş teklif ekranı — motor hazır,
bağlanmayı bekliyor.
