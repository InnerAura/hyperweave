"""The intended unified surface — one spec shape in, one response shape out.

The design target (Architectural Invariant 9) is for CLI, MCP, and HTTP to all
accept the same :class:`SpecEnvelope` and return the same :class:`ResponseEnvelope`,
so the three wires become thin adapters over a single shared core. ``compose_surface``
is that core — but it is **not yet wired**: today the CLI, MCP, and HTTP paths each
build a ``ComposeSpec`` and call ``compose`` directly, so ``compose_surface`` has no
production callers (it is exercised by the surface tests and the content-addressed
transport). Routing the three wires through it is the alpha.6 surface-unification line.

It builds a ``ComposeSpec``, renders once, caches the result under its content
digest, and returns ``{envelope, url, ...}`` per the requested ``emit`` targets —
never forcing the inline SVG on a caller that only wants the actionable envelope.

Live ``data``-token resolution is async and frame-specific, so it stays in the
transport layer (the GET routes); a caller that has already fetched live data
passes it in ``spec`` as ``connector_data``/``data_tokens``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from hyperweave.compose.artifact_store import store_artifact
from hyperweave.compose.engine import compose
from hyperweave.compose.targets import apply_target
from hyperweave.core.enums import FrameType
from hyperweave.core.envelope import extract_envelope, extract_payload
from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.core.models import ComposeSpec

# Frame content that maps to a dedicated ComposeSpec field rather than a kwarg.
_IR_FIELD: dict[str, str] = {"matrix": "matrix", "diagram": "diagram"}

# emit targets understood by the surface (png lands with the raster path later).
_VALID_EMIT = {"svg", "md", "payload", "compressed"}

# Known frame types incl. the `card` alias (accepted, canonicalized to stats).
_FRAME_TYPES = {f.value for f in FrameType} | {"card"}


@dataclass(frozen=True)
class SpecEnvelope:
    """The canonical compose input, identical across every transport."""

    type: str
    genome: str = "primer"
    variant: str = ""
    spec: dict[str, Any] = field(default_factory=dict)
    data: str = ""
    target: str = "web"
    emit: tuple[str, ...] = ("svg",)


@dataclass(frozen=True)
class ResponseEnvelope:
    """The canonical compose output. Default emit (svg) returns just the bytes;
    multi-target emit returns the full dict so an agent reads the envelope and
    embeds the url without the pixels ever entering its context."""

    svg: str = ""
    md: str = ""
    payload: dict[str, Any] | None = None
    compressed: dict[str, Any] | None = None
    width: int = 0
    height: int = 0
    genome: str = ""
    variant: str = ""
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "width": self.width,
            "height": self.height,
            "genome": self.genome,
            "variant": self.variant,
            "url": self.url,
        }
        if self.svg:
            out["svg"] = self.svg
        if self.md:
            out["md"] = self.md
        if self.payload is not None:
            out["payload"] = self.payload
        if self.compressed is not None:
            out["compressed"] = self.compressed
        return out


def build_artifact_url(digest: str, base_url: str = "") -> str:
    """Content-addressed handle for a digest (``sha256:...`` or bare hex)."""
    hexd = digest.split(":", 1)[1] if digest.startswith("sha256:") else digest
    return f"{base_url.rstrip('/')}/v1/a/{hexd}" if base_url else f"/v1/a/{hexd}"


def _to_compose_spec(env: SpecEnvelope) -> ComposeSpec:
    """Map a SpecEnvelope to a ComposeSpec, raising HwError on a bad spec."""
    content = dict(env.spec or {})
    kwargs: dict[str, Any] = {"type": env.type, "genome_id": env.genome}
    if env.variant:
        kwargs["variant"] = env.variant
    ir_field = _IR_FIELD.get(env.type)
    if ir_field:
        kwargs[ir_field] = content
    else:
        kwargs.update(content)
    try:
        return ComposeSpec(**kwargs)
    except ValidationError as exc:
        code = HwErrorCode.TYPE_UNKNOWN if env.type not in _FRAME_TYPES else HwErrorCode.SPEC_INVALID
        raise HwError(
            code,
            f"invalid {env.type} spec: {exc.error_count()} error(s)",
            detail={"errors": exc.errors(include_url=False)},
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HwError(HwErrorCode.SPEC_INVALID, str(exc)) from exc


def compose_surface(env: SpecEnvelope, *, base_url: str = "") -> ResponseEnvelope:
    """Render a SpecEnvelope, cache it under its digest, return a ResponseEnvelope."""
    emit = set(env.emit) or {"svg"}
    unknown = emit - _VALID_EMIT
    if unknown:
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            f"unknown emit target(s): {sorted(unknown)}",
            fix=f"choose from {sorted(_VALID_EMIT)}",
        )

    spec = _to_compose_spec(env)
    result = compose(spec)
    # Surface pack: flatten var()→hex / strip motion / clamp per --target. `web`
    # (default) is the identity, so the SVG is byte-stable for the common path.
    svg = apply_target(result.svg, env.target)

    payload_pair = extract_payload(svg)
    envelope = extract_envelope(svg)
    digest = str(envelope.get("id", "")) if envelope else ""
    url = ""
    if digest:
        store_artifact(digest, svg)
        url = build_artifact_url(digest, base_url)

    payload_obj: dict[str, Any] | None = None
    if "payload" in emit and payload_pair is not None:
        try:
            payload_obj = json.loads(payload_pair[1])
        except json.JSONDecodeError:
            payload_obj = None

    return ResponseEnvelope(
        svg=svg if "svg" in emit else "",
        md=result.markdown if "md" in emit else "",
        payload=payload_obj,
        compressed=envelope if "compressed" in emit else None,
        width=result.width,
        height=result.height,
        genome=spec.genome_id,
        variant=spec.variant,
        url=url,
    )


def validate_surface(env: SpecEnvelope) -> dict[str, Any]:
    """Validate a SpecEnvelope without rendering. Returns a report dict."""
    try:
        _to_compose_spec(env)
    except HwError as exc:
        return {"valid": False, **exc.envelope()}
    return {"valid": True, "type": env.type, "genome": env.genome}
