from sqlalchemy import Boolean, Column, Integer, String, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # İlişkiler
    owner = relationship("User", back_populates="categories")
    products = relationship("Product", back_populates="category", cascade="all, delete-orphan")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    brand = Column(String)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    
    # Numeric(12,4): 8 tam + 4 ondalık basamak. Ondalık 2 iken KM fiyatı metreye
    # bölününce ucuz malzemelerin fiyatı sıfıra yuvarlanıyordu (0,004 → 0,00).
    unit_price = Column(Numeric(12, 4), nullable=False)
    vat_rate = Column(Integer, default=20)
    unit = Column(String, default="Adet")
    # Liste fiyatı TL olmak zorunda değil: Klemsan tamamen EURO, Grup Arge aynı
    # dosyada TL ve USD veriyor. Teklife alınırken kur uygulanıp dondurulur.
    currency = Column(String(3), default="TRY", nullable=False)
    # Entegrasyon (Logo/Mikro/Netsis) sonradan gelirse baştan yazmamak için şimdi.
    supplier_code = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    technical_specs = Column(String, nullable=True)

    # --- Aranabilir parametreler ------------------------------------------
    # `technical_specs` uzun bir metin; içindeki karar veren değerler ayrı kolona
    # çıkarıldı. Ayrı kolon tercih edildi (EAV veya JSON değil): alanlar az sayıda,
    # sayısal ve aralık sorgusu istiyor ("2.5-6 mm² arası"), index'lenebilir ve
    # okunur kalıyor. Ayrıştırıcı `app/product_search.py`'da; çıkaramadığı alanlar
    # NULL kalır ve ürün metinle bulunmaya devam eder.
    cross_section = Column(Numeric(8, 3), nullable=True, index=True)   # mm²
    core_count = Column(Integer, nullable=True, index=True)            # damar sayısı
    conductor = Column(String, nullable=True)                          # bakır / alüminyum
    insulation = Column(String, nullable=True)                         # PVC / XLPE / HFFR...
    sheathed = Column(Boolean, nullable=True)                          # kılıflı mı

    # İlişkiler
    category = relationship("Category", back_populates="products")