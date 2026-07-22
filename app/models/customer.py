from sqlalchemy import Column, Integer, String, ForeignKey, Numeric, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)  # Firma veya kişi adı
    phone = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    balance = Column(Numeric(10, 2), default=0, nullable=False)  # FR-06: para → Numeric

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    owner = relationship("User", back_populates="customers")