"""Phase B columns are added idempotently to legacy products/businesses tables."""
import pytest
from sqlalchemy import inspect


@pytest.mark.asyncio
async def test_product_and_business_phase_b_columns_present(client):
    """The app fixture runs init_db(); new columns must exist after startup."""
    import database

    async with database.engine.begin() as conn:
        cols = await conn.run_sync(
            lambda sync: {
                "products": {c["name"] for c in inspect(sync).get_columns("products")},
                "businesses": {c["name"] for c in inspect(sync).get_columns("businesses")},
            }
        )
    assert {"embedding", "embedding_hash"} <= cols["products"]
    assert {"payment_methods", "qris_image_url"} <= cols["businesses"]
