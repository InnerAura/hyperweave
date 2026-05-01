"""FastAPI application -- HTTP interface to the compositor."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from hyperweave import __version__

app = FastAPI(
    title="HyperWeave",
    description="Compositor API for self-contained SVG artifacts.",
    version=__version__,
)


# -- Health probe (before middleware, minimal) --------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe for container orchestration."""
    return {"status": "ok"}


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
        response.headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return response


# Request / Response models


class ComposeRequest(BaseModel):
    """Full compose request (POST /v1/compose)."""

    type: str = "badge"
    genome: str = "brutalist-emerald"
    title: str = ""
    value: str = ""
    state: str = "active"
    motion: str = "static"
    glyph: str = ""
    glyph_mode: str = "auto"
    regime: str = "normal"
    variant: str = "default"
    shape: str = ""
    family: str = ""
    metadata_tier: int = 3
    divider_variant: str = "zeropoint"
    direction: str = "ltr"
    speeds: list[float] | None = None


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
    variant: Annotated[str, Query()] = "default",
    family: Annotated[str, Query(description="Chromatic family (automata): blue, purple, bifamily")] = "",
) -> Response:
    """Static badge: /v1/badge/{title}/{value}/{genome}.{motion}.

    Three path segments. Use the 2-segment route below
    (/v1/badge/{title}/{genome}.{motion}?data=...) for data-driven badges.
    """
    genome, motion = _parse_genome_motion(genome_motion)

    from hyperweave.core.models import ComposeSpec

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
        variant=variant,
        family=family,
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
                "kv:KEY=VALUE | gh:owner/repo.metric | pypi:pkg.metric | etc. "
                "Embedded commas in text/kv payloads escape as \\,."
            )
        ),
    ] = "",
    t: Annotated[str, Query(description="Title override (use when title contains slashes)")] = "",
    glyph: Annotated[str, Query()] = "",
    glyph_mode: Annotated[str, Query()] = "auto",
    state: Annotated[str, Query()] = "active",
    regime: Annotated[str, Query()] = "normal",
    variant: Annotated[str, Query()] = "default",
    family: Annotated[str, Query(description="Chromatic family (automata): blue, purple, bifamily")] = "",
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
            headers={"Cache-Control": "max-age=60", "X-HW-Error-Code": "400"},
        )

    # Badge has a single value slot — title is in the path, value is the
    # rendered string. format_for_badge extracts just the resolved value
    # (no LABEL: prefix), unlike strip which uses format_for_value to
    # produce "K1:V1,K2:V2" pairs for its multi-cell layout.
    from hyperweave.serve.data_tokens import (
        format_for_badge,
        parse_data_tokens,
        resolve_data_tokens,
    )

    try:
        tokens = parse_data_tokens(data)
        resolved, ttl = await resolve_data_tokens(tokens)
    except ValueError as exc:
        return Response(
            content=_error_badge(f"data parse: {exc}", status_code=400),
            media_type="image/svg+xml",
            status_code=200,
            headers={"Cache-Control": "max-age=60", "X-HW-Error-Code": "400"},
        )

    final_value = format_for_badge(resolved)

    from hyperweave.core.models import ComposeSpec

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
        variant=variant,
        family=family,
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
    variant: Annotated[str, Query()] = "default",
    regime: Annotated[str, Query()] = "normal",
    family: Annotated[str, Query(description="Chromatic family (automata): blue, purple, bifamily")] = "",
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
                headers={"Cache-Control": "max-age=60", "X-HW-Error-Code": "400"},
            )

    # Subtitle wires through connector_data.repo_slug — the same field
    # resolve_strip reads when generate_proofset.py passes connector_data
    # explicitly. Empty subtitle leaves connector_data=None so paradigms
    # that don't opt into subtitles (brutalist, chrome) stay unaffected.
    connector_data: dict[str, Any] | None = {"repo_slug": subtitle} if subtitle else None

    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="strip",
        genome_id=genome,
        title=t or title,
        value=final_value,
        state=state,
        motion=motion,
        glyph=glyph,
        glyph_mode=glyph_mode,
        variant=variant,
        regime=regime,
        family=family,
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
    variant: Annotated[str, Query()] = "default",
    state: Annotated[str, Query()] = "active",
    regime: Annotated[str, Query()] = "normal",
    family: Annotated[str, Query(description="Chromatic family (automata): blue, purple, bifamily")] = "",
) -> Response:
    """Compose an icon: /v1/icon/{glyph}/{genome}.{motion}?shape=circle"""
    genome, motion = _parse_genome_motion(genome_motion)

    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="icon",
        genome_id=genome,
        title=glyph,
        glyph=glyph,
        glyph_mode=glyph_mode,
        motion=motion,
        shape=shape,
        variant=variant,
        state=state,
        regime=regime,
        family=family,
    )
    return _compose_and_respond(spec, request)


@app.get(
    "/v1/divider/{variant}/{genome_motion}",
    response_class=Response,
)
async def compose_divider_url(
    request: Request,
    variant: str,
    genome_motion: str,
    family: Annotated[str, Query(description="Chromatic family (automata): blue, purple, bifamily")] = "",
) -> Response:
    """Compose a divider: /v1/divider/{variant}/{genome}.{motion}"""
    genome, motion = _parse_genome_motion(genome_motion)

    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="divider",
        genome_id=genome,
        motion=motion,
        divider_variant=variant,
        family=family,
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
                "gh:owner/repo.metric | pypi:pkg.metric | etc. When set, the title "
                "param is ignored as a data source — tokens drive the scroll. Embedded "
                "commas in text/kv payloads escape as \\,."
            )
        ),
    ] = "",
    direction: Annotated[str, Query(description="Scroll direction: ltr or rtl")] = "ltr",
    speeds: Annotated[str, Query(description="Scroll speed multiplier (single float)")] = "",
    state: Annotated[str, Query()] = "active",
    regime: Annotated[str, Query()] = "normal",
    family: Annotated[str, Query(description="Chromatic family (automata): blue, purple, bifamily")] = "",
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
            from hyperweave.serve.data_tokens import (
                parse_data_tokens,
                resolve_data_tokens,
            )

            tokens = parse_data_tokens(data)
            data_tokens_resolved_seq, ttl = await resolve_data_tokens(tokens)
            data_tokens_resolved = list(data_tokens_resolved_seq)
        except ValueError as exc:
            return Response(
                content=_error_badge(f"data parse: {exc}", status_code=400),
                media_type="image/svg+xml",
                status_code=200,
                headers={"Cache-Control": "max-age=60", "X-HW-Error-Code": "400"},
            )

    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="marquee-horizontal",
        genome_id=genome,
        title=t or title,
        motion=motion,
        marquee_direction=direction,
        marquee_speeds=parsed_speeds,
        state=state,
        regime=regime,
        family=family,
        data_tokens=data_tokens_resolved,
    )

    if data:
        return _compose_and_respond_with_ttl(spec, request, ttl)
    return _compose_and_respond(spec, request)


@app.post("/v1/compose", response_class=Response)
async def compose_post(request: Request, req: ComposeRequest) -> Response:
    """Compose any artifact via POST with full ComposeSpec."""
    from hyperweave.core.models import ComposeSpec

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
        variant=req.variant,
        shape=req.shape,
        family=req.family,
        metadata_tier=req.metadata_tier,
        divider_variant=req.divider_variant,
        marquee_direction=req.direction,
        marquee_speeds=req.speeds,
    )
    return _compose_and_respond(spec, request)


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
) -> Response:
    """Compose a star history chart: /v1/chart/stars/{owner}/{repo}/{genome}.{motion}.

    Fetches sampled stargazer history from GitHub (cached 1h) and delegates
    rendering to the chart frame. On fetch failure, renders a placeholder
    series with ``data-hw-status="stale"`` (graceful degradation).
    """
    genome, motion = _parse_genome_motion(genome_motion)

    connector_data: dict[str, Any] | None = None
    try:
        from hyperweave.connectors.github import fetch_stargazer_history

        connector_data = await fetch_stargazer_history(owner, repo)
    except Exception:
        connector_data = None

    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="chart",
        genome_id=genome,
        chart_owner=owner,
        chart_repo=repo,
        motion=motion,
        connector_data=connector_data,
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
) -> Response:
    """Compose a GitHub stats card: /v1/stats/{username}/{genome}.{motion}.

    Fetches user profile + repos + commits + PRs + issues + contribution
    calendar in parallel (cached 1h) and renders through the stats frame.
    Graceful degradation: individual sub-fetch failures result in partial
    data with ``data-hw-status="stale"`` only when ALL sub-fetches fail.
    """
    genome, motion = _parse_genome_motion(genome_motion)

    connector_data: dict[str, Any] | None = None
    try:
        from hyperweave.connectors.github import fetch_user_stats

        connector_data = await fetch_user_stats(username)
    except Exception:
        connector_data = None

    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="stats",
        genome_id=genome,
        stats_username=username,
        motion=motion,
        connector_data=connector_data,
    )
    return _compose_and_respond_with_ttl(spec, request, ttl=3600)


class KitRequest(BaseModel):
    """Kit compose request."""

    genome: str = "brutalist-emerald"
    project: str = ""
    badges: str = ""
    social: str = ""


@app.post("/v1/kit/readme", response_model=None)
async def compose_kit_post(req: KitRequest) -> dict[str, str]:
    """Compose a full artifact kit. Returns dict of SVG strings."""
    from hyperweave.kit import compose_kit

    results = compose_kit("readme", req.genome, req.project, req.badges, req.social)
    return {name: result.svg for name, result in results.items()}


# Discovery endpoints


_FRAME_URL_GRAMMAR: dict[str, dict[str, Any]] = {
    "badge (static)": {
        "pattern": "/v1/badge/{title}/{value}/{genome}.{motion}",
        "query_params": ["glyph", "glyph_mode", "state", "regime", "variant", "family"],
    },
    "badge (data-driven)": {
        "pattern": "/v1/badge/{title}/{genome}.{motion}?data=...",
        "query_params": ["data", "glyph", "glyph_mode", "state", "regime", "variant", "family"],
    },
    "strip": {
        "pattern": "/v1/strip/{title}/{genome}.{motion}",
        "query_params": ["value", "data", "glyph", "glyph_mode", "state", "variant", "regime", "family", "subtitle"],
    },
    "icon": {
        "pattern": "/v1/icon/{glyph}/{genome}.{motion}",
        "query_params": ["glyph_mode", "shape", "state", "regime", "family", "variant"],
    },
    "divider": {
        "pattern": "/v1/divider/{variant}/{genome}.{motion}",
        "query_params": ["family"],
    },
    "marquee-horizontal": {
        "pattern": "/v1/marquee/{title}/{genome}.{motion}",
        "query_params": ["data", "direction", "speeds", "state", "regime", "family"],
    },
    "chart-stars": {
        "pattern": "/v1/chart/stars/{owner}/{repo}/{genome}.{motion}",
        "query_params": [],
    },
    "stats": {
        "pattern": "/v1/stats/{username}/{genome}.{motion}",
        "query_params": [],
    },
    "receipt": {"pattern": "POST /v1/compose", "query_params": []},
    "rhythm-strip": {"pattern": "POST /v1/compose", "query_params": []},
    "master-card": {"pattern": "POST /v1/compose", "query_params": []},
    "catalog": {"pattern": "POST /v1/compose", "query_params": []},
}


@app.get("/v1/frames")
async def list_frames() -> list[dict[str, Any]]:
    """List all frame types with URL grammar and query params."""
    from hyperweave.core.enums import FrameType

    return [
        {
            "type": ft.value,
            **_FRAME_URL_GRAMMAR.get(ft.value, {"pattern": "POST /v1/compose", "query_params": []}),
        }
        for ft in FrameType
    ]


@app.get("/v1/genomes")
async def list_genomes(response: Response) -> list[dict[str, Any]]:
    """List available genomes."""
    from hyperweave.config.loader import get_loader

    response.headers["Cache-Control"] = "public, max-age=3600"
    loader = get_loader()
    return [
        {"id": gid, "name": g.get("name", gid), "category": g.get("category", "dark")}
        for gid, g in loader.genomes.items()
    ]


@app.get("/v1/genomes/{genome_id}", response_model=None)
async def get_genome(genome_id: str, response: Response) -> dict[str, Any] | JSONResponse:
    """Get a specific genome's full config."""
    from hyperweave.config.loader import get_loader

    response.headers["Cache-Control"] = "public, max-age=3600"
    loader = get_loader()
    genome = loader.genomes.get(genome_id)
    if not genome:
        return JSONResponse({"error": f"Genome '{genome_id}' not found"}, status_code=404)
    return genome


@app.get("/v1/motions")
async def list_motions(response: Response) -> list[dict[str, Any]]:
    """List available motion primitives."""
    from hyperweave.config.loader import get_loader

    response.headers["Cache-Control"] = "public, max-age=3600"
    loader = get_loader()
    return [
        {"id": mid, "name": m.get("name", mid), "cim_compliant": m.get("cim_compliant", True)}
        for mid, m in loader.motions.items()
    ]


@app.get("/v1/glyphs")
async def list_glyphs(response: Response) -> list[str]:
    """List available glyph IDs."""
    from hyperweave.config.loader import get_loader

    response.headers["Cache-Control"] = "public, max-age=3600"
    loader = get_loader()
    return sorted(loader.glyphs.keys()) if hasattr(loader, "glyphs") else []


# Artifact Store (/a/inneraura/) -- Editorial specimens


@app.get("/a/inneraura", response_model=None)
async def list_specimens() -> list[dict[str, str]]:
    """List all editorial specimens available under /a/inneraura/."""
    registry = _load_specimens_registry()
    return [{"slug": slug, "url": f"/a/inneraura/{slug}"} for slug in sorted(registry)]


@app.get("/a/inneraura/{slug}", response_class=Response)
async def serve_specimen(slug: str) -> Response:
    """Serve an editorial specimen SVG by slug."""
    registry = _load_specimens_registry()
    rel_path = registry.get(slug)
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

    from hyperweave.config.settings import get_settings

    svg_content = svg_path.read_text(encoding="utf-8")
    ttl = get_settings().static_cache_ttl
    return Response(
        content=svg_content,
        media_type="image/svg+xml",
        headers={"Cache-Control": f"public, max-age={ttl}, immutable", "X-HW-Artifact-Type": "editorial-specimen"},
    )


@app.get("/a/inneraura/{slug}/meta.json", response_model=None)
async def serve_specimen_meta(slug: str) -> Response | JSONResponse:
    """Serve metadata-only for an editorial specimen."""
    registry = _load_specimens_registry()
    rel_path = registry.get(slug)
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


# Genome Registry (/g/)


@app.get("/g/{genome_slug}", response_model=None)
async def genome_registry(genome_slug: str) -> Response | JSONResponse:
    """Serve genome DNA (JSON)."""
    import json

    from hyperweave.config.loader import get_loader

    loader = get_loader()
    genome = loader.genomes.get(genome_slug)
    if not genome:
        return JSONResponse({"error": f"Genome '{genome_slug}' not found"}, status_code=404)
    from hyperweave.config.settings import get_settings

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
        "catalog_url": f"/a/inneraura/{drop_id}-catalog-v1",
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


async def _resolve_data_param(data: str, *, fallback: str = "") -> tuple[str, int]:
    """Parse ?data= param via the unified token grammar and format for ``value``.

    Returns ``(formatted_value, min_ttl)``. Empty input returns the
    fallback at the default TTL. Invalid token strings raise
    ``ValueError`` so callers can surface a 400 to the user.
    """
    from hyperweave.serve.data_tokens import (
        format_for_value,
        parse_data_tokens,
        resolve_data_tokens,
    )

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

    from hyperweave.config.settings import get_settings

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
                    "Cache-Control": f"public, max-age={settings.data_cache_ttl}",
                },
            )

    try:
        from hyperweave.compose.engine import compose

        result = compose(spec)
        return Response(
            content=result.svg,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": f"public, max-age={settings.data_cache_ttl}",
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
            headers={
                "Cache-Control": "max-age=60",
                "X-HW-Error-Code": str(status_code),
            },
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
        from hyperweave.compose.engine import compose

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
            headers={
                "Cache-Control": "max-age=60",
                "X-HW-Error-Code": str(status_code),
            },
        )


_specimens_cache: dict[str, str] | None = None


def _load_specimens_registry() -> dict[str, str]:
    global _specimens_cache
    if _specimens_cache is not None:
        return _specimens_cache
    import pathlib

    import yaml

    registry_path = pathlib.Path(__file__).resolve().parent.parent / "data" / "specimens.yaml"
    if not registry_path.exists():
        return {}
    with registry_path.open() as f:
        _specimens_cache = yaml.safe_load(f) or {}
    return _specimens_cache


def _error_badge(message: str, status_code: int = 500) -> str:
    """Render the universal SMPTE NO SIGNAL fallback SVG.

    Routes through the same Jinja2 template pipeline as every composed
    artifact (``render_template`` -> ``error-badge.svg.j2``). The status
    code is embedded in the value slab (``ERR_404`` / ``ERR_422`` / ``ERR_500``);
    the message goes into ``<title>``/``<desc>`` only. Each error badge gets
    a stable per-message uid so two failures on the same README page don't
    collide on gradient or clip-path IDs.
    """
    from hyperweave.render.fonts import load_font_face_css
    from hyperweave.render.templates import render_template

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
    from hyperweave.compose.resolver import GenomeNotFoundError

    if isinstance(exc, GenomeNotFoundError):
        return 404
    try:
        from pydantic import ValidationError
    except ImportError:
        return 500
    if isinstance(exc, ValidationError):
        return 422
    return 500
