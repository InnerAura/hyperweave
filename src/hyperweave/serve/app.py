"""FastAPI application -- HTTP interface to the compositor."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(
    title="HyperWeave",
    description="Compositor API for self-contained SVG artifacts.",
    version="0.1.0",
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
    metadata_tier: int = 3
    divider_variant: str = "zeropoint"
    direction: str = "ltr"
    rows: int = 3
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
    glyph: Annotated[str, Query()] = "",
    glyph_mode: Annotated[str, Query()] = "auto",
    state: Annotated[str, Query()] = "active",
    regime: Annotated[str, Query()] = "normal",
    variant: Annotated[str, Query()] = "default",
) -> Response:
    """Compose a badge: /v1/badge/{title}/{value}/{genome}.{motion}"""
    genome, motion = _parse_genome_motion(genome_motion)

    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="badge",
        genome_id=genome,
        title=title,
        value=value,
        state=state,
        motion=motion,
        glyph=glyph,
        glyph_mode=glyph_mode,
        regime=regime,
        variant=variant,
    )
    return _compose_and_respond(spec, request)


@app.get(
    "/v1/strip/{title}/{genome_motion}",
    response_class=Response,
)
async def compose_strip_url(
    request: Request,
    title: str,
    genome_motion: str,
    value: Annotated[str, Query()] = "",
    live: Annotated[str, Query()] = "",
    glyph: Annotated[str, Query()] = "",
    glyph_mode: Annotated[str, Query()] = "auto",
    state: Annotated[str, Query()] = "active",
    variant: Annotated[str, Query()] = "default",
    regime: Annotated[str, Query()] = "normal",
) -> Response:
    """Compose a strip: /v1/strip/{title}/{genome}.{motion}?value=&live="""
    genome, motion = _parse_genome_motion(genome_motion)

    ttl = 300
    final_value = value

    # Live data: ?live=github:owner/repo:stars,pypi:pkg:version
    if live:
        final_value, ttl = await _fetch_live_metrics(live, fallback=value)

    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="strip",
        genome_id=genome,
        title=title,
        value=final_value,
        state=state,
        motion=motion,
        glyph=glyph,
        glyph_mode=glyph_mode,
        variant=variant,
        regime=regime,
    )

    if live:
        return _compose_and_respond_with_ttl(spec, request, ttl)
    return _compose_and_respond(spec, request)


@app.get(
    "/v1/banner/{title}/{genome_motion}",
    response_class=Response,
)
async def compose_banner_url(
    request: Request,
    title: str,
    genome_motion: str,
    value: Annotated[str, Query()] = "",
    glyph: Annotated[str, Query()] = "",
    glyph_mode: Annotated[str, Query()] = "auto",
    state: Annotated[str, Query()] = "active",
    variant: Annotated[str, Query()] = "default",
    regime: Annotated[str, Query()] = "normal",
) -> Response:
    """Compose a banner: /v1/banner/{title}/{genome}.{motion}"""
    genome, motion = _parse_genome_motion(genome_motion)

    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="banner",
        genome_id=genome,
        title=title,
        value=value,
        motion=motion,
        glyph=glyph,
        glyph_mode=glyph_mode,
        state=state,
        variant=variant,
        regime=regime,
    )
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
) -> Response:
    """Compose a divider: /v1/divider/{variant}/{genome}.{motion}"""
    genome, motion = _parse_genome_motion(genome_motion)

    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="divider",
        genome_id=genome,
        motion=motion,
        divider_variant=variant,
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
    direction: Annotated[str, Query()] = "ltr",
    rows: Annotated[int, Query()] = 3,
    speeds: Annotated[str, Query()] = "",
    state: Annotated[str, Query()] = "active",
    regime: Annotated[str, Query()] = "normal",
) -> Response:
    """Compose a marquee: /v1/marquee/{title}/{genome}.{motion}"""
    genome, motion = _parse_genome_motion(genome_motion)

    # Determine marquee type from direction/rows
    if rows > 1:
        mtype = "marquee-counter"
    elif direction in ("up", "down"):
        mtype = "marquee-vertical"
    else:
        mtype = "marquee-horizontal"

    # Parse speeds: comma-separated floats
    parsed_speeds: list[float] | None = None
    if speeds:
        try:
            parsed_speeds = [float(s.strip()) for s in speeds.split(",") if s.strip()]
        except ValueError:
            parsed_speeds = None

    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type=mtype,
        genome_id=genome,
        title=title,
        motion=motion,
        marquee_direction=direction,
        marquee_rows=rows,
        marquee_speeds=parsed_speeds,
        state=state,
        regime=regime,
    )
    return _compose_and_respond(spec, request)


@app.get(
    "/v1/live/{provider}/{identifier:path}/{metric}/{genome_motion}",
    response_class=Response,
)
async def compose_live_badge(
    provider: str,
    identifier: str,
    metric: str,
    genome_motion: str,
    glyph: Annotated[str, Query()] = "",
    glyph_mode: Annotated[str, Query()] = "auto",
    state: Annotated[str, Query()] = "active",
) -> Response:
    """Compose a badge with live data: /v1/live/{provider}/{identifier}/{metric}/{genome}.{motion}"""
    genome, motion = _parse_genome_motion(genome_motion)

    label = metric
    value = "n/a"
    cache_tier = "connector"
    ttl = 300
    try:
        from hyperweave.connectors import fetch_metric

        data = await fetch_metric(provider, identifier, metric)
        value = str(data.get("value", "n/a"))
        ttl = data.get("ttl", 300)
    except Exception:
        value = "error"
        cache_tier = "error"
        ttl = 60

    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="badge",
        genome_id=genome,
        title=label,
        value=value,
        state=state,
        motion=motion,
        glyph=glyph,
        glyph_mode=glyph_mode,
    )
    try:
        from hyperweave.compose.engine import compose

        result = compose(spec)
        return Response(
            content=result.svg,
            media_type="image/svg+xml",
            headers={
                "Cache-Control": f"public, max-age={ttl}, stale-while-revalidate=3600",
                "X-HW-Genome": genome,
                "X-HW-Frame": "badge",
                "X-HW-Cache-Tier": cache_tier,
                "X-HW-Provider": provider,
            },
        )
    except Exception as exc:
        return Response(
            content=_error_badge(str(exc)),
            media_type="image/svg+xml",
            status_code=500,
            headers={"Cache-Control": "max-age=60"},
        )


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
        metadata_tier=req.metadata_tier,
        divider_variant=req.divider_variant,
        marquee_direction=req.direction,
        marquee_rows=req.rows,
        marquee_speeds=req.speeds,
    )
    return _compose_and_respond(spec, request)


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
    "badge": {
        "pattern": "/v1/badge/{title}/{value}/{genome}.{motion}",
        "query_params": ["glyph", "glyph_mode", "state", "regime", "variant"],
    },
    "strip": {
        "pattern": "/v1/strip/{title}/{genome}.{motion}",
        "query_params": ["value", "live", "glyph", "glyph_mode", "state", "variant", "regime"],
    },
    "banner": {
        "pattern": "/v1/banner/{title}/{genome}.{motion}",
        "query_params": ["value", "glyph", "glyph_mode", "state", "variant", "regime"],
    },
    "icon": {
        "pattern": "/v1/icon/{glyph}/{genome}.{motion}",
        "query_params": ["glyph_mode", "shape", "state", "regime"],
    },
    "divider": {
        "pattern": "/v1/divider/{variant}/{genome}.{motion}",
        "query_params": [],
    },
    "marquee-horizontal": {
        "pattern": "/v1/marquee/{title}/{genome}.{motion}",
        "query_params": ["direction", "rows", "speeds", "state", "regime"],
    },
    "marquee-vertical": {
        "pattern": "/v1/marquee/{title}/{genome}.{motion}?direction=up",
        "query_params": ["direction", "rows", "speeds", "state", "regime"],
    },
    "marquee-counter": {
        "pattern": "/v1/marquee/{title}/{genome}.{motion}?rows=3",
        "query_params": ["direction", "rows", "speeds", "state", "regime"],
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
            content=_error_badge(f"Specimen '{slug}' not found"), media_type="image/svg+xml", status_code=404
        )

    import pathlib

    specs_dir = pathlib.Path(__file__).resolve().parent.parent.parent.parent / "specs"
    svg_path = specs_dir / rel_path
    if not svg_path.exists():
        return Response(
            content=_error_badge(f"File not found: {rel_path}"), media_type="image/svg+xml", status_code=404
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


async def _fetch_live_metrics(live: str, *, fallback: str = "") -> tuple[str, int]:
    """Parse ?live= param and fetch metrics concurrently.

    Format: provider:identifier:metric,provider:identifier:metric
    Returns (formatted_value, min_ttl).
    """
    from hyperweave.connectors import fetch_metric

    segments: list[tuple[str, str, str]] = []
    for seg in live.split(","):
        seg = seg.strip()
        if not seg:
            continue
        parts = seg.split(":", 2)
        if len(parts) == 3:
            segments.append((parts[0], parts[1], parts[2]))

    if not segments:
        return fallback, 300

    tasks = [fetch_metric(p, i, m) for p, i, m in segments]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    live_metrics: list[str] = []
    min_ttl = 300
    for (_p, _i, m), result in zip(segments, results, strict=True):
        if isinstance(result, BaseException):
            live_metrics.append(f"{m.upper()}:--")
        else:
            live_metrics.append(f"{m.upper()}:{result.get('value', 'n/a')}")
            min_ttl = min(min_ttl, result.get("ttl", 300))

    return ",".join(live_metrics), min_ttl


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
        return Response(
            content=_error_badge(str(exc)),
            media_type="image/svg+xml",
            status_code=500,
            headers={"Cache-Control": "max-age=60"},
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
        return Response(
            content=_error_badge(str(exc)),
            media_type="image/svg+xml",
            status_code=500,
            headers={"Cache-Control": "max-age=60"},
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


def _error_badge(message: str) -> str:
    safe_msg = message[:80].replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    from hyperweave.render.templates import render_template

    return render_template("error-badge.svg.j2", {"message": safe_msg})
