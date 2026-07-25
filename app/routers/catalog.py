import io

import openpyxl
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_user
from app.models import Category, Product, User

router = APIRouter(
    prefix="/catalog",
    tags=["Catalog"]
)

templates = Jinja2Templates(directory="app/templates")


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


def parse_price(value) -> float | None:
    """Türkçe fiyat girdisini float'a çevirir. Anlaşılmazsa None.

    '1.200,50' → 1200.5 · '1200.50' → 1200.5 · '850 TL' → 850.0
    Kural: hem nokta hem virgül varsa nokta binlik ayracıdır, atılır.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    raw = str(value).upper().replace("TL", "").replace(" ", "").strip()
    if not raw:
        return None
    if "." in raw and "," in raw:
        raw = raw.replace(".", "")
    raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def build_product_name(brand: str, technical_specs: str, category_name: str) -> str:
    """Ürün adını parçalardan derler: 'Marka Özellik Kategori'."""
    return " ".join(p for p in (brand, technical_specs, category_name) if p).strip()


# --- Route'lar -----------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
def get_catalog_page(
    request: Request,
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

    return templates.TemplateResponse(
        request,
        "catalog.html",
        {"categories": categories, "products": products}
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
    contents = await file.read()
    workbook = openpyxl.load_workbook(filename=io.BytesIO(contents), data_only=True)
    sheet = workbook.active

    for index, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        if not any(row):
            continue

        col_kat = str(row[0]).strip() if len(row) > 0 and row[0] is not None else "Diğer"
        col_spec = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        col_marka = str(row[2]).strip() if len(row) > 2 and row[2] is not None else ""
        col_fiyat = row[3] if len(row) > 3 else None
        col_birim = str(row[4]).strip() if len(row) > 4 and row[4] is not None else "Adet"

        fiyat = parse_price(col_fiyat) or 0.0

        # Kullanıcı "Bu fiyatlar KM bazlıdır" dediyse, anında 1000'e böl
        birim = col_birim
        if is_km_price and fiyat > 0:
            fiyat = fiyat / 1000.0
            birim = "Metre"

        malzeme_adi = build_product_name(col_marka, col_spec, col_kat)

        # Kategori aramasında user_id şart: aynı isim başka kullanıcıda da olabilir
        category = (
            db.query(Category)
            .filter(Category.name == col_kat, Category.user_id == current_user.id)
            .first()
        )
        if not category:
            category = Category(name=col_kat, user_id=current_user.id)
            db.add(category)
            db.commit()
            db.refresh(category)

        existing_product = db.query(Product).filter(
            Product.category_id == category.id,
            Product.technical_specs == col_spec,
            Product.brand == col_marka
        ).first()

        if not existing_product:
            new_product = Product(
                name=malzeme_adi,
                brand=col_marka,
                category_id=category.id,
                technical_specs=col_spec,
                unit_price=fiyat,
                unit=birim
            )
            db.add(new_product)

    db.commit()
    return RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/product")
def create_product(
    technical_specs: str = Form(""),
    brand: str = Form(""),
    category_id: int = Form(...),
    unit_price: float = Form(...),
    vat_rate: int = Form(20),
    unit: str = Form("Adet"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    # Kategori kullanıcının olmalı; değilse başkasının kataloğuna ürün yazılırdı
    category = get_owned_category(db, current_user, category_id)
    if category is None:
        return HTMLResponse("Kategori bulunamadı.", status_code=404)

    new_product = Product(
        name=build_product_name(brand, technical_specs, category.name),
        technical_specs=technical_specs,
        brand=brand,
        category_id=category.id,
        unit_price=unit_price,
        vat_rate=vat_rate,
        unit=unit
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

    # Hatalı fiyat girilirse eski fiyatta bırak
    fiyat = parse_price(unit_price)
    if fiyat is None:
        fiyat = product.unit_price

    product.technical_specs = technical_specs
    product.brand = brand
    product.category_id = category.id
    product.unit_price = fiyat
    product.unit = unit
    product.name = build_product_name(brand, technical_specs, category.name)

    db.commit()

    # Güncellenmiş satırı HTMX ile ekrana geri bas
    return templates.TemplateResponse(request, "partials/catalog_rows.html", {"products": [product]})
