from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from database import get_db
from models import Order, OrderItem, PurchaseRecord, Product
from datetime import datetime, timezone, timedelta, date
import calendar
import os
from typing import Optional

router = APIRouter(prefix="/api/reports", tags=["reports"])

BOSS_RATIO = 0.30
SELF_RATIO = 0.70


def _week_range(ref: date):
    monday = ref - timedelta(days=ref.weekday())
    return monday, monday + timedelta(days=6)


def _month_range(year: int, month: int):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _quarter_range(year: int, quarter: int):
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    last_day = calendar.monthrange(year, end_month)[1]
    return date(year, start_month, 1), date(year, end_month, last_day)


def _revenue_in_range(db: Session, start: date, end: date) -> float:
    result = (
        db.query(func.sum(Order.final_amount))
        .filter(
            Order.order_date >= start,
            Order.order_date <= end,
            Order.status != "退款",
        )
        .scalar()
    )
    return result or 0.0


def _daily_breakdown(db: Session, start: date, end: date) -> list:
    day_names = ["一", "二", "三", "四", "五", "六", "日"]
    result = []
    d = start
    while d <= end:
        result.append({
            "date": f"{d.month}/{d.day}",
            "day": day_names[d.weekday()],
            "revenue": _revenue_in_range(db, d, d),
            "order_count": _order_count_in_range(db, d, d),
            "grams": _grams_in_range(db, d, d),
            "purchases": _purchases_in_range(db, d, d),
        })
        d += timedelta(days=1)
    return result


def _weekly_breakdown(db: Session, start: date, end: date) -> list:
    week_start = start - timedelta(days=start.weekday())
    result = []
    while week_start <= end:
        week_end = week_start + timedelta(days=6)
        eff_start = max(week_start, start)
        eff_end = min(week_end, end)
        result.append({
            "label": f"{eff_start.month}/{eff_start.day}－{eff_end.month}/{eff_end.day}",
            "revenue": _revenue_in_range(db, eff_start, eff_end),
            "order_count": _order_count_in_range(db, eff_start, eff_end),
            "grams": _grams_in_range(db, eff_start, eff_end),
            "purchases": _purchases_in_range(db, eff_start, eff_end),
        })
        week_start += timedelta(days=7)
    return result


def _purchases_in_range(db: Session, start: date, end: date) -> list:
    dt_start = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    dt_end = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)
    records = (
        db.query(PurchaseRecord)
        .options(joinedload(PurchaseRecord.product))
        .filter(PurchaseRecord.purchased_at >= dt_start, PurchaseRecord.purchased_at <= dt_end)
        .order_by(PurchaseRecord.purchased_at)
        .all()
    )
    return [
        {
            "date": r.purchased_at.strftime("%-m/%-d"),
            "product": r.product.name if r.product else "—",
            "grams": r.quantity_grams,
            "total_cost": r.total_cost,
        }
        for r in records
    ]


def _monthly_breakdown_in_range(db: Session, start: date, end: date) -> list:
    result = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        ms, me = _month_range(y, m)
        eff_start = max(ms, start)
        eff_end = min(me, end)
        result.append({
            "label": f"{y}/{m:02d}",
            "revenue": _revenue_in_range(db, eff_start, eff_end),
            "order_count": _order_count_in_range(db, eff_start, eff_end),
            "grams": _grams_in_range(db, eff_start, eff_end),
            "purchases": _purchases_in_range(db, eff_start, eff_end),
        })
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result


def _shipping_in_range(db: Session, start: date, end: date) -> float:
    result = (
        db.query(func.sum(Order.shipping_fee))
        .filter(
            Order.order_date >= start,
            Order.order_date <= end,
            Order.status != "退款",
        )
        .scalar()
    )
    return result or 0.0


def _product_breakdown_in_range(db: Session, start: date, end: date) -> list:
    rows = (
        db.query(
            Product.name,
            OrderItem.subtotal,
            OrderItem.quantity,
            OrderItem.gram_size,
            Order.subtotal.label("order_subtotal"),
            Order.final_amount,
            Order.shipping_fee,
        )
        .join(OrderItem.order)
        .join(OrderItem.product)
        .filter(
            Order.order_date >= start,
            Order.order_date <= end,
            Order.status != "退款",
        )
        .all()
    )
    product_data: dict = {}
    for r in rows:
        name = r.name
        if name not in product_data:
            product_data[name] = {"revenue": 0.0, "shipping": 0.0, "quantity": 0, "grams": 0.0}
        ratio = r.subtotal / r.order_subtotal if r.order_subtotal else 1.0
        product_revenue_base = r.final_amount - (r.shipping_fee or 0)
        product_data[name]["revenue"] += r.subtotal * (product_revenue_base / r.order_subtotal if r.order_subtotal else 1.0)
        product_data[name]["shipping"] += (r.shipping_fee or 0) * ratio
        product_data[name]["quantity"] += r.quantity
        product_data[name]["grams"] += r.gram_size * r.quantity
    return [
        {
            "product": name,
            "revenue": round(v["revenue"], 1),
            "shipping": round(v["shipping"], 1),
            "quantity": v["quantity"],
            "grams": v["grams"],
        }
        for name, v in sorted(product_data.items(), key=lambda x: -x[1]["revenue"])
    ]


def _credit_unpaid_in_range(db: Session, start: date, end: date) -> float:
    result = (
        db.query(func.sum(Order.final_amount))
        .filter(
            Order.order_date >= start,
            Order.order_date <= end,
            Order.is_credit == True,
            Order.credit_paid == False,
            Order.status != "退款",
        )
        .scalar()
    )
    return result or 0.0


def _purchase_cost_in_range(db: Session, start: date, end: date) -> float:
    dt_start = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    dt_end = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)
    result = (
        db.query(func.sum(PurchaseRecord.total_cost))
        .filter(PurchaseRecord.purchased_at >= dt_start, PurchaseRecord.purchased_at <= dt_end)
        .scalar()
    )
    return result or 0.0


def _order_count_in_range(db: Session, start: date, end: date) -> int:
    return db.query(Order).filter(Order.order_date >= start, Order.order_date <= end).count()


def _grams_in_range(db: Session, start: date, end: date) -> float:
    result = (
        db.query(func.sum(OrderItem.gram_size * OrderItem.quantity))
        .join(Order)
        .filter(
            Order.order_date >= start,
            Order.order_date <= end,
            Order.status != "退款",
        )
        .scalar()
    )
    return result or 0.0


@router.get("/weekly")
def weekly_report(week_offset: int = 0, local_date: Optional[str] = None, db: Session = Depends(get_db)):
    if local_date:
        try:
            base = date.fromisoformat(local_date)
        except ValueError:
            base = date.today()
    else:
        base = date.today()
    ref = base - timedelta(weeks=week_offset)
    start, end = _week_range(ref)
    revenue = _revenue_in_range(db, start, end)
    cost = _purchase_cost_in_range(db, start, end)
    net_profit = revenue - cost
    credit_unpaid = _credit_unpaid_in_range(db, start, end)
    return {
        "period": f"{start} ~ {end}",
        "revenue": revenue,
        "shipping_total": _shipping_in_range(db, start, end),
        "order_count": _order_count_in_range(db, start, end),
        "purchase_cost": cost,
        "net_profit": net_profit,
        "credit_unpaid": credit_unpaid,
        "actual_net_profit": net_profit - credit_unpaid,
        "product_breakdown": _product_breakdown_in_range(db, start, end),
        "daily_breakdown": _daily_breakdown(db, start, end),
        "purchases": _purchases_in_range(db, start, end),
    }


@router.get("/monthly")
def monthly_report(year: Optional[int] = None, month: Optional[int] = None, db: Session = Depends(get_db)):
    today = date.today()
    y = year or today.year
    m = month or today.month
    start, end = _month_range(y, m)
    revenue = _revenue_in_range(db, start, end)
    cost = _purchase_cost_in_range(db, start, end)
    net_profit = revenue - cost
    credit_unpaid = _credit_unpaid_in_range(db, start, end)
    return {
        "period": f"{y}-{m:02d}",
        "revenue": revenue,
        "shipping_total": _shipping_in_range(db, start, end),
        "order_count": _order_count_in_range(db, start, end),
        "purchase_cost": cost,
        "net_profit": net_profit,
        "credit_unpaid": credit_unpaid,
        "actual_net_profit": net_profit - credit_unpaid,
        "product_breakdown": _product_breakdown_in_range(db, start, end),
        "weekly_breakdown": _weekly_breakdown(db, start, end),
        "purchases": _purchases_in_range(db, start, end),
    }


def _months_in_range(start_ym: str, end_ym: str):
    sy, sm = int(start_ym[:4]), int(start_ym[5:7])
    ey, em = int(end_ym[:4]), int(end_ym[5:7])
    pairs = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        pairs.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return pairs


@router.get("/quarterly")
def quarterly_report(
    start_ym: Optional[str] = None,
    end_ym: Optional[str] = None,
    year: Optional[int] = None,
    quarter: Optional[int] = None,
    db: Session = Depends(get_db),
):
    today = date.today()

    if start_ym and end_ym:
        month_pairs = _months_in_range(start_ym, end_ym)
    else:
        y = year or today.year
        q = quarter or ((today.month - 1) // 3 + 1)
        sm = (q - 1) * 3 + 1
        month_pairs = [(y, m) for m in range(sm, sm + 3)]

    monthly_breakdown = []
    for py, pm in month_pairs:
        ms, me = _month_range(py, pm)
        rev = _revenue_in_range(db, ms, me)
        cost = _purchase_cost_in_range(db, ms, me)
        monthly_breakdown.append({
            "month": f"{py}-{pm:02d}",
            "revenue": rev,
            "purchase_cost": cost,
            "net_profit": rev - cost,
            "grams": _grams_in_range(db, ms, me),
            "purchases": _purchases_in_range(db, ms, me),
        })

    total_revenue = sum(r["revenue"] for r in monthly_breakdown)
    total_cost = sum(r["purchase_cost"] for r in monthly_breakdown)
    net_profit = total_revenue - total_cost
    all_start, _ = _month_range(*month_pairs[0])
    _, all_end = _month_range(*month_pairs[-1])
    credit_unpaid = _credit_unpaid_in_range(db, all_start, all_end)

    total_grams = 0.0
    for py, pm in month_pairs:
        ms, me = _month_range(py, pm)
        total_grams += (
            db.query(func.sum(OrderItem.gram_size * OrderItem.quantity))
            .join(Order)
            .filter(Order.order_date >= ms, Order.order_date <= me)
            .scalar()
        ) or 0.0

    order_count = sum(_order_count_in_range(db, *_month_range(py, pm)) for py, pm in month_pairs)

    (y0, m0), (yn, mn) = month_pairs[0], month_pairs[-1]
    if len(month_pairs) == 1:
        period_str = f"{y0}年 {m0}月"
    elif y0 == yn:
        period_str = f"{y0}年 {m0}～{mn}月"
    else:
        period_str = f"{y0}/{m0:02d} ～ {yn}/{mn:02d}"

    return {
        "period": period_str,
        "revenue": total_revenue,
        "shipping_total": _shipping_in_range(db, all_start, all_end),
        "order_count": order_count,
        "purchase_cost": total_cost,
        "net_profit": net_profit,
        "credit_unpaid": credit_unpaid,
        "actual_net_profit": net_profit - credit_unpaid,
        "boss_payout": round(net_profit * BOSS_RATIO, 2),
        "self_payout": round(net_profit * SELF_RATIO, 2),
        "total_grams": total_grams,
        "total_pounds": round(total_grams / 453.592, 3),
        "product_breakdown": _product_breakdown_in_range(db, all_start, all_end),
        "monthly_breakdown": monthly_breakdown,
        "purchases": _purchases_in_range(db, all_start, all_end),
    }


@router.get("/custom")
def custom_report(start_date: str, end_date: str, db: Session = Depends(get_db)):
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except ValueError:
        return {"error": "Invalid date format"}
    revenue = _revenue_in_range(db, start, end)
    cost = _purchase_cost_in_range(db, start, end)
    net_profit = revenue - cost
    credit_unpaid = _credit_unpaid_in_range(db, start, end)
    total_grams = _grams_in_range(db, start, end)
    return {
        "period": f"{start.month}/{start.day} ~ {end.month}/{end.day}",
        "revenue": revenue,
        "shipping_total": _shipping_in_range(db, start, end),
        "order_count": _order_count_in_range(db, start, end),
        "purchase_cost": cost,
        "net_profit": net_profit,
        "credit_unpaid": credit_unpaid,
        "actual_net_profit": net_profit - credit_unpaid,
        "boss_payout": round(net_profit * BOSS_RATIO, 2),
        "self_payout": round(net_profit * SELF_RATIO, 2),
        "total_grams": total_grams,
        "total_pounds": round(total_grams / 453.592, 3),
        "product_breakdown": _product_breakdown_in_range(db, start, end),
        "daily_breakdown": _daily_breakdown(db, start, end),
        "weekly_breakdown": _weekly_breakdown(db, start, end),
        "monthly_breakdown": _monthly_breakdown_in_range(db, start, end),
        "purchases": _purchases_in_range(db, start, end),
    }


def _get_sheets_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = Credentials(
        token=None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    creds.refresh(Request())
    return build("sheets", "v4", credentials=creds)


@router.post("/export-sheets")
def export_to_sheets(
    start_ym: str,
    end_ym: str,
    split_mode: str = "cost",
    db: Session = Depends(get_db),
):
    data = quarterly_report(start_ym=start_ym, end_ym=end_ym, db=db)
    use_cost = split_mode == "cost"
    boss_amt = data["boss_payout"] if use_cost else data["revenue"] * 0.3
    self_amt = data["self_payout"] if use_cost else data["revenue"] * 0.7

    sheet_name = f"{start_ym}~{end_ym}"
    ss_id = os.environ["SHEETS_SPREADSHEET_ID"]
    service = _get_sheets_service()
    sheets = service.spreadsheets()

    existing = sheets.get(spreadsheetId=ss_id).execute()
    existing_titles = [s["properties"]["title"] for s in existing["sheets"]]
    if sheet_name not in existing_titles:
        sheets.batchUpdate(spreadsheetId=ss_id, body={
            "requests": [{"addSheet": {"properties": {"title": sheet_name}}}]
        }).execute()

    rows = [
        ["季報", data["period"]],
        [],
        ["項目", "金額"],
        ["總營業額", data["revenue"]],
        ["總訂單數", data["order_count"]],
        ["進貨成本", data["purchase_cost"]],
        ["淨利", data["net_profit"]],
        ["應匯老闆 (30%)", boss_amt],
        ["自留 (70%)", self_amt],
        ["總銷售克數", data["total_grams"]],
        ["換算磅數", data["total_pounds"]],
        [],
        ["月份", "營業額", "進貨成本", "淨利", "銷售克數"],
    ]
    for m in data["monthly_breakdown"]:
        rows.append([m["month"], m["revenue"], m["purchase_cost"], m["net_profit"], m["grams"]])

    sheets.values().update(
        spreadsheetId=ss_id,
        range=f"{sheet_name}!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    return {"url": f"https://docs.google.com/spreadsheets/d/{ss_id}"}


@router.post("/export-sheets-custom")
def export_custom_to_sheets(
    start_date: str,
    end_date: str,
    breakdown: str = "daily",
    db: Session = Depends(get_db),
):
    data = custom_report(start_date=start_date, end_date=end_date, db=db)

    sheet_name = f"{start_date}~{end_date}"
    ss_id = os.environ["SHEETS_SPREADSHEET_ID"]
    service = _get_sheets_service()
    sheets = service.spreadsheets()

    existing = sheets.get(spreadsheetId=ss_id).execute()
    existing_titles = [s["properties"]["title"] for s in existing["sheets"]]
    if sheet_name not in existing_titles:
        sheets.batchUpdate(spreadsheetId=ss_id, body={
            "requests": [{"addSheet": {"properties": {"title": sheet_name}}}]
        }).execute()

    rows = [
        ["自訂報表", data["period"]],
        [],
        ["項目", "金額"],
        ["總營業額", data["revenue"]],
        ["總訂單數", data["order_count"]],
        ["進貨成本", data["purchase_cost"]],
        ["淨利", data["net_profit"]],
        ["應匯老闆 (30%)", data["boss_payout"]],
        ["自留 (70%)", data["self_payout"]],
        ["總銷售克數", data["total_grams"]],
        ["換算磅數", data["total_pounds"]],
        [],
    ]

    if breakdown == "weekly":
        rows.append(["週次", "訂單數", "營業額", "銷售克數"])
        for w in data["weekly_breakdown"]:
            rows.append([w["label"], w["order_count"], w["revenue"], w["grams"]])
    elif breakdown == "monthly":
        rows.append(["月份", "訂單數", "營業額", "銷售克數"])
        for m in data["monthly_breakdown"]:
            rows.append([m["label"], m["order_count"], m["revenue"], m["grams"]])
    else:
        rows.append(["日期", "星期", "訂單數", "營業額", "銷售克數"])
        for d in data["daily_breakdown"]:
            rows.append([d["date"], f"週{d['day']}", d["order_count"], d["revenue"], d["grams"]])

    if data["purchases"]:
        rows.append([])
        rows.append(["進貨日期", "品名", "克數", "成本"])
        for p in data["purchases"]:
            rows.append([p["date"], p["product"], p["grams"], p["total_cost"]])

    sheets.values().update(
        spreadsheetId=ss_id,
        range=f"{sheet_name}!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    return {"url": f"https://docs.google.com/spreadsheets/d/{ss_id}"}
