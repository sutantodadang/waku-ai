"""
SQLAlchemy ORM models for Waku backend.
"""
from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Business(Base):
    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    settings: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    customers: Mapped[list["Customer"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(back_populates="business", cascade="all, delete-orphan")
    products: Mapped[list["Product"]] = relationship(back_populates="business", cascade="all, delete-orphan")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[Optional[str]] = mapped_column(String(255))
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=False)

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

    business: Mapped["Business"] = relationship(back_populates="messages")
    customer: Mapped["Customer"] = relationship(back_populates="messages")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=False)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False)
    items: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    total: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending | confirmed | completed | cancelled
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship(back_populates="orders")
    customer: Mapped["Customer"] = relationship(back_populates="orders")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(Integer, ForeignKey("businesses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    image_url: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    business: Mapped["Business"] = relationship(back_populates="products")
