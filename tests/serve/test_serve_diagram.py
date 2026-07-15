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
        response = client.get("/v1/diagram/rag-pipeline/primer.static?variant=porcelain")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/svg+xml")
        assert 'data-hw-subvariant="pipeline"' in response.text
        assert "ETag" in response.headers

    def test_etag_304(self, client: TestClient) -> None:
        first = client.get("/v1/diagram/flywheel-orbit/primer.static")
        revisit = client.get(
            "/v1/diagram/flywheel-orbit/primer.static", headers={"if-none-match": first.headers["ETag"]}
        )
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
        # The kit grammar is compositor-only by construction — the artifact
        # self-describes composite-only on every tier.
        response = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&edge_motion=particle")
        assert 'performance="composite-only"' in response.text

    def test_retired_motion_rejected_at_the_edge(self, client: TestClient) -> None:
        # beam/flow retired with the kit grammar: the Query pattern 422s
        # before compose ever runs.
        response = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&edge_motion=beam")
        assert response.status_code == 422

    def test_composite_only_renders_the_same_grammar(self, client: TestClient) -> None:
        url = f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&edge_motion=particle&performance=composite-only"
        response = client.get(url)
        assert response.status_code == 200
        rendered = payload_of(response.text)["rendered"]
        assert rendered["performance"] == "composite-only"
        assert set(rendered["edge_motion"]) == {"particle"}
        assert payload_of(response.text)["spec"]["edge_motion"] == "particle"

    def test_performance_rejects_unknown_tier(self, client: TestClient) -> None:
        response = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&performance=warp-speed")
        assert response.status_code == 422  # FastAPI Query pattern validation

    def test_public_diagram_never_renders_masthead_or_brand_footer(self, client: TestClient) -> None:
        """`chrome` is retired from the public HTTP surface — every diagram
        renders kit chrome (caption): no masthead band, no brand-footer
        line, ONE caption sentence at the base (subtitle falls back to
        title). The title still ships in the metadata projections."""
        svg = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&variant=porcelain").text
        assert 'fill="var(--dna-surface)"' in svg  # the substrate rect still paints (plate ground)
        assert 'data-hw-region="masthead"' not in svg
        assert "INNERAURA LABS" not in svg
        assert ">Tiny</text>" in svg  # the caption sentence
        assert '"title":"Tiny"' in svg  # payload spec keeps it

    def test_chrome_query_param_is_ignored(self, client: TestClient) -> None:
        """`?chrome=` has no public route parameter anymore — FastAPI drops
        the unrecognized query key, so a stray value (old bookmarked URL,
        stale client) neither errors nor changes the render or its identity."""
        # Strip every live ISO-8601 timestamp (hw:created, dc:date, the
        # envelope payload's "ts" field) so the comparison isolates the
        # chrome axis rather than tripping on request-time clocks.
        strip_created = lambda svg: re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+\+00:00", "", svg)  # noqa: E731
        plain = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}").text
        with_param = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&chrome=bare").text
        with_bad_value = client.get(f"/v1/diagram/custom/primer.static?spec={b64(TINY)}&chrome=fancy")
        uid_of = lambda svg: re.search(r'data-hw-id="([^"]+)"', svg).group(1)  # noqa: E731
        assert uid_of(plain) == uid_of(with_param)
        assert strip_created(plain) == strip_created(with_param)
        assert with_bad_value.status_code == 200

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

    def test_post_composite_only_same_grammar(self, client: TestClient) -> None:
        response = client.post(
            "/v1/compose",
            json={
                "type": "diagram",
                "genome": "primer",
                "diagram": dict(TINY, edge_motion="dash"),
                "performance": "composite-only",
            },
        )
        assert response.status_code == 200
        rendered = payload_of(response.text)["rendered"]
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
    """POST /v1/diagram is retired — use POST /v1/compose with type=diagram."""

    def test_post_diagram_is_gone(self, client: TestClient) -> None:
        r = client.post("/v1/diagram", json={"genome": "primer", "diagram": TINY})
        assert r.status_code in (404, 405)


class TestFramesLayoutSlugs:
    def test_frames_diagram_enumerates_16_slugs(self, client: TestClient) -> None:
        frames = client.get("/v1/frames").json()
        dia = next(f for f in frames if f["type"] == "diagram")
        slugs = dia["layout_slugs"]
        assert len(slugs) == 18
        assert {"fanout-radial", "fanout-downward", "tree-radial", "dag", "state-machine", "hub", "lanes"} <= set(slugs)
