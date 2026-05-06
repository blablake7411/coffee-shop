from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from database import get_db
from models import PurchaseRecord, Product
from schemas import PurchaseRecordCreate, PurchaseRecordOut
from typing import List

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
