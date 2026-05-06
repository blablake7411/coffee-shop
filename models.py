from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Date, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime, timezone, date
from database import Base


def now():
    return datetime.now(timezone.utc)


def today():
    return date.today()


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    price_3g = Column(Float, nullable=True)
    price_7g = Column(Float, nullable=True)
    price_14g = Column(Float, nullable=True)
    price_28g = Column(Float, nullable=True)
    price_custom_grams = Column(Float, nullable=True)
    price_custom_price = Column(Float, nullable=True)
    stock_grams = Column(Float, default=0)
    low_stock_threshold_grams = Column(Float, default=100)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    order_items = relationship("OrderItem", back_populates="product")
    purchase_records = relationship("PurchaseRecord", back_populates="product")


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    messenger_name = Column(String)
    phone = Column(String)
    notes = Column(Text)
    created_at = Column(DateTime, default=now)

    orders = relationship("Order", back_populates="customer")


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    order_date = Column(Date, default=today)
    status = Column(String, default="待確認")
    subtotal = Column(Float, default=0)
    discount_amount = Column(Float, default=0)
    final_amount = Column(Float, default=0)
    payment_method = Column(String, default="現金")
    is_credit = Column(Boolean, default=False)
    credit_paid = Column(Boolean, default=False)
    credit_paid_at = Column(DateTime, nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    gram_size = Column(Float, nullable=False)   # 3 / 7 / 14 / 28 或自訂
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False)  # 這個規格的售價
    subtotal = Column(Float, nullable=False)    # unit_price * quantity

    order = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")


class PurchaseRecord(Base):
    __tablename__ = "purchase_records"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity_grams = Column(Float, nullable=False)
    cost_per_gram = Column(Float, nullable=False)
    total_cost = Column(Float, nullable=False)
    purchased_at = Column(DateTime, default=now)
    notes = Column(Text)

    product = relationship("Product", back_populates="purchase_records")
