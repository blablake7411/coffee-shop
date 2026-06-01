from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from database import get_db
from models import Customer, Order, OrderItem
from schemas import CustomerCreate, CustomerUpdate, CustomerOut
from typing import List

router = APIRouter(prefix="/api/customers", tags=["customers"])


@router.get("/", response_model=List[CustomerOut])
def list_customers(db: Session = Depends(get_db)):
    spent_subq = (
        db.query(Order.customer_id, func.sum(Order.final_amount).label("total_spent"))
        .filter(Order.status != "退款")
        .group_by(Order.customer_id)
        .subquery()
    )
    rows = (
        db.query(Customer, spent_subq.c.total_spent)
        .outerjoin(spent_subq, Customer.id == spent_subq.c.customer_id)
        .order_by(Customer.name)
        .all()
    )
    result = []
    for customer, total_spent in rows:
        customer.total_spent = total_spent or 0
        result.append(customer)
    return result


@router.post("/", response_model=CustomerOut)
def create_customer(data: CustomerCreate, db: Session = Depends(get_db)):
    customer = Customer(**data.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


@router.get("/credits")
def credit_summary(db: Session = Depends(get_db)):
    rows = (
        db.query(Customer, Order.final_amount, Order.credit_amount)
        .join(Order, Order.customer_id == Customer.id)
        .filter(Order.is_credit == True, Order.credit_paid == False)
        .all()
    )
    by_customer: dict = {}
    for c, final_amount, credit_amount in rows:
        owed = credit_amount if (credit_amount or 0) > 0 else final_amount
        if c.id not in by_customer:
            by_customer[c.id] = {"customer": c, "total_owed": 0.0, "order_count": 0}
        by_customer[c.id]["total_owed"] += owed
        by_customer[c.id]["order_count"] += 1
    return sorted([
        {"id": v["customer"].id, "name": v["customer"].name,
         "messenger_name": v["customer"].messenger_name,
         "total_owed": round(v["total_owed"], 0), "order_count": v["order_count"]}
        for v in by_customer.values()
    ], key=lambda x: -x["total_owed"])


@router.get("/{customer_id}/orders")
def customer_orders(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    orders = (
        db.query(Order)
        .options(joinedload(Order.items).joinedload(OrderItem.product))
        .filter(Order.customer_id == customer_id)
        .order_by(Order.order_date.desc(), Order.created_at.desc())
        .all()
    )
    total_spent = sum(
        o.final_amount for o in orders
        if (o.status == "完成" and not o.is_credit) or (o.is_credit and o.credit_paid)
    )
    credit_owed = sum(
        (o.credit_amount if (o.credit_amount or 0) > 0 else o.final_amount)
        for o in orders if o.is_credit and not o.credit_paid
    )
    return {
        "customer": {
            "id": customer.id, "name": customer.name,
            "messenger_name": customer.messenger_name,
            "phone": customer.phone, "notes": customer.notes,
        },
        "total_orders": len(orders),
        "total_spent": round(total_spent, 0),
        "credit_owed": round(credit_owed, 0),
        "orders": [
            {
                "id": o.id,
                "order_date": str(o.order_date),
                "status": o.status,
                "payment_method": o.payment_method,
                "final_amount": o.final_amount,
                "is_credit": o.is_credit,
                "credit_amount": o.credit_amount or 0,
                "credit_paid": o.credit_paid,
                "notes": o.notes,
                "items": [
                    {"product_name": i.product.name if i.product else "?",
                     "gram_size": i.gram_size, "quantity": i.quantity, "subtotal": i.subtotal}
                    for i in o.items
                ],
            }
            for o in orders
        ],
    }


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: int, data: CustomerUpdate, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer


@router.delete("/{customer_id}")
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    db.delete(customer)
    db.commit()
    return {"ok": True}
