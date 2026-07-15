"""Surface parity — the structural no-drift proof.

Three guarantees:

1. **Reachability**: every registered :class:`Capability` is reachable on all
   three surfaces — its ``http_path`` is a mounted POST route (or it is
   discover, whose HTTP face is bespoke), its ``cli_command`` is a registered
   CLI command (or None), and its ``mcp_tool`` is a live MCP tool (or it carries
   an ``mcp_note`` AND appears in ``hw_discover("capabilities")``).
2. **Round-trip**: one canned input per verb capability, run via direct
   dispatch, the HTTP ASGI route, the CLI command, and the MCP tool, yields the
   same canonical result dict.
3. **Frozen MCP tool set**: the tool-name set equals a curated list EXACTLY, so
   adding a tool without a deliberate curation decision fails CI (tool flood
   guard).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from hyperweave.cli import app as cli_app
from hyperweave.mcp import server as mcp_server
from hyperweave.serve.app import app as http_app
from hyperweave.surfaces.registry import CallContext, all_capabilities, dispatch

# The curated MCP tool set. Adding a tool requires updating this list — a
# deliberate curation decision, not an accident. hw_compress is the kept
# envelope-depth alias; artifact-fetch is a RESOURCE (hyperweave://artifact/…),
# deliberately NOT a tool, so it is absent here.
_CURATED_MCP_TOOLS = frozenset(
    {
        "hw_compose",
        "hw_validate",
        "hw_extract",
        "hw_compress",
        "hw_verify",
        "hw_transform",
        "hw_diff",
        "hw_query",
        "hw_discover",
    }
)

runner = CliRunner()


def _http_post_paths() -> set[str]:
    return {r.path for r in http_app.routes if "POST" in getattr(r, "methods", set())}


def _cli_command_names() -> set[str]:
    from typer.main import get_command

    return set(get_command(cli_app).commands.keys())  # type: ignore[attr-defined]


async def _mcp_tool_names() -> set[str]:
    return {t.name for t in await mcp_server.mcp.list_tools()}


# ── 1. Reachability ──────────────────────────────────────────────────────────


def test_every_capability_http_path_is_mounted() -> None:
    posts = _http_post_paths()
    for cap in all_capabilities():
        if cap.http_path is None:
            continue
        assert cap.http_path in posts, f"{cap.name}: {cap.http_path} not a mounted POST route"


def test_every_capability_cli_command_is_registered() -> None:
    commands = _cli_command_names()
    for cap in all_capabilities():
        if cap.cli_command is None:
            continue
        assert cap.cli_command in commands, f"{cap.name}: CLI command {cap.cli_command!r} not registered"


async def test_every_capability_reachable_on_mcp_or_documented() -> None:
    tools = await _mcp_tool_names()
    disc = mcp_server_capability_index()
    documented = {row["name"] for row in disc}
    for cap in all_capabilities():
        if cap.mcp_tool is not None:
            assert cap.mcp_tool in tools, f"{cap.name}: MCP tool {cap.mcp_tool!r} not live"
        else:
            assert cap.mcp_note, f"{cap.name}: no mcp_tool and no mcp_note"
            assert cap.name in documented, f"{cap.name}: absent from hw_discover(capabilities)"


def mcp_server_capability_index() -> list[dict[str, Any]]:
    from hyperweave.surfaces.discover import capability_index

    return capability_index()


# ── 2. Round-trip across surfaces ────────────────────────────────────────────


@pytest.fixture()
async def sample_svg() -> str:
    """A composed badge SVG to feed the read verbs."""
    ctx = CallContext(surface="test")
    result = await dispatch(
        "compose",
        {"type": "badge", "genome": "brutalist", "title": "STARS", "value": "42", "emit": ["svg"]},
        ctx,
    )
    return str(result["svg"])


@pytest.fixture()
async def http_client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=http_app), base_url="http://test") as ac:
        yield ac


async def test_extract_parity_across_surfaces(sample_svg: str, http_client: AsyncClient) -> None:
    payload = {"source": sample_svg, "respond": "envelope"}
    ctx = CallContext(surface="test")

    direct = await dispatch("extract", payload, ctx)
    http = (await http_client.post("/v1/extract", json=payload)).json()
    # MCP params are unified with the HTTP/CLI vocabulary (source, not svg_or_url).
    mcp = await mcp_server.hw_extract(source=sample_svg, respond="envelope")
    cli = _cli_json(["extract", sample_svg, "--respond", "envelope"])

    assert direct == http == mcp == cli
    assert direct["schema"] == "badge/1"


async def test_verify_parity_across_surfaces(sample_svg: str, http_client: AsyncClient) -> None:
    ctx = CallContext(surface="test")
    direct = await dispatch("verify", {"source": sample_svg}, ctx)
    http = (await http_client.post("/v1/verify", json={"source": sample_svg})).json()
    mcp = await mcp_server.hw_verify(source=sample_svg)  # unified: source, not svg
    cli = _cli_json(["verify", sample_svg])

    assert direct == http == mcp == cli
    assert direct["valid"] is True


async def test_query_parity_across_surfaces(sample_svg: str, http_client: AsyncClient) -> None:
    ctx = CallContext(surface="test")
    q = "what is the title"
    direct = await dispatch("query", {"source": sample_svg, "question": q}, ctx)
    http = (await http_client.post("/v1/query", json={"source": sample_svg, "question": q})).json()
    mcp = await mcp_server.hw_query(source=sample_svg, question=q)  # unified: source
    cli = _cli_json(["query", sample_svg, q])

    # Parity is the guarantee: identical result across all four surfaces.
    assert direct == http == mcp == cli
    assert direct["field"] == "title"
    assert direct["mechanism"] == "deterministic"


async def test_diff_parity_across_surfaces(sample_svg: str, http_client: AsyncClient) -> None:
    ctx = CallContext(surface="test")
    direct = await dispatch("diff", {"a": sample_svg, "b": sample_svg}, ctx)
    http = (await http_client.post("/v1/diff", json={"a": sample_svg, "b": sample_svg})).json()
    mcp = await mcp_server.hw_diff(a=sample_svg, b=sample_svg)  # unified: a/b, not svg_a/svg_b
    cli = _cli_json(["diff", sample_svg, sample_svg])

    assert direct == http == mcp == cli
    assert direct["same"] is True


def _cli_json(args: list[str]) -> dict[str, Any]:
    """Invoke a CLI command and parse its JSON stdout."""
    result = runner.invoke(cli_app, args)
    assert result.exit_code == 0, f"CLI {args[0]} exit {result.exit_code}: {result.output}"
    return json.loads(result.stdout)  # type: ignore[no-any-return]


# ── 3. Frozen MCP tool set ───────────────────────────────────────────────────


async def test_mcp_tool_set_is_frozen() -> None:
    tools = await _mcp_tool_names()
    assert tools == set(_CURATED_MCP_TOOLS), (
        "MCP tool set drifted — adding/removing a tool is a curation decision. "
        f"unexpected={sorted(tools - _CURATED_MCP_TOOLS)} missing={sorted(set(_CURATED_MCP_TOOLS) - tools)}"
    )
