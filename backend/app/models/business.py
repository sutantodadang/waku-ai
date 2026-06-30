from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.core.database import Base


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Human-readable display number (e.g. 0812...). NOT used for webhook routing.
    phone_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    settings: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    # ── Multi-tenant WhatsApp connection (set by Embedded Signup) ──
    phone_number_id: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True)  # Meta routing id
    waba_id: Mapped[Optional[str]] = mapped_column(String(64))
    access_token: Mapped[Optional[str]] = mapped_column(EncryptedString(512))  # encrypted at rest
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # ── Phase B: payment delivery ──
    payment_methods: Mapped[list] = mapped_column(JSON, default=list)
    qris_image_url: Mapped[Optional[str]] = mapped_column(String(512))
    # ── Phase C: business type ──
    business_type: Mapped[str] = mapped_column(String(16), default="warung", nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    customers: Mapped[list["Customer"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    products: Mapped[list["Product"]] = relationship(back_populates="business", cascade="all, delete-orphan")


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
