"""Matrix HTTP surface: GET preset/custom routes, POST json, error grammar."""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from hyperweave.serve.app import app
from tests.conftest import FIXTURES_DIR

TINY = {
    "title": "Tiny",
    "columns": [{"id": "v", "label": "V"}],
    "rows": [{"label": "one", "cells": [{"value": 1}]}],
}


def b64(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestGetPreset:
    def test_connectors_preset(self, client: TestClient) -> None:
        response = client.get("/v1/matrix/connectors/primer.static?variant=porcelain")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        assert 'data-hw-subvariant="registry"' in response.text
        assert "ETag" in response.headers

    def test_etag_304(self, client: TestClient) -> None:
        first = client.get("/v1/matrix/connectors/primer.static")
        revisit = client.get("/v1/matrix/connectors/primer.static", headers={"if-none-match": first.headers["ETag"]})
        assert revisit.status_code == 304

    def test_unknown_preset_degrades_to_smpte_404(self, client: TestClient) -> None:
        response = client.get("/v1/matrix/nope/primer.static")
        assert response.status_code == 200  # Camo rule: error class in header + SVG
        assert response.headers["X-HW-Error-Code"] == "404"
        assert "NO SIGNAL" in response.text or "data-hw-status-code" in response.text


class TestGetCustomSpec:
    def test_inline_spec_renders(self, client: TestClient) -> None:
        response = client.get(f"/v1/matrix/custom/primer.static?spec={b64(TINY)}")
        assert response.status_code == 200
        assert "TINY" in response.text  # masthead uppercases the title

    def test_fixture_spec_renders(self, client: TestClient) -> None:
        check = json.loads((FIXTURES_DIR / "matrix" / "check.json").read_text())
        response = client.get(f"/v1/matrix/custom/primer.static?variant=noir&spec={b64(check)}")
        assert response.status_code == 200
        assert 'data-hw-subvariant="check"' in response.text

    def test_missing_spec_is_400(self, client: TestClient) -> None:
        response = client.get("/v1/matrix/custom/primer.static")
        assert response.status_code == 200
        assert response.headers["X-HW-Error-Code"] == "400"

    def test_garbage_spec_is_400(self, client: TestClient) -> None:
        response = client.get("/v1/matrix/custom/primer.static?spec=%%%not-b64")
        assert response.headers["X-HW-Error-Code"] == "400"

    def test_oversize_spec_is_400(self, client: TestClient) -> None:
        huge = dict(TINY, title="x" * 9000)
        response = client.get(f"/v1/matrix/custom/primer.static?spec={b64(huge)}")
        assert response.headers["X-HW-Error-Code"] == "400"

    def test_hard_cap_is_422(self, client: TestClient) -> None:
        over = {
            "title": "Cap",
            "columns": [{"id": "v", "label": "V"}],
            "rows": [{"label": f"r{i}", "cells": [{"value": i}]} for i in range(31)],
        }
        response = client.get(f"/v1/matrix/custom/primer.static?spec={b64(over)}")
        assert response.headers["X-HW-Error-Code"] == "422"

    def test_unsupported_genome_is_422(self, client: TestClient) -> None:
        response = client.get("/v1/matrix/connectors/brutalist.static")
        assert response.headers["X-HW-Error-Code"] == "422"


class TestPostCompose:
    def test_matrix_body_svg(self, client: TestClient) -> None:
        response = client.post("/v1/compose", json={"type": "matrix", "genome": "primer", "matrix": TINY})
        assert response.status_code == 200
        assert response.text.startswith("<svg")

    def test_respond_json_carries_markdown_shadow(self, client: TestClient) -> None:
        response = client.post(
            "/v1/compose",
            json={"type": "matrix", "genome": "primer", "variant": "porcelain", "matrix": TINY, "respond": "json"},
        )
        body = response.json()
        assert body["svg"].startswith("<svg")
        assert body["markdown"].startswith("**Tiny**")
        # adaptive width: a one-column TINY matrix shrinks to the frame floor
        assert 400 <= body["width"] <= 900 and body["height"] > 0


class TestDiscovery:
    def test_frames_endpoint_lists_matrix_grammar(self, client: TestClient) -> None:
        frames = client.get("/v1/frames").json()
        matrix = next(f for f in frames if f["type"] == "matrix")
        assert matrix["pattern"] == "/v1/matrix/{preset}/{genome}.{motion}"
        assert "spec" in matrix["query_params"]
