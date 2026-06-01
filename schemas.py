from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date


class ProductCreate(BaseModel):
    name: str
    price_3g: Optional[float] = None
    price_7g: Optional[float] = None
    price_14g: Optional[float] = None
    price_28g: Optional[float] = None
    price_custom_grams: Optional[float] = None
    price_custom_price: Optional[float] = None
    stock_grams: float = 0
    low_stock_threshold_grams: float = 100


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price_3g: Optional[float] = None
    price_7g: Optional[float] = None
    price_14g: Optional[float] = None
    price_28g: Optional[float] = None
    price_custom_grams: Optional[float] = None
    price_custom_price: Optional[float] = None
    low_stock_threshold_grams: Optional[float] = None
    is_active: Optional[bool] = None


class ProductOut(BaseModel):
    id: int
    name: str
    price_3g: Optional[float]
    price_7g: Optional[float]
    price_14g: Optional[float]
    price_28g: Optional[float]
    price_custom_grams: Optional[float]
    price_custom_price: Optional[float]
    stock_grams: float
    low_stock_threshold_grams: float
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CustomerCreate(BaseModel):
    name: str
    messenger_name: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    messenger_name: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class CustomerOut(BaseModel):
    id: int
    name: str
    messenger_name: Optional[str]
    phone: Optional[str]
    notes: Optional[str]
    created_at: datetime
    total_spent: Optional[float] = None

    class Config:
        from_attributes = True


class OrderItemCreate(BaseModel):
    product_id: int
    gram_size: float
    quantity: int = 1
    unit_price: float
    discount_amount: float = 0
    shipping_fee: float = 0


class OrderItemOut(BaseModel):
    id: int
    product_id: int
    gram_size: float
    quantity: int
    unit_price: float
    subtotal: float
    discount_amount: float = 0
    shipping_fee: float = 0
    product: Optional[ProductOut] = None

    class Config:
        from_attributes = True


class OrderItemsReplace(BaseModel):
    items: List[OrderItemCreate]
    discount_amount: Optional[float] = None


class OrderCreate(BaseModel):
    customer_id: int
    order_date: Optional[date] = None
    status: str = "待確認"
    payment_method: str = "現金"
    discount_amount: float = 0
    shipping_fee: float = 0
    is_credit: bool = False
    notes: Optional[str] = None
    items: List[OrderItemCreate]


class OrderUpdate(BaseModel):
    customer_id: Optional[int] = None
    status: Optional[str] = None
    order_date: Optional[date] = None
    payment_method: Optional[str] = None
    discount_amount: Optional[float] = None
    shipping_fee: Optional[float] = None
    final_amount: Optional[float] = None
    is_credit: Optional[bool] = None
    credit_paid: Optional[bool] = None
    notes: Optional[str] = None


class OrderOut(BaseModel):
    id: int
    customer_id: int
    order_date: date
    status: str
    payment_method: str
    subtotal: float
    discount_amount: float
    shipping_fee: float = 0
    final_amount: float
    is_credit: bool
    credit_paid: bool
    credit_paid_at: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime
    customer: Optional[CustomerOut] = None
    items: List[OrderItemOut] = []

    class Config:
        from_attributes = True


class PurchaseRecordCreate(BaseModel):
    product_id: int
    quantity_grams: float
    cost_per_gram: float
    purchased_at: Optional[date] = None
    notes: Optional[str] = None


class PurchaseRecordUpdate(BaseModel):
    quantity_grams: Optional[float] = None
    total_cost: Optional[float] = None
    purchased_at: Optional[date] = None
    notes: Optional[str] = None


class PurchaseRecordOut(BaseModel):
    id: int
    product_id: int
    quantity_grams: float
    cost_per_gram: float
    total_cost: float
    purchased_at: datetime
    notes: Optional[str]
    product: Optional[ProductOut] = None

    class Config:
        from_attributes = True
