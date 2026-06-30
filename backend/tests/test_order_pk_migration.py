"""Migration: legacy integer-PK orders table → UUIDv7 string PK + per-business order_seq."""
import sqlite3
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app import models  # noqa: F401  (populates Base.metadata)
from app.core.database import Base, _run_migrations


async def test_order_pk_migration(tmp_path):
    db = tmp_path / "orders_legacy.db"
    con = sqlite3.connect(db)
    # Minimal legacy schema — just the tables migrations check for
    con.execute(
        "CREATE TABLE businesses ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "phone_number VARCHAR(32) UNIQUE NOT NULL, "
        "business_name VARCHAR(255) NOT NULL, "
        "settings JSON, "
        "created_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    con.execute("INSERT INTO businesses (phone_number, business_name) VALUES ('0811', 'Toko A')")
    con.execute(
        "CREATE TABLE orders ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "business_id INTEGER NOT NULL, "
        "customer_id INTEGER NOT NULL, "
        "items JSON NOT NULL, "
        "total FLOAT, "
        "status VARCHAR(32), "
        "created_at DATETIME NOT NULL)"
    )
    # 3 rows: business 1 × 2 rows, business 2 × 1 row
    con.execute("INSERT INTO orders (business_id, customer_id, items, total, status, created_at) VALUES (1, 10, '[]', 10.0, 'pending', '2024-01-01 10:00:00')")
    con.execute("INSERT INTO orders (business_id, customer_id, items, total, status, created_at) VALUES (1, 11, '[]', 20.0, 'pending', '2024-01-01 11:00:00')")
    con.execute("INSERT INTO orders (business_id, customer_id, items, total, status, created_at) VALUES (2, 12, '[]', 30.0, 'pending', '2024-01-01 12:00:00')")
    con.commit()
    con.close()

    eng = create_async_engine(f"sqlite+aiosqlite:///{db}")
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_run_migrations)
            await conn.run_sync(_run_migrations)  # idempotent — must not error
        async with eng.connect() as conn:
            # Check id column type is now TEXT/VARCHAR
            col_info = (await conn.execute(text("PRAGMA table_info(orders)"))).all()
            id_col = next(c for c in col_info if c[1] == "id")
            assert "INT" not in id_col[2].upper(), f"id column type should not be INT, got {id_col[2]}"

            rows = (await conn.execute(text("SELECT id, business_id, order_seq FROM orders ORDER BY business_id, order_seq"))).all()
            assert len(rows) == 3

            # Each id must parse as a UUID
            for row in rows:
                uuid.UUID(row[0])  # raises if invalid

            # per-business order_seq must be {1, 2} for biz 1 and {1} for biz 2
            biz1 = {r[2] for r in rows if r[1] == 1}
            biz2 = {r[2] for r in rows if r[1] == 2}
            assert biz1 == {1, 2}, f"Expected {{1, 2}} for biz 1, got {biz1}"
            assert biz2 == {1}, f"Expected {{1}} for biz 2, got {biz2}"
    finally:
        await eng.dispose()
