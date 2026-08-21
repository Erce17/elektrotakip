"""Teklif ekranı.

Hesabın tamamı `app/quote_engine.py`'da; burada tek bir çarpma bile yok. Bu ayrım
bilinçli: denetimde çıkan ciddi hataların hepsi hesap tarafındaydı ve arayüzden
görünmüyordu. Route'a hesap yazmak o hataları test edilemez hâle geri getirir.

Kalıp `customers.py`'dan: koruma route imzasında (`require_user`), izolasyon her
sorguda (`Quote.user_id == current_user.id`). Sahiplik zinciri tek yardımcıda
toplandı (`get_owned_quote`) — açığın tekrar açılmasını engelliyor.
"""

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from itertools import zip_longest

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app import quote_engine as motor
from app import quote_service
from app.database import get_db
from app.dependencies import require_user
from app.excel_import import normalize_currency, parse_price
from app.models import (
    Category,
    Customer,
    Product,
    Quote,
    QuoteAdjustment,
    QuoteDefaults,
    QuoteItem,
    User,
)
from app.templating import templates

router = APIRouter(prefix="/quotes", tags=["quotes"])

PARA_BIRIMLERI = ("TRY", "USD", "EUR")

# Zincire eklenebilecek adımlar. Ekranda seçenek olarak çıkıyor; motorun tanıdığı
# türlerle birebir aynı olmalı.
ZINCIR_TURLERI = {
    motor.ISKONTO_YUZDE: "İskonto (%)",
    motor.ISKONTO_TUTAR: "İskonto (tutar)",
    motor.EK_YUZDE: "Ekleme (%)",
    motor.EK_TUTAR: "Ekleme (tutar)",
}

KALEM_TURLERI = {
    motor.MALZEME: "Malzeme",
    motor.ISCILIK: "İşçilik",
    motor.DIGER: "Diğer",
}


# --- Sahiplik ------------------------------------------------------------


def get_owned_quote(db: Session, user: User, quote_id: int) -> Quote | None:
    """Teklifi sadece kullanıcıya aitse döner. Değilse None — yoksa da None."""
    return (
        db.query(Quote)
        .filter(Quote.id == quote_id, Quote.user_id == user.id)
        .first()
    )


def get_owned_item(db: Session, quote: Quote, item_id: int) -> QuoteItem | None:
    """Kalemi sadece bu teklife aitse döner. Teklifin sahipliği zaten doğrulanmış."""
    return (
        db.query(QuoteItem)
        .filter(QuoteItem.id == item_id, QuoteItem.quote_id == quote.id)
        .first()
    )


def get_owned_adjustment(db: Session, quote: Quote, adj_id: int) -> QuoteAdjustment | None:
    """Zincir satırını sadece bu teklife aitse döner."""
    return (
        db.query(QuoteAdjustment)
        .filter(QuoteAdjustment.id == adj_id, QuoteAdjustment.quote_id == quote.id)
        .first()
    )


def get_owned_product(db: Session, user: User, product_id: int) -> Product | None:
    """Ürünün sahibi kategorisi üzerinden belli olur; bu yüzden join gerekiyor."""
    return (
        db.query(Product)
        .join(Category)
        .filter(Product.id == product_id, Category.user_id == user.id)
        .first()
    )


# --- Yardımcılar ---------------------------------------------------------


def kullanici_varsayilanlari(db: Session, user: User) -> QuoteDefaults:
    """İşletme varsayılanlarını getirir, yoksa oluşturur.

    Varsayılan/istisna ayrımı ürünün tek vaadini ayakta tutan şey: kullanıcı her
    teklifte her oranı elle giriyorsa iş yine yarım saat sürer, sadece Excel yerine
    bizim ekranda sürer.
    """
    ayar = db.query(QuoteDefaults).filter(QuoteDefaults.user_id == user.id).first()
    if ayar is None:
        ayar = QuoteDefaults(user_id=user.id)
        db.add(ayar)
        db.commit()
    return ayar


def yeni_teklif_numarasi(db: Session, user: User) -> str:
    """Kullanıcı için boş bir teklif numarası üretir: '2026-001'.

    Numara kullanıcıya görünen kimlik; `(user_id, number, version)` tekil olduğu
    için revizyonlar aynı numarayı paylaşır. Boşluk aramak sayaç tutmaktan basit
    ve silinen teklif numarasını da geri kazandırıyor.
    """
    yil = date.today().year
    kullanilan = {
        no for (no,) in db.query(Quote.number).filter(Quote.user_id == user.id).distinct()
    }
    sira = 1
    while f"{yil}-{sira:03d}" in kullanilan:
        sira += 1
    return f"{yil}-{sira:03d}"


def ondalik_oku(ham: str, varsayilan: Decimal = Decimal(0)) -> Decimal:
    """Formdan gelen sayıyı okur. '1.200,50' de yazılabilsin diye `parse_price`.

    Ekranda Türkçe yazımla gösterdiğimiz bir sayıyı kullanıcı aynı şekilde geri
    yazabilmeli; ayrı bir ayrıştırıcı yazmak iki farklı kopya doğururdu.
    """
    if ham is None or str(ham).strip() == "":
        return varsayilan
    deger = parse_price(ham)
    return varsayilan if deger is None else deger


def iskonto_zinciri_oku(ham: str) -> tuple[Decimal, ...]:
    """'20/10' veya '20 10' gibi yazılmış iskonto zincirini okur.

    Sektörde zincir bu yazımla konuşuluyor ("yirmi bölü on"). Tek alanda toplamak
    kullanıcıyı her kademe için ayrı kutu doldurmaktan kurtarıyor; motor yine
    sırayla ve çarpımsal uyguluyor.
    """
    if not ham:
        return ()
    parcalar = str(ham).replace("/", " ").replace("+", " ").replace(",", ".").split()
    oranlar = []
    for parca in parcalar:
        try:
            oran = Decimal(parca.strip().rstrip("%"))
        except (InvalidOperation, ValueError):
            continue
        if 0 < oran < 100:
            oranlar.append(oran)
    return tuple(oranlar)


def zincir_sirasi(quote: Quote) -> int:
    """Zincirin sonuna eklenecek satırın sırası."""
    return max((a.position for a in quote.adjustments), default=-1) + 1


def govde_yaniti(request: Request, db: Session, quote: Quote) -> HTMLResponse:
    """Teklifin kalem + zincir + toplam bölümünü yeniden çizer.

    Her değişiklikten sonra tek parça dönüyoruz: bir kalemin iskontosu teklifin
    toplamını da değiştiriyor, kısmi güncelleme ikisini ayrı tutmayı gerektirirdi.
    """
    db.refresh(quote)
    return templates.TemplateResponse(
        request,
        "partials/quote_body.html",
        govde_baglami(db, quote),
    )


def govde_baglami(db: Session, quote: Quote) -> dict:
    sonuc = quote_service.hesapla(quote)

    # Motorun çıktısını DB kaydıyla açıkça eşleştiriyoruz. Şablonda indeks saymak
    # bileşen kalemleri devreye girdiği gün sessizce kayardı: motor bileşenleri
    # atlıyor, `quote.items` atlamıyor. Ayrıca zincirin eklediği satırların
    # (işçilik, nakliye) DB karşılığı yok — onlar `None` ile eşleşiyor.
    kalem_ciftleri = list(
        zip_longest(sonuc.kalemler, quote_service.hesaba_giren_kalemler(quote))
    )
    zincir_ciftleri = list(zip(sonuc.zincir, quote_service.zincir_satirlari(quote)))

    return {
        "quote": quote,
        "sonuc": sonuc,
        "kalem_ciftleri": kalem_ciftleri,
        "zincir_ciftleri": zincir_ciftleri,
        "zincir_turleri": ZINCIR_TURLERI,
        "kalem_turleri": KALEM_TURLERI,
        "urunler": (
            db.query(Product)
            .join(Category)
            .filter(Category.user_id == quote.user_id)
            .order_by(Product.name.asc())
            .limit(500)
            .all()
        ),
    }


# --- Liste ve oluşturma --------------------------------------------------


@router.get("", response_class=HTMLResponse)
def get_quotes_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Teklif listesi. Sadece giriş yapan kullanıcının teklifleri."""
    quotes = (
        db.query(Quote)
        .filter(Quote.user_id == current_user.id)
        .order_by(Quote.created_at.desc(), Quote.id.desc())
        .all()
    )
    customers = (
        db.query(Customer)
        .filter(Customer.user_id == current_user.id)
        .order_by(Customer.name.asc())
        .all()
    )
    # Listede toplam göstermek için her teklif hesaplanıyor. Hesap DB'ye gitmiyor,
    # kalemler zaten yüklü; teklif sayısı büyürse burası sayfalanır.
    toplamlar = {q.id: quote_service.hesapla(q).genel_toplam for q in quotes}

    return templates.TemplateResponse(
        request,
        "quotes.html",
        {
            "quotes": quotes,
            "customers": customers,
            "toplamlar": toplamlar,
            "yeni_numara": yeni_teklif_numarasi(db, current_user),
        },
    )


@router.post("")
def create_quote(
    title: str = Form(""),
    customer_id: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Yeni teklif açar ve varsayılan iskonto zincirini kopyalar.

    Kopyalanır, bağlanmaz: müşterinin varsayılanı sonradan değişse geçmiş teklif
    kendiliğinden bozulmasın. Teklif kurulduktan sonra kendi zincirinin sahibi.
    """
    ayar = kullanici_varsayilanlari(db, current_user)

    customer = None
    if customer_id:
        customer = (
            db.query(Customer)
            .filter(Customer.id == int(customer_id), Customer.user_id == current_user.id)
            .first()
        )

    # Müşterinin kendi zinciri varsa o, yoksa işletme şablonu.
    sablon = (customer.default_adjustments if customer else None) or ayar.adjustment_template

    quote = Quote(
        user_id=current_user.id,
        customer_id=customer.id if customer else None,
        number=yeni_teklif_numarasi(db, current_user),
        title=title or None,
        currency=ayar.currency,
        valid_until=date.today() + timedelta(days=ayar.validity_days),
        adjustments=quote_service.sablondan_zincir(sablon),
    )
    db.add(quote)
    db.commit()

    return RedirectResponse(url=f"/quotes/{quote.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/{quote_id}", response_class=HTMLResponse)
def get_quote_page(
    request: Request,
    quote_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    quote = get_owned_quote(db, current_user, quote_id)
    if quote is None:
        return HTMLResponse("Teklif bulunamadı.", status_code=404)

    baglam = govde_baglami(db, quote)
    baglam["customers"] = (
        db.query(Customer)
        .filter(Customer.user_id == current_user.id)
        .order_by(Customer.name.asc())
        .all()
    )
    baglam["para_birimleri"] = PARA_BIRIMLERI
    return templates.TemplateResponse(request, "quote_detail.html", baglam)


@router.post("/{quote_id}")
def update_quote(
    quote_id: int,
    title: str = Form(""),
    customer_id: str = Form(""),
    currency: str = Form("TRY"),
    valid_until: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Teklif başlığını günceller. Kalemlerin dondurulmuş fiyatına dokunmaz."""
    quote = get_owned_quote(db, current_user, quote_id)
    if quote is None:
        return HTMLResponse("Teklif bulunamadı.", status_code=404)

    quote.title = title or None
    quote.notes = notes or None
    quote.currency = normalize_currency(currency) or "TRY"
    if customer_id:
        sahibi_dogru = (
            db.query(Customer)
            .filter(Customer.id == int(customer_id), Customer.user_id == current_user.id)
            .first()
        )
        quote.customer_id = sahibi_dogru.id if sahibi_dogru else None
    else:
        quote.customer_id = None
    if valid_until:
        quote.valid_until = date.fromisoformat(valid_until)
    db.commit()

    return RedirectResponse(url=f"/quotes/{quote.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{quote_id}/delete")
def delete_quote(
    quote_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    quote = get_owned_quote(db, current_user, quote_id)
    if quote:
        db.delete(quote)
        db.commit()
    return RedirectResponse(url="/quotes", status_code=status.HTTP_303_SEE_OTHER)


# --- Kalemler ------------------------------------------------------------


@router.post("/{quote_id}/items", response_class=HTMLResponse)
def add_item(
    request: Request,
    quote_id: int,
    product_id: str = Form(""),
    name: str = Form(""),
    quantity: str = Form("1"),
    unit_price: str = Form("0"),
    unit: str = Form("Adet"),
    kind: str = Form(motor.MALZEME),
    vat_rate: str = Form("20"),
    source_currency: str = Form(""),
    fx_rate: str = Form("1"),
    discounts: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Teklife kalem ekler. Katalogdan ya da elle.

    Katalogdan gelirse fiyat ve kur **teklif anında dondurulur** — ürünle canlı bağ
    kurulmaz. Kablo fiyatı bakıra ve dolara endeksli, günlük oynuyor; bağ kurulsaydı
    katalog güncellenince geçmiş teklifler kendiliğinden bozulurdu.
    """
    quote = get_owned_quote(db, current_user, quote_id)
    if quote is None:
        return HTMLResponse("Teklif bulunamadı.", status_code=404)

    miktar = ondalik_oku(quantity, Decimal(1))
    kur = ondalik_oku(fx_rate, Decimal(1)) or Decimal(1)
    iskontolar = iskonto_zinciri_oku(discounts)

    if product_id:
        urun = get_owned_product(db, current_user, int(product_id))
        if urun is None:
            return HTMLResponse("Ürün bulunamadı.", status_code=404)
        item = quote_service.kalem_kur(urun, miktar=miktar, kur=kur, iskontolar=iskontolar)
    else:
        # Elle kalem: işçilik ve "diğer" kalemler katalogda durmuyor.
        if not name.strip():
            return HTMLResponse("Kalem adı gerekli.", status_code=400)
        kaynak_fiyat = ondalik_oku(unit_price)
        item = QuoteItem(
            name=name.strip(),
            unit=unit or "Adet",
            kind=kind if kind in KALEM_TURLERI else motor.DIGER,
            quantity=miktar,
            source_currency=normalize_currency(source_currency) or quote.currency,
            source_unit_price=kaynak_fiyat,
            fx_rate=kur,
            unit_price=motor.kur_uygula(kaynak_fiyat, kur),
            vat_rate=ondalik_oku(vat_rate, Decimal(20)),
            # İşçilik sektörde genelde iskontoya girmez. Bu bir varsayılan,
            # kural değil — kullanıcı kalem üzerinden değiştirebiliyor.
            discountable=kind != motor.ISCILIK,
            adjustments=[
                QuoteAdjustment(position=sira, kind=motor.ISKONTO_YUZDE, value=oran)
                for sira, oran in enumerate(iskontolar)
            ],
        )

    item.position = max((i.position for i in quote.items), default=-1) + 1
    quote.items.append(item)
    db.commit()

    return govde_yaniti(request, db, quote)


@router.post("/{quote_id}/items/{item_id}", response_class=HTMLResponse)
def update_item(
    request: Request,
    quote_id: int,
    item_id: int,
    quantity: str = Form(""),
    unit_price: str = Form(""),
    vat_rate: str = Form(""),
    discounts: str = Form(""),
    discountable: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Kalemi günceller. Fiyat elle değiştirilebilir — teklif kendi kopyasının sahibi."""
    quote = get_owned_quote(db, current_user, quote_id)
    if quote is None:
        return HTMLResponse("Teklif bulunamadı.", status_code=404)
    item = get_owned_item(db, quote, item_id)
    if item is None:
        return HTMLResponse("Kalem bulunamadı.", status_code=404)

    if quantity:
        item.quantity = ondalik_oku(quantity, Decimal(1))
    if unit_price:
        yeni = ondalik_oku(unit_price)
        # Elle girilen fiyat teklifin para biriminde: kur zaten uygulanmış sayılır.
        item.source_unit_price = yeni
        item.unit_price = yeni
        item.fx_rate = Decimal(1)
        item.source_currency = quote.currency
    if vat_rate:
        item.vat_rate = ondalik_oku(vat_rate, Decimal(20))
    item.discountable = discountable

    # Kalem zincirini baştan kur: kısmi güncelleme sırayı bozar.
    for eski in list(item.adjustments):
        db.delete(eski)
    item.adjustments = [
        QuoteAdjustment(position=sira, kind=motor.ISKONTO_YUZDE, value=oran)
        for sira, oran in enumerate(iskonto_zinciri_oku(discounts))
    ]
    db.commit()

    return govde_yaniti(request, db, quote)


@router.delete("/{quote_id}/items/{item_id}", response_class=HTMLResponse)
def delete_item(
    request: Request,
    quote_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    quote = get_owned_quote(db, current_user, quote_id)
    if quote is None:
        return HTMLResponse("Teklif bulunamadı.", status_code=404)
    item = get_owned_item(db, quote, item_id)
    if item is not None:
        db.delete(item)
        db.commit()

    return govde_yaniti(request, db, quote)


# --- Hesap zinciri -------------------------------------------------------


@router.post("/{quote_id}/adjustments", response_class=HTMLResponse)
def add_adjustment(
    request: Request,
    quote_id: int,
    kind: str = Form(...),
    value: str = Form("0"),
    label: str = Form(""),
    base: str = Form(motor.TABAN_YURUYEN),
    scope: str = Form(motor.KAPSAM_ISKONTOYA_TABI),
    vat_rate: str = Form(""),
    added_kind: str = Form(motor.DIGER),
    added_discountable: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Zincire yeni bir adım ekler. Sona eklenir; sıra sonucu değiştirir."""
    quote = get_owned_quote(db, current_user, quote_id)
    if quote is None:
        return HTMLResponse("Teklif bulunamadı.", status_code=404)
    if kind not in ZINCIR_TURLERI:
        return HTMLResponse("Bilinmeyen zincir adımı.", status_code=400)

    quote.adjustments.append(
        QuoteAdjustment(
            position=zincir_sirasi(quote),
            kind=kind,
            value=ondalik_oku(value),
            label=label.strip() or None,
            base=base if base in (motor.TABAN_YURUYEN, motor.TABAN_KALEM_TOPLAMI)
            else motor.TABAN_YURUYEN,
            scope=scope if scope in (motor.KAPSAM_ISKONTOYA_TABI, motor.KAPSAM_TUMU)
            else motor.KAPSAM_ISKONTOYA_TABI,
            # Sadece ek satırlarında anlamlı; boşsa motor işletme varsayılanını kullanır.
            vat_rate=ondalik_oku(vat_rate) if vat_rate else None,
            added_kind=added_kind if added_kind in KALEM_TURLERI else motor.DIGER,
            added_discountable=added_discountable,
        )
    )
    db.commit()

    return govde_yaniti(request, db, quote)


@router.delete("/{quote_id}/adjustments/{adj_id}", response_class=HTMLResponse)
def delete_adjustment(
    request: Request,
    quote_id: int,
    adj_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    quote = get_owned_quote(db, current_user, quote_id)
    if quote is None:
        return HTMLResponse("Teklif bulunamadı.", status_code=404)
    adjustment = get_owned_adjustment(db, quote, adj_id)
    if adjustment is not None:
        db.delete(adjustment)
        db.commit()

    return govde_yaniti(request, db, quote)


@router.post("/{quote_id}/adjustments/{adj_id}/move", response_class=HTMLResponse)
def move_adjustment(
    request: Request,
    quote_id: int,
    adj_id: int,
    yon: str = Form("up"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Zincir adımını bir yukarı/aşağı taşır.

    Sıranın değiştirilebilir olması ürünün varlık sebebi: iskonto önce mi işçilik
    önce mi sorusunun cevabı işletmeye göre değişiyor ve sonucu değiştiriyor.
    """
    quote = get_owned_quote(db, current_user, quote_id)
    if quote is None:
        return HTMLResponse("Teklif bulunamadı.", status_code=404)

    sirali = sorted(quote.adjustments, key=lambda a: a.position)
    indeks = next((i for i, a in enumerate(sirali) if a.id == adj_id), None)
    if indeks is None:
        return HTMLResponse("Zincir adımı bulunamadı.", status_code=404)

    hedef = indeks - 1 if yon == "up" else indeks + 1
    if 0 <= hedef < len(sirali):
        sirali[indeks], sirali[hedef] = sirali[hedef], sirali[indeks]
        # Sırayı baştan numaralandır: takas sonrası boşluk kalmasın.
        for yeni_sira, adim in enumerate(sirali):
            adim.position = yeni_sira
        db.commit()

    return govde_yaniti(request, db, quote)
