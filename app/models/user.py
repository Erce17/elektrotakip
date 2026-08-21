from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    categories = relationship("Category", back_populates="owner", cascade="all, delete-orphan")
    customers = relationship("Customer", back_populates="owner", cascade="all, delete-orphan")
    quotes = relationship("Quote", back_populates="owner", cascade="all, delete-orphan")
    quote_defaults = relationship(
        "QuoteDefaults", back_populates="owner", uselist=False, cascade="all, delete-orphan"
    )
