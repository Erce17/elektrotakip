import io
from decimal import Decimal
from urllib.parse import urlencode

import openpyxl
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.templating import templates
from app.dependencies import require_user
from app.models import Category, Product, User
from app.product_search import parametreleri_coz, urun_ara
# Fiyat/birim ayrıştırma ve dosya okuma saf katmanda; router yalnızca kullanır.
# İsimler burada da bağlı kalıyor: mevcut testler `app.routers.catalog` üzerinden
# içe aktarıyor ve bu modül onların doğal adresi.
from app.excel_import import (  # noqa: F401
    ADET_BAZLI_BIRIMLER,
    BIRIM_KARSILIKLARI,
    KM_METRE,
    MAX_IMPORT_BYTES,
    MAX_UNIT_PRICE,
    PRICE_DECIMALS,
    OkunamadiHatasi,
    normalize_currency,
    normalize_unit,
    oku as excel_oku,
    parse_price,
    quantize_price,
    sayfa_adi_kategori_olur_mu,
)

router = APIRouter(
    prefix="/catalog",
    tags=["Catalog"]
)


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


def build_product_name(brand: str, technical_specs: str, category_name: str) -> str:
    """Ürün adını parçalardan derler: 'Marka Özellik Kategori'."""
    return " ".join(p for p in (brand, technical_specs, category_name) if p).strip()


def kategori_adini_sec(kayit) -> str:
    """Satırın hangi kategoriye gireceğine karar verir.

    Sıra: grup sütunu → sayfa adı → 'Diğer'. Grup sütunu olmayan dosyalarda
    (Öznur, Pofaco) sayfa adı tek anlamlı ipucu; ama 'Sayfa1' gibi Excel'in kendi
    verdiği adlar bilgi taşımadığı için elenir.
    """
    if kayit.grup:
        return kayit.grup
    if sayfa_adi_kategori_olur_mu(kayit.sayfa):
        return kayit.sayfa
    return "Diğer"


def urun_kimligi(category_id: int, kayit, spec: str, parametre) -> tuple:
    """Mükerrer tespitinde kullanılacak kimlik.

    Tedarikçi kodu varsa o kullanılır: aynı ürün listede iki farklı açıklamayla
    geçebiliyor, kod ise tekil.

    Kod yoksa **parametreler kimliğe dahil edilmeli.** Öznur'un 1673 satırında kod
    yok ve ürün adı 5 satırda birebir aynı; ürünleri ayıran şey kesit. Parametreler
    kimliğe girmediğinde 1673 satırın 1614'ü mükerrer sanılıp atılıyordu — kablo
    kataloğunun tamamı 59 ürüne iniyordu.
    """
    if kayit.kod:
        return (category_id, "kod", kayit.kod)
    return (
        category_id,
        spec,
        kayit.marka,
        parametre.cross_section,
        parametre.core_count,
    )


def mevcut_urun_var_mi(db: Session, category_id: int, kayit, spec: str, parametre) -> bool:
    """Ürün bu kategoride zaten kayıtlı mı. Kimlik kuralı `urun_kimligi` ile aynı."""
    sorgu = db.query(Product).filter(Product.category_id == category_id)
    if kayit.kod:
        return sorgu.filter(Product.supplier_code == kayit.kod).first() is not None
    return (
        sorgu.filter(
            Product.technical_specs == spec,
            Product.brand == kayit.marka,
            Product.cross_section.is_(None) if parametre.cross_section is None
            else Product.cross_section == parametre.cross_section,
            Product.core_count.is_(None) if parametre.core_count is None
            else Product.core_count == parametre.core_count,
        ).first()
        is not None
    )


def parametre_etiketi(parametre) -> str:
    """Parametreleri ürün adına girecek kısa etikete çevirir: '3x2.5 mm²'.

    Ürün adı `marka + özellik + kategori` olarak derleniyordu ve Öznur'da aynı ad
    onlarca satırda tekrar ediyordu — liste okunmuyordu. Kesit adın içinde olunca
    kullanıcı listeye bakıp ayırt edebiliyor.
    """
    if parametre.cross_section is None:
        return ""
    kesit = format(parametre.cross_section.normalize(), "f")
    if parametre.core_count:
        return f"{parametre.core_count}x{kesit} mm²"
    return f"{kesit} mm²"


def fiyati_coz(kayit, is_km_price: bool) -> tuple[Decimal, str, bool]:
    """Satırın fiyatını ve birimini kaydedilecek hâle getirir.

    `(fiyat, birim, sorunlu)` döner. `sorunlu` True ise fiyat 0 yazıldı ve
    kullanıcının düzeltmesi gerekiyor — satır atılmıyor, ürün girsin.
    """
    fiyat = kayit.fiyat
    birim = kayit.birim
    if fiyat is None:
        # 'Bilgi Alınız' (Tense), 'FİYAT SORUNUZ', 'KDV DAHİL NET FİYAT' (Grup Arge)
        return Decimal(0), birim, True

    # KM → metre dönüşümü satır bazlı: tedarikçi dosyalarında birimler karışık
    # geliyor, tek kutucuk dosyanın tamamı için doğru olmuyor. Satır KM diyorsa
    # her hâlükârda çevrilir (Öznur 'TL/km'). Kutucuk işaretliyse metre ve birimi
    # belirtilmemiş satırlar da çevrilir; adet bazlı olanlara (kutu, paket,
    # takım...) dokunulmaz — yanlış çevrimin asıl kaynağı buydu.
    satir_km = birim == "KM" or (is_km_price and birim not in ADET_BAZLI_BIRIMLER)
    if satir_km and fiyat > 0:
        fiyat = fiyat / KM_METRE
        birim = "Metre"

    if fiyat > MAX_UNIT_PRICE:
        # DB kolonunun sınırını aşıyor; kaydetmeye çalışırsak içe aktarmanın
        # tamamı çöker. Ürünü al, fiyatı kullanıcı düzeltsin.
        return Decimal(0), birim, True

    return quantize_price(fiyat), birim, False


def import_result_redirect(
    eklendi: int = 0,
    atlandi: int = 0,
    fiyatsiz: int = 0,
    hata: str = "",
    atlanan_sayfalar: list[str] | None = None,
) -> RedirectResponse:
    """İçe aktarma sonucunu /catalog'a query string ile taşır.

    POST sonrası yönlendirme yapıldığı için sonuç bir sonraki istekte lazım;
    oturumda flash mesajı tutmak yerine URL'de taşımak yeterli.

    Atlanan sayfa adları da taşınıyor: çok sayfalı dosyada bir sayfanın fiyat
    sütunu yoksa (Molwex 'Tüm Kodlar') kullanıcı eksik ürünün sebebini görsün.
    """
    params = {"eklendi": eklendi, "atlandi": atlandi, "fiyatsiz": fiyatsiz}
    if atlanan_sayfalar:
        params["atlanan_sayfalar"] = ", ".join(atlanan_sayfalar)
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
    atlanan_sayfalar: str = Query(""),
    guncellendi: int = Query(-1),
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
        ic_aktarma = {
            "eklendi": eklendi,
            "atlandi": atlandi,
            "fiyatsiz": fiyatsiz,
            "atlanan_sayfalar": atlanan_sayfalar,
        }

    return templates.TemplateResponse(
        request,
        "catalog.html",
        {
            "categories": categories,
            "products": products,
            "ic_aktarma": ic_aktarma,
            "guncellendi": guncellendi,
        },
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


@router.post("/reparse-parameters")
def reparse_parameters(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Mevcut ürünlerin aranabilir parametrelerini yeniden çıkarır.

    Parametreler içe aktarma sırasında çıkarılıyor. Bu route, parametre alanları
    eklenmeden ÖNCE içe aktarılmış katalogları kurtarmak için var — onlar olmadan
    o ürünler kesitle aranamıyor. Ayrıştırıcı geliştiğinde de yeniden koşturulabilir.

    Elle girilmiş değeri ezmemek için yalnızca parametresi boş olan ürünlere dokunur.
    """
    guncellendi = 0
    for urun in user_products(db, current_user).filter(Product.cross_section.is_(None)):
        parametre = parametreleri_coz(urun.name, urun.technical_specs or "")
        if parametre.bos_mu:
            continue
        urun.cross_section = parametre.cross_section
        urun.core_count = parametre.core_count
        urun.conductor = parametre.conductor
        urun.insulation = parametre.insulation
        urun.sheathed = parametre.sheathed
        guncellendi += 1
    db.commit()

    return RedirectResponse(
        url="/catalog?" + urlencode({"guncellendi": guncellendi}),
        status_code=status.HTTP_303_SEE_OTHER,
    )


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
    """Tedarikçi fiyat listesini kataloğa aktarır. Sonucu özet olarak /catalog'a taşır.

    Dosyanın ayrıştırılması `app/excel_import.py`'da; burada yapılan iş kayıtları
    ürüne çevirmek ve sahiplik/mükerrer kurallarını uygulamak.
    """
    dosya_adi = (file.filename or "").lower()
    if not dosya_adi.endswith((".xlsx", ".xls")):
        return import_result_redirect(hata="Sadece .xlsx veya .xls dosyası yükleyebilirsin.")

    contents = await file.read()
    if not contents:
        return import_result_redirect(hata="Dosya boş görünüyor.")
    if len(contents) > MAX_IMPORT_BYTES:
        return import_result_redirect(
            hata=f"Dosya çok büyük (en fazla {MAX_IMPORT_BYTES // (1024 * 1024)} MB)."
        )

    try:
        okunan = excel_oku(contents, dosya_adi)
    except OkunamadiHatasi:
        return import_result_redirect(
            hata="Dosya okunamadı. Bozuk, şifreli veya desteklenmeyen bir biçim olabilir."
        )

    if not okunan.sayfalar or all(s.baslik_satiri is None for s in okunan.sayfalar):
        return import_result_redirect(
            hata="Dosyada fiyat sütunu bulunamadı. Başlık satırında 'Fiyat' benzeri "
                 "bir sütun olmalı."
        )

    eklendi = 0
    atlandi = 0
    fiyatsiz = 0
    # Aynı dosya içindeki mükerrerleri yakalamak için: DB sorgusu henüz
    # commit edilmemiş satırları görmez.
    bu_dosyada_gorulen = set()
    kategori_onbellegi: dict[str, Category] = {}

    for kayit in okunan.satirlar:
        kategori_adi = kategori_adini_sec(kayit)

        # Kategori aramasında user_id şart: aynı isim başka kullanıcıda da olabilir
        category = kategori_onbellegi.get(kategori_adi)
        if category is None:
            category = (
                db.query(Category)
                .filter(Category.name == kategori_adi, Category.user_id == current_user.id)
                .first()
            )
            if not category:
                category = Category(name=kategori_adi, user_id=current_user.id)
                db.add(category)
                db.flush()  # id lazım; commit dosyanın tamamı bitince
            kategori_onbellegi[kategori_adi] = category

        spec = kayit.aciklama or kayit.ad

        # Aranabilir parametreler içe aktarma sırasında çıkarılıyor: ürün ne zaman
        # girdiyse o zaman aranabilir olmalı. Çıkarılamayanlar NULL kalır ve ürün
        # metinle bulunmaya devam eder. Mükerrer kimliği de bunlara bakıyor.
        parametre = parametreleri_coz(kayit.ad, kayit.aciklama, kesit_metni=kayit.kesit)

        kimlik = urun_kimligi(category.id, kayit, spec, parametre)
        if kimlik in bu_dosyada_gorulen:
            atlandi += 1
            continue
        if mevcut_urun_var_mi(db, category.id, kayit, spec, parametre):
            atlandi += 1
            continue

        fiyat, birim, fiyat_sorunlu = fiyati_coz(kayit, is_km_price)
        if fiyat_sorunlu:
            fiyatsiz += 1

        db.add(Product(
            name=build_product_name(
                kayit.marka,
                " ".join(p for p in (spec or kayit.kod, parametre_etiketi(parametre)) if p),
                kategori_adi,
            ),
            brand=kayit.marka,
            category_id=category.id,
            technical_specs=spec,
            supplier_code=kayit.kod or None,
            unit_price=fiyat,
            cross_section=parametre.cross_section,
            core_count=parametre.core_count,
            conductor=parametre.conductor,
            insulation=parametre.insulation,
            sheathed=parametre.sheathed,
            # Para birimi dosyada yoksa TL varsayılır: Klemsan tamamen EURO,
            # Grup Arge aynı dosyada TL ve USD veriyor — sütun varsa ona uyulur.
            currency=kayit.para_birimi or "TRY",
            unit=birim or "Adet",
        ))
        bu_dosyada_gorulen.add(kimlik)
        eklendi += 1

    # Tek commit: dosya yarıda hata verirse katalog yarım kalmaz
    db.commit()
    return import_result_redirect(
        eklendi=eklendi,
        atlandi=atlandi,
        fiyatsiz=fiyatsiz,
        atlanan_sayfalar=okunan.atlanan_sayfalar,
    )


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

    parametre = parametreleri_coz(technical_specs, brand)
    new_product = Product(
        name=build_product_name(brand, technical_specs, category.name),
        technical_specs=technical_specs,
        brand=brand,
        category_id=category.id,
        unit_price=quantize_price(fiyat),
        vat_rate=vat_rate,
        unit=normalize_unit(unit) or "Adet",
        cross_section=parametre.cross_section,
        core_count=parametre.core_count,
        conductor=parametre.conductor,
        insulation=parametre.insulation,
        sheathed=parametre.sheathed,
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
    """HTMX ile canlı malzeme araması yapar.

    Sahada konuşulan ifadeyi anlıyor: "3x2.5 NYY" → 3 damar + 2,5 mm² + adı NYY'ye
    uyanlar. Ayrıştırma `app/product_search.py`'da; buradaki tek iş sahiplik
    filtresini koymak.
    """
    query = user_products(db, current_user)
    products = urun_ara(query, Product, q, limit=200) if q else query.limit(200).all()

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
