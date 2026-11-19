import pytest
from httpx import ASGITransport, AsyncClient

from app.api.main import app


@pytest.mark.asyncio
async def test_api_liveness_is_public_and_contains_no_private_data() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")
        docs = await client.get("/docs")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert docs.status_code == 404
