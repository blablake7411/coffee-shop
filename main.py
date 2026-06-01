from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from database import engine
import models

models.Base.metadata.create_all(bind=engine)

from sqlalchemy import text
with engine.connect() as _conn:
    for _sql in [
        "ALTER TABLE orders ADD COLUMN shipping_fee FLOAT DEFAULT 0",
        "ALTER TABLE order_items ADD COLUMN discount_amount FLOAT DEFAULT 0",
        "ALTER TABLE order_items ADD COLUMN shipping_fee FLOAT DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN credit_amount FLOAT DEFAULT 0",
    ]:
        try:
            _conn.execute(text(_sql))
            _conn.commit()
        except Exception:
            pass

from routers import customers, products, orders, inventory, reports

app = FastAPI(title="Coffee Shop Manager")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(customers.router)
app.include_router(products.router)
app.include_router(orders.router)
app.include_router(inventory.router)
app.include_router(reports.router)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    return FileResponse("static/index.html")
