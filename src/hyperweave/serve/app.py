"""FastAPI application -- HTTP interface to the compositor."""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import FastAPI, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from hyperweave import __version__
from hyperweave.compose.artifact_store import get_artifact
from hyperweave.compose.engine import compose
from hyperweave.compose.resolver import GenomeNotFoundError
from hyperweave.compose.surface import SpecEnvelope, validate_surface
from hyperweave.config.loader import get_loader
from hyperweave.config.settings import get_settings
from hyperweave.connectors.base import close_client, get_client
from hyperweave.connectors.github import fetch_stargazer_history, fetch_user_stats
from hyperweave.core.enums import FrameType
from hyperweave.core.models import ComposeSpec
from hyperweave.render.fonts import load_font_face_css
from hyperweave.render.templates import render_template
from hyperweave.serve.data_tokens import (
    format_for_badge,
    format_for_value,
    parse_data_tokens,
    resolve_data_tokens,
)

# Shared by lifespan warmup and /health endpoint. Single source of truth so
# both paths exercise an identical compose pipeline. Construction is safe at
# module-import time — ComposeSpec validators (core/models.py:82-97) only read
# from the static _GENOME_PROFILE_MAP and ProfileId enum; no I/O, no registry.
_PROBE_SPEC = ComposeSpec(
    type="badge",
    genome_id="brutalist",
    title="HEALTH",
    value="ok",
    state="active",
    motion="static",
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Pre-warm the compose pipeline so first traffic doesn't pay cold-import cost.

    compose() has its own internal lazy imports (resolver, assembler, context,
    lanes, templates -- see compose/engine.py:26-45). The single warmup call
    here is what actually triggers them to load. Module-scope imports in this
    file only handle the OUTER lazy imports.

    The httpx singleton is also force-initialized so the HTTP/2 connection pool
    is established eagerly -- the marquee fan-out (5 tokens / 3 providers) then
    multiplexes over already-open connections instead of paying 5 fresh TLS
    handshakes on first traffic.
    """
    get_client()
    compose(_PROBE_SPEC)
    yield
    await close_client()


app = FastAPI(
    title="HyperWeave",
    description="Compositor API for self-contained SVG artifacts.",
    version=__version__,
    lifespan=lifespan,
)


# -- Readiness probe ---------------------------------------------------------


@app.get("/health", response_model=None)
async def health() -> Response:
    """Readiness probe -- exercises the compose pipeline.

    Returns 200 if the compositor can produce an artifact. Returns 503 (NOT
    500) if compose fails for any reason (lifespan warmup not complete,
    template missing, font asset corrupt, etc). 503 is the semantically
    correct status for "process is up but cannot serve yet" -- any
    sophisticated load balancer interprets it as retriable rather than as a
    hard failure.

    Combined with `min_machines_running=1` + `auto_stop="suspend"` in
    fly.toml, this means a freshly-woken machine is held out of rotation
    until the warmup compose succeeds, eliminating the 18:47-style spike
    where Camo fans out to a not-yet-warm origin and gets seconds-long p99.
    """
    try:
        compose(_PROBE_SPEC)
    except Exception:
        return JSONResponse({"status": "degraded"}, status_code=503)
    return JSONResponse({"status": "ok"})


# -- Camo-hardening middleware ------------------------------------------------
# Applies CORS and Vary headers to all SVG responses so artifacts behave
# correctly behind GitHub Camo and other CDN/proxy layers.


@app.middleware("http")
async def svg_camo_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("image/svg+xml"):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Vary"] = "Accept"
        response.headers["X-Content-Type-Options"] = "nosniff"
        # font-src data: permits the woff2 faces embedded directly in the SVG
        # (@font-face src=url(data:font/woff2;...)). Without it, font-src inherits
        # default-src 'none' and the browser refuses the SVG's OWN embedded fonts
        # on the direct-served route — the display font silently falls back to a
        # wider system face, overflowing tight slots (the brutalist strip identity
        # bleed). A CSP must permit the fonts its own response embeds; this is
        # server-wide (the middleware wraps every SVG), so one directive fixes
        # every genome/frame. Invariant: tests/test_serve_font_csp.py.
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; font-src data:"
    return response


# -- Request observability middleware ---------------------------------------
# Emits one greppable `HW_REQUEST` line per non-probe request so we can
# track which GitHub repos embed our SVGs via Camo (referer header) and how
# often they're viewed. Probe endpoints stay silent to keep Fly health-check
# noise out of the access log. Bodies are never logged.

_ACCESS_LOG = logging.getLogger("hyperweave.serve.access")
_SILENT_PATHS = frozenset({"/health", "/metrics"})


# Uvicorn's default log_config never wires the root logger; our access logger needs an explicit handler to reach stdout.
def _configure_access_logging() -> None:
    """Wire HW_REQUEST to stdout and silence the uvicorn.access duplicate."""
    if not _ACCESS_LOG.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(message)s"))
        _ACCESS_LOG.addHandler(handler)
        _ACCESS_LOG.setLevel(logging.INFO)
    uvicorn_access = logging.getLogger("uvicorn.access")
    uvicorn_access.handlers = []
    uvicorn_access.propagate = False
    uvicorn_access.disabled = True


_configure_access_logging()


def _scrub(value: str | None) -> str:
    """Collapse whitespace in header values so each key=value stays a single grep token."""
    if not value:
        return "-"
    return value.replace(" ", "_").replace("\t", "_")


@app.middleware("http")
async def access_log(request: Request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    if request.url.path in _SILENT_PATHS:
        return response
    path = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    ip = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "-")
    _ACCESS_LOG.info(
        "HW_REQUEST method=%s path=%s ua=%s ref=%s ip=%s status=%d",
        request.method,
        _scrub(path),
        _scrub(request.headers.get("user-agent")),
        _scrub(request.headers.get("referer")),
        _scrub(ip),
        response.status_code,
    )
    return response


# Request / Response models


class ComposeRequest(BaseModel):
    """Full compose request (POST /v1/compose)."""

    type: str = "badge"
    genome: str = "brutalist"
    title: str = ""
    value: str = ""
    state: str = "active"
    motion: str = "static"
    glyph: str = ""
    glyph_mode: str = "auto"
    regime: str = "normal"
    size: str = "default"
    shape: str = ""
    variant: str = ""
    metadata_tier: int = 3
    divider_variant: str = "zeropoint"
    direction: str = "ltr"
    speeds: list[float] | None = None
    matrix: dict[str, Any] | None = None
    """Matrix frame table IR (type=matrix) — validated into MatrixSpec."""

    diagram: dict[str, Any] | None = None
    """Diagram frame topology IR (type=diagram) — validated into DiagramSpec."""
    glyph_tint: str = ""
    """Glyph fill selection: ink | brand | full (empty defers to the
    genome default). Per-slot IR declarations outrank it."""
    performance: str = ""
    """Surface performance tier: '' (paint-ok) | 'composite-only' (diagram
    motion ladders beam->particle, flow->dash; recorded in the payload)."""
    chrome: str = "card"
    """Presentation chrome (diagram): card (default) | bare — transparent
    paper, no masthead/footer; presentational, outside the envelope digest."""
    respond: str = "svg"
    """Response shape: ``svg`` (raw image bytes, default) or ``json``
    (``{svg, markdown, width, height}`` — the markdown shadow alongside)."""


class SpecEnvelopeBody(BaseModel):
    """The canonical spec-envelope POST body (unified surface)."""

    type: str
    genome: str = "primer"
    variant: str = ""
    spec: dict[str, Any] = {}
    data: str = ""
    target: str = "web"
    emit: list[str] = ["svg"]


# Composition endpoints


@app.get(
    "/v1/badge/{title}/{value}/{genome_motion}",
    response_class=Response,
)
async def compose_badge_url(
    request: Request,
    title: str,
    value: str,
    genome_motion: str,
    t: Annotated[str, Query(description="Title override (use when title contains slashes)")] = "",
    glyph: Annotated[str, Query()] = "",
    glyph_mode: Annotated[str, Query()] = "auto",
    state: Annotated[str, Query()] = "active",
    regime: Annotated[str, Query()] = "normal",
    size: Annotated[str, Query()] = "default",
    variant: Annotated[str, Query(description="Variant slug (whitelist in genome JSON)")] = "",
    pair: Annotated[
        str,
        Query(
            description=(
                "Cellular paradigm pairing modifier (automata only). "
                "Composes any solo tone with any other solo tone — e.g. "
                "?variant=teal&pair=violet. Bifamily frames (strip, divider) "
                "consume the pair; other frames silently ignore it."
            ),
        ),
    ] = "",
    state_glyph_shape: Annotated[
        str,
        Query(description="Badge state-indicator shape override: square | circle | diamond."),
    ] = "",
) -> Response:
    """Static badge: /v1/badge/{title}/{value}/{genome}.{motion}.

    Three path segments. Use the 2-segment route below
    (/v1/badge/{title}/{genome}.{motion}?data=...) for data-driven badges.
    """
    genome, motion = _parse_genome_motion(genome_motion)

    spec = ComposeSpec(
        type="badge",
        genome_id=genome,
        title=t or title,
        value=value,
        state=state,
        motion=motion,
        glyph=glyph,
        glyph_mode=glyph_mode,
        regime=regime,
        size=size,
        variant=variant,
        pair=pair,
        state_glyph_shape=state_glyph_shape,
    )
    return _compose_and_respond(spec, request)


@app.get(
    "/v1/badge/{title}/{genome_motion}",
    response_class=Response,
)
async def compose_badge_data_url(
    request: Request,
    title: str,
    genome_motion: str,
    data: Annotated[
        str,
        Query(
            description=(
                "Required. Data tokens, comma-separated. Forms: text:STRING | "
                "kv:KEY=VALUE | gh:owner/repo.metric | pypi:pkg.metric | npm | hf | "
                "arxiv | docker | crates | scorecard:owner/repo | dora:owner/repo. "
                "Embedded commas in text/kv payloads escape as \\,."
            )
        ),
    ] = "",
    t: Annotated[str, Query(description="Title override (use when title contains slashes)")] = "",
    glyph: Annotated[str, Query()] = "",
    glyph_mode: Annotated[str, Query()] = "auto",
    state: Annotated[str, Query()] = "active",
    regime: Annotated[str, Query()] = "normal",
    size: Annotated[str, Query()] = "default",
    variant: Annotated[str, Query(description="Variant slug (whitelist in genome JSON)")] = "",
    pair: Annotated[
        str,
        Query(
            description=(
                "Cellular paradigm pairing modifier (automata only). "
                "Composes any solo tone with any other solo tone — e.g. "
                "?variant=teal&pair=violet. Bifamily frames (strip, divider) "
                "consume the pair; other frames silently ignore it."
            ),
        ),
    ] = "",
    state_glyph_shape: Annotated[
        str,
        Query(description="Badge state-indicator shape override: square | circle | diamond."),
    ] = "",
) -> Response:
    """Data-driven badge: /v1/badge/{title}/{genome}.{motion}?data=...

    Requires ``?data=``. Returns 400 (as a SMPTE error SVG, HTTP 200 to
    survive Camo) when ``?data=`` is missing or malformed. The token
    grammar is shared across HTTP / CLI / MCP — see
    :mod:`hyperweave.serve.data_tokens`.
    """
    genome, motion = _parse_genome_motion(genome_motion)

    if not data:
        return Response(
            content=_error_badge("?data= required on this route", status_code=400),
            media_type="image/svg+xml",
            status_code=200,
            headers=_error_response_headers(400),
        )

    # Badge has a single value slot — title is in the path, value is the
    # rendered string. format_for_badge extracts just the resolved value
    # (no LABEL: prefix), unlike strip which uses format_for_value to
    # produce "K1:V1,K2:V2" pairs for its multi-cell layout.
    try:
        tokens = parse_data_tokens(data)
        resolved, ttl = await resolve_data_tokens(tokens)
    except ValueError as exc:
        return Response(
            content=_error_badge(f"data parse: {exc}", status_code=400),
            media_type="image/svg+xml",
            status_code=200,
            headers=_error_response_headers(400),
        )

    final_value = format_for_badge(resolved)

    spec = ComposeSpec(
        type="badge",
        genome_id=genome,
        title=t or title,
        value=final_value,
        state=state,
        motion=motion,
        glyph=glyph,
        glyph_mode=glyph_mode,
        regime=regime,
        size=size,
        variant=variant,
        pair=pair,
        state_glyph_shape=state_glyph_shape,
    )
    return _compose_and_respond_with_ttl(spec, request, ttl)


@app.get(
    "/v1/strip/{title}/{genome_motion}",
    response_class=Response,
)
async def compose_strip_url(
    request: Request,
    title: str,
    genome_motion: str,
    t: Annotated[str, Query(description="Title override (use when title contains slashes)")] = "",
    value: Annotated[str, Query()] = "",
    data: Annotated[
        str,
        Query(
            description=(
                "Data tokens, comma-separated. Forms: text:STRING | kv:KEY=VALUE | "
                "gh:owner/repo.metric | pypi:pkg.metric | etc. Embedded commas in "
                "text/kv payloads escape as \\,."
            )
        ),
    ] = "",
    glyph: Annotated[str, Query()] = "",
    glyph_mode: Annotated[str, Query()] = "auto",
    state: Annotated[str, Query()] = "active",
    size: Annotated[str, Query()] = "default",
    regime: Annotated[str, Query()] = "normal",
    variant: Annotated[str, Query(description="Variant slug (whitelist in genome JSON)")] = "",
    pair: Annotated[
        str,
        Query(
            description=(
                "Cellular paradigm pairing modifier (automata only). "
                "Composes any solo tone with any other solo tone — e.g. "
                "?variant=teal&pair=violet. Bifamily frames (strip, divider) "
                "consume the pair; other frames silently ignore it."
            ),
        ),
    ] = "",
    subtitle: Annotated[
        str,
        Query(description="Strip subtitle (e.g. 'eli64s/readme-ai'). Cellular paradigm renders under identity."),
    ] = "",
) -> Response:
    """Compose a strip: /v1/strip/{title}/{genome}.{motion}?value=&data=&subtitle=."""
    genome, motion = _parse_genome_motion(genome_motion)

    ttl = 300
    final_value = value

    # Data tokens: ?data=gh:owner/repo.stars,pypi:pkg.version
    if data:
        try:
            final_value, ttl = await _resolve_data_param(data, fallback=value)
        except ValueError as exc:
            return Response(
                content=_error_badge(f"data parse: {exc}", status_code=400),
                media_type="image/svg+xml",
                status_code=200,
                headers=_error_response_headers(400),
            )

    # Subtitle wires through connector_data.repo_slug — the same field
    # resolve_strip reads when generate_proofset.py passes connector_data
    # explicitly. Empty subtitle leaves connector_data=None so paradigms
    # that don't opt into subtitles (brutalist, chrome) stay unaffected.
    connector_data: dict[str, Any] | None = {"repo_slug": subtitle} if subtitle else None

    spec = ComposeSpec(
        type="strip",
        genome_id=genome,
        title=t or title,
        value=final_value,
        state=state,
        motion=motion,
        glyph=glyph,
        glyph_mode=glyph_mode,
        size=size,
        regime=regime,
        variant=variant,
        pair=pair,
        connector_data=connector_data,
    )

    if data:
        return _compose_and_respond_with_ttl(spec, request, ttl)
    return _compose_and_respond(spec, request)


@app.get(
    "/v1/icon/{glyph}/{genome_motion}",
    response_class=Response,
)
async def compose_icon_url(
    request: Request,
    glyph: str,
    genome_motion: str,
    glyph_mode: Annotated[str, Query()] = "auto",
    shape: Annotated[str, Query()] = "",
    size: Annotated[str, Query()] = "default",
    state: Annotated[str, Query()] = "active",
    regime: Annotated[str, Query()] = "normal",
    variant: Annotated[str, Query(description="Variant slug (whitelist in genome JSON)")] = "",
    pair: Annotated[
        str,
        Query(
            description=(
                "Cellular paradigm pairing modifier (automata only). "
                "Composes any solo tone with any other solo tone — e.g. "
                "?variant=teal&pair=violet. Bifamily frames (strip, divider) "
                "consume the pair; other frames silently ignore it."
            ),
        ),
    ] = "",
) -> Response:
    """Compose an icon: /v1/icon/{glyph}/{genome}.{motion}?shape=circle"""
    genome, motion = _parse_genome_motion(genome_motion)

    spec = ComposeSpec(
        type="icon",
        genome_id=genome,
        title=glyph,
        glyph=glyph,
        glyph_mode=glyph_mode,
        motion=motion,
        shape=shape,
        size=size,
        state=state,
        regime=regime,
        variant=variant,
        pair=pair,
    )
    return _compose_and_respond(spec, request)


# v0.2.19: editorial-only divider slugs no longer route through /v1/divider/.
# They moved to /a/inneraura/dividers/<slug> (genome-agnostic editorial assets).
# Per-genome dividers (dissolve, band, seam) continue here — validated against
# genome.dividers at resolve-time.
_EDITORIAL_DIVIDER_SLUGS: frozenset[str] = frozenset({"block", "current", "takeoff", "void", "zeropoint"})


@app.get(
    "/v1/divider/{divider_variant}/{genome_motion}",
    response_class=Response,
)
async def compose_divider_url(
    request: Request,
    divider_variant: str,
    genome_motion: str,
    variant: Annotated[str, Query(description="Variant slug (whitelist in genome JSON)")] = "",
    pair: Annotated[
        str,
        Query(
            description=(
                "Cellular paradigm pairing modifier (automata only). "
                "Composes any solo tone with any other solo tone — e.g. "
                "?variant=teal&pair=violet. Bifamily frames (strip, divider) "
                "consume the pair; other frames silently ignore it."
            ),
        ),
    ] = "",
) -> Response:
    """Compose a genome-themed divider: /v1/divider/{divider_variant}/{genome}.{motion}.

    The 5 editorial generics (block, current, takeoff, void, zeropoint) live at
    /a/inneraura/dividers/<slug> — they don't theme to genomes. This route only
    serves dividers declared in the genome's `dividers` whitelist.
    """
    if divider_variant in _EDITORIAL_DIVIDER_SLUGS:
        return Response(
            content=_error_badge(
                f"Divider '{divider_variant}' is editorial — see /a/inneraura/dividers/{divider_variant}",
                status_code=404,
            ),
            media_type="image/svg+xml",
            status_code=200,
            headers={
                "X-HW-Error-Code": "404",
                "X-HW-Specimen-Moved": f"/a/inneraura/dividers/{divider_variant}",
            },
        )
    genome, motion = _parse_genome_motion(genome_motion)

    spec = ComposeSpec(
        type="divider",
        genome_id=genome,
        motion=motion,
        divider_variant=divider_variant,
        variant=variant,
        pair=pair,
    )
    return _compose_and_respond(spec, request)


@app.get(
    "/v1/marquee/{title}/{genome_motion}",
    response_class=Response,
)
async def compose_marquee_url(
    request: Request,
    title: str,
    genome_motion: str,
    t: Annotated[str, Query(description="Title override (use when title contains slashes)")] = "",
    data: Annotated[
        str,
        Query(
            description=(
                "Data tokens, comma-separated. Forms: text:STRING | kv:KEY=VALUE | "
                "gh:owner/repo.metric | pypi | npm | hf | arxiv | docker | crates | "
                "scorecard | dora | etc. When set, the title param is ignored as a data "
                "source — tokens drive the scroll. Embedded commas in text/kv payloads "
                "escape as \\,."
            )
        ),
    ] = "",
    direction: Annotated[str, Query(description="Scroll direction: ltr or rtl")] = "ltr",
    speeds: Annotated[str, Query(description="Scroll speed multiplier (single float)")] = "",
    state: Annotated[str, Query()] = "active",
    regime: Annotated[str, Query()] = "normal",
    variant: Annotated[str, Query(description="Variant slug (whitelist in genome JSON)")] = "",
    pair: Annotated[
        str,
        Query(
            description=(
                "Cellular paradigm pairing modifier (automata only). "
                "Composes any solo tone with any other solo tone — e.g. "
                "?variant=teal&pair=violet. Bifamily frames (strip, divider) "
                "consume the pair; other frames silently ignore it."
            ),
        ),
    ] = "",
) -> Response:
    """Marquee-horizontal: /v1/marquee/{title}/{genome}.{motion}.

    Two input modes (mutually exclusive priority — ``data`` wins when both
    are supplied):

    - **Raw text mode:** ``title`` is split on ``|`` (or ``·``) into bullets.
    - **Data-token mode:** ``?data=`` parses the unified token grammar and
      drives the scroll with mixed text + live values.
    """
    genome, motion = _parse_genome_motion(genome_motion)

    parsed_speeds: list[float] | None = None
    if speeds:
        try:
            parsed_speeds = [float(s.strip()) for s in speeds.split(",") if s.strip()]
        except ValueError:
            parsed_speeds = None

    # ``data_tokens`` populates spec.data_tokens (consumed by _resolve_horizontal).
    data_tokens_resolved: list[Any] | None = None
    ttl = 300
    if data:
        try:
            tokens = parse_data_tokens(data)
            data_tokens_resolved_seq, ttl = await resolve_data_tokens(tokens)
            data_tokens_resolved = list(data_tokens_resolved_seq)
        except ValueError as exc:
            return Response(
                content=_error_badge(f"data parse: {exc}", status_code=400),
                media_type="image/svg+xml",
                status_code=200,
                headers=_error_response_headers(400),
            )

    spec = ComposeSpec(
        type="marquee",
        genome_id=genome,
        title=t or title,
        motion=motion,
        marquee_direction=direction,
        marquee_speeds=parsed_speeds,
        state=state,
        regime=regime,
        variant=variant,
        pair=pair,
        data_tokens=data_tokens_resolved,
    )

    if data:
        return _compose_and_respond_with_ttl(spec, request, ttl)
    return _compose_and_respond(spec, request)


@app.post("/v1/compose", response_class=Response)
async def compose_post(request: Request, req: ComposeRequest) -> Response:
    """Compose any artifact via POST with full ComposeSpec."""
    spec = ComposeSpec(
        type=req.type,
        genome_id=req.genome,
        title=req.title,
        value=req.value,
        state=req.state,
        motion=req.motion,
        glyph=req.glyph,
        glyph_mode=req.glyph_mode,
        regime=req.regime,
        size=req.size,
        shape=req.shape,
        variant=req.variant,
        metadata_tier=req.metadata_tier,
        divider_variant=req.divider_variant,
        marquee_direction=req.direction,
        marquee_speeds=req.speeds,
        matrix=req.matrix,
        diagram=req.diagram,
        glyph_tint=req.glyph_tint,
        performance=req.performance,
        chrome=req.chrome,
    )
    if req.respond == "json":
        # Both projections in one response: the SVG plus its markdown
        # shadow (POST keeps JSON semantics; GET stays pure image for Camo).
        result = compose(spec)
        return JSONResponse(
            {
                "svg": result.svg,
                "markdown": result.markdown,
                "width": result.width,
                "height": result.height,
            }
        )
    return _compose_and_respond(spec, request)


@app.post("/v1/validate", response_model=None)
async def validate_post(body: SpecEnvelopeBody) -> JSONResponse:
    """Validate a spec envelope without rendering. Returns a {valid, ...} report."""
    report = validate_surface(
        SpecEnvelope(
            type=body.type,
            genome=body.genome,
            variant=body.variant,
            spec=body.spec,
            data=body.data,
            target=body.target,
            emit=tuple(body.emit),
        )
    )
    return JSONResponse(report, status_code=200 if report.get("valid") else 400)


@app.get("/v1/a/{digest}", response_class=Response)
async def serve_artifact(digest: str) -> Response:
    """Content-addressed handle: GET /v1/a/{digest} serves the stored SVG.

    The compact handle the round-trip loop embeds. Served from the in-process
    LRU, falling back to the durable disk tier when ``HW_ARTIFACT_CACHE_DIR`` is
    set — so a cold handle (per-process eviction or a restart) still resolves
    cross-session from disk. Only when neither tier holds the id does it 404, and
    the caller falls back to the self-describing spec URL.
    """
    svg = get_artifact(digest)
    if svg is None:
        return JSONResponse(
            {
                "error": {
                    "code": "ENVELOPE_CORRUPT",
                    "message": "artifact not in cache",
                    "fix": "recompose; the content cache is per-process and may have evicted this id",
                    "detail": {},
                }
            },
            status_code=404,
        )
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


# ── Verb routes (read/write algebra over the seed) ───────────────────────────


class _ExtractBody(BaseModel):
    source: str  # SVG string or /v1/a/{digest} url
    respond: str = "envelope"


class _VerifyBody(BaseModel):
    svg: str


class _TransformBody(BaseModel):
    source: str
    mutations: list[dict[str, Any]]


class _DiffBody(BaseModel):
    a: str
    b: str


class _QueryBody(BaseModel):
    svg: str
    question: str


def _verb_response(fn: Any, *args: Any, **kwargs: Any) -> JSONResponse:
    """Run a verb, return its result dict or the structured error envelope + 4xx."""
    from hyperweave.core.errors import HwError

    try:
        return JSONResponse(fn(*args, **kwargs).to_dict())
    except HwError as exc:
        return JSONResponse(exc.envelope(), status_code=exc.http_status)


@app.post("/v1/extract", response_model=None)
async def extract_post(body: _ExtractBody) -> JSONResponse:
    """Extract the seed at envelope | payload | markdown depth."""
    from hyperweave.verbs import extract

    return _verb_response(extract, body.source, respond=body.respond)


@app.post("/v1/verify", response_model=None)
async def verify_post(body: _VerifyBody) -> JSONResponse:
    """Recompute the hash; prove id == sha256(payload)."""
    from hyperweave.verbs import verify

    return _verb_response(verify, body.svg)


@app.post("/v1/transform", response_model=None)
async def transform_post(body: _TransformBody) -> JSONResponse:
    """Mutate an artifact via structural JSON patch → new artifact ({envelope, url})."""
    from hyperweave.verbs import transform

    return _verb_response(transform, body.source, body.mutations, base_url=get_settings().public_base_url)


@app.post("/v1/diff", response_model=None)
async def diff_post(body: _DiffBody) -> JSONResponse:
    """Payload-bound structured delta between two artifacts."""
    from hyperweave.verbs import diff

    return _verb_response(diff, body.a, body.b)


@app.post("/v1/query", response_model=None)
async def query_post(body: _QueryBody) -> JSONResponse:
    """Answer a question about an artifact from its compact envelope."""
    from hyperweave.verbs import query

    return _verb_response(query, body.svg, body.question)


@app.get("/llms.txt", response_class=Response)
async def llms_txt() -> Response:
    """The agent contract — a cold agent reads this to discover the protocol."""
    from hyperweave.core.contract import LLMS_TXT

    return Response(
        content=LLMS_TXT,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/skill", response_class=Response)
async def skill_md() -> Response:
    """The shippable agent SKILL file (the verb workflow)."""
    path = get_settings().data_dir / "skills" / "hyperweave-verbs" / "SKILL.md"
    if not path.exists():
        return Response(content="SKILL file not packaged", media_type="text/plain", status_code=404)
    return Response(
        content=path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ── Matrix routes ────────────────────────────────────────────────────────────

_MATRIX_SPEC_PARAM_MAX_BYTES = 8192


@app.get(
    "/v1/matrix/{preset}/{genome_motion}",
    response_class=Response,
)
async def compose_matrix_url(
    request: Request,
    preset: str,
    genome_motion: str,
    variant: Annotated[str, Query(description="Variant slug (whitelist in genome JSON)")] = "",
    spec: Annotated[
        str,
        Query(
            description=(
                "base64url-encoded MatrixSpec JSON (preset must be 'custom'). "
                "Decoded size cap: 8 KB. Gives arbitrary user tables a "
                "Camo-embeddable GET URL with a per-spec ETag."
            ),
        ),
    ] = "",
    glyph_tint: Annotated[
        str,
        Query(
            description=(
                "Glyph fill selection: ink | brand | full. Per-slot IR "
                "declarations outrank it; degrades full -> gradient -> "
                "brand -> ink."
            ),
            pattern="^(|ink|brand|full)$",
        ),
    ] = "",
) -> Response:
    """Compose a matrix: /v1/matrix/{preset}/{genome}.{motion}.

    ``preset`` names a server-known matrix (``connectors`` — the generated
    connector registry, a data file away from new presets) or ``custom``
    with an inline ``?spec=`` base64url MatrixSpec. Long-cached: matrix
    content is request-static, so the pure-compose cache tier applies.
    """
    genome, motion = _parse_genome_motion(genome_motion)

    matrix_payload: dict[str, Any] | None = None
    connector_data: dict[str, Any] | None = None
    if preset == "custom":
        decode_error = ""
        if not spec:
            decode_error = "preset 'custom' requires ?spec=<base64url MatrixSpec JSON>"
        else:
            import base64
            import binascii
            import json as _json

            try:
                padded = spec + "=" * (-len(spec) % 4)
                raw = base64.urlsafe_b64decode(padded.encode("ascii"))
                if len(raw) > _MATRIX_SPEC_PARAM_MAX_BYTES:
                    decode_error = f"?spec= exceeds the {_MATRIX_SPEC_PARAM_MAX_BYTES} byte cap after decoding"
                else:
                    matrix_payload = _json.loads(raw)
            except (ValueError, binascii.Error) as exc:
                decode_error = f"?spec= is not base64url-encoded JSON: {exc}"
        if decode_error:
            return Response(
                content=_error_badge(decode_error, status_code=400),
                media_type="image/svg+xml",
                status_code=200,
                headers=_error_response_headers(400),
            )
    else:
        from hyperweave.compose.matrix.input import resolve_matrix_preset
        from hyperweave.core.matrix import MatrixInputError

        try:
            connector_data = resolve_matrix_preset(preset)
        except MatrixInputError as exc:
            return Response(
                content=_error_badge(str(exc), status_code=404),
                media_type="image/svg+xml",
                status_code=200,
                headers=_error_response_headers(404),
            )

    compose_spec = ComposeSpec(
        type="matrix",
        genome_id=genome,
        motion=motion,
        variant=variant,
        matrix=matrix_payload,
        connector_data=connector_data,
        glyph_tint=glyph_tint,
    )
    return _compose_and_respond(compose_spec, request)


# ── Diagram routes ───────────────────────────────────────────────────────────


@app.get(
    "/v1/diagram/{preset}/{genome_motion}",
    response_class=Response,
)
async def compose_diagram_url(
    request: Request,
    preset: str,
    genome_motion: str,
    variant: Annotated[str, Query(description="Variant slug (whitelist in genome JSON)")] = "",
    spec: Annotated[
        str,
        Query(
            description=(
                "base64url-encoded DiagramSpec JSON (preset must be 'custom'). "
                "Decoded size cap: 8 KB. Gives arbitrary topologies a "
                "Camo-embeddable GET URL with a per-spec ETag."
            ),
        ),
    ] = "",
    glyph_tint: Annotated[
        str,
        Query(
            description=(
                "Node-glyph fill selection: ink | brand | full. Per-slot IR "
                "declarations outrank it; degrades full -> gradient -> "
                "brand -> ink."
            ),
            pattern="^(|ink|brand|full)$",
        ),
    ] = "",
    edge_motion: Annotated[
        str,
        Query(
            description=(
                "Artifact-level edge motion override — the closed 2x2: "
                "dash | particle | beam | flow (genome allowlist enforced; "
                "per-edge IR declarations outrank it)."
            ),
            pattern="^(|dash|particle|beam|flow)$",
        ),
    ] = "",
    performance: Annotated[
        str,
        Query(
            description=(
                "Surface performance tier. 'composite-only' applies the "
                "fallback ladder (beam->particle, flow->dash); the payload's "
                "rendered block records fallback_applied."
            ),
            pattern="^(|composite-only)$",
        ),
    ] = "",
    chrome: Annotated[
        str,
        Query(
            description=(
                "Presentation chrome: card (substrate + masthead + footer, "
                "default) | bare (transparent paper, no masthead/footer; the "
                "title ships in hw:title/aria/markdown/payload only). "
                "Presentational — excluded from the envelope digest. Bare "
                "callers own paper matching: the genome's inks assume its "
                "own surface family."
            ),
            pattern="^(card|bare)$",
        ),
    ] = "card",
) -> Response:
    """Compose a diagram: /v1/diagram/{preset}/{genome}.{motion}.

    ``preset`` names a server-known diagram (the specimen recreations in
    ``data/presets/diagram.yaml`` — a data file away from new presets) or
    ``custom`` with an inline ``?spec=`` base64url DiagramSpec. Long-cached:
    diagram content is request-static, so the pure-compose cache tier
    applies.
    """
    genome, motion = _parse_genome_motion(genome_motion)

    diagram_payload: dict[str, Any] | None = None
    if preset == "custom":
        decode_error = ""
        if not spec:
            decode_error = "preset 'custom' requires ?spec=<base64url DiagramSpec JSON>"
        else:
            import base64
            import binascii
            import json as _json

            try:
                padded = spec + "=" * (-len(spec) % 4)
                raw = base64.urlsafe_b64decode(padded.encode("ascii"))
                if len(raw) > _MATRIX_SPEC_PARAM_MAX_BYTES:
                    decode_error = f"?spec= exceeds the {_MATRIX_SPEC_PARAM_MAX_BYTES} byte cap after decoding"
                else:
                    diagram_payload = _json.loads(raw)
            except (ValueError, binascii.Error) as exc:
                decode_error = f"?spec= is not base64url-encoded JSON: {exc}"
        if decode_error:
            return Response(
                content=_error_badge(decode_error, status_code=400),
                media_type="image/svg+xml",
                status_code=200,
                headers=_error_response_headers(400),
            )
    else:
        from hyperweave.compose.diagram.input import resolve_diagram_preset
        from hyperweave.core.diagram import DiagramInputError

        try:
            diagram_payload = resolve_diagram_preset(preset)
        except DiagramInputError as exc:
            return Response(
                content=_error_badge(str(exc), status_code=404),
                media_type="image/svg+xml",
                status_code=200,
                headers=_error_response_headers(404),
            )

    if edge_motion and isinstance(diagram_payload, dict):
        diagram_payload = {**diagram_payload, "edge_motion": edge_motion}

    compose_spec = ComposeSpec(
        type="diagram",
        genome_id=genome,
        motion=motion,
        variant=variant,
        diagram=diagram_payload,
        glyph_tint=glyph_tint,
        performance=performance,
        chrome=chrome,
    )
    return _compose_and_respond(compose_spec, request)


# ── Chart / Stats routes ─────────────────────────────────────────────────────


@app.get(
    "/v1/chart/stars/{owner}/{repo}/{genome_motion}",
    response_class=Response,
)
async def compose_chart_stars(
    request: Request,
    owner: str,
    repo: str,
    genome_motion: str,
    variant: Annotated[str, Query(description="Variant slug (whitelist in genome JSON)")] = "",
    pair: Annotated[
        str,
        Query(
            description=(
                "Cellular paradigm pairing modifier (automata only). "
                "Composes any solo tone with any other solo tone — e.g. "
                "?variant=teal&pair=violet. Bifamily frames (strip, divider) "
                "consume the pair; other frames silently ignore it."
            ),
        ),
    ] = "",
) -> Response:
    """Compose a star history chart: /v1/chart/stars/{owner}/{repo}/{genome}.{motion}.

    Fetches sampled stargazer history from GitHub (cached 1h) and delegates
    rendering to the chart frame. On fetch failure, renders a placeholder
    series with ``data-hw-status="stale"`` (graceful degradation).
    """
    genome, motion = _parse_genome_motion(genome_motion)

    connector_data: dict[str, Any] | None = None
    try:
        connector_data = await fetch_stargazer_history(owner, repo)
    except Exception:
        connector_data = None

    spec = ComposeSpec(
        type="chart",
        genome_id=genome,
        chart_owner=owner,
        chart_repo=repo,
        motion=motion,
        connector_data=connector_data,
        variant=variant,
        pair=pair,
    )
    return _compose_and_respond_with_ttl(spec, request, ttl=3600)


@app.get(
    "/v1/stats/{username}/{genome_motion}",
    response_class=Response,
)
async def compose_stats(
    request: Request,
    username: str,
    genome_motion: str,
    data: Annotated[
        str,
        Query(
            description=(
                "Optional data tokens appended to the stats card as provider metric slots. "
                "Forms: gh:owner/repo.metric | pypi:pkg.metric | hf:org/model.metric | etc."
            )
        ),
    ] = "",
    variant: Annotated[str, Query(description="Variant slug (whitelist in genome JSON)")] = "",
    pair: Annotated[
        str,
        Query(
            description=(
                "Cellular paradigm pairing modifier (automata only). "
                "Composes any solo tone with any other solo tone — e.g. "
                "?variant=teal&pair=violet. Bifamily frames (strip, divider) "
                "consume the pair; other frames silently ignore it."
            ),
        ),
    ] = "",
) -> Response:
    """Compose a GitHub stats card: /v1/stats/{username}/{genome}.{motion}.

    Fetches user profile + repos + commits + PRs + issues + contribution
    calendar in parallel (cached 1h) and renders through the stats frame.
    Graceful degradation: individual sub-fetch failures result in partial
    data with ``data-hw-status="stale"`` only when ALL sub-fetches fail.
    """
    genome, motion = _parse_genome_motion(genome_motion)

    connector_data: dict[str, Any] | None = None
    data_tokens_resolved: list[Any] | None = None
    ttl = 3600
    if data:
        try:
            tokens = parse_data_tokens(data)
            resolved, data_ttl = await resolve_data_tokens(tokens)
            data_tokens_resolved = list(resolved)
            ttl = min(ttl, data_ttl)
        except ValueError as exc:
            return Response(
                content=_error_badge(f"data parse: {exc}", status_code=400),
                media_type="image/svg+xml",
                status_code=200,
                headers=_error_response_headers(400),
            )

    try:
        connector_data = await fetch_user_stats(username)
    except Exception:
        connector_data = None

    spec = ComposeSpec(
        type="stats",
        genome_id=genome,
        stats_username=username,
        motion=motion,
        connector_data=connector_data,
        data_tokens=data_tokens_resolved,
        variant=variant,
        pair=pair,
    )
    return _compose_and_respond_with_ttl(spec, request, ttl=ttl)


# Discovery endpoints


_FRAME_URL_GRAMMAR: dict[str, dict[str, Any]] = {
    "badge (static)": {
        "pattern": "/v1/badge/{title}/{value}/{genome}.{motion}",
        "query_params": ["glyph", "glyph_mode", "state", "regime", "size", "variant", "pair"],
    },
    "badge (data-driven)": {
        "pattern": "/v1/badge/{title}/{genome}.{motion}?data=...",
        "query_params": ["data", "glyph", "glyph_mode", "state", "regime", "size", "variant", "pair"],
    },
    "strip": {
        "pattern": "/v1/strip/{title}/{genome}.{motion}",
        "query_params": [
            "value",
            "data",
            "glyph",
            "glyph_mode",
            "state",
            "size",
            "regime",
            "variant",
            "pair",
            "subtitle",
        ],
    },
    "icon": {
        "pattern": "/v1/icon/{glyph}/{genome}.{motion}",
        "query_params": ["glyph_mode", "shape", "state", "regime", "variant", "pair", "size"],
    },
    "divider": {
        "pattern": "/v1/divider/{variant}/{genome}.{motion}",
        "query_params": ["variant", "pair"],
    },
    "marquee": {
        "pattern": "/v1/marquee/{title}/{genome}.{motion}",
        "query_params": ["data", "direction", "speeds", "state", "regime", "variant", "pair"],
    },
    "chart-stars": {
        "pattern": "/v1/chart/stars/{owner}/{repo}/{genome}.{motion}",
        "query_params": ["variant", "pair"],
    },
    "stats": {
        "pattern": "/v1/stats/{username}/{genome}.{motion}",
        "query_params": ["data", "variant", "pair"],
    },
    "diagram": {
        "pattern": "/v1/diagram/{preset}/{genome}.{motion}",
        "query_params": ["variant", "spec", "glyph_tint", "edge_motion", "performance", "chrome"],
        "presets": "data/presets/diagram.yaml slugs, or 'custom' + ?spec=",
    },
    "matrix": {
        "pattern": "/v1/matrix/{preset}/{genome}.{motion}",
        "query_params": ["variant", "spec"],
    },
    "receipt": {"pattern": "POST /v1/compose", "query_params": []},
}


@app.get("/v1/frames")
async def list_frames() -> list[dict[str, Any]]:
    """List all frame types with URL grammar and query params."""
    from hyperweave.compose.diagram import registered_slugs

    frames: list[dict[str, Any]] = []
    for ft in FrameType:
        entry: dict[str, Any] = {
            "type": ft.value,
            **_FRAME_URL_GRAMMAR.get(ft.value, {"pattern": "POST /v1/compose", "query_params": []}),
        }
        if ft.value == "diagram":
            # The flattened requestable layout set (topology x orientation), so a
            # caller sees fanout-radial / tree-radial explicitly, not as prose.
            entry["layout_slugs"] = registered_slugs()
        frames.append(entry)
    return frames


@app.get("/v1/genomes")
async def list_genomes(response: Response) -> list[dict[str, Any]]:
    """List available genomes."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    loader = get_loader()
    return [
        {"id": gid, "name": g.get("name", gid), "category": g.get("category", "dark")}
        for gid, g in loader.genomes.items()
    ]


@app.get("/v1/genomes/{genome_id}", response_model=None)
async def get_genome(genome_id: str, response: Response) -> dict[str, Any] | JSONResponse:
    """Get a specific genome's full config."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    loader = get_loader()
    genome = loader.genomes.get(genome_id)
    if not genome:
        return JSONResponse({"error": f"Genome '{genome_id}' not found"}, status_code=404)
    return genome


@app.get("/v1/motions")
async def list_motions(response: Response) -> list[dict[str, Any]]:
    """List available motion primitives."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    loader = get_loader()
    return [
        {"id": mid, "name": m.get("name", mid), "cim_compliant": m.get("cim_compliant", True)}
        for mid, m in loader.motions.items()
    ]


@app.get("/v1/glyphs")
async def list_glyphs(response: Response) -> list[str]:
    """List available glyph IDs."""
    response.headers["Cache-Control"] = "public, max-age=3600"
    loader = get_loader()
    return sorted(loader.glyphs.keys()) if hasattr(loader, "glyphs") else []


# Artifact Store (/a/inneraura/) -- Editorial specimens


@app.get("/a/inneraura", response_model=None)
async def list_specimens() -> list[dict[str, str]]:
    """List all editorial specimens — categorized (v0.2.19+) + legacy flat slugs."""
    registry = _load_specimens_registry()
    out: list[dict[str, str]] = []
    for category, entries in sorted(_categorized_specimens(registry).items()):
        for slug in sorted(entries):
            out.append({"category": category, "slug": slug, "url": f"/a/inneraura/{category}/{slug}"})
    for slug in sorted(_flat_specimens(registry)):
        out.append({"category": "legacy", "slug": slug, "url": f"/a/inneraura/{slug}"})
    return out


@app.get("/a/inneraura/{slug}/meta.json", response_model=None)
async def serve_specimen_meta(slug: str) -> Response | JSONResponse:
    """Serve metadata-only for a legacy flat-slug editorial specimen.

    NOTE: declared before the catch-all `/a/inneraura/{category}/{slug}` so the
    literal `meta.json` segment matches before the two-greedy-segment pattern.
    """
    registry = _load_specimens_registry()
    rel_path = _flat_specimens(registry).get(slug)
    if not rel_path:
        return JSONResponse({"error": f"Specimen '{slug}' not found"}, status_code=404)

    import json as json_mod

    category = slug.split("-")[0] if "-" in slug else "unknown"
    meta = {
        "slug": slug,
        "category": category,
        "path": rel_path,
        "url": f"/a/inneraura/{slug}",
        "tier": 3,
        "type": "editorial-specimen",
    }
    return Response(
        content=json_mod.dumps(meta, indent=2),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/a/inneraura/{category}/{slug}", response_class=Response)
async def serve_categorized_specimen(category: str, slug: str) -> Response:
    """Serve an editorial specimen by (category, slug). v0.2.19+ shape.

    For category=='dividers', renders the divider template directly (no
    compositor pipeline, no genome). Other categories TBD.
    """
    registry = _load_specimens_registry()
    cat_entries = _categorized_specimens(registry).get(category)
    if not cat_entries:
        return Response(
            content=_error_badge(f"Category '{category}' not found", status_code=404),
            media_type="image/svg+xml",
            status_code=200,
            headers={"X-HW-Error-Code": "404"},
        )
    entry = cat_entries.get(slug)
    if not entry:
        return Response(
            content=_error_badge(f"Specimen '{category}/{slug}' not found", status_code=404),
            media_type="image/svg+xml",
            status_code=200,
            headers={"X-HW-Error-Code": "404"},
        )

    if category == "dividers":
        # Editorial dividers route through compose() with a default genome (brutalist).
        # The 5 editorial divider templates hardcode their own colors and ignore the
        # genome dict by design — so the choice of genome only affects the metadata
        # attributes (data-hw-genome etc.), not the rendered visual. The
        # X-HW-Artifact-Type header advertises the editorial-specimen status as the
        # source of truth for consumers parsing the response.
        spec = ComposeSpec(
            type="divider",
            genome_id="brutalist",
            motion="static",
            divider_variant=entry["divider_variant"],
        )
        result = compose(spec)
        ttl = get_settings().static_cache_ttl
        return Response(
            content=result.svg,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": f"public, max-age={ttl}, immutable",
                "X-HW-Artifact-Type": "editorial-specimen",
            },
        )

    return Response(
        content=_error_badge(f"Category '{category}' has no renderer yet", status_code=501),
        media_type="image/svg+xml",
        status_code=200,
        headers={"X-HW-Error-Code": "501"},
    )


@app.get("/a/inneraura/{slug}", response_class=Response)
async def serve_specimen(slug: str) -> Response:
    """Serve a legacy flat-slug editorial specimen SVG (specs/ filesystem)."""
    registry = _load_specimens_registry()
    rel_path = _flat_specimens(registry).get(slug)
    if not rel_path:
        return Response(
            content=_error_badge(f"Specimen '{slug}' not found", status_code=404),
            media_type="image/svg+xml",
            status_code=200,
            headers={"X-HW-Error-Code": "404"},
        )

    import pathlib

    specs_dir = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "specs"
    svg_path = specs_dir / rel_path
    if not svg_path.exists():
        return Response(
            content=_error_badge(f"File not found: {rel_path}", status_code=404),
            media_type="image/svg+xml",
            status_code=200,
            headers={"X-HW-Error-Code": "404"},
        )

    svg_content = svg_path.read_text(encoding="utf-8")
    ttl = get_settings().static_cache_ttl
    return Response(
        content=svg_content,
        media_type="image/svg+xml",
        headers={"Cache-Control": f"public, max-age={ttl}, immutable", "X-HW-Artifact-Type": "editorial-specimen"},
    )


# Genome Registry (/g/)


@app.get("/g/{genome_slug}", response_model=None)
async def genome_registry(genome_slug: str) -> Response | JSONResponse:
    """Serve genome DNA (JSON)."""
    import json

    loader = get_loader()
    genome = loader.genomes.get(genome_slug)
    if not genome:
        return JSONResponse({"error": f"Genome '{genome_slug}' not found"}, status_code=404)
    ttl = get_settings().genome_cache_ttl
    return Response(
        content=json.dumps(genome, indent=2),
        media_type="application/json",
        headers={"Cache-Control": f"public, max-age={ttl}, stale-while-revalidate=604800"},
    )


# Drop Events (/d/)


@app.get("/d/{drop_id}", response_model=None)
async def get_drop(drop_id: str) -> dict[str, Any]:
    """Serve drop event metadata. Links to genome and artifacts."""
    parts = drop_id.split("-", 1)
    sequence = parts[0] if parts else "000"
    name = parts[1] if len(parts) > 1 else drop_id

    return {
        "id": drop_id,
        "sequence": sequence,
        "name": name,
        "genome_url": f"/g/{name}",
        "specimens_url": f"/a/inneraura?prefix={name}",
    }


# Helpers


def _etag_matches(if_none_match: str, etag: str) -> bool:
    """Check whether *etag* appears in an If-None-Match header value.

    Handles wildcard ``*``, single values, and comma-separated lists
    per RFC 7232 S3.2.
    """
    if if_none_match.strip() == "*":
        return True
    raw = etag.strip('"')
    for candidate in if_none_match.split(","):
        candidate = candidate.strip().strip('"')
        if candidate == raw:
            return True
    return False


def _parse_genome_motion(gm: str) -> tuple[str, str]:
    if "." in gm:
        parts = gm.rsplit(".", 1)
        return parts[0], parts[1]
    return gm, "static"


def _error_response_headers(status_code: int) -> dict[str, str]:
    """Cache-Control + error-class headers for SMPTE error fallback responses.

    Aggressive TTL (default 5s + stale-while-revalidate=60s, configurable via
    HW_ERROR_CACHE_TTL) so a recovered origin re-populates Camo edge within
    seconds rather than the previous minute. See settings.error_cache_ttl —
    the prior 60s sticky-error cache amplified short cold-start outages into
    minute-long broken-image cascades for every README visitor.
    """
    ttl = get_settings().error_cache_ttl
    return {
        "Cache-Control": f"max-age={ttl}, stale-while-revalidate=60",
        "X-HW-Error-Code": str(status_code),
    }


async def _resolve_data_param(data: str, *, fallback: str = "") -> tuple[str, int]:
    """Parse ?data= param via the unified token grammar and format for ``value``.

    Returns ``(formatted_value, min_ttl)``. Empty input returns the
    fallback at the default TTL. Invalid token strings raise
    ``ValueError`` so callers can surface a 400 to the user.
    """
    if not data:
        return fallback, 300

    tokens = parse_data_tokens(data)
    if not tokens:
        return fallback, 300

    resolved, min_ttl = await resolve_data_tokens(tokens)
    formatted = format_for_value(resolved)
    return formatted or fallback, min_ttl


def _compose_and_respond(spec: Any, request: Request | None = None) -> Response:
    import hashlib

    settings = get_settings()

    etag = hashlib.sha256(spec.model_dump_json().encode()).hexdigest()[:16]
    etag_header = f'"{etag}"'

    if request is not None:
        if_none_match = request.headers.get("if-none-match")
        if if_none_match and _etag_matches(if_none_match, etag_header):
            return Response(
                status_code=304,
                headers={
                    "ETag": etag_header,
                    # Pure-compose route: artifact has no upstream data and only
                    # changes when HyperWeave version ships. Long Camo cache.
                    "Cache-Control": f"public, max-age={settings.compose_cache_ttl}",
                },
            )

    try:
        result = compose(spec)
        return Response(
            content=result.svg,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": f"public, max-age={settings.compose_cache_ttl}",
                "ETag": etag_header,
                "X-HW-Genome": spec.genome_id,
                "X-HW-Frame": spec.type,
            },
        )
    except Exception as exc:
        status_code = _classify_compose_exception(exc)
        return Response(
            content=_error_badge(str(exc), status_code=status_code),
            media_type="image/svg+xml",
            # HTTP 200 — Camo refuses to proxy 4xx image responses, which would
            # cause the README to render a broken-image icon despite the server
            # producing a valid SMPTE SVG. The error class travels in the SVG
            # (``data-hw-status-code``, ``ERR_NNN`` slab) and the response header.
            status_code=200,
            headers=_error_response_headers(status_code),
        )


def _compose_and_respond_with_ttl(spec: Any, request: Request | None, ttl: int) -> Response:
    """Like _compose_and_respond but with a custom TTL for live data strips."""
    import hashlib

    etag = hashlib.sha256(spec.model_dump_json().encode()).hexdigest()[:16]
    etag_header = f'"{etag}"'

    if request is not None:
        if_none_match = request.headers.get("if-none-match")
        if if_none_match and _etag_matches(if_none_match, etag_header):
            return Response(
                status_code=304,
                headers={"ETag": etag_header, "Cache-Control": f"public, max-age={ttl}"},
            )

    try:
        result = compose(spec)
        return Response(
            content=result.svg,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": f"public, max-age={ttl}, stale-while-revalidate=3600",
                "ETag": etag_header,
                "X-HW-Genome": spec.genome_id,
                "X-HW-Frame": spec.type,
                "X-HW-Cache-Tier": "connector",
            },
        )
    except Exception as exc:
        status_code = _classify_compose_exception(exc)
        return Response(
            content=_error_badge(str(exc), status_code=status_code),
            media_type="image/svg+xml",
            # HTTP 200 — Camo refuses to proxy 4xx image responses, which would
            # cause the README to render a broken-image icon despite the server
            # producing a valid SMPTE SVG. The error class travels in the SVG
            # (``data-hw-status-code``, ``ERR_NNN`` slab) and the response header.
            status_code=200,
            headers=_error_response_headers(status_code),
        )


_specimens_cache: dict[str, Any] | None = None


def _load_specimens_registry() -> dict[str, Any]:
    """Load the editorial specimens registry from data/registries/specimens.yaml.

    Returns a mixed dict: top-level keys may be either flat slugs (str values
    pointing at a relative file path under specs/) or categories (dict values
    keyed by slug). v0.2.19+ uses the categorized form for new content; legacy
    flat-slug entries remain as scaffolding for the upcoming golden-200 dataset.
    """
    global _specimens_cache
    if _specimens_cache is not None:
        return _specimens_cache
    import pathlib

    import yaml

    registry_path = pathlib.Path(__file__).resolve().parent.parent / "data" / "registries" / "specimens.yaml"
    if not registry_path.exists():
        _specimens_cache = {}
        return _specimens_cache
    with registry_path.open() as f:
        _specimens_cache = yaml.safe_load(f) or {}
    return _specimens_cache


def _flat_specimens(registry: dict[str, Any]) -> dict[str, str]:
    """Filter to legacy flat-slug entries (str values only)."""
    return {k: v for k, v in registry.items() if isinstance(v, str)}


def _categorized_specimens(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Filter to categorized entries (dict values only). v0.2.19+ form."""
    return {k: v for k, v in registry.items() if isinstance(v, dict)}


def _error_badge_palette() -> dict[str, Any]:
    """Return the SMPTE fallback palette outside the Jinja stencil."""
    return {
        "error_viewbox": "0 0 192 32",
        "error_w": 192,
        "error_h": 32,
        "error_rects": {
            "bars_clip": {"x": 2, "y": 2, "w": 117, "h": 28},
            "frame": {"w": 192, "h": 32},
            "inner_stroke": {"x": 1, "y": 1, "w": 190, "h": 30},
            "body": {"x": 2, "y": 2, "w": 188, "h": 28},
            "top_highlight": {"x": 22, "y": 2, "w": 166, "h": 1},
            "bottom_shadow": {"x": 22, "y": 29.5, "w": 166, "h": 0.5},
            "noise_1": {"x": 2, "y": 8, "w": 117, "h": 0.5},
            "noise_2": {"x": 2, "y": 20, "w": 117, "h": 0.5},
            "scan": {"x": 2, "y": 2, "w": 117, "h": 0.8},
            "banner": {"x": 14, "y": 9, "w": 93, "h": 14},
            "seam": {"x": 119, "y": 2, "w": 1, "h": 28},
            "seam_gap": {"x": 120, "y": 2, "w": 2, "h": 28},
            "value": {"x": 122, "y": 2, "w": 68, "h": 28},
        },
        "error_texts": {
            "signal": {"x": 60.5, "y": 20},
            "value": {"x": 156, "y": 21},
        },
        "error_rim_stops": [
            {"offset": "0%", "color": "#E8E8E8"},
            {"offset": "10%", "color": "#B8B8B8"},
            {"offset": "28%", "color": "#787878"},
            {"offset": "48%", "color": "#3A3A3A"},
            {"offset": "72%", "color": "#1A1A1A"},
            {"offset": "90%", "color": "#0A0A0A"},
            {"offset": "100%", "color": "#020202"},
        ],
        "error_value_stops": [
            {"offset": "0%", "color": "#0C0C12"},
            {"offset": "100%", "color": "#040408"},
        ],
        "error_seam_stops": [
            {"offset": "0%", "color": "#FF0040", "opacity": "0"},
            {"offset": "18%", "color": "#FF0040", "opacity": "0.55"},
            {"offset": "50%", "color": "#00E0FF", "opacity": "0.82"},
            {"offset": "82%", "color": "#FF0040", "opacity": "0.55"},
            {"offset": "100%", "color": "#FF0040", "opacity": "0"},
        ],
        "error_bar_colors": [
            {"x": 2, "y": 2, "width": 17, "height": 28, "color": "#C0C0C0"},
            {"x": 19, "y": 2, "width": 17, "height": 28, "color": "#C0C000"},
            {"x": 36, "y": 2, "width": 17, "height": 28, "color": "#00C0C0"},
            {"x": 53, "y": 2, "width": 17, "height": 28, "color": "#00C000"},
            {"x": 70, "y": 2, "width": 17, "height": 28, "color": "#C000C0"},
            {"x": 87, "y": 2, "width": 17, "height": 28, "color": "#C00000"},
            {"x": 104, "y": 2, "width": 15, "height": 28, "color": "#0000C0"},
        ],
        "error_shadow_color": "#000000",
        "error_pulse_color": "#FF3858",
        "error_inner_stroke": "#000510",
        "error_body_fill": "#040408",
        "error_top_highlight": "#E8E8E8",
        "error_bottom_shadow": "#020202",
        "error_noise_fill": "#FFFFFF",
        "error_banner_fill": "#000000",
        "error_banner_stroke": "#FFFFFF",
        "error_seam_gap_fill": "#020308",
        "error_signal_text": "#FFFFFF",
        "error_value_text": "#FF6B7E",
    }


def _error_badge(message: str, status_code: int = 500) -> str:
    """Render the universal SMPTE NO SIGNAL fallback SVG.

    Routes through the same Jinja2 template pipeline as every composed
    artifact (``render_template`` -> ``error-badge.svg.j2``). The status
    code is embedded in the value slab (``ERR_404`` / ``ERR_422`` / ``ERR_500``);
    the message goes into ``<title>``/``<desc>`` only. Each error badge gets
    a stable per-message uid so two failures on the same README page don't
    collide on gradient or clip-path IDs.
    """
    truncated = (message or "compose failed")[:120]
    uid = f"hw-err-{abs(hash(truncated)) % 100000:05d}"
    font_faces = load_font_face_css(["chakra-petch", "orbitron"])
    return render_template(
        "error-badge.svg.j2",
        {
            "status_code": int(status_code),
            "message": truncated,
            "uid": uid,
            "font_faces": font_faces,
            **_error_badge_palette(),
        },
    )


def _classify_compose_exception(exc: BaseException) -> int:
    """Map a compose-pipeline exception to the HTTP status code the SVG should
    encode in its ``ERR_NNN`` value slab and ``data-hw-status-code`` attribute.

    GenomeNotFoundError -> 404 (the URL named a genome the registry doesn't have).
    Pydantic ``ValidationError`` -> 422 (a field value is structurally invalid).
    Anything else -> 500 (unexpected failure -- template missing, render error, ...).

    NOTE: This is the *SVG-internal* status code, not the HTTP envelope code.
    Error responses always return HTTP 200 so GitHub Camo proxies and browser
    ``<img>`` elements actually render the SMPTE NO SIGNAL fallback body —
    Camo refuses to forward 4xx image responses, which would cause the
    README to show a broken-image icon despite the server producing a valid
    SVG. Programmatic consumers that need the underlying error class can
    read ``data-hw-status-code`` from the SVG attributes or the
    ``X-HW-Error-Code`` response header.
    """
    if isinstance(exc, GenomeNotFoundError):
        return 404
    try:
        from pydantic import ValidationError
    except ImportError:
        return 500
    if isinstance(exc, ValidationError):
        return 422
    # Path B grammar (v0.2.19): resolvers raise ValueError when
    # spec.variant or spec.divider_variant is not in the genome's whitelist.
    # Detect by message prefix rather than a custom exception class to keep
    # the resolver layer dependency-free.
    if isinstance(exc, ValueError) and (str(exc).startswith("variant '") or str(exc).startswith("divider_variant '")):
        return 422
    # Matrix input problems are caller errors: no usable input, unknown
    # preset/adapter/glyph id, hard-cap overflow (MatrixCapacityError is a
    # MatrixInputError), or a genome without a matrix paradigm entry.
    from hyperweave.core.diagram import DiagramInputError
    from hyperweave.core.matrix import MatrixInputError

    if isinstance(exc, MatrixInputError):
        return 422
    if isinstance(exc, DiagramInputError):
        return 422
    if isinstance(exc, ValueError) and str(exc).startswith("diagram frame is not supported"):
        return 422
    if isinstance(exc, ValueError) and str(exc).startswith("matrix frame is not supported"):
        return 422
    return 500


@app.exception_handler(PydanticValidationError)
async def _spec_validation_error_handler(request: Request, exc: PydanticValidationError) -> Response:
    """Degrade ComposeSpec field-validation failures to the SMPTE error SVG.

    The image GET routes construct ``ComposeSpec(...)`` directly, so a bad ENUM
    value (e.g. an unknown ``divider_variant`` like ``aura`` on a server that
    doesn't ship that divider yet, or an unknown ``shape``/``size``) raises a
    pydantic ``ValidationError`` in the handler body — BEFORE
    ``_compose_and_respond``'s try/except. Without this it escapes to FastAPI's
    default 500 ``text/plain``, which GitHub Camo refuses to proxy, rendering a
    broken-image icon instead of the NO SIGNAL fallback. (An unknown GENOME fails
    later, at compose, so it was already caught — hence the asymmetry the divider
    exposed.) Returning the SMPTE SVG at HTTP 200 puts enum failures on the same
    degradation path as every other compose error. Only GET image routes degrade
    to the SVG; POST /v1/compose (which builds its ComposeSpec from the JSON body)
    keeps a JSON 422 error envelope.
    """
    if request.method != "GET":
        return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})
    status_code = _classify_compose_exception(exc)
    return Response(
        content=_error_badge(str(exc), status_code=status_code),
        media_type="image/svg+xml",
        status_code=200,
        headers=_error_response_headers(status_code),
    )
