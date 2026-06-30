"""
Order extraction service — parse Indonesian order patterns from text,
manage orders and provide daily summaries.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Customer, Message, Order, Product

logger = logging.getLogger(__name__)

REGULAR_THRESHOLD = 5

# ── Regex patterns for Indonesian order text ────────────────────────────────────
# Matches patterns like:
#   "beli 2 nasi goreng"
#   "1 es teh"
#   "pesan 3 ayam geprek"
#   "2x bakso"
#   "2 buah nasi goreng"
#   "satu nasi goreng"
QUANTITY_WORDS: dict[str, int] = {
    "satu": 1, "dua": 2, "tiga": 3, "empat": 4,
    "lima": 5, "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9,
    "sepuluh": 10,
}

# Match digits (including word numbers) followed by an item name.
# Item names are sequences of word characters, spaces, hyphens, parentheses.
# We split items on commas / 'dan' / 'sama' / 'plus' first.
ITEM_UNIT = r"(?:x|\*|buah|porsi|gelas|bungkus|pack|kotak|lembar|piring|mangkok|botol|kardus|slop|kg|gram|liter|ml)"

ITEM_PATTERN = re.compile(
    r"(?P<qty>\d+)\s*"
    + ITEM_UNIT + r"?\s*"
    + r"(?P<item>[\w\s\-\(\)]+)"
    + r"(?:\s+" + ITEM_UNIT + r")?"
    + r"(?:\s+(?:sebesar|rp|idr)\s*(?P<price>[\d.,]+))?",
    re.IGNORECASE,
)

# Split on commas, 'dan', 'sama', 'plus', '&' for multiple items
SPLIT_PATTERN = re.compile(
    r"(?:,|\s+dan\s+|\s+sama\s+|\s+plus\s+|\s*&\s*)",
    re.IGNORECASE,
)


def extract_order_from_message(text: str, known_products: Optional[dict[str, float]] = None) -> list[dict]:
    """
    Parse a natural-language order message in Indonesian.
    Returns a list of item dicts: [{"name": str, "quantity": int, "price": Optional[float]}]

    Examples:
        "beli 2 nasi goreng dan 1 es teh"  → [{"name":"nasi goreng","qty":2}, {"name":"es teh","qty":1}]
        "2x bakso, 3 es jeruk"              → [{"name":"bakso","qty":2}, {"name":"es jeruk","qty":3}]
        "saya mau pesan 1 nasi goreng"      → [{"name":"nasi goreng","qty":1}]
    """
    text = text.strip()
    items: list[dict] = []
    seen: set[str] = set()

    # Strip common prefixes (beli, pesan, mau, etc.)
    prefix_pattern = re.compile(
        r"^(?:saya\s+)?(?:mau|ingin|pesan|beli|order|minta|tolong)\s+",
        re.IGNORECASE,
    )
    text = prefix_pattern.sub("", text).strip()

    # Catalog-driven matching: when we know the business's products, match those
    # names directly. Far more reliable than the generic regex, and gives correct
    # display name + price (so the dashboard total is real, not 0).
    if known_products:
        text_low = re.sub(r"\s+", " ", text.lower())
        for pname in sorted(known_products, key=len, reverse=True):
            nlow = pname.lower()
            if nlow in seen or nlow not in text_low:
                continue
            idx = text_low.find(nlow)
            before, after = text_low[:idx], text_low[idx + len(nlow):]
            qty = 1
            m_before = re.search(r"(\d+)\s*x?\s*$", before)
            m_after = re.match(r"\s*x?\s*(\d+)", after)
            if m_before:
                qty = int(m_before.group(1))
            elif m_after:
                qty = int(m_after.group(1))
            else:
                for word, num in QUANTITY_WORDS.items():
                    if re.search(r"\b" + word + r"\b", before):
                        qty = num
                        break
            seen.add(nlow)
            items.append({"name": pname, "quantity": qty, "price": known_products[pname]})
        # Catalog is authoritative: an off-catalog item ("motor", "mobil") is not a
        # real order. Return whatever matched (possibly nothing) and never fall
        # through to the generic regex, which would invent a Rp0 phantom order.
        logger.debug("Catalog-matched %d items from: '%s'", len(items), text[:80])
        return items

    # No catalog known — best-effort generic parse.
    # Split into segments on commas / dan / sama / plus
    segments = SPLIT_PATTERN.split(text)

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        # Normalise whitespace
        segment = re.sub(r"\s+", " ", segment)

        m = ITEM_PATTERN.search(segment)
        if not m:
            continue

        raw_item = m.group("item").strip().lower()
        # Remove trailing noise (units, etc.)
        for unit in ["x", "*", "buah", "porsi", "gelas", "bungkus", "pack",
                      "kotak", "lembar", "piring", "mangkok", "botol",
                      "kardus", "slop", "kg", "gram", "liter", "ml"]:
            if raw_item.endswith(" " + unit):
                raw_item = raw_item[: -len(unit) - 1].strip()
                break
            if raw_item.endswith(unit):
                raw_item = raw_item[: -len(unit)].strip()
                break
            if raw_item.endswith(" " + unit + "s"):
                raw_item = raw_item[: -len(unit) - 2].strip()
                break

        raw_item = re.sub(r"\s+", " ", raw_item)
        if not raw_item or raw_item in seen:
            continue
        seen.add(raw_item)

        qty: int = 1
        if m.group("qty"):
            qty = int(m.group("qty"))
        else:
            # Check for Indonesian number words before the item
            for word, num in QUANTITY_WORDS.items():
                if word in segment.lower():
                    qty = num
                    break

        price: Optional[float] = None
        if m.group("price"):
            price_str = m.group("price").replace(",", ".")
            try:
                price = float(price_str)
            except ValueError:
                price = None
        elif known_products and raw_item in known_products:
            price = known_products[raw_item]

        items.append({
            "name": raw_item,
            "quantity": qty,
            "price": price,
        })

    if not items:
        # Fallback: try to extract any "number + word" pattern
        fallback = re.findall(r"(\d+)\s*[x\*]?\s*([a-zA-Z]+(?:[\s-][a-zA-Z]+)*)", text, re.IGNORECASE)
        for qty_str, item_name in fallback:
            name = item_name.strip().lower()
            name = re.sub(r"\s+", " ", name)
            if name not in seen:
                seen.add(name)
                items.append({"name": name, "quantity": int(qty_str), "price": None})

    logger.debug("Extracted %d items from: '%s'", len(items), text[:80])
    return items


# ── Database operations ─────────────────────────────────────────────────────────
async def get_or_create_customer(
    session: AsyncSession,
    business_id: int,
    phone_number: str,
    name: Optional[str] = None,
) -> Customer:
    """Look up a customer by phone + business, or create them."""
    stmt = select(Customer).where(
        Customer.business_id == business_id,
        Customer.phone_number == phone_number,
    )
    result = await session.execute(stmt)
    customer = result.scalar_one_or_none()

    if customer is None:
        customer = Customer(
            phone_number=phone_number,
            business_id=business_id,
            name=name or phone_number,
        )
        session.add(customer)
        await session.flush()
        logger.info("Created customer %s for business %d", phone_number, business_id)
    elif name and customer.name != name:
        customer.name = name
        await session.flush()

    return customer


async def save_message(
    session: AsyncSession,
    business_id: int,
    customer_id: int,
    content: str,
    direction: str,
    wamid: Optional[str] = None,
    media_url: Optional[str] = None,
) -> Message:
    """Persist a message to the database."""
    msg = Message(
        business_id=business_id,
        customer_id=customer_id,
        content=content,
        direction=direction,
        wamid=wamid,
        media_url=media_url,
    )
    session.add(msg)
    await session.flush()
    return msg


async def create_order(
    session: AsyncSession,
    business_id: int,
    customer_id: int,
    items: list[dict],
) -> Order:
    """Create an order from a list of item dicts."""
    total = sum(
        (it.get("price") or 0) * (it.get("quantity") or 1)
        for it in items
    )
    next_seq = (
        await session.execute(
            select(func.coalesce(func.max(Order.order_seq), 0) + 1).where(
                Order.business_id == business_id
            )
        )
    ).scalar_one()
    # ponytail: MAX+1 per business — fine for UMKM volume / single worker.
    # If concurrent writers ever collide, the uq_orders_business_seq constraint catches it.
    order = Order(
        business_id=business_id,
        customer_id=customer_id,
        order_seq=next_seq,
        items=items,
        total=total,
        status="pending",
    )
    session.add(order)
    await session.flush()
    logger.info(
        "Order #%s created — business=%d customer=%d total=%.2f",
        order.id, business_id, customer_id, total,
    )
    return order


async def find_amendable_order(
    session: AsyncSession, business_id: int, customer_id: int, within_hours: int = 6
) -> Optional[Order]:
    """Most recent non-terminal order (pending/confirmed) within the window, else None."""
    cutoff = datetime.utcnow() - timedelta(hours=within_hours)
    stmt = (
        select(Order)
        .where(
            Order.business_id == business_id,
            Order.customer_id == customer_id,
            Order.status.in_(("pending", "confirmed")),
            Order.created_at >= cutoff,
        )
        .order_by(Order.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def update_order_items(session: AsyncSession, order: Order, items: list[dict]) -> Order:
    """Replace an order's items and recompute its total."""
    order.items = items
    order.total = sum((it.get("price") or 0) * (it.get("quantity") or 1) for it in items)
    await session.flush()
    return order


def is_regular(cust: Customer) -> bool:
    """Loyalty is derived, never stored. Owner override wins when set."""
    if cust.is_regular_override is not None:
        return bool(cust.is_regular_override)
    return (cust.order_count or 0) >= REGULAR_THRESHOLD


async def recompute_customer_stats(session: AsyncSession, customer_id: int) -> None:
    """Recompute the cached stats on a customer from their non-cancelled orders.
    Single source of truth — call after any order create / status change."""
    cust = await session.get(Customer, customer_id)
    if cust is None:
        return

    orders = list((await session.execute(
        select(Order)
        .where(Order.customer_id == customer_id, Order.status != "cancelled")
        .order_by(Order.created_at)
    )).scalars().all())

    cust.order_count = len(orders)
    cust.total_spent = float(sum(o.total or 0 for o in orders))
    cust.last_order_at = orders[-1].created_at if orders else None

    counts: dict[str, int] = {}
    for o in orders:
        for it in (o.items or []):
            name = (it.get("name") or "").strip()
            if not name:
                continue
            qty = int(it.get("quantity") or it.get("qty") or 1)
            counts[name] = counts.get(name, 0) + qty
    top = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
    cust.top_items = [{"name": n, "count": c} for n, c in top]

    if len(orders) >= 2:
        dates = [o.created_at for o in orders]
        gaps = [(dates[i] - dates[i - 1]).total_seconds() / 86400 for i in range(1, len(dates))]
        cust.avg_cadence_days = sum(gaps) / len(gaps)
    else:
        cust.avg_cadence_days = None

    cust.stats_updated_at = datetime.utcnow()
    await session.flush()


async def get_orders_for_business(
    session: AsyncSession,
    business_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[Order]:
    """Fetch orders for a given business, newest first."""
    stmt = (
        select(Order)
        .where(Order.business_id == business_id)
        .order_by(Order.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_daily_summary(session: AsyncSession, business_id: int, day: Optional[date] = None) -> dict:
    """
    Aggregate daily statistics for a business.
    Returns:
        {
            "date": "2025-01-15",
            "total_conversations": int,   # unique customers who messaged
            "total_orders": int,
            "total_revenue": float,
            "orders": [Order, ...]
        }
    """
    if day is None:
        day = date.today()

    day_start = datetime.combine(day, datetime.min.time())
    day_end = datetime.combine(day, datetime.max.time())

    # Count unique customers who had inbound messages today
    conv_stmt = (
        select(func.count(func.distinct(Message.customer_id)))
        .where(
            Message.business_id == business_id,
            Message.direction == "inbound",
            Message.timestamp >= day_start,
            Message.timestamp <= day_end,
        )
    )
    conv_result = await session.execute(conv_stmt)
    total_conversations: int = conv_result.scalar() or 0

    # Orders today
    order_stmt = (
        select(Order)
        .where(
            Order.business_id == business_id,
            Order.created_at >= day_start,
            Order.created_at <= day_end,
        )
        .order_by(Order.created_at.desc())
    )
    order_result = await session.execute(order_stmt)
    orders = list(order_result.scalars().all())

    total_orders = len(orders)
    total_revenue = sum(o.total for o in orders)

    return {
        "date": day.isoformat(),
        "total_conversations": total_conversations,
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "orders": orders,
    }
