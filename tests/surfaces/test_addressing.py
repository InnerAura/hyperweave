"""Addressing guards — a projected address must reach the artifact it names.

Per the Guard Law these exercise the surfaces a caller actually touches: the
built URL goes through the real FastAPI app, the built argv through the real
Typer parser, the built kwargs through the real MCP tool. Asserting only that
``spec_to_url`` returns a plausible-looking string is how a green test ships a
URL that 404s.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hyperweave.cli import app as cli_app
from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_url_grammar
from hyperweave.core.enums import FrameType
from hyperweave.core.models import ComposeSpec
from hyperweave.serve.app import app as http_app
from hyperweave.surfaces.addressing import (
    Unaddressable,
    canonical_spec,
    normalize_artifact,
    spec_to_cli_argv,
    spec_to_mcp_args,
    spec_to_url,
)

# One spec per addressable frame shape, spanning all four genomes and the axes
# the routes actually carry (variant, pair, size, shape, state, divider slug).
CASES: list[ComposeSpec] = [
    ComposeSpec(type="badge", genome_id="brutalist", title="build", value="passing"),
    ComposeSpec(
        type="badge",
        genome_id="automata",
        variant="teal",
        title="BUILD",
        value="passing",
        state="passing",
        glyph="github",
        size="compact",
    ),
    ComposeSpec(
        type="badge",
        genome_id="brutalist",
        variant="celadon",
        title="BUILD",
        value="critical",
        state="critical",
        glyph="github",
        state_glyph_shape="diamond",
    ),
    ComposeSpec(type="badge", genome_id="primer", variant="porcelain", title="PYPI", value="v0.4.2", glyph="python"),
    ComposeSpec(type="strip", genome_id="brutalist", title="readme-ai", value="STARS:2.9k,FORKS:278", glyph="github"),
    ComposeSpec(type="icon", genome_id="chrome", glyph="github", shape="circle", variant="moth"),
    ComposeSpec(type="icon", genome_id="automata", glyph="github", variant="teal"),
    ComposeSpec(type="divider", genome_id="automata", divider_variant="dissolve", variant="teal", pair="violet"),
    ComposeSpec(type="divider", genome_id="brutalist", divider_variant="sigil", variant="archive"),
    ComposeSpec(type="marquee", genome_id="brutalist", title="LIVING ARTIFACTS|SELF-CONTAINED SVG"),
]


def _id(spec: ComposeSpec) -> str:
    return f"{spec.type}-{spec.genome_id}-{spec.variant or 'flagship'}"


@pytest.mark.parametrize("spec", CASES, ids=_id)
def test_url_renders_the_same_artifact_as_direct_compose(spec: ComposeSpec) -> None:
    """The built URL routes, and returns byte-identical bytes to compose()."""
    spec = canonical_spec(spec)
    with TestClient(http_app) as client:
        response = client.get(spec_to_url(spec))
    assert response.status_code == 200, f"{spec_to_url(spec)} did not route"
    assert "X-HW-Error-Code" not in response.headers, f"error artifact: {response.headers}"
    assert normalize_artifact(response.text) == normalize_artifact(compose(spec).svg)


@pytest.mark.parametrize("spec", CASES, ids=_id)
def test_cli_argv_renders_the_same_artifact(spec: ComposeSpec) -> None:
    """The built argv parses on the real command and renders the same bytes."""
    spec = canonical_spec(spec)
    result = CliRunner().invoke(cli_app, ["compose", *spec_to_cli_argv(spec)])
    assert result.exit_code == 0, result.output[:400]
    assert normalize_artifact(result.stdout) == normalize_artifact(compose(spec).svg)


@pytest.mark.parametrize("spec", CASES, ids=_id)
@pytest.mark.asyncio
async def test_mcp_args_render_the_same_artifact(spec: ComposeSpec) -> None:
    """The built kwargs are accepted by hw_compose and render the same bytes."""
    from hyperweave.mcp.server import hw_compose

    spec = canonical_spec(spec)
    svg = await hw_compose(**spec_to_mcp_args(spec), respond="svg")
    assert isinstance(svg, str)
    assert normalize_artifact(svg) == normalize_artifact(compose(spec).svg)


def test_every_frame_type_is_routed_or_carries_a_reason() -> None:
    """No frame may be silently unaddressable.

    A frame absent from both `routes` and `unrouted` would make the proofset's
    coverage sweep skip it without saying so — the gap this file exists to
    prevent. Same rule surfaces/registry.py enforces with `mcp_note`.
    """
    grammar = load_url_grammar()
    declared = set(grammar["routes"]) | set(grammar["unrouted"])
    missing = sorted(ft.value for ft in FrameType if ft.value not in declared)
    assert not missing, f"frames with no route and no stated reason: {missing}"


def test_declared_examples_route() -> None:
    """Every `example:` in the grammar is a real URL, not an illustration."""
    grammar = load_url_grammar()
    with TestClient(http_app) as client:
        for frame, route in grammar["routes"].items():
            example = route.get("example", "")
            if not example or "..." in example:
                continue
            response = client.get(example)
            assert response.status_code == 200, f"{frame} example {example} → {response.status_code}"
            assert "X-HW-Error-Code" not in response.headers, f"{frame} example {example} served an error artifact"


def test_slashed_title_escapes_into_the_query() -> None:
    """A slash in a path segment would split the route; it rides ?t= instead."""
    spec = ComposeSpec(type="strip", genome_id="brutalist", title="Significant-Gravitas/AutoGPT", value="STARS:4m")
    url = spec_to_url(spec)
    assert "/v1/strip/_/" in url
    assert "t=Significant-Gravitas%2FAutoGPT" in url
    with TestClient(http_app) as client:
        assert normalize_artifact(client.get(url).text) == normalize_artifact(compose(spec).svg)


def test_escape_param_is_absent_when_nothing_needs_escaping() -> None:
    """?t= rides along only when the escape fired — not on every URL."""
    assert "t=" not in spec_to_url(ComposeSpec(type="badge", genome_id="brutalist", title="build", value="passing"))


def test_url_is_stable_for_the_same_spec() -> None:
    """Query order is sorted, so one spec has one address (cacheable, diffable)."""
    spec = ComposeSpec(
        type="badge", genome_id="chrome", variant="horizon", title="PYPI", value="v1", glyph="python", size="compact"
    )
    assert spec_to_url(spec) == spec_to_url(spec.model_copy())


def test_live_provider_tokens_are_unaddressable_with_a_reason() -> None:
    """A value fetched from a provider cannot round-trip through the grammar.

    `?data=gh:owner/repo.stars` re-fetches on the other side, so the comparison
    would be a pinned value against a fresh one — a connector's clock, not the
    surfaces. Reported rather than silently skipped: the caller prints it in the
    coverage audit.
    """
    from hyperweave.connectors.data_tokens import ResolvedToken

    spec = ComposeSpec(
        type="marquee",
        genome_id="brutalist",
        title="X",
        data_tokens=[ResolvedToken(kind="gh", label="STARS", value="2907", provider="github")],
    )
    for project in (spec_to_url, spec_to_cli_argv, spec_to_mcp_args):
        with pytest.raises(Unaddressable) as exc:
            project(spec)
        assert "live provider" in str(exc.value)
        assert "gh" in str(exc.value), "the reason should name the kind that blocked it"


def test_literal_tokens_round_trip_through_the_grammar() -> None:
    """`kv:` and `text:` tokens ARE addressable — their payload IS the value.

    Refusing every spec with tokens was over-broad: it skipped four parity specs
    whose cells are literals and reproduce exactly. The distinction is the token
    KIND, not the presence of tokens.
    """
    from hyperweave.connectors.data_tokens import ResolvedToken

    spec = ComposeSpec(
        type="marquee",
        genome_id="brutalist",
        variant="celadon",
        title="HYPERWEAVE",
        data_tokens=[
            ResolvedToken(kind="kv", label="STARS", value="2907"),
            ResolvedToken(kind="kv", label="DOWNLOADS", value="--", window="ALL-TIME"),
            ResolvedToken(kind="text", label="", value="SHIPPED"),
        ],
    )
    grammar = "kv:STARS=2907,kv:DOWNLOADS=--~ALL-TIME,text:SHIPPED"
    assert spec_to_mcp_args(spec)["data"] == grammar
    assert spec_to_cli_argv(spec)[-2:] == ["--data", grammar]
    # And the URL actually renders the same artifact.
    with TestClient(http_app) as client:
        response = client.get(spec_to_url(spec))
    assert response.status_code == 200, response.text[:300]
    assert normalize_artifact(response.text) == normalize_artifact(compose(spec).svg)


def test_a_dash_leading_positional_does_not_eat_the_flags() -> None:
    """`--` is the POSIX end-of-options marker.

    A badge whose value is the "--" placeholder for an unresolved metric put a
    bare `--` in the positional slot, and every flag after it was read as a
    positional: exit 2, on 60+ parity specs at once.
    """
    spec = ComposeSpec(type="badge", genome_id="brutalist", title="STARS", value="--")
    argv = spec_to_cli_argv(spec)
    assert argv.index("--genome") < argv.index("--"), "options must precede the separator"
    result = CliRunner().invoke(cli_app, ["compose", *argv])
    assert result.exit_code == 0, result.output[:300]
    assert normalize_artifact(result.stdout) == normalize_artifact(compose(spec).svg)


def test_an_oversize_inline_payload_is_refused_rather_than_404d() -> None:
    """The route caps ?spec= at 8 KB; hand back a reason, not a URL that fails."""
    rows = [{"label": f"row-{i}", "cells": [{"value": "x" * 60}]} for i in range(60)]
    spec = ComposeSpec(
        type="matrix",
        genome_id="primer",
        variant="porcelain",
        matrix={"title": "Huge", "columns": [{"id": "v", "label": "V"}], "rows": rows},
    )
    with pytest.raises(Unaddressable) as exc:
        spec_to_url(spec)
    assert "inline" in str(exc.value) and "cap" in str(exc.value)


def test_a_spec_with_no_payload_and_no_preset_is_refused() -> None:
    """`/v1/matrix/custom/...` with no ?spec= is a 400.

    A spec pointing at a server-side adapter has its content under a preset
    slug, which a spec does not record — so no URL is derivable, and emitting
    `custom` anyway would hand back an address the route rejects.
    """
    spec = ComposeSpec(
        type="matrix",
        genome_id="primer",
        variant="porcelain",
        connector_data={"matrix_adapter": "connector-registry"},
    )
    with pytest.raises(Unaddressable) as exc:
        spec_to_url(spec)
    assert "preset slug" in str(exc.value)


def test_receipt_reports_the_declared_reason() -> None:
    """An unrouted frame answers with its stated reason, not a generic failure."""
    spec = ComposeSpec(type="receipt", genome_id="primer", telemetry_data={"cost_usd": 1.0})
    with pytest.raises(Unaddressable) as exc:
        spec_to_url(spec)
    assert "POST /v1/compose" in str(exc.value)


def test_canonical_spec_applies_the_icon_title_derivation() -> None:
    """The icon route names the artifact after its glyph; canonicalizing makes
    a directly-composed icon match the one a URL returns."""
    spec = ComposeSpec(type="icon", genome_id="chrome", glyph="github")
    assert spec.title == ""
    assert canonical_spec(spec).title == "github"
    # Un-canonicalized, the address is refused rather than quietly diverging.
    with pytest.raises(Unaddressable) as exc:
        spec_to_url(spec)
    assert "canonical_spec" in str(exc.value)


def test_canonical_spec_is_a_no_op_where_nothing_derives() -> None:
    spec = ComposeSpec(type="badge", genome_id="brutalist", title="build", value="passing")
    assert canonical_spec(spec) is spec
