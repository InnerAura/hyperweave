"""The custom-genome boundary, exercised through the real surfaces.

The P0 injection fix: a ``genome_override`` dict is validated exactly as hard
as a registry genome (GenomeSpec grammar + battery + profile contract) before
ANY code reads it — on direct dispatch, HTTP, MCP, the CLI, and raw
``ComposeSpec`` construction. These tests drive each surface the way a caller
does (Guard Law): the real CLI parser and exit codes, the real ASGI app, the
real MCP tool functions — never only the internal validator.
"""

from __future__ import annotations

import copy
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

import hyperweave
from hyperweave.cli import app as cli_app
from hyperweave.compose.engine import compose
from hyperweave.config.genome_validator import validate_genome_override
from hyperweave.config.loader import get_loader
from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.core.models import ComposeSpec
from hyperweave.mcp import server as mcp_server
from hyperweave.serve.app import app as http_app
from hyperweave.surfaces.registry import CallContext, dispatch
from tests.helpers import build_minimal_genome_for_testing

runner = CliRunner()

_SCRIPT_PAYLOAD = "</style><script data-audit=1></script><style>"

# Adversarial mutations over a fully-lawful minimal genome. Each entry names
# the vector and the field mutation that carries it.
_HOSTILE_MUTATIONS: dict[str, dict[str, Any]] = {
    "script-in-ink": {"ink": _SCRIPT_PAYLOAD},
    "xml-element-in-name": {"name": "<circle r='9'/>"},
    "url-css-in-structural": {"structural": {"backdrop": "url(https://evil.example/x)"}},
    "at-import-in-material": {"material": {"filter_chain": "@import 'https://evil.example/x.css'"}},
    "css-escape-smuggle": {"typography": {"hint": "\\3c script\\3e"}},
    "malformed-hex": {"accent": "#GGGGGG"},
    "malformed-rgba": {"shadow_color": "rgba(0,0,0"},
    "script-in-gradient-color": {"envelope_stops": [{"offset": "0%", "color": _SCRIPT_PAYLOAD}]},
    "attr-breakout-in-gradient-offset": {"envelope_stops": [{"offset": '0%" onload="', "color": "#FFFFFF"}]},
    "unknown-gradient-key": {"envelope_stops": [{"offset": "0%", "color": "#FFFFFF", "onload": "x"}]},
    "opacity-out-of-range": {"atmosphere_stops": [{"offset": "0%", "color": "#FFFFFF", "opacity": "2"}]},
    "attr-breakout-in-id": {"id": 'x" onload="'},
    "script-in-light-mode": {"light_mode": {"surface": _SCRIPT_PAYLOAD}},
    "malformed-duration": {"cellular_pulse_base_duration": "6q"},
    "script-in-variant-override": {
        "variants": ["x"],
        "flagship_variant": "x",
        "variant_overrides": {"x": {"ink": _SCRIPT_PAYLOAD}},
    },
}


def _hostile_genome(vector: str) -> dict[str, Any]:
    genome = build_minimal_genome_for_testing(id="hostile-test", paradigms={"badge": "default"})
    genome.update(copy.deepcopy(_HOSTILE_MUTATIONS[vector]))
    return genome


@pytest.fixture()
async def http_client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=http_app), base_url="http://test") as ac:
        yield ac


# ── Refusal: every vector, at the ComposeSpec boundary ───────────────────────


@pytest.mark.parametrize("vector", sorted(_HOSTILE_MUTATIONS))
def test_hostile_override_refused_at_composespec(vector: str) -> None:
    """Raw library construction (Invariant 3) fails closed on every vector."""
    with pytest.raises(ValueError):
        ComposeSpec(type="badge", title="X", value="1", genome_override=_hostile_genome(vector))


# ── The audit reproduction, through the real MCP tool ────────────────────────


async def test_audit_reproduction_fails_closed_via_mcp() -> None:
    """The consolidation-audit repro: clone the built-in primer genome, clear
    its variant overrides, set ``ink`` to a style-breakout ``<script>`` payload,
    compose via MCP. Before the fix this shipped a ``<script>`` element in the
    SVG; now it must refuse with SPEC_INVALID and cache nothing."""
    genome = copy.deepcopy(get_loader().genomes["primer"])
    genome["variant_overrides"] = {}
    genome["ink"] = _SCRIPT_PAYLOAD
    with pytest.raises(HwError) as exc:
        await mcp_server.hw_compose(type="badge", title="X", value="1", genome_override=genome)
    assert exc.value.code is HwErrorCode.SPEC_INVALID


# ── Refusal on each surface, separately ──────────────────────────────────────


async def test_hostile_override_refused_on_direct_dispatch() -> None:
    ctx = CallContext(surface="test")
    with pytest.raises(HwError) as exc:
        await dispatch(
            "compose",
            {
                "type": "badge",
                "spec": {"title": "X", "value": "1", "genome_override": _hostile_genome("script-in-ink")},
            },
            ctx,
        )
    assert exc.value.code is HwErrorCode.SPEC_INVALID


async def test_hostile_override_refused_on_http(http_client: AsyncClient) -> None:
    resp = await http_client.post(
        "/v1/compose",
        json={"type": "badge", "title": "X", "value": "1", "genome_override": _hostile_genome("script-in-ink")},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == HwErrorCode.SPEC_INVALID.value
    # The envelope path routes through the shared capability — same refusal.
    resp2 = await http_client.post(
        "/v1/compose",
        json={
            "type": "badge",
            "title": "X",
            "value": "1",
            "genome_override": _hostile_genome("script-in-ink"),
            "respond": "envelope",
        },
    )
    assert resp2.status_code == 400
    assert resp2.json()["error"]["code"] == HwErrorCode.SPEC_INVALID.value


async def test_valid_override_composes_via_http(http_client: AsyncClient) -> None:
    resp = await http_client.post(
        "/v1/compose",
        json={
            "type": "badge",
            "genome": "brutalist",
            "title": "X",
            "value": "1",
            "genome_override": _valid_genome(),
            "respond": "envelope",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["genome"] == "inline-boundary"


async def test_hostile_override_refused_on_mcp_validate() -> None:
    report = await mcp_server.hw_validate(
        spec={
            "type": "badge",
            "spec": {"title": "X", "value": "1", "genome_override": _hostile_genome("script-in-ink")},
        }
    )
    assert report.get("valid") is not True
    assert report["error"]["code"] == HwErrorCode.SPEC_INVALID.value


def test_hostile_override_refused_on_cli(tmp_path: Path) -> None:
    """The printed sentence and the exit code, through the real parser."""
    genome_file = tmp_path / "hostile.json"
    genome_file.write_text(json.dumps(_hostile_genome("script-in-ink")))
    result = runner.invoke(cli_app, ["compose", "badge", "X", "1", "--genome-file", str(genome_file)])
    assert result.exit_code == 2, result.output
    assert "Genome file validation failed" in result.output
    assert "genome_override" in result.output


# ── The positive path: a lawful custom genome composes everywhere ────────────


def _valid_genome(**overrides: Any) -> dict[str, Any]:
    return build_minimal_genome_for_testing(
        id="inline-boundary", accent="#FF00FF", paradigms={"badge": "default"}, **overrides
    )


def test_valid_override_normalizes_and_canonicalizes_on_composespec() -> None:
    spec = ComposeSpec(type="badge", title="X", value="1", genome_id="brutalist", genome_override=_valid_genome())
    assert spec.genome_override is not None
    # Normalization proof: the boundary returned GenomeSpec.model_dump(), so
    # computed rhythm derivatives are present even though the input had none.
    assert spec.genome_override["rhythm_slow"]
    assert spec.genome_override["rhythm_fast"]
    # Canonicalization: the override's id wins over the disagreeing genome_id.
    assert spec.genome_id == "inline-boundary"


async def test_valid_override_composes_via_mcp_with_canonical_genome() -> None:
    svg = await mcp_server.hw_compose(
        type="badge", title="X", value="1", genome="brutalist", genome_override=_valid_genome(), respond="svg"
    )
    assert 'data-hw-genome="inline-boundary"' in svg
    assert "#FF00FF" in svg
    assert "<script" not in svg.lower()


async def test_valid_override_composes_via_direct_dispatch() -> None:
    ctx = CallContext(surface="test")
    result = await dispatch(
        "compose",
        {
            "type": "badge",
            "genome": "brutalist",
            "spec": {"title": "X", "value": "1", "genome_override": _valid_genome()},
        },
        ctx,
    )
    assert result["genome"] == "inline-boundary"


def test_valid_genome_file_composes_via_cli(tmp_path: Path) -> None:
    genome_file = tmp_path / "custom.json"
    genome_file.write_text(json.dumps(_valid_genome()))
    out = tmp_path / "a.svg"
    result = runner.invoke(cli_app, ["compose", "badge", "X", "1", "--genome-file", str(genome_file), "-o", str(out)])
    assert result.exit_code == 0, result.output
    svg = out.read_text()
    assert 'data-hw-genome="inline-boundary"' in svg


# ── validate-genome shares the same boundary ─────────────────────────────────


def test_validate_genome_command_passes_lawful_file(tmp_path: Path) -> None:
    genome_file = tmp_path / "custom.json"
    genome_file.write_text(json.dumps(_valid_genome()))
    result = runner.invoke(cli_app, ["validate-genome", str(genome_file)])
    assert result.exit_code == 0, result.output
    assert "PASSED" in result.output


def test_validate_genome_command_refuses_hostile_file(tmp_path: Path) -> None:
    genome_file = tmp_path / "hostile.json"
    genome_file.write_text(json.dumps(_hostile_genome("script-in-ink")))
    result = runner.invoke(cli_app, ["validate-genome", str(genome_file)])
    assert result.exit_code == 2, result.output
    assert "FAILED" in result.output


def test_validate_genome_command_profile_flag(tmp_path: Path) -> None:
    """--profile stays a live public option: it overrides the file's profile."""
    genome_file = tmp_path / "custom.json"
    genome_file.write_text(json.dumps(_valid_genome()))
    result = runner.invoke(cli_app, ["validate-genome", str(genome_file), "--profile", "flat"])
    assert result.exit_code == 0, result.output
    bad = runner.invoke(cli_app, ["validate-genome", str(genome_file), "--profile", "no-such-profile"])
    assert bad.exit_code == 2, bad.output


# ── Removed contract: custom_glyph_svg is refused, not silently dropped ──────


async def test_custom_glyph_svg_is_a_refused_unknown_field() -> None:
    """The dead ``custom_glyph_svg`` contract is gone: a spec carrying it is
    refused as an unknown field on the shared wire, never silently ignored
    while stamping ``data-hw-glyph="custom"`` (the audit #2 failure)."""
    ctx = CallContext(surface="test")
    with pytest.raises(HwError) as exc:
        await dispatch(
            "compose",
            {"type": "badge", "spec": {"title": "X", "value": "1", "custom_glyph_svg": "<circle r='4'/>"}},
            ctx,
        )
    assert exc.value.code is HwErrorCode.SPEC_INVALID
    assert "custom_glyph_svg" in str(exc.value.detail)


# ── Review round 2: four fail-closed gaps in the boundary ────────────────────
# Each reproduction below PASSED validation and then broke at render time (or
# never broke at all, which was worse). Guarded through the real surfaces.


_PARADIGM_VECTORS = {
    "paradigm-template-traversal": {"paradigms": {"badge": "../../document"}},
    "paradigm-unknown-slug": {"paradigms": {"badge": "nonexistent"}},
    "paradigm-uppercase-slug": {"paradigms": {"badge": "Default"}},
}

_VARIANT_VECTORS = {
    "variant-entity": {"variants": ["x&y"], "flagship_variant": "x&y", "variant_overrides": {"x&y": {}}},
    "variant-override-key": {"variants": ["ok"], "variant_overrides": {"a<b": {}}},
    "variant-tones-key": {"variant_tones": {'q"r': {}}},
    "flagship-not-a-slug": {"flagship_variant": "../x"},
}

_DURATION_VECTORS = {
    "rhythm-nan": {"rhythm_base": "nan"},
    "rhythm-inf": {"rhythm_base": "inf"},
    "rhythm-negative": {"rhythm_base": "-5s"},
    "rhythm-unitless": {"rhythm_base": "5"},
    "rhythm-bad-unit": {"rhythm_base": "6q"},
    "rhythm-slow-nan": {"rhythm_slow": "nan"},
    "rhythm-fast-negative": {"rhythm_fast": "-1s"},
    "cellular-base-inf": {"cellular_pulse_base_duration": "inf"},
    "cellular-fast-unitless": {"cellular_pulse_fast_duration": "3"},
}

_RGBA_VECTORS = {
    "rgba-channel-out-of-range": {"surface_0": "rgba(999,999,999,9)"},
    "rgba-alpha-out-of-range": {"surface_0": "rgba(10,10,10,9)"},
    "rgba-channel-256": {"surface_1": "rgba(256,0,0,1)"},
}

_ROUND2_VECTORS = {**_PARADIGM_VECTORS, **_VARIANT_VECTORS, **_DURATION_VECTORS, **_RGBA_VECTORS}


def _vector_genome(vector: str) -> dict[str, Any]:
    base = build_minimal_genome_for_testing(id="round2", paradigms={"badge": "default"})
    base.update(copy.deepcopy(_ROUND2_VECTORS[vector]))
    return base


@pytest.mark.parametrize("vector", sorted(_ROUND2_VECTORS))
def test_round2_vector_refused_at_the_boundary(vector: str) -> None:
    """None of these reaches a renderer: each failed late (TemplateNotFound,
    malformed XML) or silently shipped an unrenderable value."""
    with pytest.raises(HwError) as exc:
        validate_genome_override(_vector_genome(vector))
    assert exc.value.code is HwErrorCode.SPEC_INVALID


@pytest.mark.parametrize("vector", sorted(_ROUND2_VECTORS))
def test_round2_vector_refused_on_composespec(vector: str) -> None:
    with pytest.raises(ValueError):
        ComposeSpec(type="badge", title="X", value="1", genome_override=_vector_genome(vector))


async def test_round2_vectors_refused_on_http_mcp_and_dispatch(http_client: AsyncClient) -> None:
    """One representative per finding, through each real surface."""
    ctx = CallContext(surface="test")
    for vector in ("paradigm-unknown-slug", "variant-entity", "rhythm-nan", "rgba-channel-out-of-range"):
        genome = _vector_genome(vector)
        resp = await http_client.post(
            "/v1/compose", json={"type": "badge", "title": "X", "value": "1", "genome_override": genome}
        )
        assert resp.status_code == 400, f"{vector}: HTTP accepted it"
        assert resp.json()["error"]["code"] == HwErrorCode.SPEC_INVALID.value

        with pytest.raises(HwError) as mcp_exc:
            await mcp_server.hw_compose(type="badge", title="X", value="1", genome_override=genome)
        assert mcp_exc.value.code is HwErrorCode.SPEC_INVALID, vector

        with pytest.raises(HwError) as dispatch_exc:
            await dispatch(
                "compose",
                {"type": "badge", "spec": {"title": "X", "value": "1", "genome_override": genome}},
                ctx,
            )
        assert dispatch_exc.value.code is HwErrorCode.SPEC_INVALID, vector


def test_round2_vectors_refused_on_cli(tmp_path: Path) -> None:
    for vector in ("paradigm-template-traversal", "variant-entity", "rhythm-inf", "rgba-alpha-out-of-range"):
        genome_file = tmp_path / f"{vector}.json"
        genome_file.write_text(json.dumps(_vector_genome(vector)))
        result = runner.invoke(cli_app, ["compose", "badge", "X", "1", "--genome-file", str(genome_file)])
        assert result.exit_code == 2, f"{vector}: {result.output}"
        assert "Genome file validation failed" in result.output


def test_declared_paradigm_dispatches_to_a_real_template() -> None:
    """The positive half: a slug WITH a partial composes, and the by-variant
    divider frame stays exempt (it dispatches on variant, not paradigm)."""
    genome = build_minimal_genome_for_testing(id="round2-ok", paradigms={"badge": "default", "divider": "default"})
    svg = compose(ComposeSpec(type="badge", title="X", value="1", genome_override=genome)).svg
    assert "<svg" in svg


def test_lawful_variant_composes_to_well_formed_xml() -> None:
    """Finding 2's real-composition guard: the artifact PARSES. The rejected
    'x&y' produced `<hw:variant>x&y</hw:variant>` — malformed XML from a
    genome that had passed validation (Invariant 14)."""
    genome = build_minimal_genome_for_testing(
        id="round2-variant",
        paradigms={"badge": "default"},
        variants=["afterimage"],
        flagship_variant="afterimage",
    )
    svg = compose(ComposeSpec(type="badge", title="X", value="1", variant="afterimage", genome_override=genome)).svg
    ET.fromstring(svg)
    assert "<hw:variant>afterimage</hw:variant>" in svg


def test_every_required_contrast_pair_is_evaluated_for_rgba_surfaces() -> None:
    """Finding 4b: a translucent surface used to skip the WCAG gate entirely
    because the check demanded two '#' strings. Now every declared pair is
    graded against a deterministic composited backdrop — or refused."""
    from hyperweave.config.genome_validator import _contract_errors

    contract = json.loads((Path(hyperweave.__file__).parent / "data" / "profiles" / "flat.contract.json").read_text())
    required = [pair["label"] for pair in contract["contrast_pairs"]]
    assert required, "flat contract declares no contrast pairs"

    # A near-opaque light surface on a dark genome fails every ink pair; the
    # point is that the pairs are GRADED, not skipped.
    failing = _contract_errors(
        build_minimal_genome_for_testing(id="rgba-low", surface_0="rgba(200,200,200,0.9)"), "flat"
    )
    graded = [label for label in required if any(label in line for line in failing)]
    assert graded, f"no pair evaluated for a translucent surface; got {failing}"

    # And an unresolvable color is refused rather than skipped.
    unresolvable = _contract_errors({**build_minimal_genome_for_testing(id="x"), "ink": "not-a-color"}, "flat")
    assert any("cannot establish contrast" in line for line in unresolvable), unresolvable


def test_rgba_surface_genome_still_composes_when_it_meets_the_floor() -> None:
    genome = build_minimal_genome_for_testing(
        id="rgba-ok", paradigms={"badge": "default"}, surface_0="rgba(10,10,10,0.5)"
    )
    svg = compose(ComposeSpec(type="badge", title="X", value="1", genome_override=genome)).svg
    ET.fromstring(svg)


# ── Review round 3: four P1 boundary gaps ───────────────────────────────────


_VARIANT_BODY_VECTORS = {
    "override-non-string": {"surface_0": 123},
    "override-invalid-color": {"surface_0": "notacolor"},
    "override-contrast-collapse": {"ink": "#000000", "surface_0": "#000000"},
    "override-not-a-dict": None,
}

_DISPATCH_VECTORS = {
    "substrate-subpartial-light": "primer-light",
    "substrate-subpartial-dark": "brutalist-dark",
}

_MOTION_VECTORS = {
    "motion-entity": "x&y",
    "motion-unknown": "nonexistent",
}

_TIME_VECTORS = {
    "duration-overflows-to-inf": "1" + "0" * 400 + ".0s",
    "duration-zero-base": "0s",
}


def _variant_genome(body: object) -> dict[str, Any]:
    return build_minimal_genome_for_testing(
        id="round3",
        paradigms={"badge": "default"},
        variants=["v"],
        flagship_variant="v",
        variant_overrides={"v": body},
    )


@pytest.mark.parametrize("vector", sorted(_VARIANT_BODY_VECTORS))
def test_effective_variant_is_validated(vector: str) -> None:
    """A variant override is merged into the genome AFTER base validation, so
    an unvalidated body reached the renderer as a late AttributeError, invalid
    CSS, or an ink/surface pair that never faced the contrast gate."""
    with pytest.raises(HwError) as exc:
        validate_genome_override(_variant_genome(_VARIANT_BODY_VECTORS[vector]))
    assert exc.value.code is HwErrorCode.SPEC_INVALID


def test_lawful_variant_override_still_passes() -> None:
    """The positive half: an override that holds its contrast floors composes."""
    genome = _variant_genome({"accent": "#7FD8A0"})
    svg = compose(ComposeSpec(type="badge", title="X", value="1", variant="v", genome_override=genome)).svg
    ET.fromstring(svg)


@pytest.mark.parametrize("vector", sorted(_DISPATCH_VECTORS))
def test_substrate_subpartial_is_not_a_dispatch_target(vector: str) -> None:
    """``primer-light``/``brutalist-dark`` are subpartials INCLUDED BY a
    paradigm's content file — they exist as ``-content.j2`` but own no
    ``-defs.j2``, so they passed a content-only check and then died at render
    time on the missing defs."""
    genome = build_minimal_genome_for_testing(id="round3", paradigms={"badge": _DISPATCH_VECTORS[vector]})
    with pytest.raises(HwError) as exc:
        validate_genome_override(genome)
    assert exc.value.code is HwErrorCode.SPEC_INVALID
    assert "defs.j2" in str(exc.value.fix)


def test_strip_requires_its_status_partial_too() -> None:
    """The required suffix set is read from the frame template, so strip's
    third include (``-status.j2``) is enforced without a table in Python."""
    from hyperweave.compose.validate_paradigms import _dispatch_suffixes

    assert set(_dispatch_suffixes("strip")) == {"content", "defs", "status"}
    assert set(_dispatch_suffixes("badge")) == {"content", "defs"}


@pytest.mark.parametrize("vector", sorted(_MOTION_VECTORS))
def test_compatible_motion_ids_are_slug_safe_and_real(vector: str) -> None:
    """An entity-bearing id broke ``data-hw-motion``; a lawful-looking absent
    id composed a static artifact that still claimed the motion."""
    genome = build_minimal_genome_for_testing(
        id="round3", paradigms={"badge": "default"}, compatible_motions=["static", _MOTION_VECTORS[vector]]
    )
    with pytest.raises(HwError) as exc:
        validate_genome_override(genome)
    assert exc.value.code is HwErrorCode.SPEC_INVALID


def test_requested_motion_is_slug_safe_even_ungoverned() -> None:
    """The ungoverned lane passes the caller's motion through by design — it
    must still be an id that cannot break the attribute it lands in."""
    with pytest.raises(ValueError):
        ComposeSpec(type="badge", title="X", value="1", motion="x&y", regime="ungoverned")
    svg = compose(
        ComposeSpec(type="badge", genome_id="brutalist", title="X", value="1", motion="rimrun", regime="ungoverned")
    ).svg
    ET.fromstring(svg)


@pytest.mark.parametrize("vector", sorted(_TIME_VECTORS))
def test_duration_grammar_is_finite_and_total(vector: str) -> None:
    """Grammar alone was not enough: a long literal decimal overflowed to inf
    through ``float()``, and a zero base divided by zero deriving the phi
    ladder (a ZeroDivisionError, not a refusal)."""
    genome = build_minimal_genome_for_testing(
        id="round3", paradigms={"badge": "default"}, rhythm_base=_TIME_VECTORS[vector]
    )
    with pytest.raises(HwError) as exc:
        validate_genome_override(genome)
    assert exc.value.code is HwErrorCode.SPEC_INVALID


def test_zero_duration_never_reaches_the_phi_ladder() -> None:
    """The division-by-zero path directly: explicit zero derivatives included."""
    from hyperweave.core.schema import GenomeSpec

    with pytest.raises(ValueError):
        GenomeSpec(
            **build_minimal_genome_for_testing(id="round3", rhythm_base="0s", rhythm_slow="0s", rhythm_fast="0s")
        )


# ── Review round 4: the boundary as a CLASS, not per-reproduction ───────────


_ATTRIBUTE_INJECTION = 'x" onload="alert(1)'
_ENTITY_BREAK = "x&y"


@pytest.mark.parametrize("payload", [_ATTRIBUTE_INJECTION, _ENTITY_BREAK])
@pytest.mark.parametrize("field", ["state", "size"])
def test_state_and_size_cannot_inject_attributes(field: str, payload: str) -> None:
    """Both fields landed unescaped in root attributes, so an attribute-closing
    value produced a VALID SVG carrying an event handler."""
    with pytest.raises(ValueError):
        ComposeSpec(type="badge", title="X", value="1", **{field: payload})


@pytest.mark.parametrize(("field", "value"), [("size", "large"), ("size", "compact"), ("state", "passing")])
def test_slug_grammar_keeps_legitimate_vocabulary(field: str, value: str) -> None:
    """The grammar blocks injection WITHOUT inventing a closed vocabulary:
    ``size="large"`` is a real size (the cellular badge renders 32 tall against
    the default 20), and a typo'd ``?state=`` still renders neutral rather
    than 400-ing."""
    spec = ComposeSpec(type="badge", genome_id="brutalist", title="X", value="1", **{field: value})
    assert getattr(spec, field) == value
    ET.fromstring(compose(spec).svg)


_DISPATCH_FIELDS = [
    "motion",
    "glyph",
    "shape",
    "series",
    "platform",
    "marquee_direction",
    "glyph_tint",
    "performance",
    "ground",
    "palette",
    "surface_face",
    "font_mode",
    "frame_id",
    "profile_id",
]


@pytest.mark.parametrize("field", _DISPATCH_FIELDS)
@pytest.mark.parametrize("payload", [_ATTRIBUTE_INJECTION, _ENTITY_BREAK])
def test_every_dispatch_field_takes_the_slug_grammar(field: str, payload: str) -> None:
    """The whole class, not the two fields that had reproductions: every value
    that names an id, a dispatch key or a policy axis is slug-bounded."""
    with pytest.raises(ValueError):
        ComposeSpec(type="badge", title="X", value="1", **{field: payload})


@pytest.mark.parametrize("payload", [_ATTRIBUTE_INJECTION, _ENTITY_BREAK])
def test_variant_is_refused_at_resolve_time(payload: str) -> None:
    """``variant`` keeps its documented Path-B contract — a lenient field with
    a resolve-time whitelist refusal — so the guard belongs there. A genome
    declaring NO whitelist used to skip the check entirely and let any string
    reach the emitted variant."""
    from hyperweave.compose.surface import resolve_presentation

    with pytest.raises(HwError) as exc:
        resolve_presentation("badge", "brutalist", payload)
    assert exc.value.code is HwErrorCode.VARIANT_UNKNOWN


def test_every_root_attribute_is_escaped() -> None:
    """Structural guard: no interpolation may reach a root attribute raw.

    The three exclusions are not attributes — the stylesheet body, the XML
    comment, and the pre-escaped inline style. Anything else added without an
    escape fails here rather than in an artifact."""
    template = (Path(hyperweave.__file__).parent / "templates" / "document.svg.j2").read_text()
    exempt = {"css", "self_instruct", "inline_style_overrides"}
    expressions = [e.strip() for e in re.findall(r"\{\{ ([^}]*) \}\}", template) if e.strip() not in exempt]
    raw = [e for e in expressions if "xml_escape" not in e]
    assert not raw, f"unescaped interpolations in document.svg.j2: {raw}"
    # Presence of the filter is not enough: Jinja binds a filter tighter than
    # `or`, so `a | default(0) or b | xml_escape` escapes ONLY the fallback
    # branch. A compound expression must be parenthesised so the escape covers
    # the whole value.
    ungrouped = [e for e in expressions if " or " in e and not e.startswith("(")]
    assert not ungrouped, f"compound expressions escape only one branch: {ungrouped}"


_NESTED_VECTORS = {
    "stops-entity-offset": {"panel_gradient_stops": [{"offset": "x&y", "color": "#FFFFFF"}]},
    "stops-invalid-color": {"panel_gradient_stops": [{"offset": "0%", "color": "notacolor"}]},
    "diagram-role-invalid": {"diagram_dark": {"card_hi": "notacolor"}},
    "diagram-faces-invalid": {"diagram_faces": {"light": {"ink": "notacolor"}}},
    "ramp-invalid": {"receipt_ramp": ["#FFFFFF", "notacolor"]},
    "scalar-invalid": {"seam_color": "notacolor"},
    "opacity-out-of-range": {"stroke_opacity": "9"},
    "substrate-unknown": {"substrate_kind": "sideways"},
    "unknown-override-key": {"totally_unknown_key": "#FFFFFF"},
}


@pytest.mark.parametrize("vector", sorted(_NESTED_VECTORS))
def test_nested_override_structures_are_typed(vector: str) -> None:
    """Roughly twenty override keys are not GenomeSpec fields; they used to
    ride in as raw dicts guarded only by the character sweep, so a gradient
    offset broke the composed SVG and a role color emitted invalid CSS."""
    genome = build_minimal_genome_for_testing(
        id="round4",
        paradigms={"badge": "default"},
        variants=["v"],
        flagship_variant="v",
        variant_overrides={"v": _NESTED_VECTORS[vector]},
    )
    with pytest.raises(HwError) as exc:
        validate_genome_override(genome)
    assert exc.value.code is HwErrorCode.SPEC_INVALID


@pytest.mark.parametrize("key", ["id", "profile", "compatible_motions", "paradigms", "variants", "roles"])
def test_variant_override_cannot_touch_the_control_plane(key: str) -> None:
    """A variant restyles the artifact; it never re-identifies it. An override
    carrying {"id": "other"} changed the emitted data-hw-genome away from the
    genome the caller actually requested."""
    genome = build_minimal_genome_for_testing(
        id="round4",
        paradigms={"badge": "default"},
        variants=["v"],
        flagship_variant="v",
        variant_overrides={"v": {key: "other" if key in {"id", "profile"} else ["x"]}},
    )
    with pytest.raises(HwError) as exc:
        validate_genome_override(genome)
    assert "control-plane" in str(exc.value.fix)


def test_variant_tone_values_are_typed() -> None:
    """Tone primitives resolve into rendered paint, so they are typed too."""
    genome = build_minimal_genome_for_testing(
        id="round4", paradigms={"badge": "default"}, variant_tones={"violet": {"canvas_top": "x&y"}}
    )
    with pytest.raises(HwError):
        validate_genome_override(genome)


def test_every_builtin_genome_passes_the_effective_variant_gate() -> None:
    """No waiver: the registry faces the identical gate an inline genome does.

    Enabling this exposed 14 real WCAG failures in brutalist's light variants
    (amber #F59E0B on cream surfaces at 1.7-1.9:1 against a 3:1 floor); those
    variants now carry the light-substrate amber, so the shipped corpus holds
    the contract it claims rather than being excused from it."""
    from hyperweave.config.genome_validator import effective_variant_errors
    from hyperweave.config.loader import get_loader

    for genome_id, spec in get_loader().genome_specs.items():
        assert not effective_variant_errors(spec, spec.profile), genome_id


def test_brutalist_light_variants_meet_the_warning_contrast_floor() -> None:
    """The repaired pair, measured: every light variant clears 3:1."""
    from hyperweave.config.loader import get_loader
    from hyperweave.core.color import contrast_ratio

    spec = get_loader().genome_specs["brutalist"]
    checked = 0
    for variant, override in spec.variant_overrides.items():
        if override.get("substrate_kind") != "light":
            continue
        merged = {**spec.model_dump(), **override}
        ratio = contrast_ratio(merged["accent_warning"], merged["surface_2"])
        assert ratio >= 3.0, f"{variant}: status-warning vs surface-deep is {ratio:.2f}:1"
        checked += 1
    assert checked == 14


def test_ungoverned_motion_must_exist_or_report_static() -> None:
    """Ungoverned waives the genome's compatibility policy, not existence: a
    motion with no definition animates nothing, so claiming it in
    data-hw-motion and hw:motion would be a false claim."""
    svg = compose(
        ComposeSpec(
            type="badge", genome_id="brutalist", title="X", value="1", motion="nonexistent", regime="ungoverned"
        )
    ).svg
    assert 'data-hw-motion="static"' in svg
    assert 'vocabulary="static"' in svg
    # A real motion still passes through the ungoverned lane.
    live = compose(
        ComposeSpec(type="badge", genome_id="brutalist", title="X", value="1", motion="rimrun", regime="ungoverned")
    ).svg
    assert 'data-hw-motion="rimrun"' in live


def test_optional_partials_are_not_required_for_dispatch() -> None:
    """marquee's -overlay.j2 is included `ignore missing`, so requiring it
    rejected a genome for using the perfectly valid marquee/default paradigm."""
    from hyperweave.compose.validate_paradigms import _dispatch_suffixes

    assert "overlay" not in _dispatch_suffixes("marquee")
    genome = build_minimal_genome_for_testing(id="round4", paradigms={"marquee": "default"})
    validate_genome_override(genome)


# ── Review round 5: model-owned colour fields were assumed typed ────────────


_UNTYPED_COLOR_FIELDS = [
    "highlight_color",
    "diamond_stroke",
    "frame_fill",
    "badge_value_text",
    "glyph_fill",
    "card_border",
    "state_warning_core",
    "diagram_deliberation",
    "pill_inner_bg",
    "tool_explore",
]


@pytest.mark.parametrize("field", _UNTYPED_COLOR_FIELDS)
@pytest.mark.parametrize("payload", ["x&y", "notacolor"])
def test_every_chromatic_field_takes_the_paint_grammar(field: str, payload: str) -> None:
    """Only a dozen colour fields carried a validator; the other 73 were plain
    ``str``, so ``highlight_color = "x&y"`` reached the root inline style and
    broke XML parsing while ``notacolor`` emitted invalid CSS."""
    with pytest.raises(HwError) as exc:
        validate_genome_override(
            build_minimal_genome_for_testing(id="round5", paradigms={"badge": "default"}, **{field: payload})
        )
    assert exc.value.code is HwErrorCode.SPEC_INVALID


@pytest.mark.parametrize("field", _UNTYPED_COLOR_FIELDS[:5])
@pytest.mark.parametrize("payload", ["x&y", "notacolor"])
def test_chromatic_grammar_applies_through_variant_overrides(field: str, payload: str) -> None:
    """The override path delegates its typing to the model, so it inherited the
    same hole — a primer override of {"highlight_color": "x&y"} composed an SVG
    ElementTree could not parse."""
    genome = build_minimal_genome_for_testing(
        id="round5",
        paradigms={"badge": "default"},
        variants=["v"],
        flagship_variant="v",
        variant_overrides={"v": {field: payload}},
    )
    with pytest.raises(HwError):
        validate_genome_override(genome)


def test_every_genome_string_field_has_a_grammar() -> None:
    """Structural guard: the chromatic partition stays TOTAL.

    Every ``str`` field on GenomeSpec is either declared non-chromatic (and
    carries its own slug/length/time/number/font grammar) or is validated as a
    paint. A colour field added later is covered by default — the failure mode
    that left 73 fields unchecked was an allowlist that simply never grew."""
    from hyperweave.core.schema import _NON_CHROMATIC_STR_FIELDS, GenomeSpec, chromatic_fields

    str_fields = {name for name, f in GenomeSpec.model_fields.items() if f.annotation is str}
    assert chromatic_fields() | _NON_CHROMATIC_STR_FIELDS == str_fields
    assert not (chromatic_fields() & _NON_CHROMATIC_STR_FIELDS)
    unknown = _NON_CHROMATIC_STR_FIELDS - str_fields
    assert not unknown, f"non-chromatic set names fields that no longer exist: {sorted(unknown)}"


def test_css_emission_escapes_the_entity_character() -> None:
    """Defense in depth, not a substitute: a bare ``&`` reaching CSS parses as
    an undefined XML entity. The paint grammar rejects it upstream; this makes
    the sink safe even if something slips."""
    from hyperweave.compose.assembler import _css_safe

    assert _css_safe("x&y") == "x&amp;y"
    assert _css_safe('</style><x y="z">') == "&lt;/style&gt;&lt;x y=&quot;z&quot;&gt;"


def test_lawful_paints_still_compose() -> None:
    """Each paint kind accepts what its policy allows: hex anywhere, alpha on
    an atmospheric surface, `transparent` on a documented optional layer."""
    genome = build_minimal_genome_for_testing(
        id="round5",
        paradigms={"badge": "default"},
        highlight_color="#FFFFFF",
        diamond_stroke="#8899AA",
        border_tint="rgba(10, 20, 30, 0.5)",
        card_border="transparent",
    )
    ET.fromstring(compose(ComposeSpec(type="badge", title="X", value="1", genome_override=genome)).svg)


# ── Review round 6: paint policy is per field, not universal ────────────────


_INVISIBLE_PAINTS = ["transparent", "rgba(0, 0, 0, 0)"]
_REQUIRED_TEXT_PAINTS = [
    "badge_value_text",
    "state_warning_core",
    "state_passing_core",
    "glyph_fill",
    "frame_fill",
    "highlight_color",
    "brand_text",
    "metric_text",
    "diagram_status_critical",
]


@pytest.mark.parametrize("field", _REQUIRED_TEXT_PAINTS)
@pytest.mark.parametrize("paint", _INVISIBLE_PAINTS)
def test_required_paints_reject_invisible_values(field: str, paint: str) -> None:
    """One universal grammar admitted ``transparent`` on all 84 fields, so a
    badge's semantic value could render invisible while the artifact still
    declared a11y="WCAG-AA". Zero-alpha rgba is the same claim written
    differently and is refused with it."""
    with pytest.raises(HwError) as exc:
        validate_genome_override(
            build_minimal_genome_for_testing(id="round6", paradigms={"badge": "default"}, **{field: paint})
        )
    assert exc.value.code is HwErrorCode.SPEC_INVALID


@pytest.mark.parametrize("paint", _INVISIBLE_PAINTS)
def test_variant_override_cannot_make_a_required_paint_invisible(paint: str) -> None:
    """The override path inherits the policy — the same field, the same answer."""
    genome = build_minimal_genome_for_testing(
        id="round6",
        paradigms={"badge": "default"},
        variants=["v"],
        flagship_variant="v",
        variant_overrides={"v": {"badge_value_text": paint}},
    )
    with pytest.raises(HwError):
        validate_genome_override(genome)


async def test_invisible_value_paint_is_refused_on_every_surface(http_client: AsyncClient) -> None:
    """Through the real wires, not just the validator."""
    genome = build_minimal_genome_for_testing(
        id="round6", paradigms={"badge": "default"}, badge_value_text="transparent"
    )
    resp = await http_client.post(
        "/v1/compose", json={"type": "badge", "title": "X", "value": "1", "genome_override": genome}
    )
    assert resp.status_code == 400
    with pytest.raises(HwError):
        await mcp_server.hw_compose(type="badge", title="X", value="1", genome_override=genome)
    with pytest.raises(HwError):
        await dispatch(
            "compose",
            {"type": "badge", "spec": {"title": "X", "value": "1", "genome_override": genome}},
            CallContext(surface="test"),
        )


def test_documented_optional_layers_still_accept_transparent() -> None:
    """The policy is per field, so the layers whose description documents
    ``transparent`` as "render this element absent" keep working."""
    genome = build_minimal_genome_for_testing(
        id="round6",
        paradigms={"badge": "default"},
        card_border="transparent",
        pill_outer_bg="transparent",
        pill_rule_top="transparent",
    )
    ET.fromstring(compose(ComposeSpec(type="badge", title="X", value="1", genome_override=genome)).svg)


def test_atmospheric_surfaces_still_accept_alpha() -> None:
    """Translucent layering (the codex atmosphere) is unaffected — but a
    zero-alpha surface is a mistake, not a request for absence."""
    genome = build_minimal_genome_for_testing(
        id="round6", paradigms={"badge": "default"}, surface_0="rgba(10, 12, 14, 0.6)"
    )
    validate_genome_override(genome)
    with pytest.raises(HwError):
        validate_genome_override(
            build_minimal_genome_for_testing(
                id="round6", paradigms={"badge": "default"}, surface_0="rgba(10, 12, 14, 0)"
            )
        )


def test_paint_policy_partition_is_total_and_defaults_opaque() -> None:
    """Structural guard: every chromatic field maps to exactly one kind, the
    named sets reference real fields, and anything unnamed defaults to opaque —
    so a colour field added later cannot silently become transparent-capable."""
    from hyperweave.core.schema import (
        _OPTIONAL_PAINT_FIELDS,
        _TRANSLUCENT_PAINT_FIELDS,
        chromatic_fields,
        paint_kind,
    )

    chromatic = chromatic_fields()
    assert chromatic >= _OPTIONAL_PAINT_FIELDS
    assert chromatic >= _TRANSLUCENT_PAINT_FIELDS
    assert not (_OPTIONAL_PAINT_FIELDS & _TRANSLUCENT_PAINT_FIELDS)
    kinds = {field: paint_kind(field) for field in chromatic}
    assert set(kinds.values()) <= {"opaque", "translucent", "optional"}
    defaulted = chromatic - _OPTIONAL_PAINT_FIELDS - _TRANSLUCENT_PAINT_FIELDS
    assert all(kinds[field] == "opaque" for field in defaulted)
    assert len(defaulted) > 70, "the opaque default must cover the bulk of the registry"


# ── Review round 7: heterogeneous role maps need per-leaf policy ────────────


_SEMANTIC_DIAGRAM_LEAVES = ["ink", "ink_hero", "ink_dim", "ink_zone", "accent_text", "glyph", "chip_text", "conn"]
_DIAGRAM_WASH_LEAVES = ["edge_hi", "edge_mid", "edge_lo", "edge_faint", "border"]
_INVISIBLE_LEAF_PAINTS = ["transparent", "rgba(255, 255, 255, 0.0001)", "rgba(0, 0, 0, 0.5)"]


def _diagram_genome(role: str, paint: str) -> dict[str, Any]:
    """A real primer clone whose variant overrides one diagram_dark role."""
    genome = copy.deepcopy(get_loader().genomes["primer"])
    variant = next(iter(genome["variant_overrides"]))
    genome["variant_overrides"] = dict(genome["variant_overrides"])
    genome["variant_overrides"][variant] = {
        **genome["variant_overrides"][variant],
        "diagram_dark": {role: paint},
    }
    return genome


@pytest.mark.parametrize("role", _SEMANTIC_DIAGRAM_LEAVES)
@pytest.mark.parametrize("paint", _INVISIBLE_LEAF_PAINTS)
def test_semantic_diagram_roles_reject_translucent_paint(role: str, paint: str) -> None:
    """``diagram_dark`` mixes edge washes with the ink a diagram is READ by, so
    a blanket translucent kind let ``ink`` land at alpha 0.0001 — invisible
    primary text on an artifact still claiming WCAG-AA."""
    with pytest.raises(HwError) as exc:
        validate_genome_override(_diagram_genome(role, paint))
    assert exc.value.code is HwErrorCode.SPEC_INVALID


@pytest.mark.parametrize("role", _DIAGRAM_WASH_LEAVES)
def test_documented_edge_washes_still_accept_alpha(role: str) -> None:
    """The five leaves that ship alpha in the corpus keep working."""
    validate_genome_override(_diagram_genome(role, "rgba(226, 232, 240, 0.05)"))


def test_unknown_diagram_role_defaults_to_opaque() -> None:
    """A role added later inherits the safe policy, not the permissive one."""
    with pytest.raises(HwError):
        validate_genome_override(_diagram_genome("some_future_role", "rgba(1, 2, 3, 0.5)"))


def test_real_diagram_composes_with_lawful_dark_roles() -> None:
    """The positive half, through a real diagram render."""
    genome = _diagram_genome("edge_lo", "rgba(226, 232, 240, 0.02)")
    svg = compose(
        ComposeSpec(
            type="diagram",
            genome_override=genome,
            diagram={
                "topology": "pipeline",
                "title": "Roles",
                "nodes": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
            },
        )
    ).svg
    ET.fromstring(svg)


async def test_invisible_diagram_ink_is_refused_on_every_surface(http_client: AsyncClient) -> None:
    """Base, variant, and all three wires — the nested leaf gets the same
    treatment the top-level required paints do."""
    genome = _diagram_genome("ink", "rgba(255, 255, 255, 0.0001)")
    ir = {
        "topology": "pipeline",
        "title": "Roles",
        "nodes": [{"label": "A"}, {"label": "B"}, {"label": "C"}],
    }
    resp = await http_client.post("/v1/compose", json={"type": "diagram", "diagram": ir, "genome_override": genome})
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == HwErrorCode.SPEC_INVALID.value

    with pytest.raises(HwError) as mcp_exc:
        await mcp_server.hw_compose(type="diagram", diagram=ir, genome_override=genome)
    assert mcp_exc.value.code is HwErrorCode.SPEC_INVALID

    with pytest.raises(HwError) as dispatch_exc:
        await dispatch(
            "compose",
            {"type": "diagram", "spec": {**ir, "genome_override": genome}},
            CallContext(surface="test"),
        )
    assert dispatch_exc.value.code is HwErrorCode.SPEC_INVALID


def test_role_map_policy_defaults_opaque_and_names_real_leaves() -> None:
    """Structural guard: the wash allowlist names leaves that exist, and every
    role outside it resolves opaque."""
    import json as _json
    import pathlib

    from hyperweave.core.schema import _ROLE_MAP_TRANSLUCENT_LEAVES

    declared: set[str] = set()
    for path in (pathlib.Path(hyperweave.__file__).parent / "data" / "genomes").glob("*.json"):
        genome = _json.loads(path.read_text())
        for body in (genome.get("variant_overrides") or {}).values():
            declared |= set(body.get("diagram_dark") or {})
    washes = _ROLE_MAP_TRANSLUCENT_LEAVES["diagram_dark"]
    assert washes <= declared, f"wash allowlist names absent roles: {sorted(washes - declared)}"
    assert not (washes & set(_SEMANTIC_DIAGRAM_LEAVES))
