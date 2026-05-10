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
    # Pre-v0.2.25 the inference fired on EVERY frame regardless of title —
    # so a STARS=42 badge was auto-inferred to state="critical" (leading
    # digit 4) and rendered an orange/red status indicator on a value with
    # no semantic state.
    #
    # Frame-aware logic:
    #   Badge → title-keyed inference. Title in allowlist → run infer_state.
    #   Strip → per-cell rolled-up inference. Strip's spec.title is the
    #           repo identifier (HYPERWEAVE, readme-ai), not a state-
    #           bearing label — state lives in the metric cells. Parse
    #           cells, run infer_state on each allowlisted (label, value)
    #           pair, take the most severe state.
    if spec.state == "active" and spec.value:
        from hyperweave.compose.layout import normalize_title
        from hyperweave.config.loader import load_badge_modes
        from hyperweave.core.enums import FrameType
        from hyperweave.core.state import infer_state

        allowlist = load_badge_modes()
        # Severity ordering when rolling up across multiple metric cells.
        # critical / failing share the most-severe slot — both render red.
        _SEVERITY = {
            "active": 0,
            "passing": 1,
            "building": 2,
            "warning": 3,
            "critical": 4,
            "failing": 4,
        }

        inferred: str = "active"
        if spec.type == FrameType.BADGE and spec.title:
            if normalize_title(spec.title) in allowlist:
                inferred = infer_state(spec.title, spec.value)
        elif spec.type == FrameType.STRIP:
            # Roll up across metric cells. v0.2.24 and earlier accidentally
            # got this for free because infer_state ran on the strip's
            # whole comma-separated value string and found "fail" in
            # "BUILD:failing" — a happy substring-match accident. v0.2.25's
            # title gate broke that path. Per-cell inference is the
            # principled replacement: only allowlisted cells contribute
            # state, and we pick the most severe.
            best_severity = 0
            for label, value in _parse_strip_metric_pairs(spec):
                if normalize_title(label) in allowlist:
                    cell_state = infer_state(label, value)
                    sev = _SEVERITY.get(cell_state, 0)
                    if sev > best_severity:
                        inferred = cell_state
                        best_severity = sev

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


def _parse_strip_metric_pairs(spec: ComposeSpec) -> list[tuple[str, str]]:
    """Parse strip metric (label, value) pairs from spec.

    Mirrors ``compose/resolver.py:_parse_metrics`` but lives here so engine
    step 0 can run state inference before resolve() is called. Two sources:

    * ``spec.slots`` entries with zones starting with ``metric`` —
      ``slot.value`` of the form ``"LABEL:value"``.
    * Comma-separated fallback in ``spec.value`` —
      ``"STARS:2.9k,FORKS:278,BUILD:failing"``.

    TODO: unify with ``resolver._parse_metrics`` when ``resolver.py`` is split
    (architecture review Phase 4, deferred to v0.3.1+). The duplication is
    intentional for now — engine step 0 runs before resolve(), so it can't
    import from resolver.py without a circular dependency. Unification target
    is ``core/`` once the resolver-too-fat split lands.
    """
    pairs: list[tuple[str, str]] = []
    for slot in spec.slots:
        if slot.zone.startswith("metric") and ":" in slot.value:
            k, v = slot.value.split(":", 1)
            pairs.append((k.strip(), v.strip()))
    if not pairs and spec.value:
        for pair_str in spec.value.split(","):
            stripped = pair_str.strip()
            if ":" in stripped:
                k, v = stripped.split(":", 1)
                pairs.append((k.strip(), v.strip()))
    return pairs


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
