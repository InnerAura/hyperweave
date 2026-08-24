"""--font-mode: embed (default) | cdn | system."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from hyperweave.cli import app
from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec

runner = CliRunner()


def _svg(font_mode: str) -> str:
    return compose(
        ComposeSpec(
            type="strip",
            genome_id="primer",
            title="readme-ai",
            value="STARS:2.9k,FORKS:278",
            font_mode=font_mode,
        )
    ).svg


def test_embed_is_self_contained_base64() -> None:
    svg = _svg("embed")
    assert "@font-face" in svg and "base64" in svg


def test_cdn_uses_google_import_not_base64() -> None:
    svg = _svg("cdn")
    assert "fonts.googleapis.com" in svg
    assert "base64" not in svg


def test_system_embeds_no_fonts() -> None:
    svg = _svg("system")
    assert "@font-face" not in svg
    assert "base64" not in svg


def test_cdn_and_system_are_much_lighter_than_embed() -> None:
    embed, cdn, system = _svg("embed"), _svg("cdn"), _svg("system")
    assert len(cdn) < len(embed) // 2  # the base64 font blob dominates embed
    assert len(system) < len(embed) // 2


# ── data-hw-fonts reports the delivery that actually happened ─────────────
# The attribute answers "can this file render its own type offline?". It used
# to hardcode "self-contained" off a non-empty payload, so a cdn render shipped
# a Google @import while claiming to need nothing.


@pytest.mark.parametrize(
    ("font_mode", "attribute", "constraint"),
    [
        ("embed", "self-contained", "self-contained"),
        ("cdn", "cdn", "cdn-fonts"),
        ("system", "system", "system-fonts"),
    ],
)
def test_both_portability_claims_name_the_delivery(font_mode: str, attribute: str, constraint: str) -> None:
    svg = _svg(font_mode)
    assert f'data-hw-fonts="{attribute}"' in svg
    assert f"<hw:constraints-applied>{constraint}, " in svg


@pytest.mark.parametrize("font_mode", ["cdn", "system"])
def test_a_render_that_needs_outside_type_never_claims_self_contained(font_mode: str) -> None:
    """Both claims, one assertion: the word must not survive anywhere in a
    render whose type comes from the network or the reader's machine."""
    assert "self-contained" not in _svg(font_mode)


def test_cdn_is_honest_about_the_dependency_it_took() -> None:
    assert "fonts.googleapis.com" in _svg("cdn")


def test_a_frame_that_loads_no_type_omits_the_attribute_and_stays_self_contained() -> None:
    """Icons render zero <text>, so there is no font question to answer — and
    an artifact that needs nothing genuinely is self-contained."""
    svg = compose(ComposeSpec(type="icon", genome_id="primer", glyph="github")).svg
    assert "data-hw-fonts" not in svg
    assert "<hw:constraints-applied>self-contained, " in svg


@pytest.mark.parametrize(
    ("font_mode", "label"),
    [("embed", "self-contained"), ("cdn", "cdn"), ("system", "system")],
)
def test_font_attribute_through_the_real_cli(font_mode: str, label: str, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Guard Law: the flag a caller actually types, through the real parser."""
    out = tmp_path / f"{font_mode}.svg"
    result = runner.invoke(
        app,
        ["compose", "strip", "readme-ai", "STARS:2.9k", "-g", "primer", "--font-mode", font_mode, "-o", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert f'data-hw-fonts="{label}"' in out.read_text()


# ── The axis must exist on every surface, not just the CLI ───────────────────
# font_mode shipped as a CLI-only flag: HTTP and MCP had no way to ask for it,
# so the same artifact requested three ways came back with three different
# font payloads. Invariant 9 says the three surfaces have feature parity, and a
# delivery axis one surface cannot express is a parity hole. These guards drive
# each surface the way a caller does — the query string, the tool kwargs — so a
# route that silently drops the parameter fails here rather than in a review.


@pytest.mark.parametrize(
    ("font_mode", "label"),
    [("embed", "self-contained"), ("cdn", "cdn"), ("system", "system")],
)
def test_font_mode_through_the_real_http_route(font_mode: str, label: str) -> None:
    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app as http_app

    with TestClient(http_app) as client:
        response = client.get(f"/v1/strip/readme-ai/primer.static?value=STARS:2.9k&font_mode={font_mode}")
    assert response.status_code == 200, response.text[:300]
    assert f'data-hw-fonts="{label}"' in response.text


@pytest.mark.parametrize(
    ("font_mode", "label"),
    [("embed", "self-contained"), ("cdn", "cdn"), ("system", "system")],
)
@pytest.mark.asyncio
async def test_font_mode_through_the_real_mcp_tool(font_mode: str, label: str) -> None:
    from hyperweave.mcp.server import hw_compose

    svg = await hw_compose(
        type="strip",
        genome="primer",
        title="readme-ai",
        value="STARS:2.9k",
        font_mode=font_mode,
        respond="svg",
    )
    assert isinstance(svg, str)
    assert f'data-hw-fonts="{label}"' in svg


@pytest.mark.parametrize("font_mode", ["embed", "cdn", "system"])
def test_every_surface_returns_the_same_bytes_for_one_font_mode(font_mode: str) -> None:
    """The point of the axis existing everywhere: asking three ways is one answer.

    Compares through the volatile-fragment scrub, so what is being asserted is
    the artifact, not its per-render identity.
    """
    import asyncio

    from fastapi.testclient import TestClient

    from hyperweave.serve.app import app as http_app
    from hyperweave.surfaces.addressing import normalize_artifact

    spec = ComposeSpec(
        type="strip",
        genome_id="primer",
        title="readme-ai",
        value="STARS:2.9k",
        font_mode=font_mode,
    )
    direct = normalize_artifact(compose(spec).svg)

    with TestClient(http_app) as client:
        http = client.get(f"/v1/strip/readme-ai/primer.static?value=STARS:2.9k&font_mode={font_mode}").text
    assert normalize_artifact(http) == direct, f"HTTP diverged from compose() on font_mode={font_mode}"

    cli = runner.invoke(app, ["compose", "strip", "readme-ai", "STARS:2.9k", "-g", "primer", "--font-mode", font_mode])
    assert cli.exit_code == 0, cli.output
    assert normalize_artifact(cli.stdout) == direct, f"CLI diverged from compose() on font_mode={font_mode}"

    from hyperweave.mcp.server import hw_compose

    mcp = asyncio.run(
        hw_compose(
            type="strip",
            genome="primer",
            title="readme-ai",
            value="STARS:2.9k",
            font_mode=font_mode,
            respond="svg",
        )
    )
    assert isinstance(mcp, str)
    assert normalize_artifact(mcp) == direct, f"MCP diverged from compose() on font_mode={font_mode}"
