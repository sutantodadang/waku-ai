from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.constants import DB_TO_DASHBOARD_STATUS
from app.core.database import get_db
from app.core.security import get_current_business
from app.models import Business, Customer, Message, Order
from app.schemas import DashboardSummary
from app.services.report_service import build_sales_report_xlsx

router = APIRouter()


@router.get("/api/dashboard/summary", response_model=DashboardSummary)
async def dashboard_summary(
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/dashboard/summary — daily stats shaped for the dashboard home page."""
    today = date.today()
    day_start = datetime.combine(today, datetime.min.time())
    day_end = datetime.combine(today, datetime.max.time())

    orders_today_stmt = (
        select(Order)
        .where(
            Order.business_id == business.id,
            Order.created_at >= day_start,
            Order.created_at <= day_end,
        )
        .order_by(Order.created_at.desc())
    )
    orders_today = list((await session.execute(orders_today_stmt)).scalars().all())

    revenue_today = sum(o.total for o in orders_today)

    messages_handled_stmt = (
        select(func.count(Message.id))
        .where(
            Message.business_id == business.id,
            Message.direction == "outbound",
            Message.timestamp >= day_start,
            Message.timestamp <= day_end,
        )
    )
    messages_handled = (await session.execute(messages_handled_stmt)).scalar() or 0

    pending_stmt = (
        select(func.count(Order.id))
        .where(
            Order.business_id == business.id,
            Order.status.in_(["pending", "confirmed"]),
        )
    )
    pending_orders = (await session.execute(pending_stmt)).scalar() or 0

    product_counts: dict[str, dict] = {}
    for o in orders_today:
        for item in (o.items or []):
            name = (item.get("name") or "").strip().lower()
            if not name:
                continue
            qty = int(item.get("quantity") or item.get("qty") or 1)
            entry = product_counts.setdefault(name, {"name": item.get("name", name), "count": 0})
            entry["count"] += qty
    top_products = sorted(product_counts.values(), key=lambda x: x["count"], reverse=True)[:5]

    return DashboardSummary(
        orders_today=len(orders_today),
        revenue_today=revenue_today,
        messages_handled=messages_handled,
        pending_orders=pending_orders,
        top_products=top_products,
    )


@router.get("/api/reports/sales")
async def sales_report(
    month: Optional[str] = Query(None, description="Bulan YYYY-MM. Default bulan berjalan."),
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/reports/sales?month=YYYY-MM — download .xlsx laporan penjualan bulanan."""
    today = date.today()
    if month:
        try:
            y, m = month.split("-")
            start = date(int(y), int(m), 1)
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Format bulan harus YYYY-MM.")
    else:
        start = today.replace(day=1)
    end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    day_start = datetime.combine(start, datetime.min.time())
    day_end = datetime.combine(end, datetime.min.time())

    stmt = (
        select(Order, Customer)
        .join(Customer, Order.customer_id == Customer.id)
        .where(
            Order.business_id == business.id,
            Order.created_at >= day_start,
            Order.created_at < day_end,
        )
        .order_by(Order.created_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    xlsx = build_sales_report_xlsx(rows, business.business_name, f"{start:%Y-%m}", DB_TO_DASHBOARD_STATUS)
    filename = f"laporan-penjualan-{start:%Y-%m}.xlsx"
    return StreamingResponse(
        BytesIO(xlsx),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
