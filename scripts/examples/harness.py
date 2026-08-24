"""3-path proofset regression harness (v0.3.9).

Renders artifacts via three entry points and asserts byte-equal output:
1. Direct ``compose()`` in-process
2. Local FastAPI subprocess hit via HTTP
3. Local MCP server hit via ``fastmcp.Client`` (in-process via memory transport)

Any divergence is a parity bug — all three entry points share the same
``compose()`` function downstream of their input handling, so equivalent
SVG output is the contract. CLI/HTTP/MCP feature parity is HyperWeave
Invariant 9 (CLAUDE.md).

Volatile-fragment normalization (UIDs, timestamps, version strings) reuses
the regex pack from ``tests/test_url_stability.py:_normalize`` so the same
artifact rendered twice compares equal even though embedded IDs differ.

Fixture cache at ``tests/fixtures/proofset_data.json`` backs live-data
tokens — on network failure the cache provides reproducibility.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from fastmcp import Client as MCPClient

from hyperweave.surfaces.addressing import normalize_artifact

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "proofset_data.json"

# The volatile-fragment contract lives in the package, next to the addressing
# it is the other half of: an address is correct when what it returns matches a
# direct compose EXCEPT for these. It used to be a verbatim copy here, kept "in
# sync" by hand with two other copies.
normalize = normalize_artifact


def unwrap_mcp_svg(call_result: Any) -> str:
    """Extract raw SVG from MCP CallToolResult envelope.

    FastMCP wraps tool returns in ``CallToolResult.content`` as a list of
    ``TextContent`` (or similar) blocks. For ``hw_compose`` invoked with
    ``respond="svg"`` the first block's ``text`` is the SVG markup. Comparing
    the FastMCP content envelope to a bare SVG string would be a guaranteed
    false negative — always unwrap first.
    """
    content = call_result.content
    if not content:
        raise RuntimeError("MCP tool returned empty content envelope")
    first = content[0]
    if not hasattr(first, "text"):
        raise RuntimeError(f"MCP first content lacks .text attribute: {type(first).__name__}")
    return str(first.text)


@contextmanager
def fastapi_server(port: int = 8765, ready_timeout: float = 15.0) -> Iterator[str]:
    """Start ``hyperweave.serve.app`` under uvicorn; yield base URL.

    Spawns a real subprocess so the harness exercises the network stack
    (headers, query parsing, response serialization) that ASGITransport
    would short-circuit. On exit: SIGTERM, wait 5s, SIGKILL if needed —
    guarantees no orphan processes even on exception.
    """
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "hyperweave.serve.app:app",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://localhost:{port}"
    try:
        deadline = time.monotonic() + ready_timeout
        while time.monotonic() < deadline:
            try:
                r = httpx.get(f"{base_url}/health", timeout=0.5)
                if r.status_code == 200:
                    yield base_url
                    return
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout):
                pass
            time.sleep(0.25)
        raise RuntimeError(f"uvicorn didn't become ready on {base_url} within {ready_timeout}s")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


@asynccontextmanager
async def mcp_client() -> AsyncIterator[MCPClient[Any]]:
    """In-process MCP client via ``fastmcp.Client(mcp_server)``.

    No subprocess — the Client runs FastMCP directly over a memory
    transport. Tests the same code paths a remote MCP call would hit
    (tool dispatch, parameter parsing, response framing) without
    subprocess lifecycle overhead. The stdio/HTTP transports add
    network/IPC plumbing but the tool-handler logic is identical.
    """
    from hyperweave.mcp.server import mcp

    async with MCPClient(mcp) as client:
        yield client


# ── Fixture cache ───────────────────────────────────────────────────────


def load_fixtures() -> dict[str, Any]:
    """Load connector fixture cache; empty dict if file doesn't exist."""
    if not FIXTURE_PATH.exists():
        return {}
    return dict(json.loads(FIXTURE_PATH.read_text()))


def save_fixtures(data: dict[str, Any]) -> None:
    """Persist connector cache, sorted for deterministic diffs."""
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


async def fetch_or_cache(
    provider: str,
    identifier: str,
    metric: str,
    fixtures: dict[str, Any],
) -> Any:
    """Fetch a metric live; cache on success, fall back to cache on failure.

    Token shape: ``provider:identifier.metric`` (e.g., ``gh:ollama/ollama.stars``).
    Returns the cached value if both live fetch and cache miss — raises only
    when both fail.
    """
    from hyperweave.connectors import fetch_metric

    cache_key = f"{provider}:{identifier}.{metric}"
    try:
        result = await fetch_metric(provider, identifier, metric)
        # connectors return dict with 'value' key
        value = result.get("value") if isinstance(result, dict) else result
        fixtures[cache_key] = {"value": value, "fetched_at": time.time()}
        return value
    except Exception as exc:
        cached = fixtures.get(cache_key)
        if cached is not None:
            return cached["value"]
        raise RuntimeError(f"No fixture cache for {cache_key} and live fetch failed: {exc}") from exc


# ── Parity rendering ────────────────────────────────────────────────────


@dataclass
class ParitySpec:
    """A single 3-path render specification.

    ``spec_id`` is the filename stem used to save artifacts. The same
    ComposeSpec must round-trip through HTTP and MCP equivalently —
    ``http_path`` and ``mcp_args`` are computed by the matrix builder so
    they encode the SAME compositional intent as ``compose_spec``.
    """

    spec_id: str
    compose_spec: Any  # ComposeSpec — typed Any to keep harness import-light
    mcp_tool: str = "hw_compose"

    # The HTTP URL and the MCP kwargs DERIVE from compose_spec. Both stay
    # overridable because a handful of entries legitimately need an address the
    # spec cannot express — a table served under a server-known preset slug, for
    # one, since a spec records the adapter it points at but not the slug.
    #
    # Passing them for any other reason is writing one intent down three times,
    # which is what this matrix used to do for every entry. Left empty they are
    # projected by `surfaces/addressing.py`, and a spec no surface can express
    # raises Unaddressable with a reason rather than quietly rendering something
    # else.
    http_path_override: str = ""
    mcp_args_override: dict[str, Any] = field(default_factory=dict)

    @property
    def http_path(self) -> str:
        from hyperweave.surfaces.addressing import spec_to_url

        return self.http_path_override or spec_to_url(self.compose_spec)

    @property
    def mcp_args(self) -> dict[str, Any]:
        from hyperweave.surfaces.addressing import spec_to_mcp_args

        return self.mcp_args_override or spec_to_mcp_args(self.compose_spec)


async def render_three_paths(
    spec: ParitySpec,
    http_base_url: str,
    mcp: MCPClient[Any],
) -> tuple[str, str, str]:
    """Render via direct/http/mcp; return all three raw SVGs.

    Caller asserts equality after ``normalize()``. Hard fails on HTTP
    non-2xx so a misrouted URL surfaces as a clear error, not a silent
    parity mismatch downstream.
    """
    from hyperweave.compose.engine import compose

    direct_svg = compose(spec.compose_spec).svg

    http_resp = httpx.get(f"{http_base_url}{spec.http_path}", timeout=15.0)
    http_resp.raise_for_status()
    http_svg = http_resp.text

    # hw_compose defaults to respond="envelope" (the ~200-token handle, not
    # inline markup). Parity compares pixels across surfaces, so
    # ask MCP for the pixels explicitly — spec.mcp_args stays a pure description
    # of the semantic request; the SVG opt-in is a comparison detail.
    mcp_result = await mcp.call_tool(spec.mcp_tool, {**spec.mcp_args, "respond": "svg"})
    mcp_svg = unwrap_mcp_svg(mcp_result)

    return direct_svg, http_svg, mcp_svg


@dataclass
class ParityReport:
    """Outcome of a single 3-path render — paths to saved files + parity status."""

    spec_id: str
    direct_path: Path
    http_path: Path
    mcp_path: Path
    parity_direct_http: bool
    parity_direct_mcp: bool
    parity_http_mcp: bool

    @property
    def all_match(self) -> bool:
        return self.parity_direct_http and self.parity_direct_mcp and self.parity_http_mcp


async def render_and_save_three_paths(
    spec: ParitySpec,
    http_base_url: str,
    mcp: MCPClient[Any],
    out_dir: Path,
) -> ParityReport:
    """Render via all three paths, save each SVG, return ParityReport.

    Files saved as ``{spec_id}-direct.svg``, ``{spec_id}-http.svg``,
    ``{spec_id}-mcp.svg`` under ``out_dir``. Parity is computed via
    ``normalize()`` on raw SVGs so volatile UIDs/timestamps don't
    introduce false-negative drift.
    """
    direct_svg, http_svg, mcp_svg = await render_three_paths(spec, http_base_url, mcp)

    out_dir.mkdir(parents=True, exist_ok=True)
    direct_path = out_dir / f"{spec.spec_id}-direct.svg"
    http_path = out_dir / f"{spec.spec_id}-http.svg"
    mcp_path = out_dir / f"{spec.spec_id}-mcp.svg"
    direct_path.write_text(direct_svg)
    http_path.write_text(http_svg)
    mcp_path.write_text(mcp_svg)

    n_direct = normalize(direct_svg)
    n_http = normalize(http_svg)
    n_mcp = normalize(mcp_svg)

    return ParityReport(
        spec_id=spec.spec_id,
        direct_path=direct_path,
        http_path=http_path,
        mcp_path=mcp_path,
        parity_direct_http=(n_direct == n_http),
        parity_direct_mcp=(n_direct == n_mcp),
        parity_http_mcp=(n_http == n_mcp),
    )
