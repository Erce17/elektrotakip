from fastapi import FastAPI, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session


from app.database import get_db

app = FastAPI(title="ElektroTakip")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/db-health")
def db_health(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1")).scalar()
    return {"database": "ok", "result": result}