from sqlalchemy import text
from app.database import SessionLocal

def clear_tables():
    db = SessionLocal()
    try:
        # CASCADE: Bağlı ürünleri siler. RESTART IDENTITY: ID'leri 1'den başlatır.
        db.execute(text("TRUNCATE TABLE categories, products RESTART IDENTITY CASCADE;"))
        db.commit()
        print("✅ Tabloların içi başarıyla boşaltıldı ve ID'ler sıfırlandı!")
    except Exception as e:
        db.rollback()
        print(f"❌ Bir hata oluştu: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    clear_tables()