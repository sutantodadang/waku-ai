from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=False)

    # ── Kenal Langganan: owner-entered ──
    notes: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    is_regular_override: Mapped[Optional[bool]] = mapped_column(Boolean)

    # ── Kenal Langganan: cached stats (recomputed from orders) ──
    order_count: Mapped[int] = mapped_column(Integer, default=0)
    total_spent: Mapped[float] = mapped_column(Float, default=0.0)
    last_order_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    top_items: Mapped[list] = mapped_column(JSON, default=list)
    avg_cadence_days: Mapped[Optional[float]] = mapped_column(Float)
    stats_updated_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)

    business: Mapped["Business"] = relationship(back_populates="customers")
    messages: Mapped[list["Message"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # "inbound" | "outbound"
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    wamid: Mapped[Optional[str]] = mapped_column(String(255))  # WhatsApp message ID
    media_url: Mapped[Optional[str]] = mapped_column(String(512))  # inbound media (image) saved under /uploads

    business: Mapped["Business"] = relationship(back_populates="messages")
    customer: Mapped["Customer"] = relationship(back_populates="messages")
