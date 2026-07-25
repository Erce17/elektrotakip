from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Numeric
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    technical_specs = Column(String, nullable=True) 

    # İlişkiler
    category = relationship("Category", back_populates="products")