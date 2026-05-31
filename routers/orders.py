from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models import Order, OrderItem, Product, Customer
from schemas import OrderCreate, OrderUpdate, OrderOut, OrderItemsReplace
from datetime import datetime, timezone, date
import calendar
from typing import List, Optional

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _load_order(db: Session, order_id: int) -> Order:
    order = (
        db.query(Order)
        .options(
            joinedload(Order.customer),
            joinedload(Order.items).joinedload(OrderItem.product),
        )
        .filter(Order.id == order_id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/search", response_model=List[OrderOut])
def search_orders(
    q: Optional[str] = None,
    credit_unpaid: Optional[bool] = None,
    payment_method: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = (
        db.query(Order)
        .options(
            joinedload(Order.customer),
            joinedload(Order.items).joinedload(OrderItem.product),
        )
        .join(Order.customer)
    )
    if q:
        query = query.filter(Customer.name.contains(q))
    if credit_unpaid:
        query = query.filter(Order.is_credit == True, Order.credit_paid == False)
    if payment_method:
        query = query.filter(Order.payment_method == payment_method)
    return query.order_by(Order.order_date.desc(), Order.created_at.desc()).limit(200).all()


@router.get("/today", response_model=List[OrderOut])
def today_orders(local_date: Optional[str] = None, db: Session = Depends(get_db)):
    if local_date:
        try:
            today = date.fromisoformat(local_date)
        except ValueError:
            today = date.today()
    else:
        today = date.today()
    orders = (
        db.query(Order)
        .options(
            joinedload(Order.customer),
            joinedload(Order.items).joinedload(OrderItem.product),
        )
        .filter(Order.order_date == today)
        .order_by(Order.created_at.desc())
        .all()
    )
    return orders


@router.get("/", response_model=List[OrderOut])
def list_orders(
    status: Optional[str] = None,
    credit_unpaid: Optional[bool] = None,
    upcoming: Optional[bool] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Order).options(
        joinedload(Order.customer),
        joinedload(Order.items).joinedload(OrderItem.product),
    )

    today = date.today()

    if upcoming:
        q = q.filter(Order.order_date > today)
    else:
        y = year or today.year
        m = month or today.month
        last_day = calendar.monthrange(y, m)[1]
        q = q.filter(
            Order.order_date >= date(y, m, 1),
            Order.order_date <= date(y, m, last_day),
        )

    if status:
        q = q.filter(Order.status == status)
    if credit_unpaid is True:
        q = q.filter(Order.is_credit == True, Order.credit_paid == False)

    return q.order_by(Order.order_date.desc(), Order.created_at.desc()).all()


@router.post("/", response_model=OrderOut)
def create_order(data: OrderCreate, db: Session = Depends(get_db)):
    subtotal = 0.0
    items_data = []
    for item in data.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {item.product_id} not found")
        item_subtotal = item.unit_price * item.quantity
        subtotal += item_subtotal
        items_data.append((item, item_subtotal, product))

    final_amount = subtotal - data.discount_amount + data.shipping_fee
    order_date = data.order_date or date.today()

    order = Order(
        customer_id=data.customer_id,
        order_date=order_date,
        status=data.status,
        subtotal=subtotal,
        discount_amount=data.discount_amount,
        shipping_fee=data.shipping_fee,
        final_amount=final_amount,
        is_credit=data.is_credit,
        notes=data.notes,
    )
    db.add(order)
    db.flush()

    for item, item_subtotal, product in items_data:
        db.add(OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            gram_size=item.gram_size,
            quantity=item.quantity,
            unit_price=item.unit_price,
            subtotal=item_subtotal,
        ))
        product.stock_grams -= item.gram_size * item.quantity

    db.commit()
    return _load_order(db, order.id)


@router.put("/{order_id}/items", response_model=OrderOut)
def replace_order_items(order_id: int, data: OrderItemsReplace, db: Session = Depends(get_db)):
    order = db.query(Order).options(joinedload(Order.items)).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    for item in order.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            product.stock_grams += item.gram_size * item.quantity

    db.query(OrderItem).filter(OrderItem.order_id == order_id).delete()
    db.flush()

    subtotal = 0.0
    for item_data in data.items:
        product = db.query(Product).filter(Product.id == item_data.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail=f"Product {item_data.product_id} not found")
        item_subtotal = item_data.unit_price * item_data.quantity
        subtotal += item_subtotal
        db.add(OrderItem(
            order_id=order.id,
            product_id=item_data.product_id,
            gram_size=item_data.gram_size,
            quantity=item_data.quantity,
            unit_price=item_data.unit_price,
            subtotal=item_subtotal,
        ))
        product.stock_grams -= item_data.gram_size * item_data.quantity

    discount = data.discount_amount if data.discount_amount is not None else order.discount_amount
    order.subtotal = subtotal
    order.discount_amount = discount
    order.final_amount = subtotal - discount + (order.shipping_fee or 0)
    order.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _load_order(db, order.id)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    return _load_order(db, order_id)


@router.patch("/{order_id}", response_model=OrderOut)
def update_order(order_id: int, data: OrderUpdate, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    updates = data.model_dump(exclude_none=True)

    if "credit_paid" in updates and updates["credit_paid"] and not order.credit_paid:
        order.credit_paid_at = datetime.now(timezone.utc)

    for field, value in updates.items():
        setattr(order, field, value)

    order.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _load_order(db, order_id)


@router.delete("/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    for item in order.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            product.stock_grams += item.gram_size * item.quantity
    db.delete(order)
    db.commit()
    return {"ok": True}
