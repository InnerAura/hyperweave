"""Served-response invariant: a CSP must permit the fonts its own SVG embeds.

v0.3.12. The brutalist strip identity bled past its seam on the
direct-served URL: ``serve/app.py``'s ``svg_camo_headers`` middleware set
``Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`` with
NO ``font-src`` directive, so ``font-src`` inherited ``default-src 'none'`` and
the browser refused the SVG's OWN embedded ``data:font/woff2`` faces. The
display font silently fell back to a wider system face → tight slots overflowed.
It was NOT a layout/measurement bug — the engine measured the embedded font
correctly; a header threw that font away after layout.

The bug lives on the MIDDLEWARE (every served SVG passes through it), so it is
server-wide, not strip-specific — every genome/frame that embeds a font loses
it on the direct route; most just have enough slack to substitute silently. The
fix is one ``font-src data:`` directive at the chokepoint.

This invariant is the durable guard: the v0.3.9 direct/HTTP/MCP render-check
compares SVG *bytes* (identical across surfaces), so it structurally cannot
catch a header/body mismatch. This test parses the actual served
``Content-Security-Policy`` header and asserts that whenever the SVG body embeds
a ``data:font/``, the effective ``font-src`` permits ``data:``. If any future
change ships an embedded-font SVG behind a header that blocks it, this fails
BEFORE a browser ever sees it.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from hyperweave.serve.app import app

# Static (network-free) served routes spanning genomes + frame types that embed
# fonts. The strip is the original symptom; badge/marquee prove server-wide
# scope (the middleware wraps them all).
_FONT_EMBEDDING_ROUTES: list[str] = [
    "/v1/strip/TRANSFORMERS-V2/brutalist.static?value=STARS:2.9k,BUILD:passing",
    "/v1/badge/build/passing/brutalist.static",
    "/v1/badge/stars/2900/chrome.static",
    "/v1/marquee/HYPERWEAVE/chrome.static",
]


def _effective_font_src(csp: str) -> list[str]:
    """Return the source list the browser applies to fonts.

    An explicit ``font-src`` wins; otherwise fonts fall back to ``default-src``
    (CSP fetch-directive fallback). Returns the whitespace-split source tokens.
    """
    directives: dict[str, str] = {}
    for part in csp.split(";"):
        name, _, rest = part.strip().partition(" ")
        if name:
            directives[name.lower()] = rest.strip()
    src = directives.get("font-src", directives.get("default-src", ""))
    return src.split()


def _font_src_permits_data(csp: str) -> bool:
    """True if the effective font-src allows ``data:`` URIs (or any source)."""
    tokens = _effective_font_src(csp)
    return "data:" in tokens or "*" in tokens


@pytest.fixture()
async def client() -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.parametrize("url", _FONT_EMBEDDING_ROUTES)
async def test_served_csp_permits_every_embedded_font(client: AsyncClient, url: str) -> None:
    """Server-wide invariant: any served SVG embedding a data:font/ must have a
    CSP whose effective font-src permits data:. Asserts the header against the
    body — the check the byte-comparison render gate cannot make."""
    resp = await client.get(url)
    assert resp.status_code == 200, f"{url} returned {resp.status_code}"
    assert resp.headers.get("content-type", "").startswith("image/svg+xml"), url
    csp = resp.headers.get("content-security-policy", "")
    assert csp, f"{url}: SVG response is missing a Content-Security-Policy header"
    if "data:font/" in resp.text:
        assert _font_src_permits_data(csp), (
            f"{url}: SVG embeds a data:font/ face but the served CSP font-src forbids it "
            f"(fonts would fall back to a system face in-browser). CSP={csp!r}"
        )


async def test_brutalist_strip_embeds_font_and_csp_allows_it(client: AsyncClient) -> None:
    """Focused regression on the original symptom: the brutalist strip both
    embeds a data:font/woff2 AND is served with a font-src that permits it, so
    the condensed identity font loads on the direct route and the seam holds."""
    resp = await client.get("/v1/strip/TRANSFORMERS-V2/brutalist.static?value=STARS:2.9k,BUILD:passing")
    assert resp.status_code == 200
    assert "data:font/woff2" in resp.text, "brutalist strip should embed its woff2 faces"
    assert _font_src_permits_data(resp.headers.get("content-security-policy", "")), (
        "served CSP must permit the strip's own embedded font"
    )


async def test_csp_still_locks_down_non_font_sources(client: AsyncClient) -> None:
    """The font-src widening must NOT loosen the rest of the policy: default-src
    stays 'none' and only inline style is permitted (camo-hardening intact)."""
    resp = await client.get("/v1/badge/build/passing/brutalist.static")
    csp = resp.headers.get("content-security-policy", "")
    assert "default-src 'none'" in csp
    assert "style-src 'unsafe-inline'" in csp
    # font-src is scoped to data: only — not a blanket allow.
    assert _effective_font_src(csp) == ["data:"]
