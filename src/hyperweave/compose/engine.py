"""Composition engine -- the single entry point for all artifact generation."""

from __future__ import annotations

import time

from hyperweave.core.models import ArtifactMetadata, ComposeResult, ComposeSpec, ResolvedArtifact


def compose(spec: ComposeSpec) -> ComposeResult:
    """Compose an artifact from a ComposeSpec."""
    start = time.monotonic()

    # ── 0. Infer state from value when the caller left the default ──
    # Any explicit override (?state=failing, --state passing, MCP state arg,
    # etc.) sets spec.state to something other than "active" and survives
    # this step untouched. This is the single chokepoint covering HTTP,
    # CLI, MCP, and kit.
    #
    # v0.2.25: gated on the stateful-title allowlist (data/badge_modes.yaml).
    # Pre-v0.2.25 the inference fired on EVERY badge regardless of title —
    # so a STARS=42 badge was auto-inferred to state="critical" (leading
    # digit 4) and then re-classified as "explicit" mode by resolve_badge_mode,
    # rendering an orange/red status indicator on a value with no semantic
    # state. Now inference only fires for titles that meaningfully pass/fail
    # (build / coverage / uptime / health / score / lint / ci / deploy / status).
    if spec.state == "active" and spec.value and spec.title:
        from hyperweave.compose.layout import normalize_title
        from hyperweave.config.loader import load_badge_modes
        from hyperweave.core.state import infer_state

        # Normalize for separator-insensitive lookup (BUILD-STATUS,
        # CI_CD, etc.) — same normalizer ``resolve_badge_mode`` uses.
        if normalize_title(spec.title) in load_badge_modes():
            inferred = infer_state(spec.title, spec.value)
            if inferred != "active":
                spec = spec.model_copy(update={"state": inferred})

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
