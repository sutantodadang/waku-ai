from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_business
from app.models import Business, Product
from app.schemas import (
    ProductCreate,
    ProductResponse,
    ProductUpdate,
)
from app.services.embeddings import embed_product

logger = logging.getLogger("waku.backend")

router = APIRouter()


@router.get("/api/products", response_model=list[ProductResponse])
async def dashboard_list_products(
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """GET /api/products — list all products for the authenticated business."""
    stmt = (
        select(Product)
        .where(Product.business_id == business.id)
        .order_by(Product.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


@router.post("/api/products", response_model=ProductResponse, status_code=201)
async def dashboard_create_product(
    body: ProductCreate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """POST /api/products — create a product for the authenticated business."""
    product = Product(
        business_id=business.id,
        name=body.name,
        price=body.price,
        description=body.description,
        image_url=body.image_url,
        duration_minutes=body.duration_minutes,
    )
    session.add(product)
    await session.flush()
    await embed_product(session, product)
    logger.info("Product #%d '%s' created for business %d", product.id, product.name, business.id)
    return product


@router.put("/api/products/{product_id}", response_model=ProductResponse)
async def dashboard_update_product(
    product_id: int,
    body: ProductUpdate,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """PUT /api/products/{id} — update a product (partial update)."""
    stmt = select(Product).where(Product.id == product_id, Product.business_id == business.id)
    product = (await session.execute(stmt)).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found for this business.")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
    await session.flush()
    await embed_product(session, product)
    return product


@router.delete("/api/products/{product_id}")
async def dashboard_delete_product(
    product_id: int,
    session: AsyncSession = Depends(get_db),
    business: Business = Depends(get_current_business),
):
    """DELETE /api/products/{id} — delete a product."""
    stmt = select(Product).where(Product.id == product_id, Product.business_id == business.id)
    product = (await session.execute(stmt)).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found for this business.")

    await session.delete(product)
    await session.flush()
    return {"status": "ok", "deleted": product_id}
