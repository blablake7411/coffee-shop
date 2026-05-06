from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models import PurchaseRecord, Product
from schemas import PurchaseRecordCreate, PurchaseRecordOut, PurchaseRecordUpdate
from typing import List
from datetime import datetime, timezone

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("/purchases", response_model=List[PurchaseRecordOut])
def list_purchases(limit: int = 50, db: Session = Depends(get_db)):
    return (
        db.query(PurchaseRecord)
        .options(joinedload(PurchaseRecord.product))
        .order_by(PurchaseRecord.purchased_at.desc())
        .limit(limit)
        .all()
    )


@router.post("/purchases", response_model=PurchaseRecordOut)
def add_purchase(data: PurchaseRecordCreate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == data.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    total_cost = data.quantity_grams * data.cost_per_gram
    record = PurchaseRecord(
        product_id=data.product_id,
        quantity_grams=data.quantity_grams,
        cost_per_gram=data.cost_per_gram,
        total_cost=total_cost,
        notes=data.notes,
    )
    if data.purchased_at:
        record.purchased_at = datetime(
            data.purchased_at.year, data.purchased_at.month, data.purchased_at.day,
            tzinfo=timezone.utc
        )
    db.add(record)
    product.stock_grams += data.quantity_grams
    db.commit()
    db.refresh(record)

    return (
        db.query(PurchaseRecord)
        .options(joinedload(PurchaseRecord.product))
        .filter(PurchaseRecord.id == record.id)
        .first()
    )


@router.patch("/purchases/{purchase_id}", response_model=PurchaseRecordOut)
def update_purchase(purchase_id: int, data: PurchaseRecordUpdate, db: Session = Depends(get_db)):
    record = (
        db.query(PurchaseRecord)
        .options(joinedload(PurchaseRecord.product))
        .filter(PurchaseRecord.id == purchase_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Purchase record not found")

    if data.quantity_grams is not None:
        delta = data.quantity_grams - record.quantity_grams
        record.product.stock_grams += delta
        record.quantity_grams = data.quantity_grams

    if data.total_cost is not None:
        record.total_cost = data.total_cost

    record.cost_per_gram = record.total_cost / record.quantity_grams if record.quantity_grams > 0 else 0

    if data.purchased_at is not None:
        record.purchased_at = datetime(
            data.purchased_at.year, data.purchased_at.month, data.purchased_at.day,
            tzinfo=timezone.utc
        )

    if data.notes is not None:
        record.notes = data.notes or None

    db.commit()
    db.refresh(record)
    return (
        db.query(PurchaseRecord)
        .options(joinedload(PurchaseRecord.product))
        .filter(PurchaseRecord.id == record.id)
        .first()
    )
