from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Category, Product 
import io
import openpyxl
from fastapi import UploadFile, File 
from fastapi import Query
from fastapi import Form


router = APIRouter(
    prefix="/catalog",
    tags=["Catalog"]
)

templates = Jinja2Templates(directory="app/templates")

# İleride get_current_user dependency'si eklediğinde route'ları korumaya alacağız.
# Şimdilik geliştirme aşamasında olduğumuz için basit tutuyoruz.

@router.get("/", response_class=HTMLResponse)
def get_catalog_page(request: Request, db: Session = Depends(get_db)):
    """Katalog ana sayfasını ve mevcut kategori/ürünleri listeler."""
    # Şimdilik tüm kategorileri ve ürünleri çekiyoruz. Auth tam oturduğunda 
    # filter(Category.user_id == current_user.id) eklenecek.
    categories = db.query(Category).all()
    products = db.query(Product).all()
    
    return templates.TemplateResponse(
        request, 
        "catalog.html", 
        {"categories": categories, "products": products}
    )

@router.post("/category")
def create_category(
    name: str = Form(...),
    db: Session = Depends(get_db)
):
    """Yeni bir kategori oluşturur."""
    # current_user entegre edilene kadar user_id'yi manuel 1 veriyoruz
    new_category = Category(name=name, user_id=1) 
    db.add(new_category)
    db.commit()
    
    # HTMX ile eklendiğinde aynı sayfaya geri dönüp yenilenmiş halini göstersin
    return RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/download-template")
def download_excel_template():
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
    db: Session = Depends(get_db)
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
        
        fiyat = 0.0
        if col_fiyat is not None:
            if isinstance(col_fiyat, (int, float)):
                fiyat = float(col_fiyat)
            else:
                raw_price = str(col_fiyat).upper().replace("TL", "").replace(" ", "").strip()
                try:
                    if "." in raw_price and "," in raw_price:
                        raw_price = raw_price.replace(".", "")
                    raw_price = raw_price.replace(",", ".")
                    fiyat = float(raw_price)
                except ValueError:
                    fiyat = 0.0

        # YENİ: Eğer kullanıcı "Bu fiyatlar KM bazlıdır" dediyse, anında 1000'e böl
        birim = col_birim
        if is_km_price and fiyat > 0:
            fiyat = fiyat / 1000.0
            birim = "Metre"

        malzeme_adi = f"{col_marka} {col_spec} {col_kat}".strip()

        category = db.query(Category).filter(Category.name == col_kat).first()
        if not category:
            category = Category(name=col_kat, user_id=1)
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
    db: Session = Depends(get_db)
):
    # Kategoriyi bul
    category = db.query(Category).filter(Category.id == category_id).first()
    kat_adi = category.name if category else ""

    # İsmi otomatik oluştur
    otomatik_isim = f"{brand} {technical_specs} {kat_adi}".strip()

    new_product = Product(
        name=otomatik_isim,
        technical_specs=technical_specs,
        brand=brand,
        category_id=category_id,
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
    db: Session = Depends(get_db)
):
    """HTMX ile canlı malzeme araması yapar."""
    if q:
        # İsim, marka veya teknik özellikte arama yap (büyük/küçük harf duyarsız)
        search_term = f"%{q}%"
        products = db.query(Product).filter(
            (Product.name.ilike(search_term)) | 
            (Product.brand.ilike(search_term)) |
            (Product.technical_specs.ilike(search_term))
        ).all()
    else:
        # Arama kutusu boşsa tümünü getir
        products = db.query(Product).all()
        
    # Sadece tablo satırlarını (tbody içeriğini) render edip döndürüyoruz
    return templates.TemplateResponse(
        request, 
        "partials/catalog_rows.html", 
        {"products": products}
    )

@router.delete("/product/{product_id}", response_class=HTMLResponse)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """HTMX ile arayüzden malzeme siler."""
    product = db.query(Product).filter(Product.id == product_id).first()
    
    if product:
        db.delete(product)
        db.commit()
        
    # HTMX hx-swap="outerHTML" ile tetiklendiğinde boş dönen bu string, 
    # HTML tablosundaki o satırın (<tr>) anında yok olmasını sağlar.
    return ""

@router.get("/product/{product_id}/edit", response_class=HTMLResponse)
def edit_product_form(request: Request, product_id: int, db: Session = Depends(get_db)):
    """Düzenleme butonuna basıldığında tablo satırını forma çeviren HTML'i döndürür."""
    product = db.query(Product).filter(Product.id == product_id).first()
    categories = db.query(Category).all()
    
    return templates.TemplateResponse(
        request, 
        "partials/catalog_edit_row.html", 
        {"product": product, "categories": categories}
    )

@router.get("/product/{product_id}", response_class=HTMLResponse)
def get_single_product(request: Request, product_id: int, db: Session = Depends(get_db)):
    """Düzenlemekten vazgeçildiğinde (İptal) veya kaydedildiğinde satırın normal halini döndürür."""
    product = db.query(Product).filter(Product.id == product_id).first()
    # Tek bir ürünü, aynı tablo döngüsüne [liste] içinde gönderiyoruz
    return templates.TemplateResponse(request, "partials/catalog_rows.html", {"products": [product]})

@router.put("/product/{product_id}", response_class=HTMLResponse)
def update_product(
    request: Request,
    product_id: int,
    technical_specs: str = Form(""),
    brand: str = Form(""),
    category_id: int = Form(...),
    unit_price: str = Form(...), # Virgülden dolayı string alıp temizliyoruz
    unit: str = Form("Adet"),
    db: Session = Depends(get_db)
):
    """Değişiklikleri veritabanına kaydeder."""
    product = db.query(Product).filter(Product.id == product_id).first()
    
    # Fiyat Temizliği (Kullanıcı 1.200,50 de yazsa 1200.50 de yazsa anlar)
    try:
        raw_price = str(unit_price).upper().replace("TL", "").strip()
        if "." in raw_price and "," in raw_price:
            raw_price = raw_price.replace(".", "")
        raw_price = raw_price.replace(",", ".")
        fiyat = float(raw_price)
    except ValueError:
        fiyat = product.unit_price # Hatalı girilirse eski fiyatta bırak

    # Kategori adını bul (Otomatik isimlendirme için)
    category = db.query(Category).filter(Category.id == category_id).first()
    kat_adi = category.name if category else ""

    # Değerleri Güncelle
    product.technical_specs = technical_specs
    product.brand = brand
    product.category_id = category_id
    product.unit_price = fiyat
    product.unit = unit
    product.name = f"{brand} {technical_specs} {kat_adi}".strip() # İsmi yeniden derle
    
    db.commit()
    
    # Güncellenmiş satırı HTMX ile ekrana geri bas
    return templates.TemplateResponse(request, "partials/catalog_rows.html", {"products": [product]})