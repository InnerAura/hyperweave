"""The published OpenAPI contract for routes that can answer with a Response.

A route annotated ``-> dict[str, Any] | JSONResponse`` (the shape that lets an
error branch hand back an envelope) makes FastAPI refuse to infer a response
model. Silencing that with ``response_model=None`` erases the published 200
schema to ``{}`` — the route still works, every functional test still passes,
and only the OpenAPI document regresses. So the schema itself is asserted here.

The fix is an explicit ``response_model``; these tests pin that it stays.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from hyperweave.serve.app import app

# Routes that return a union with JSONResponse and must still publish a schema.
_UNION_RETURN_ROUTES = ["/v1/discover"]


def _response_schema(path: str, status: str = "200") -> dict[str, Any]:
    """The JSON schema the OpenAPI document publishes for ``path``."""
    spec = app.openapi()
    content = spec["paths"][path]["get"]["responses"][status]["content"]
    schema: dict[str, Any] = content["application/json"]["schema"]
    return schema


@pytest.fixture()
async def client() -> Any:
    """Async test client wrapping the FastAPI app via ASGI transport."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.parametrize("path", _UNION_RETURN_ROUTES)
def test_union_return_routes_still_publish_an_object_schema(path: str) -> None:
    """An empty ``{}`` here means a response_model was dropped, not that the route broke."""
    schema = _response_schema(path)
    assert schema, f"{path} publishes an empty 200 schema — response_model was erased"
    assert schema.get("type") == "object", f"{path} 200 schema type is {schema.get('type')!r}, expected 'object'"
    assert schema.get("additionalProperties") is True, f"{path} 200 schema lost additionalProperties: {schema!r}"


async def test_discover_answers_a_known_selector(client: AsyncClient) -> None:
    """The happy path the published object schema describes."""
    response = await client.get("/v1/discover", params={"what": "verbs"})
    assert response.status_code == 200
    assert isinstance(response.json(), dict)


async def test_discover_refuses_an_unknown_selector(client: AsyncClient) -> None:
    """The error branch — the reason the return annotation is a union at all."""
    response = await client.get("/v1/discover", params={"what": "not-a-real-selector"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TYPE_UNKNOWN"
