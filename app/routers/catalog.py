import io
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from urllib.parse import urlencode

import openpyxl
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.dependencies import require_user
from app.models import Category, Product, User

router = APIRouter(
    prefix="/catalog",
    tags=["Catalog"]
)


# Dosyanın tamamı belleğe okunuyor; fiyat listesi dosyaları küçük olur.
MAX_IMPORT_BYTES = 5 * 1024 * 1024

KM_METRE = Decimal(1000)

# unit_price kolonu Numeric(12,4): 8 tam + 4 ondalık basamak.
# Sınırı aşan değeri kaydetmeye çalışmak Postgres'te DataError'a, yani
# içe aktarmanın tamamının çökmesine yol açıyor.
PRICE_DECIMALS = Decimal("0.0001")
MAX_UNIT_PRICE = Decimal("99999999.9999")


# --- Yardımcılar ---------------------------------------------------------
# Ürünün sahibi yoktur, kategorinin sahibi vardır. Bu yüzden her ürün sorgusu
# Category üzerinden geçer; aşağıdaki iki fonksiyon bunu tek yerde tutar.

def user_products(db: Session, user: User):
    """Kullanıcının ürünleri için temel sorgu. Üstüne filtre eklenebilir."""
    return db.query(Product).join(Category).filter(Category.user_id == user.id)


def get_owned_product(db: Session, user: User, product_id: int) -> Product | None:
    """Ürünü sadece kullanıcıya aitse döner. Değilse None — yoksa da None."""
    return user_products(db, user).filter(Product.id == product_id).first()


def get_owned_category(db: Session, user: User, category_id: int) -> Category | None:
    """Kategoriyi sadece kullanıcıya aitse döner."""
    return (
        db.query(Category)
        .filter(Category.id == category_id, Category.user_id == user.id)
        .first()
    )


def parse_price(value) -> Decimal | None:
    """Fiyat girdisini Decimal'e çevirir. Anlaşılmazsa None.

    Tedarikçi listeleri tek bir formatta gelmiyor; ayracın hangisi olduğuna
    şu sırayla karar veriyoruz:

    1. Hem nokta hem virgül varsa → SONDAKİ ondalık ayracıdır.
       '1.200,50' → 1200.50   ·   '1,200.50' → 1200.50
    2. Sadece virgül varsa → ondalık ayracı (Türkçe varsayılan).
       '850,75' → 850.75
    3. Sadece nokta varsa → belirsiz. Birden fazla nokta varsa ya da tek
       noktadan sonra tam 3 hane varsa binlik ayracıdır:
       '1.200' → 1200   ·   '1.234.567' → 1234567   ·   '1200.50' → 1200.50
       Tek istisna: tam sayı kısmı 0 ise ondalıktır ('0.500' → 0.5).

    Decimal kullanılıyor çünkü float ikili tabanda çalışır ve para değerinde
    yuvarlama hatası biriktirir; DB kolonu da Numeric.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        # Excel hücresi zaten sayı; float'ın ikili gösteriminden kaçınmak için
        # metin üzerinden Decimal'e geçiyoruz
        return Decimal(str(value))

    raw = str(value).upper()
    for gereksiz in ("TL", "TRY", "₺", "\xa0"):
        raw = raw.replace(gereksiz, "")
    raw = raw.replace(" ", "").strip()
    if not raw:
        return None

    nokta, virgul = "." in raw, "," in raw
    if nokta and virgul:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")   # 1.200,50
        else:
            raw = raw.replace(",", "")                     # 1,200.50
    elif virgul:
        raw = raw.replace(",", ".")
    elif nokta:
        tam_kisim, _, son_grup = raw.rpartition(".")
        binlik = raw.count(".") > 1 or (len(son_grup) == 3 and tam_kisim.strip("-") != "0")
        if binlik:
            raw = raw.replace(".", "")

    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


# Tedarikçilerin birim sütununa yazdıkları. Soldaki ham yazımlar, sağdaki
# bizim kullandığımız karşılık. Listede olmayan bir yazım olduğu gibi kalır.
BIRIM_KARSILIKLARI = {
    "KM": "KM", "KM.": "KM", "K.M": "KM", "KMTL": "KM", "1000M": "KM",
    "1000MT": "KM", "1000METRE": "KM", "KILOMETRE": "KM",
    "M": "Metre", "MT": "Metre", "MT.": "Metre", "METRE": "Metre", "M.": "Metre",
    "AD": "Adet", "AD.": "Adet", "ADET": "Adet", "ADT": "Adet",
    "KUTU": "Kutu", "KT": "Kutu", "KT.": "Kutu", "BOX": "Kutu",
    "PK": "Paket", "PKT": "Paket", "PAKET": "Paket", "TAKIM": "Takım", "TK": "Takım",
    "KG": "Kg", "KG.": "Kg", "KILO": "Kg",
    "ROLE": "Rulo", "RULO": "Rulo",
}


def quantize_price(value: Decimal) -> Decimal:
    """Fiyatı kolonun tuttuğu basamak sayısına yuvarlar.

    Yuvarlamayı DB'ye bırakmıyoruz: burada yapınca kaydedilen değerle ekranda
    gösterilen değer aynı oluyor.
    """
    return value.quantize(PRICE_DECIMALS, rounding=ROUND_HALF_UP)


# Uzunlukla değil sayıyla satılanlar: bunlar hiçbir koşulda 1000'e bölünmez
ADET_BAZLI_BIRIMLER = {"Adet", "Kutu", "Paket", "Takım", "Kg", "Rulo"}


def normalize_unit(raw: str) -> str:
    """Tedarikçinin yazdığı birimi bizim kullandığımız yazıma çevirir.

    'MT', 'mt.', 'metre' hepsi 'Metre' olur. Böylece aynı birim listede üç
    farklı isimle görünmüyor ve KM tespiti güvenilir çalışıyor. Boş girdi boş
    döner — "birim belirtilmemiş" ile "adet" birbirinden ayrılabilsin diye.
    """
    if not raw or not raw.strip():
        return ""
    anahtar = raw.upper().replace(" ", "").replace("/", "").strip()
    return BIRIM_KARSILIKLARI.get(anahtar, raw.strip())


def build_product_name(brand: str, technical_specs: str, category_name: str) -> str:
    """Ürün adını parçalardan derler: 'Marka Özellik Kategori'."""
    return " ".join(p for p in (brand, technical_specs, category_name) if p).strip()


def import_result_redirect(
    eklendi: int = 0,
    atlandi: int = 0,
    fiyatsiz: int = 0,
    hata: str = "",
) -> RedirectResponse:
    """İçe aktarma sonucunu /catalog'a query string ile taşır.

    POST sonrası yönlendirme yapıldığı için sonuç bir sonraki istekte lazım;
    oturumda flash mesajı tutmak yerine URL'de taşımak yeterli.
    """
    params = {"eklendi": eklendi, "atlandi": atlandi, "fiyatsiz": fiyatsiz}
    if hata:
        params = {"hata": hata}
    url = "/catalog?" + urlencode(params)
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


# --- Route'lar -----------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def get_catalog_page(
    request: Request,
    eklendi: int = Query(0),
    atlandi: int = Query(0),
    fiyatsiz: int = Query(0),
    hata: str = Query(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Katalog ana sayfasını ve kullanıcının kategori/ürünlerini listeler."""
    categories = (
        db.query(Category)
        .filter(Category.user_id == current_user.id)
        .order_by(Category.name.asc())
        .all()
    )
    products = user_products(db, current_user).all()

    # İçe aktarmadan yönlendirildiysek sonucu bir kez göster
    ic_aktarma = None
    if hata:
        ic_aktarma = {"hata": hata}
    elif eklendi or atlandi or fiyatsiz:
        ic_aktarma = {"eklendi": eklendi, "atlandi": atlandi, "fiyatsiz": fiyatsiz}

    return templates.TemplateResponse(
        request,
        "catalog.html",
        {"categories": categories, "products": products, "ic_aktarma": ic_aktarma}
    )


@router.post("/category")
def create_category(
    name: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Yeni bir kategori oluşturur."""
    new_category = Category(name=name, user_id=current_user.id)
    db.add(new_category)
    db.commit()

    # HTMX ile eklendiğinde aynı sayfaya geri dönüp yenilenmiş halini göstersin
    return RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/download-template")
def download_excel_template(current_user: User = Depends(require_user)):
    """Kullanıcının veri gireceği standart Excel şablonunu dinamik olarak üretir ve indirir."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ElektroTakip_Sablon"

    # "Malzeme" başlığı çıkarıldı, tam olarak yazdığımız algoritmaya uygun 5 sütun:
    headers = ["Kategori", "Teknik Özellik", "Marka", "Birim Fiyat", "Birim"]
    ws.append(headers)

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=elektrotakip_sablon.xlsx"}
    )


@router.post("/import-excel")
async def import_catalog_excel(
    file: UploadFile = File(...),
    is_km_price: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Excel fiyat listesini kataloğa aktarır. Sonucu özet olarak /catalog'a taşır."""
    if not (file.filename or "").lower().endswith(".xlsx"):
        return import_result_redirect(hata="Sadece .xlsx dosyası yükleyebilirsin.")

    contents = await file.read()
    if not contents:
        return import_result_redirect(hata="Dosya boş görünüyor.")
    if len(contents) > MAX_IMPORT_BYTES:
        return import_result_redirect(
            hata=f"Dosya çok büyük (en fazla {MAX_IMPORT_BYTES // (1024 * 1024)} MB)."
        )

    try:
        workbook = openpyxl.load_workbook(filename=io.BytesIO(contents), data_only=True)
    except Exception:
        # openpyxl bozuk/şifreli/eski format dosyalarda çok çeşitli hata atar;
        # kullanıcı için hepsi aynı sonuca çıkıyor.
        return import_result_redirect(
            hata="Dosya okunamadı. Şablonu indirip verilerini onun üzerine yazmayı dene."
        )

    sheet = workbook.active
    if sheet is None:
        return import_result_redirect(hata="Dosyada okunabilir bir sayfa yok.")

    eklendi = 0
    atlandi = 0
    fiyatsiz = 0
    # Aynı dosya içindeki mükerrerleri yakalamak için: DB sorgusu henüz
    # commit edilmemiş satırları görmez.
    bu_dosyada_gorulen = set()

    for row in sheet.iter_rows(min_row=2, values_only=True):
        if not any(row):
            continue

        col_kat = str(row[0]).strip() if len(row) > 0 and row[0] is not None else "Diğer"
        col_spec = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        col_marka = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
        col_fiyat = row[3] if len(row) > 3 else None
        col_birim = str(row[4]).strip() if len(row) > 4 and row[4] is not None else ""

        fiyat = parse_price(col_fiyat)
        if fiyat is None:
            # Satırı atmıyoruz: ürün girsin, fiyatı sonra düzeltilsin. Ama sayısını say.
            fiyat = Decimal(0)
            fiyatsiz += 1

        birim = normalize_unit(col_birim)

        # KM → metre dönüşümü satır bazlı: tedarikçi dosyalarında birimler
        # karışık geliyor, tek kutucuk dosyanın tamamı için doğru olmuyor.
        # Satır KM diyorsa her hâlükârda çevrilir. Kutucuk işaretliyse metre
        # ve birimi belirtilmemiş satırlar da çevrilir; adet bazlı olanlara
        # (kutu, paket, takım...) dokunulmaz — yanlış çevrimin asıl kaynağı buydu.
        satir_km = birim == "KM" or (is_km_price and birim not in ADET_BAZLI_BIRIMLER)
        if satir_km and fiyat > 0:
            fiyat = fiyat / KM_METRE
            birim = "Metre"

        if fiyat > MAX_UNIT_PRICE:
            # DB kolonunun sınırını aşıyor; kaydetmeye çalışırsak içe aktarmanın
            # tamamı çöker. Ürünü al, fiyatı kullanıcı düzeltsin.
            fiyat = Decimal(0)
            fiyatsiz += 1
        else:
            fiyat = quantize_price(fiyat)

        # Kategori aramasında user_id şart: aynı isim başka kullanıcıda da olabilir
        category = (
            db.query(Category)
            .filter(Category.name == col_kat, Category.user_id == current_user.id)
            .first()
        )
        if not category:
            category = Category(name=col_kat, user_id=current_user.id)
            db.add(category)
            db.flush()  # id lazım; commit dosyanın tamamı bitince

        kimlik = (category.id, col_spec, col_marka)
        if kimlik in bu_dosyada_gorulen:
            atlandi += 1
            continue

        existing_product = db.query(Product).filter(
            Product.category_id == category.id,
            Product.technical_specs == col_spec,
            Product.brand == col_marka
        ).first()

        if existing_product:
            atlandi += 1
            continue

        db.add(Product(
            name=build_product_name(col_marka, col_spec, col_kat),
            brand=col_marka,
            category_id=category.id,
            technical_specs=col_spec,
            unit_price=fiyat,
            unit=birim or "Adet"
        ))
        bu_dosyada_gorulen.add(kimlik)
        eklendi += 1

    # Tek commit: dosya yarıda hata verirse katalog yarım kalmaz
    db.commit()
    return import_result_redirect(eklendi=eklendi, atlandi=atlandi, fiyatsiz=fiyatsiz)


@router.post("/product")
def create_product(
    technical_specs: str = Form(""),
    brand: str = Form(""),
    category_id: int = Form(...),
    unit_price: str = Form(...),  # '1.200,50' de yazılabilsin diye string
    vat_rate: int = Form(20),
    unit: str = Form("Adet"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    # Kategori kullanıcının olmalı; değilse başkasının kataloğuna ürün yazılırdı
    category = get_owned_category(db, current_user, category_id)
    if category is None:
        return HTMLResponse("Kategori bulunamadı.", status_code=404)

    # Excel'deki ayrıştırmanın aynısı: elle eklerken de '1.200,50' yazılabilsin
    fiyat = parse_price(unit_price)
    if fiyat is None or fiyat < 0 or fiyat > MAX_UNIT_PRICE:
        return HTMLResponse("Birim fiyat okunamadı.", status_code=400)

    new_product = Product(
        name=build_product_name(brand, technical_specs, category.name),
        technical_specs=technical_specs,
        brand=brand,
        category_id=category.id,
        unit_price=quantize_price(fiyat),
        vat_rate=vat_rate,
        unit=normalize_unit(unit) or "Adet"
    )
    db.add(new_product)
    db.commit()

    return RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/search", response_class=HTMLResponse)
def search_catalog(
    request: Request,
    q: str = Query(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """HTMX ile canlı malzeme araması yapar."""
    query = user_products(db, current_user)
    if q:
        # İsim, marka veya teknik özellikte arama yap (büyük/küçük harf duyarsız)
        search_term = f"%{q}%"
        query = query.filter(
            (Product.name.ilike(search_term)) |
            (Product.brand.ilike(search_term)) |
            (Product.technical_specs.ilike(search_term))
        )
    products = query.all()

    # Sadece tablo satırlarını (tbody içeriğini) render edip döndürüyoruz
    return templates.TemplateResponse(
        request,
        "partials/catalog_rows.html",
        {"products": products}
    )


@router.delete("/product/{product_id}", response_class=HTMLResponse)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """HTMX ile arayüzden malzeme siler."""
    product = get_owned_product(db, current_user, product_id)

    if product:
        db.delete(product)
        db.commit()

    # HTMX hx-swap="outerHTML" ile tetiklendiğinde boş dönen bu string,
    # HTML tablosundaki o satırın (<tr>) anında yok olmasını sağlar.
    return HTMLResponse("")


@router.get("/product/{product_id}/edit", response_class=HTMLResponse)
def edit_product_form(
    request: Request,
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Düzenleme butonuna basıldığında tablo satırını forma çeviren HTML'i döndürür."""
    product = get_owned_product(db, current_user, product_id)
    if product is None:
        return HTMLResponse("", status_code=404)

    categories = (
        db.query(Category)
        .filter(Category.user_id == current_user.id)
        .order_by(Category.name.asc())
        .all()
    )

    return templates.TemplateResponse(
        request,
        "partials/catalog_edit_row.html",
        {"product": product, "categories": categories}
    )


@router.get("/product/{product_id}", response_class=HTMLResponse)
def get_single_product(
    request: Request,
    product_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Düzenlemekten vazgeçildiğinde (İptal) veya kaydedildiğinde satırın normal halini döndürür."""
    product = get_owned_product(db, current_user, product_id)
    if product is None:
        return HTMLResponse("", status_code=404)

    # Tek bir ürünü, aynı tablo döngüsüne [liste] içinde gönderiyoruz
    return templates.TemplateResponse(request, "partials/catalog_rows.html", {"products": [product]})


@router.put("/product/{product_id}", response_class=HTMLResponse)
def update_product(
    request: Request,
    product_id: int,
    technical_specs: str = Form(""),
    brand: str = Form(""),
    category_id: int = Form(...),
    unit_price: str = Form(...),  # Virgülden dolayı string alıp temizliyoruz
    unit: str = Form("Adet"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Değişiklikleri veritabanına kaydeder."""
    product = get_owned_product(db, current_user, product_id)
    if product is None:
        return HTMLResponse("", status_code=404)

    # Taşınmak istenen kategori de kullanıcının olmalı
    category = get_owned_category(db, current_user, category_id)
    if category is None:
        return HTMLResponse("", status_code=404)

    # Hatalı ya da sınır dışı fiyat girilirse eski fiyatta bırak
    fiyat = parse_price(unit_price)
    if fiyat is None or fiyat < 0 or fiyat > MAX_UNIT_PRICE:
        fiyat = product.unit_price
    else:
        fiyat = quantize_price(fiyat)

    product.technical_specs = technical_specs
    product.brand = brand
    product.category_id = category.id
    product.unit_price = fiyat
    product.unit = normalize_unit(unit) or product.unit
    product.name = build_product_name(brand, technical_specs, category.name)

    db.commit()

    # Güncellenmiş satırı HTMX ile ekrana geri bas
    return templates.TemplateResponse(request, "partials/catalog_rows.html", {"products": [product]})
