from fastapi import APIRouter, Depends, Request, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Customer, User

router = APIRouter(
    prefix="/customers",
    tags=["customers"]
)

templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def get_customers_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """Müşteri listesi sayfasını yükler (sadece giriş yapan kullanıcınınkiler)."""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    customers = (
        db.query(Customer)
        .filter(Customer.user_id == current_user.id)
        .order_by(Customer.name.asc())
        .all()
    )
    return templates.TemplateResponse(
        request,
        "customers.html",
        {"customers": customers}
    )


@router.post("/", response_class=RedirectResponse)
def create_customer(
    name: str = Form(...),
    phone: str = Form(""),
    address: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """Yeni müşteri ekler ve sayfayı yeniler."""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    new_customer = Customer(
        name=name,
        phone=phone,
        address=address,
        user_id=current_user.id,  # giriş yapan gerçek kullanıcı
    )
    db.add(new_customer)
    db.commit()

    return RedirectResponse(url="/customers", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/{customer_id}/edit", response_class=HTMLResponse)
def edit_customer_form(
    request: Request,
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """Düzenle'ye basınca satırı forma çevirir."""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.user_id == current_user.id)
        .first()
    )
    if customer is None:
        return HTMLResponse("", status_code=404)

    return templates.TemplateResponse(
        request, "partials/customer_edit_row.html", {"customer": customer}
    )


@router.get("/{customer_id}/row", response_class=HTMLResponse)
def get_single_customer_row(
    request: Request,
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """İptal'e basınca veya kaydettikten sonra satırın normal halini döndürür."""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.user_id == current_user.id)
        .first()
    )
    if customer is None:
        return HTMLResponse("", status_code=404)

    return templates.TemplateResponse(
        request, "partials/customer_rows.html", {"customers": [customer]}
    )


@router.put("/{customer_id}", response_class=HTMLResponse)
def update_customer(
    request: Request,
    customer_id: int,
    name: str = Form(...),
    phone: str = Form(""),
    address: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """Müşteri bilgilerini günceller, normal satırı geri döndürür."""
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.user_id == current_user.id)
        .first()
    )
    if customer is None:
        return HTMLResponse("", status_code=404)

    customer.name = name
    customer.phone = phone
    customer.address = address
    db.commit()

    return templates.TemplateResponse(
        request, "partials/customer_rows.html", {"customers": [customer]}
    )


@router.delete("/{customer_id}", response_class=HTMLResponse)
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user),
):
    """Müşteriyi siler. Boş içerik dönünce HTMX satırı yok eder."""
    if current_user is None:
        return HTMLResponse("", status_code=401)

    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.user_id == current_user.id)
        .first()
    )
    if customer:
        db.delete(customer)
        db.commit()

    return HTMLResponse("")