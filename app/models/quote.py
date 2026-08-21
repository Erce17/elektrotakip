from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class QuoteDefaults(Base):
    """İşletme varsayılanları — kurulumda bir kez tanımlanır, teklifte üzerine yazılır.

    Bu ayrım ürünün tek vaadini ayakta tutan şey: kullanıcı her teklifte her oranı
    elle giriyorsa iş yine yarım saat sürer, sadece Excel yerine bizim ekranda sürer.
    Hız esneklikten değil, varsayılanların doğru olmasından gelir.
    """

    __tablename__ = "quote_defaults"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)

    currency = Column(String(3), default="TRY", nullable=False)
    vat_rate = Column(Numeric(5, 2), default=20, nullable=False)
    labor_vat_rate = Column(Numeric(5, 2), default=20, nullable=False)
    validity_days = Column(Integer, default=15, nullable=False)

    # Yeni teklife kopyalanacak zincir şablonu: QuoteAdjustment alanlarının listesi.
    # Şablon üzerinde hesap yapılmaz, sadece kopyalanır — bu yüzden ayrı tablo değil
    # JSON. Hesaba giren zincir her zaman `quote_adjustments` satırlarıdır.
    adjustment_template = Column(JSON, default=list, nullable=False)

    owner = relationship("User", back_populates="quote_defaults")


class Quote(Base):
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True, index=True)

    number = Column(String, nullable=False)  # kullanıcıya görünen teklif no
    title = Column(String, nullable=True)
    status = Column(String, default="taslak", nullable=False)
    notes = Column(Text, nullable=True)

    # Kablo fiyatı bakır ve dolara endeksli, günlük oynar. Teklif dondurulur ve
    # geçerlilik tarihi taşır; yoksa dünkü teklif bugün başka rakam gösterir.
    valid_until = Column(Date, nullable=True)

    # Teklifin para birimi. Kalem başka para biriminde gelirse kalemde dondurulan
    # kurla buraya çevrilir.
    currency = Column(String(3), default="TRY", nullable=False)

    # Revizyon zinciri. Aynı işin ikinci-üçüncü teklifi demonun en güçlü anı, bu yüzden
    # v1'de var. Revizyon eskisini değiştirmez, yeni satır açar.
    version = Column(Integer, default=1, nullable=False)
    parent_quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (UniqueConstraint("user_id", "number", "version", name="uq_quote_no_version"),)

    # İlişkiler
    owner = relationship("User", back_populates="quotes")
    customer = relationship("Customer")
    items = relationship(
        "QuoteItem",
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="QuoteItem.position",
    )
    adjustments = relationship(
        "QuoteAdjustment",
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="QuoteAdjustment.position",
    )
    # ⚠️ Bilerek cascade YOK. Revizyon ayrı bir tekliftir, alt kayıt değil:
    # `delete-orphan` konulunca 1. sürümü silmek 2. ve 3. sürümü de götürüyordu.
    # Kullanıcı eski sürümü temizlerken en güncel teklifini kaybederdi. Silinen
    # sürümün çocukları köksüz kalır (`parent_quote_id` NULL olur), silinmez.
    revisions = relationship("Quote")


class QuoteItem(Base):
    """Teklif kalemi. Fiyat teklif anında kopyalanır, ürünle canlı bağ kurulmaz."""

    __tablename__ = "quote_items"

    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=False, index=True)

    # Sadece izlenebilirlik için. Hesap buradan okumaz; ürün silinse de teklif durur.
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    supplier_code = Column(String, nullable=True)

    position = Column(Integer, default=0, nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    unit = Column(String, default="Adet", nullable=False)
    kind = Column(String, default="malzeme", nullable=False)  # quote_engine sabitleri

    quantity = Column(Numeric(12, 4), default=1, nullable=False)

    # Kaynak para birimi + o anki kur + çevrilmiş fiyat, üçü birden dondurulur.
    # Klemsan tamamen EURO, Grup Arge aynı dosyada TL ve USD veriyor.
    source_currency = Column(String(3), default="TRY", nullable=False)
    source_unit_price = Column(Numeric(12, 4), nullable=False)
    fx_rate = Column(Numeric(18, 8), default=1, nullable=False)
    unit_price = Column(Numeric(12, 4), nullable=False)  # teklif para biriminde

    vat_rate = Column(Numeric(5, 2), default=20, nullable=False)
    # İşçilik genelde iskontoya girmez. Bayrak kalemde duruyor çünkü "girmez" bir
    # varsayılan, kural değil — işletme tersini isteyebilir.
    discountable = Column(Boolean, default=True, nullable=False)

    # Anahtar/priz tek ürün değil: mekanizma + düğme/kapak ayrı fiyatlı, çerçeve ayrıca.
    # Tek satır mı üç satır mı sorusu henüz cevaplanmadı. Bugün bu alan kullanılmıyor;
    # kalem yapısı bileşene KAPALI kurulmasın diye duruyor.
    parent_item_id = Column(Integer, ForeignKey("quote_items.id"), nullable=True)

    quote = relationship("Quote", back_populates="items")
    adjustments = relationship(
        "QuoteAdjustment",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="QuoteAdjustment.position",
    )
    components = relationship("QuoteItem", cascade="all, delete-orphan")


class QuoteAdjustment(Base):
    """Hesap zincirinin tek bir satırı. Sırası sonucu değiştirir.

    İki yerde geçiyor ve **tam olarak biri** doludur:

    - `quote_item_id` dolu → kalemin kendi iskonto zinciri (%20 sonra %5, %25 değil).
    - `quote_id` dolu → teklif seviyesi: genel iskonto, işçilik, nakliye.

    İkisi tek tabloda çünkü kavram aynı: tipi, tabanı ve sırası olan bir hesap adımı.
    Kalem satırında `quote_id` tekrar tutulmuyor; aynı bilgiyi iki yerde tutmak ikisinin
    çelişmesine kapı açar.
    """

    __tablename__ = "quote_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(Integer, ForeignKey("quotes.id"), nullable=True, index=True)
    quote_item_id = Column(Integer, ForeignKey("quote_items.id"), nullable=True, index=True)

    position = Column(Integer, default=0, nullable=False)
    label = Column(String, nullable=True)

    # quote_engine sabitleri: iskonto_yuzde / iskonto_tutar / ek_yuzde / ek_tutar
    kind = Column(String, nullable=False)
    value = Column(Numeric(12, 4), nullable=False)
    base = Column(String, default="yuruyen", nullable=False)
    scope = Column(String, default="iskontoya_tabi", nullable=False)

    # Sadece ek satırlarında anlamlı.
    vat_rate = Column(Numeric(5, 2), nullable=True)
    added_discountable = Column(Boolean, default=False, nullable=False)
    added_kind = Column(String, default="diger", nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(quote_id IS NULL) <> (quote_item_id IS NULL)",
            name="ck_adjustment_tek_sahip",
        ),
    )

    quote = relationship("Quote", back_populates="adjustments")
    item = relationship("QuoteItem", back_populates="adjustments", foreign_keys=[quote_item_id])
