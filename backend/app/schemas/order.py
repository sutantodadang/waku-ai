from __future__ import annotations

import datetime
from typing import Any, Optional

from pydantic import BaseModel


class OrderItem(BaseModel):
    """Single item inside an order."""
    name: str
    quantity: int = 1
    price: Optional[float] = None


class OrderResponse(BaseModel):
    id: str
    order_seq: int = 0
    business_id: int
    customer_id: int
    items: list[Any]
    total: float
    status: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class DailySummary(BaseModel):
    date: str
    total_conversations: int
    total_orders: int
    total_revenue: float
    orders: list[OrderResponse]


# ── Order status update + dashboard order shape ────────────────────────────────
class OrderStatusUpdate(BaseModel):
    """PATCH /api/orders/{id} body — dashboard sends Indonesian status."""
    status: str  # baru | diproses | selesai | dibatalkan


class OrderDashboardResponse(BaseModel):
    """Order shape expected by the Streamlit dashboard."""
    id: str
    order_seq: int = 0
    customer_name: str
    status: str  # Indonesian label
    total: float
    items: list[Any]
    created_at: datetime.datetime


class DashboardSummary(BaseModel):
    """GET /api/dashboard/summary shape expected by the dashboard."""
    orders_today: int
    revenue_today: float
    messages_handled: int
    pending_orders: int
    top_products: list[dict]
