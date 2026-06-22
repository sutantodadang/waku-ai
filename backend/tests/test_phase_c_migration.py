"""Phase C columns + tables exist after init_db; existing businesses default to warung."""
from sqlalchemy import inspect
import pytest


@pytest.mark.asyncio
async def test_phase_c_schema(client):
    import database

    async with database.engine.begin() as conn:
        s = await conn.run_sync(lambda conn_sync: {
            "tables": set(inspect(conn_sync).get_table_names()),
            "businesses": {c["name"] for c in inspect(conn_sync).get_columns("businesses")},
            "products": {c["name"] for c in inspect(conn_sync).get_columns("products")},
        })

    assert {"staff", "bookings"} <= s["tables"]
    assert "business_type" in s["businesses"]
    assert "duration_minutes" in s["products"]


def test_existing_business_defaults_to_warung(client):
    from helpers import register, auth
    t = register(client)
    r = client.get("/api/business", headers=auth(t["access_token"]))
    assert r.status_code == 200
    assert r.json()["business_type"] == "warung"
