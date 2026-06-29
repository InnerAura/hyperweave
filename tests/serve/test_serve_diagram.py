"""Diagram HTTP surface: GET preset/custom routes, POST json, error grammar."""

from __future__ import annotations

import base64
import json
import re

import pytest
from fastapi.testclient import TestClient

from hyperweave.serve.app import app

TINY = {
    "topology": "pipeline",
    "title": "Tiny",
    "nodes": [{"label": "A"}, {"label": "B", "role": "hero"}, {"label": "C"}],
}

_PAYLOAD_RE = re.compile(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", re.DOTALL)


def payload_of(svg: str) -> dict:
    m = _PAYLOAD_RE.search(svg)
    assert m, "hw:payload missing"
    return json.loads(m.group(1))


def b64(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestGetPreset:
    def test_pipeline_preset(self, client: TestClient) -> None:
        response = client.get("/v1/diagram/pipeline/primer.static?variant=porcelain")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        assert 'data-hw-subvariant="pipeline"' in response.text
        assert "ETag" in response.headers

    def test_etag_304(self, client: TestClient) -> None:
        first = client.get("/v1/diagram/flywheel/primer.static")
        revisit = client.get("/v1/diagram/flywheel/primer.static", headers={"if-none-match": first.headers["ETag"]})
        assert revisit.status_code == 304

    def test_unknown_preset_smpte(self, client: TestClient) -> None:
        response = client.get("/v1/diagram/no-such-preset/primer.static")
        assert response.status_code == 200  # Camo-safe SMPTE artifact
        assert response.headers["x-hw-error-code"] == "404"
        assert "NO SIGNAL" in response.text


class TestGetCustom:
    def test_inline_spec_renders(self, client: TestClient) -> None:
        response = client.get(f"/v1/diagram/custom/primer.static?variant=porcelain&spec={b64(TINY)}")
        assert response.status_code == 200
        assert 'data-hw-topology="pipeline"' in response.text

    def test_edge_motion_override(self, client: TestClient) -> None:
        response = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&edge_motion=beam")
        assert 'performance="paint-ok"' in response.text

    def test_composite_only_ladders_beam_to_particle(self, client: TestClient) -> None:
        url = f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&edge_motion=beam&performance=composite-only"
        response = client.get(url)
        assert response.status_code == 200
        rendered = payload_of(response.text)["rendered"]
        assert rendered["performance"] == "composite-only"
        assert rendered["fallback_applied"] is True
        assert set(rendered["edge_motion"]) == {"particle"}
        # Requested stays intact in the spec half — never silently diverges.
        assert payload_of(response.text)["spec"]["edge_motion"] == "beam"

    def test_performance_rejects_unknown_tier(self, client: TestClient) -> None:
        response = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&performance=warp-speed")
        assert response.status_code == 422  # FastAPI Query pattern validation

    def test_bare_chrome_drops_masthead_footer_substrate(self, client: TestClient) -> None:
        card = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&variant=porcelain").text
        bare = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&variant=porcelain&chrome=bare").text
        assert 'fill="var(--dna-surface)"' in card and 'fill="var(--dna-surface)"' not in bare
        assert ">Tiny</text>" in card and ">Tiny</text>" not in bare  # no masthead
        assert "INNERAURA LABS" in card and "INNERAURA LABS" not in bare  # no footer
        assert "<hw:title>Tiny</hw:title>" in bare or "Tiny" in bare.split("<svg")[0] or "hw:payload" in bare
        # The title still ships in the metadata projections.
        assert '"title":"Tiny"' in bare  # payload spec keeps it

    def test_chrome_is_outside_the_envelope_digest(self, client: TestClient) -> None:
        card = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}").text
        bare = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&chrome=bare").text
        uid_of = lambda svg: re.search(r'data-hw-id="([^"]+)"', svg).group(1)  # noqa: E731
        assert uid_of(card) == uid_of(bare)  # same content, same identity
        assert card != bare  # different dressing

    def test_chrome_rejects_unknown_value(self, client: TestClient) -> None:
        response = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&chrome=fancy")
        assert response.status_code == 422

    def test_missing_spec_400(self, client: TestClient) -> None:
        response = client.get("/v1/diagram/custom/primer.static")
        assert response.headers["x-hw-error-code"] == "400"

    def test_garbage_spec_400(self, client: TestClient) -> None:
        response = client.get("/v1/diagram/custom/primer.static?spec=@@not-base64@@")
        assert response.headers["x-hw-error-code"] == "400"

    def test_oversize_spec_400(self, client: TestClient) -> None:
        fat = dict(TINY, notes="x" * 9000)
        response = client.get(f"/v1/diagram/custom/primer.static?spec={b64(fat)}")
        assert response.headers["x-hw-error-code"] == "400"

    def test_bad_topology_422(self, client: TestClient) -> None:
        bad = {"topology": "sequence", "title": "T", "nodes": [{"label": "A"}, {"label": "B"}]}
        # sequence without edges is a caller error: data topologies declare
        # their content.
        response = client.get(f"/v1/diagram/custom/primer.static?spec={b64(bad)}")
        assert response.headers["x-hw-error-code"] in ("400", "422")


class TestPostCompose:
    def test_post_body(self, client: TestClient) -> None:
        response = client.post(
            "/v1/compose",
            json={"type": "diagram", "genome": "primer", "variant": "porcelain", "diagram": TINY},
        )
        assert response.status_code == 200
        assert 'data-hw-frame="diagram"' in response.text or 'data-hw-type="diagram"' in response.text

    def test_post_composite_only_records_fallback(self, client: TestClient) -> None:
        response = client.post(
            "/v1/compose",
            json={
                "type": "diagram",
                "genome": "primer",
                "diagram": dict(TINY, edge_motion="flow"),
                "performance": "composite-only",
            },
        )
        assert response.status_code == 200
        rendered = payload_of(response.text)["rendered"]
        assert rendered["fallback_applied"] is True
        assert set(rendered["edge_motion"]) == {"dash"}

    def test_post_respond_json_carries_markdown(self, client: TestClient) -> None:
        response = client.post(
            "/v1/compose",
            json={
                "type": "diagram",
                "genome": "primer",
                "diagram": TINY,
                "respond": "json",
            },
        )
        body = response.json()
        assert body["markdown"].startswith("**Tiny**")


class TestGrammar:
    def test_frames_lists_diagram(self, client: TestClient) -> None:
        response = client.get("/v1/frames")
        assert "/v1/diagram/{preset}/{genome}.{motion}" in response.text


class TestPostDiagramRetired:
    """POST /v1/diagram was retired in alpha.5 — use POST /v1/compose with type=diagram."""

    def test_post_diagram_is_gone(self, client: TestClient) -> None:
        r = client.post("/v1/diagram", json={"genome": "primer", "diagram": TINY})
        assert r.status_code in (404, 405)


class TestFramesLayoutSlugs:
    def test_frames_diagram_enumerates_14_slugs(self, client: TestClient) -> None:
        frames = client.get("/v1/frames").json()
        dia = next(f for f in frames if f["type"] == "diagram")
        slugs = dia["layout_slugs"]
        assert len(slugs) == 14
        assert {"fanout-radial", "tree-radial", "dag", "state-machine"} <= set(slugs)
