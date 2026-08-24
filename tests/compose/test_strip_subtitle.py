"""The strip subtitle, on every surface that can compose a strip.

The subtitle rides ``connector_data.repo_slug`` — the field the strip resolver
reads to draw the grayish identity line under the title, for paradigms that opt
in. HTTP has carried ``?subtitle=`` and MCP has accepted ``connector_data``
since the field existed; the CLI had neither, so a strip a caller could request
over HTTP was not expressible as a command. Invariant 9 says the three surfaces
have feature parity, and the gap only surfaced when the proofset started
rendering every artifact through all three and reporting what it could not
address.

Per the Guard Law each surface is driven the way a caller drives it: the real
query string, the real Typer parser, the real tool kwargs.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hyperweave.cli import app as cli_app
from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec
from hyperweave.serve.app import app as http_app
from hyperweave.surfaces.addressing import normalize_artifact

SLUG = "eli64s/readme-ai"
# Cellular opts into subtitles; the automata genome is where it renders.
GENOME = "automata"
VARIANT = "teal"


def _direct(subtitle: str) -> str:
    return compose(
        ComposeSpec(
            type="strip",
            genome_id=GENOME,
            variant=VARIANT,
            title="readme-ai",
            value="STARS:2.9k,FORKS:278",
            glyph="github",
            connector_data={"repo_slug": subtitle} if subtitle else None,
        )
    ).svg


def test_the_subtitle_reaches_the_artifact() -> None:
    """Without this the rest of the file would pass on an artifact that draws
    no subtitle at all — the assertions would be comparing two blanks."""
    assert SLUG in _direct(SLUG)
    assert SLUG not in _direct("")


def test_cli_can_express_a_strip_subtitle() -> None:
    """The gap itself: `compose` had no flag for it."""
    result = CliRunner().invoke(
        cli_app,
        [
            "compose",
            "strip",
            "readme-ai",
            "STARS:2.9k,FORKS:278",
            "-g",
            GENOME,
            "--variant",
            VARIANT,
            "--glyph",
            "github",
            "--subtitle",
            SLUG,
        ],
    )
    assert result.exit_code == 0, result.output[:400]
    assert SLUG in result.stdout


def test_http_query_and_cli_flag_and_mcp_payload_agree() -> None:
    """One subtitle, three ways of asking, one artifact."""
    expected = normalize_artifact(_direct(SLUG))

    with TestClient(http_app) as client:
        http = client.get(
            f"/v1/strip/readme-ai/{GENOME}.static"
            f"?value=STARS:2.9k,FORKS:278&glyph=github&variant={VARIANT}&subtitle={SLUG}"
        )
    assert http.status_code == 200, http.text[:300]
    assert normalize_artifact(http.text) == expected, "HTTP ?subtitle= diverged from compose()"

    cli = CliRunner().invoke(
        cli_app,
        [
            "compose",
            "strip",
            "readme-ai",
            "STARS:2.9k,FORKS:278",
            "-g",
            GENOME,
            "--variant",
            VARIANT,
            "--glyph",
            "github",
            "--subtitle",
            SLUG,
        ],
    )
    assert cli.exit_code == 0, cli.output[:400]
    assert normalize_artifact(cli.stdout) == expected, "CLI --subtitle diverged from compose()"

    from hyperweave.mcp.server import hw_compose

    mcp = asyncio.run(
        hw_compose(
            type="strip",
            genome=GENOME,
            variant=VARIANT,
            title="readme-ai",
            value="STARS:2.9k,FORKS:278",
            glyph="github",
            connector_data={"repo_slug": SLUG},
            respond="svg",
        )
    )
    assert isinstance(mcp, str)
    assert normalize_artifact(mcp) == expected, "MCP connector_data diverged from compose()"


def test_no_subtitle_leaves_connector_data_unset() -> None:
    """An empty flag must not fabricate an adapter payload.

    ``connector_data`` is also the pre-fetched stats/chart pathway, so an empty
    ``--subtitle`` that still built ``{"repo_slug": ""}`` would hand paradigms
    that never opted into subtitles a dict they have to ignore.
    """
    result = CliRunner().invoke(
        cli_app, ["compose", "strip", "readme-ai", "STARS:2.9k", "-g", GENOME, "--variant", VARIANT]
    )
    assert result.exit_code == 0, result.output[:400]
    assert normalize_artifact(result.stdout) == normalize_artifact(
        compose(ComposeSpec(type="strip", genome_id=GENOME, variant=VARIANT, title="readme-ai", value="STARS:2.9k")).svg
    )


@pytest.mark.parametrize("subtitle", ["a/b", "owner/repo-with-dash", "x"])
def test_subtitle_survives_the_query_string(subtitle: str) -> None:
    """The slash in a repo slug is the interesting character — it must ride the
    query, not split the route."""
    with TestClient(http_app) as client:
        response = client.get(
            f"/v1/strip/readme-ai/{GENOME}.static?value=STARS:1&variant={VARIANT}&subtitle={subtitle}"
        )
    assert response.status_code == 200, response.text[:300]
    assert subtitle in response.text
