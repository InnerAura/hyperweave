"""Composition engine -- the single entry point for all artifact generation."""

from __future__ import annotations

import time

from hyperweave.core.models import ArtifactMetadata, ComposeResult, ComposeSpec, ResolvedArtifact


def compose(spec: ComposeSpec) -> ComposeResult:
    """Compose an artifact from a ComposeSpec."""
    start = time.monotonic()

    # ── 1. Resolve genome, profile, frame ──
    from hyperweave.compose.resolver import resolve

    resolved = resolve(spec)

    # ── 2. Assemble CSS ──
    from hyperweave.compose.assembler import assemble_css

    css_bundle = assemble_css(resolved, frame_type=spec.type)

    # ── 3. Build template context ──
    from hyperweave.compose.context import build_context

    context = build_context(spec, resolved, css_bundle)

    # ── 4. Enforce policy lanes ──
    from hyperweave.compose.lanes import enforce

    context = enforce(context, spec.regime)

    # ── 5. Render template → SVG ──
    from hyperweave.render.templates import render_artifact

    svg = render_artifact(resolved.frame_template, context)

    # ── 6. Build result ──
    duration_ms = (time.monotonic() - start) * 1000

    metadata = _build_metadata(spec, resolved, duration_ms)

    result = ComposeResult(
        svg=svg,
        metadata=metadata,
        width=resolved.width,
        height=resolved.height,
    )

    # ── 7. Emit telemetry event (fire-and-forget) ──
    try:
        from hyperweave.telemetry.capture import emit_generation_event

        emit_generation_event(spec, result)
    except Exception:
        pass  # telemetry must never break compose

    return result


def _build_metadata(
    spec: ComposeSpec,
    resolved: ResolvedArtifact,
    duration_ms: float,
) -> ArtifactMetadata:
    return ArtifactMetadata(
        type=spec.type,
        genome=spec.genome_id,
        profile=resolved.profile_id,
        divider_variant=spec.divider_variant,
        motion=resolved.motion,
        state=spec.state,
        regime=spec.regime,
        width=resolved.width,
        height=resolved.height,
        metadata_tier=spec.metadata_tier,
        duration_ms=round(duration_ms, 2),
        generation=spec.generation,
        series=spec.series,
    )
