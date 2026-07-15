"""Faces emit + surface props wiring across CLI / HTTP / MCP (task #16).

The projection math (WC-1) and emission internals (WC-2a) are tested elsewhere;
this file pins the LAST mile — that ``surface``/``ground``/``palette``/``faces``
reach ``compose_surface`` from every transport, that the twin faces round-trip
(the two URLs resolve to artifacts content-identical to a direct face compose),
that the bare+fixed trap is rejected on each surface, that ``surface=`` sugar
expands to axes before ComposeSpec, and that plate/inlay/twin/faces stay distinct
content addresses. It also pins the singular ``face=`` axis (HTTP GET diagram/
matrix, POST /v1/compose, MCP hw_compose) reaching the resolver with CLI
``--face``-identical override semantics — the face commits palette=fixed even
over an explicit adaptive surface/palette request.
"""

from __future__ import annotations

import re

import pytest

from hyperweave.compose.artifact_store import get_artifact, reset_cache
from hyperweave.compose.engine import compose
from hyperweave.compose.surface import SpecEnvelope, compose_surface
from hyperweave.core.envelope import extract_envelope
from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.core.models import ComposeSpec

# Wall-clock provenance (font subsetter timestamp + <hw:created>/<dc:date>/envelope
# ts) is excluded from the content digest, so two composes at different instants
# share a digest but differ in these bytes. Normalize them to compare "byte-equal
# modulo provenance" — the honest form of the round-trip proof.
_FONT_BLOB = re.compile(r"data:[^;]*;base64,[A-Za-z0-9+/=]+")
_ISO_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+\+00:00")


def _normalize(svg: str) -> str:
    return _ISO_TS.sub("TS", _FONT_BLOB.sub("FONT", svg))


def _matrix_ir() -> dict[str, object]:
    return {
        "title": "Faces",
        "subtitle": "twin",
        "columns": [
            {"id": "m", "label": "MODEL", "role": "label"},
            {"id": "s", "label": "SCORE", "role": "data", "kind": "numeric"},
        ],
        "rows": [
            {"label": "a", "cells": [{"value": 91}]},
            {"label": "b", "cells": [{"value": 84}]},
        ],
    }


def _digest_of(url: str) -> str:
    return "sha256:" + url.rsplit("/", 1)[-1]


# ── core: faces emit round-trip + distinctness ─────────────────────────────


def test_faces_emit_returns_light_dark_urls() -> None:
    reset_cache()
    resp = compose_surface(
        SpecEnvelope(
            type="matrix",
            genome="primer",
            variant="porcelain",
            spec={**_matrix_ir(), "ground": "opaque", "palette": "adaptive"},
            emit=("faces",),
        ),
        base_url="https://hyperweave.app",
    )
    assert resp.faces is not None
    assert set(resp.faces) == {"light", "dark"}
    assert resp.faces["light"] != resp.faces["dark"]
    # both faces are cached under their digests
    assert get_artifact(_digest_of(resp.faces["light"])) is not None
    assert get_artifact(_digest_of(resp.faces["dark"])) is not None


def test_faces_round_trip_byte_equal_to_direct_compose() -> None:
    """Each faces URL resolves to an artifact content-identical to a direct
    single-face compose (byte-equal modulo wall-clock provenance)."""
    reset_cache()
    ir = _matrix_ir()
    resp = compose_surface(
        SpecEnvelope(
            type="matrix",
            genome="primer",
            variant="porcelain",
            spec={**ir, "ground": "opaque", "palette": "adaptive"},
            emit=("faces",),
        )
    )
    assert resp.faces is not None
    for face in ("light", "dark"):
        direct = compose(
            ComposeSpec(
                type="matrix",
                genome_id="primer",
                variant="porcelain",
                ground="opaque",
                palette="fixed",
                surface_face=face,
                matrix=ir,
            )
        ).svg
        digest = _digest_of(resp.faces[face])
        stored = get_artifact(digest)
        assert stored is not None
        # same content address — the artifact IS its data
        assert extract_envelope(direct).get("id") == digest
        # structurally byte-equal once provenance timestamps are normalized
        assert _normalize(stored) == _normalize(direct), f"{face} face differs from direct compose"


def test_plate_inlay_twin_faces_distinct_addresses() -> None:
    """plate, inlay, twin, and each twin face are all distinct content addresses."""
    reset_cache()
    ir = _matrix_ir()

    def _url(**surface: str) -> str:
        return compose_surface(
            SpecEnvelope(type="matrix", genome="primer", variant="porcelain", spec={**ir, **surface}, emit=("svg",))
        ).url

    plate = _url()  # opaque/fixed default
    inlay = _url(ground="bare", palette="adaptive")
    twin = _url(ground="opaque", palette="adaptive")
    faces = compose_surface(
        SpecEnvelope(
            type="matrix",
            genome="primer",
            variant="porcelain",
            spec={**ir, "ground": "opaque", "palette": "adaptive"},
            emit=("faces",),
        )
    ).faces
    assert faces is not None
    addresses = {plate, inlay, twin, faces["light"], faces["dark"]}
    assert len(addresses) == 5, f"expected 5 distinct addresses, got {len(addresses)}: {addresses}"


def test_faces_emit_on_non_twin_rejected() -> None:
    """faces is twin-only — a plate/inlay request is a loud SPEC_INVALID."""
    reset_cache()
    for surface in ({}, {"ground": "bare", "palette": "adaptive"}):  # plate, inlay
        with pytest.raises(HwError) as exc:
            compose_surface(
                SpecEnvelope(type="matrix", genome="primer", spec={**_matrix_ir(), **surface}, emit=("faces",))
            )
        assert exc.value.code is HwErrorCode.SPEC_INVALID


# ── surface props forward through compose_surface's field partition ─────────


def test_surface_axes_forward_through_spec_dict() -> None:
    """ground/palette packed into `spec` lift to ComposeSpec top-level fields
    (WB2c's model_fields partition), producing an adaptive artifact — no adapter
    re-plumbing needed."""
    reset_cache()
    resp = compose_surface(
        SpecEnvelope(
            type="matrix",
            genome="primer",
            variant="porcelain",
            spec={**_matrix_ir(), "ground": "bare", "palette": "adaptive"},
            emit=("svg",),
        )
    )
    assert 'data-hw-adapt="adaptive"' in resp.svg


def test_trap_rejected_at_core() -> None:
    reset_cache()
    with pytest.raises(HwError) as exc:
        compose_surface(
            SpecEnvelope(type="matrix", genome="primer", spec={**_matrix_ir(), "ground": "bare", "palette": "fixed"})
        )
    assert exc.value.code is HwErrorCode.SPEC_INVALID


# ── sugar expansion precedence (expand_surface_preset) ─────────────────────


def test_surface_preset_expands_to_axes() -> None:
    from hyperweave.core.surface_spec import Ground, PaletteMode, expand_surface_preset

    assert expand_surface_preset("twin", "", "") == expand_surface_preset("", "opaque", "adaptive")
    inlay = expand_surface_preset("inlay", "", "")
    assert inlay.ground is Ground.BARE and inlay.palette is PaletteMode.ADAPTIVE


def test_surface_preset_axis_contradiction_raises() -> None:
    from hyperweave.core.surface_spec import expand_surface_preset

    with pytest.raises(ValueError, match="implies"):
        expand_surface_preset("twin", "bare", "")  # twin implies opaque


def test_surface_trap_raises_on_expand() -> None:
    from hyperweave.core.surface_spec import expand_surface_preset

    with pytest.raises(ValueError, match="trap"):
        expand_surface_preset("", "bare", "fixed")


# ── CLI wiring ─────────────────────────────────────────────────────────────


def test_cli_twin_faces_writes_two_files(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from typer.testing import CliRunner

    from hyperweave.cli import app

    spec_file = tmp_path / "table.json"
    import json

    spec_file.write_text(json.dumps(_matrix_ir()))
    out = tmp_path / "m.svg"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "compose",
            "matrix",
            "--spec-file",
            str(spec_file),
            "-g",
            "primer",
            "--variant",
            "porcelain",
            "--surface",
            "twin",
            "--faces",
            "-o",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    light = out.with_name("m-light.svg")
    dark = out.with_name("m-dark.svg")
    assert light.exists() and dark.exists()
    # faces are baked plates — no @media adaptive block
    assert 'data-hw-adapt="adaptive"' not in light.read_text()
    assert light.read_text() != dark.read_text()


def test_cli_inlay_single_adaptive_artifact(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    from typer.testing import CliRunner

    from hyperweave.cli import app

    spec_file = tmp_path / "table.json"
    spec_file.write_text(json.dumps(_matrix_ir()))
    out = tmp_path / "inlay.svg"
    result = CliRunner().invoke(
        app,
        ["compose", "matrix", "--spec-file", str(spec_file), "-g", "primer", "--surface", "inlay", "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert 'data-hw-adapt="adaptive"' in out.read_text()


def test_cli_trap_rejected(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    from typer.testing import CliRunner

    from hyperweave.cli import app

    spec_file = tmp_path / "table.json"
    spec_file.write_text(json.dumps(_matrix_ir()))
    result = CliRunner().invoke(
        app,
        ["compose", "matrix", "--spec-file", str(spec_file), "-g", "primer", "--ground", "bare", "--palette", "fixed"],
    )
    assert result.exit_code == 2
    assert "trap" in result.output


def test_cli_faces_without_output_errors(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    from typer.testing import CliRunner

    from hyperweave.cli import app

    spec_file = tmp_path / "table.json"
    spec_file.write_text(json.dumps(_matrix_ir()))
    result = CliRunner().invoke(
        app, ["compose", "matrix", "--spec-file", str(spec_file), "-g", "primer", "--surface", "twin", "--faces"]
    )
    assert result.exit_code == 2
    assert "-o" in result.output or "output" in result.output


# ── HTTP wiring ────────────────────────────────────────────────────────────


def test_http_get_matrix_inlay_is_adaptive() -> None:
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.get("/v1/matrix/connectors/primer.static", params={"variant": "porcelain", "surface": "inlay"})
    assert r.status_code == 200
    assert 'data-hw-adapt="adaptive"' in r.text


def test_http_post_json_twin_faces() -> None:
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.post(
        "/v1/compose",
        json={
            "type": "matrix",
            "genome": "primer",
            "variant": "porcelain",
            "matrix": _matrix_ir(),
            "surface": "twin",
            "faces": True,
            "respond": "json",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "faces" in body and set(body["faces"]) == {"light", "dark"}
    assert body["faces"]["light"] != body["faces"]["dark"]


def test_http_post_envelope_forwards_surface() -> None:
    """The envelope path (registry dispatch → compose_surface) forwards the
    surface axes — the artifact it caches is adaptive."""
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.post(
        "/v1/compose",
        json={"type": "matrix", "genome": "primer", "matrix": _matrix_ir(), "surface": "inlay", "respond": "envelope"},
    )
    assert r.status_code == 200
    url = r.json()["url"]
    digest = url.rsplit("/", 1)[-1]
    fetched = client.get(f"/v1/a/{digest}")
    assert 'data-hw-adapt="adaptive"' in fetched.text


def test_http_post_trap_rejected() -> None:
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.post(
        "/v1/compose",
        json={"type": "matrix", "genome": "primer", "matrix": _matrix_ir(), "ground": "bare", "palette": "fixed"},
    )
    assert r.status_code == 400


def test_http_post_faces_non_twin_rejected() -> None:
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.post(
        "/v1/compose",
        json={"type": "matrix", "genome": "primer", "matrix": _matrix_ir(), "faces": True, "respond": "json"},
    )
    assert r.status_code == 400


# ── MCP wiring ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mcp_twin_faces() -> None:
    from hyperweave.mcp.server import hw_compose

    r = await hw_compose(
        type="matrix", genome="primer", variant="porcelain", matrix=_matrix_ir(), surface="twin", faces=True
    )
    assert isinstance(r, dict)
    assert "faces" in r and set(r["faces"]) == {"light", "dark"}


@pytest.mark.asyncio
async def test_mcp_inlay_adaptive() -> None:
    from hyperweave.mcp.server import hw_compose

    r = await hw_compose(type="matrix", genome="primer", matrix=_matrix_ir(), surface="inlay", respond="svg")
    assert isinstance(r, str)
    assert 'data-hw-adapt="adaptive"' in r


@pytest.mark.asyncio
async def test_mcp_trap_rejected() -> None:
    from hyperweave.mcp.server import hw_compose

    with pytest.raises(ValueError, match="trap"):
        await hw_compose(type="matrix", genome="primer", matrix=_matrix_ir(), ground="bare", palette="fixed")


# ── face= (singular): CLI --face-identical override, HTTP + MCP ────────────
# Unlike `faces` (bakes both, twin-only), `face` bakes ONE scheme and commits
# palette=fixed even over an explicit adaptive surface/palette request — the
# face wins. No 'auto' on these transports (OSC 11 terminal detection is
# CLI-only); light/dark are the shared, scriptable values.


def test_http_get_diagram_face_dark_bakes_face() -> None:
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.get("/v1/diagram/rag-pipeline/primer.static", params={"face": "dark"})
    assert r.status_code == 200
    assert 'data-hw-face="dark"' in r.text


def test_http_get_matrix_face_dark_bakes_face() -> None:
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.get("/v1/matrix/connectors/primer.static", params={"face": "dark"})
    assert r.status_code == 200
    assert 'data-hw-face="dark"' in r.text


def test_http_get_diagram_face_invalid_value_422() -> None:
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.get("/v1/diagram/rag-pipeline/primer.static", params={"face": "chartreuse"})
    assert r.status_code == 422


def test_http_get_matrix_face_invalid_value_422() -> None:
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.get("/v1/matrix/connectors/primer.static", params={"face": "chartreuse"})
    assert r.status_code == 422


def test_http_get_diagram_face_rejects_auto() -> None:
    """'auto' (OSC 11 terminal detection) is CLI-only — the HTTP axis 422s it."""
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.get("/v1/diagram/rag-pipeline/primer.static", params={"face": "auto"})
    assert r.status_code == 422


def test_http_post_face_commits_over_adaptive_surface() -> None:
    """face wins: it commits palette=fixed even over surface=twin (adaptive)."""
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.post(
        "/v1/compose",
        json={"type": "matrix", "genome": "primer", "matrix": _matrix_ir(), "surface": "twin", "face": "dark"},
    )
    assert r.status_code == 200
    assert 'data-hw-face="dark"' in r.text
    assert 'data-hw-adapt="adaptive"' not in r.text


def test_http_post_face_and_faces_exclusive() -> None:
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.post(
        "/v1/compose",
        json={
            "type": "matrix",
            "genome": "primer",
            "matrix": _matrix_ir(),
            "surface": "twin",
            "face": "dark",
            "faces": True,
            "respond": "json",
        },
    )
    assert r.status_code == 400
    assert "exclusive" in r.json()["error"]["message"]


def test_http_post_face_invalid_value_rejected() -> None:
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.post(
        "/v1/compose",
        json={"type": "matrix", "genome": "primer", "matrix": _matrix_ir(), "face": "mauve"},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == HwErrorCode.SPEC_INVALID.value


def test_http_post_envelope_forwards_face() -> None:
    """The envelope path (registry dispatch → compose_surface) forwards face too."""
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app

    client = TestClient(app)
    r = client.post(
        "/v1/compose",
        json={"type": "matrix", "genome": "primer", "matrix": _matrix_ir(), "face": "dark", "respond": "envelope"},
    )
    assert r.status_code == 200
    url = r.json()["url"]
    digest = url.rsplit("/", 1)[-1]
    fetched = client.get(f"/v1/a/{digest}")
    assert 'data-hw-face="dark"' in fetched.text


@pytest.mark.asyncio
async def test_mcp_face_dark_bakes_face() -> None:
    from hyperweave.mcp.server import hw_compose

    svg = await hw_compose(type="matrix", genome="primer", matrix=_matrix_ir(), face="dark", respond="svg")
    assert isinstance(svg, str)
    assert 'data-hw-face="dark"' in svg


@pytest.mark.asyncio
async def test_mcp_face_commits_over_adaptive_surface() -> None:
    from hyperweave.mcp.server import hw_compose

    svg = await hw_compose(
        type="matrix", genome="primer", matrix=_matrix_ir(), surface="twin", face="dark", respond="svg"
    )
    assert isinstance(svg, str)
    assert 'data-hw-face="dark"' in svg
    assert 'data-hw-adapt="adaptive"' not in svg


@pytest.mark.asyncio
async def test_mcp_face_invalid_value_raises() -> None:
    from hyperweave.mcp.server import hw_compose

    with pytest.raises(ValueError, match="face must be"):
        await hw_compose(type="matrix", genome="primer", matrix=_matrix_ir(), face="mauve")


@pytest.mark.asyncio
async def test_mcp_face_and_faces_exclusive_raises() -> None:
    from hyperweave.mcp.server import hw_compose

    with pytest.raises(ValueError, match="exclusive"):
        await hw_compose(type="matrix", genome="primer", matrix=_matrix_ir(), surface="twin", face="dark", faces=True)


# ── embed seam: faces pair feeds embed_snippets as [dark, light] ───────────


def test_faces_pair_composes_with_embed_snippets() -> None:
    from hyperweave.delivery.embed import embed_snippets

    resp = compose_surface(
        SpecEnvelope(
            type="matrix",
            genome="primer",
            variant="porcelain",
            spec={**_matrix_ir(), "ground": "opaque", "palette": "adaptive"},
            emit=("faces",),
        ),
        base_url="https://hyperweave.app",
    )
    assert resp.faces is not None
    snip = embed_snippets([resp.faces["dark"], resp.faces["light"]], title="demo")
    assert snip["markdown"].startswith("<picture>")
    assert resp.faces["dark"] in snip["markdown"]  # dark is the <img> default
    assert "prefers-color-scheme: light" in snip["markdown"]
