from fastapi import FastAPI, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.dependencies import require_user
from app.models import Category, Customer, Product, User
from app.routers import auth, catalog, customers


app = FastAPI(title="ElektroTakip")

app.include_router(auth.router)
app.include_router(catalog.router)
app.include_router(customers.router)


templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_user),
):
    # Ürünün sahibi kategorisi üzerinden belli olur, bu yüzden join gerekiyor
    urun_sayisi = (
        db.query(Product)
        .join(Category)
        .filter(Category.user_id == user.id)
        .count()
    )
    musteri_sayisi = db.query(Customer).filter(Customer.user_id == user.id).count()

    return templates.TemplateResponse(
        request,
        "home.html",
        {"user": user, "urun_sayisi": urun_sayisi, "musteri_sayisi": musteri_sayisi},
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/db-health")
def db_health(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1")).scalar()
    return {"database": "ok", "result": result}
