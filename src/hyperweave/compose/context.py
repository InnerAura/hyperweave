"""Frame context builders — per-frame template variable construction.

Each builder produces the COMPLETE context dict for its frame type's Jinja2
template.  Common variables (uid, css, metadata, content) come from
``_base_context()``.  Frame-specific defaults are only set for their frame.

Motion SVG is injected by ``_inject_motion()`` after the context is built.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from hyperweave.core.enums import ArtifactStatus, FrameType, MotionId

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec, ResolvedArtifact

_CtxBuilder = Callable[["ComposeSpec", "ResolvedArtifact", dict[str, str]], dict[str, Any]]


def build_context(
    spec: ComposeSpec,
    resolved: ResolvedArtifact,
    css_bundle: dict[str, str],
) -> dict[str, Any]:
    """Dispatch to the per-frame context builder."""
    _BUILDERS: dict[str, _CtxBuilder] = {
        FrameType.BADGE: _ctx_badge,
        FrameType.STRIP: _ctx_strip,
        FrameType.BANNER: _ctx_banner,
        FrameType.ICON: _ctx_icon,
        FrameType.DIVIDER: _ctx_divider,
        FrameType.MARQUEE_HORIZONTAL: _ctx_marquee,
        FrameType.MARQUEE_VERTICAL: _ctx_marquee,
        FrameType.MARQUEE_COUNTER: _ctx_marquee,
        FrameType.RECEIPT: _ctx_receipt,
        FrameType.RHYTHM_STRIP: _ctx_rhythm_strip,
        FrameType.MASTER_CARD: _ctx_master_card,
        FrameType.CATALOG: _ctx_catalog,
    }
    builder = _BUILDERS.get(spec.type, _ctx_badge)
    ctx = builder(spec, resolved, css_bundle)
    _inject_motion(ctx, spec, resolved)
    return ctx


# ── Base context (shared by all frames) ──────────────────────────────


def _base_context(
    spec: ComposeSpec,
    resolved: ResolvedArtifact,
    css_bundle: dict[str, str],
) -> tuple[dict[str, Any], str, str]:
    """Build the shared context dict. Returns (context, uid, artifact_id)."""
    artifact_id = str(uuid.uuid7()) if hasattr(uuid, "uuid7") else str(uuid.uuid4())
    uid = f"hw-{artifact_id[:8]}"

    css_parts = [
        css_bundle["genome"],
        css_bundle.get("bridge", ""),
        css_bundle["expression"],
        css_bundle["status"],
        css_bundle["accessibility"],
        css_bundle.get("telemetry", ""),
        css_bundle.get("motion", ""),
    ]
    css_assembled = "\n".join(p for p in css_parts if p)

    profile = resolved.profile

    ctx: dict[str, Any] = {
        # Identity
        "uid": uid,
        "artifact_id": artifact_id,
        "contract_id": artifact_id,
        "frame_type": spec.type,
        "genome_id": spec.genome_id,
        "profile_id": resolved.profile_id,
        "divider_variant": spec.divider_variant,
        "status": spec.state,
        "state": spec.state,
        "regime": spec.regime,
        "variant": spec.variant,
        "motion_id": resolved.motion,
        "motion": resolved.motion,
        "metadata_tier": spec.metadata_tier,
        # Dimensions
        "width": resolved.width,
        "height": resolved.height,
        # CSS
        "css": css_assembled,
        # Content
        "title": spec.title,
        "label": spec.title,
        "value": spec.value,
        "description": spec.value,
        "slots": [s.model_dump() for s in spec.slots],
        "numeric_value": spec.numeric_value,
        "data_hw_value": spec.numeric_value,
        # Profile
        "profile": profile,
        "badge_corner": profile.get("badge_corner", 3.33),
        "strip_corner": profile.get("strip_corner", 5),
        "accent_bar_width": profile.get("strip_accent_width", 0),
        "status_shape": profile.get("status_shape", "circle"),
        # Glyph
        "glyph_id": resolved.glyph_id,
        "glyph_path": resolved.glyph_path,
        "glyph_viewbox": resolved.glyph_viewbox or "0 0 640 640",
        "glyph_mode": spec.glyph_mode,
        "has_glyph": bool(resolved.glyph_id),
        "glyph_svg": _build_glyph_svg(
            resolved,
            spec.glyph_mode,
            resolved.frame_context.get("glyph_fill", "var(--dna-signal)"),
        ),
        # Metadata / accessibility
        "title_text": _aria_title(spec),
        "desc_text": _aria_desc(spec),
        "metadata_xml": _build_metadata_xml(spec, resolved, artifact_id),
        # Document-level attributes (used by document.svg.j2 base template)
        "terminal_id": "",
        "rule_id": "",
        # Motion SVG placeholders
        "motion_svg": "",
        "motion_border_defs": "",
        "motion_border_overlay": "",
        # Telemetry
        "telemetry": spec.telemetry_data or {},
        # Timestamp
        "created": datetime.now(UTC).isoformat(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    return ctx, uid, artifact_id


# ── Per-frame builders ───────────────────────────────────────────────


def _ctx_badge(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_strip(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_banner(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_icon(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx["icon_variant"] = ""
    ctx["glyph_svg_inline"] = ""
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_divider(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_marquee(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx["scroll_items"] = []
    ctx["scroll_rows"] = []
    ctx["counter_rows"] = []
    ctx["rows"] = []
    ctx["header_right_label"] = ""
    ctx["header_label"] = "SYSTEM TELEMETRY"
    ctx["marquee_icon_svg"] = ""
    ctx["marquee_label"] = "LIVE"
    ctx["scroll_distance"] = 1000
    ctx["scroll_dur"] = 11.09
    ctx["beacon_pulse_dur"] = "2.618s"
    ctx["separator"] = "■"
    ctx["separator_color"] = "var(--dna-border)"
    ctx["bezel"] = 4
    ctx["surface_inset"] = 5
    ctx["fade_width"] = 36
    ctx["header_h"] = 33
    ctx["row_height"] = 30
    ctx["content_h"] = 360
    ctx["item_count"] = 12
    ctx["fade_h"] = 18
    ctx["dot_size"] = 4
    ctx["dot_x"] = 14
    ctx["text_x"] = 26
    ctx["status_label_x"] = 382
    ctx["bottom_accent_h"] = 3
    ctx["live_dot_size"] = 8
    ctx["pulse_dur"] = "2.618s"
    ctx["divider_y"] = 38
    ctx["label_panel_width"] = 130
    ctx["clip_x"] = 132
    ctx["divider_w"] = 2
    ctx["accent_line_opacity"] = 0.2
    ctx["item_dx"] = 20
    ctx["item_start_x"] = 148
    ctx["rivet_size"] = 6
    ctx["rivet_opacity"] = 0.4
    ctx["accent_bar_w"] = 4
    ctx["show_pulse"] = True
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_receipt(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx["hero_profile"] = ""
    ctx["hero_headline"] = ""
    ctx["hero_subline"] = ""
    ctx["hero_right_stats"] = []
    ctx["treemap_legend"] = []
    ctx["treemap_cells"] = []
    ctx["stage_count"] = 0
    ctx["duration_minutes"] = 0
    ctx["rhythm_bars"] = []
    ctx["phase_legend"] = []
    ctx["dominant_profile"] = ""
    ctx["tools"] = []
    ctx["stages"] = []
    ctx["footer_left"] = ""
    ctx["footer_right"] = ""
    ctx["receipt_items"] = []
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_rhythm_strip(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx["session_id_short"] = ""
    ctx["call_number"] = 0
    ctx["elapsed_label"] = ""
    ctx["token_summary"] = ""
    ctx["velocity_value"] = ""
    ctx["stages"] = []
    ctx["loop_detected"] = False
    ctx["loop_elevated"] = False
    ctx["loop_label"] = "NOMINAL"
    ctx["loop_detail"] = "no loop"
    ctx["profile_label"] = ""
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_master_card(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx["mc_title"] = "Session Summary"
    ctx["mc_subtitle"] = ""
    ctx["mc_total_tokens"] = ""
    ctx["mc_total_cost"] = ""
    ctx["mc_session_count"] = 0
    ctx["mc_sessions"] = []
    ctx["mc_sparkline_points"] = ""
    ctx["mc_skills"] = []
    ctx["mc_heatmap"] = []
    ctx["session_entries"] = []
    ctx["history_svg"] = ""
    ctx["burn_svg"] = ""
    ctx["heatmap_svg"] = ""
    ctx["tools"] = []
    ctx["stages"] = []
    ctx["loop_detected"] = False
    ctx["loop_elevated"] = False
    ctx["velocity"] = {}
    ctx["footer_left"] = ""
    ctx["footer_right"] = ""
    ctx.update(resolved.frame_context)
    return ctx


def _ctx_catalog(spec: ComposeSpec, resolved: ResolvedArtifact, css: dict[str, str]) -> dict[str, Any]:
    ctx, _uid, _aid = _base_context(spec, resolved, css)
    ctx["catalog_title"] = spec.title or "Genome Catalog"
    ctx["catalog_subtitle"] = ""
    ctx["catalog_items"] = []
    ctx["catalog_footer_left"] = ""
    ctx["catalog_footer_right"] = ""
    ctx.update(resolved.frame_context)
    return ctx


# ── Motion injection ─────────────────────────────────────────────────


def _inject_motion(ctx: dict[str, Any], spec: ComposeSpec, resolved: ResolvedArtifact) -> None:
    """Populate motion_border_defs/overlay or motion_svg in the context."""
    motion_id = ctx.get("motion_id", "static")
    if motion_id == MotionId.STATIC:
        return

    try:
        from hyperweave.render.motion import build_border_overlay, build_kinetic_motion_svg

        uid = ctx["uid"]
        w = ctx["width"]
        h = ctx["height"]
        rx = ctx.get("badge_corner", ctx.get("strip_corner", 3.33))

        # Panel geometry for rimrun seam-tracing
        seam_positions: list[int] = []
        if spec.type == FrameType.STRIP:
            seam_positions = [int(x) for x in ctx.get("seam_positions", [])]
            seam_x = int(ctx.get("first_divider_x", 0))
            lp_w = seam_x
            right_x_val = seam_x
        else:
            lp_w = int(ctx.get("left_panel_width", 0))
            right_x_val = int(ctx.get("right_panel_x", 0))

        defs_svg, overlay_svg = build_border_overlay(
            motion_id,
            uid,
            w,
            h,
            rx,
            lp_w=lp_w,
            right_x=right_x_val,
            seam_positions=seam_positions,
        )
        if defs_svg or overlay_svg:
            ctx["motion_border_defs"] = defs_svg
            ctx["motion_border_overlay"] = overlay_svg

        # Kinetic typography (banner only)
        if spec.type == FrameType.BANNER and not ctx.get("motion_border_overlay"):
            is_full = resolved.frame_context.get("banner_variant", "full") == "full"
            banner_fs = 160 if is_full else 42
            text_cx = w // 2
            text_cy = h // 2
            banner_subtitle = ctx.get("banner_label", ctx.get("banner_subtitle", ""))
            motion_svg = build_kinetic_motion_svg(
                motion_id,
                uid,
                spec.title or "HYPERWEAVE",
                text_cx,
                text_cy,
                banner_fs,
                w,
                h,
                subtitle=banner_subtitle,
            )
            if motion_svg:
                ctx["motion_svg"] = motion_svg
    except Exception:
        pass  # motion SVG generation must never break compose


# ── Helpers ──────────────────────────────────────────────────────────


def _build_glyph_svg(
    resolved: ResolvedArtifact,
    glyph_mode: str = "fill",
    glyph_fill_color: str = "var(--dna-signal)",
) -> str:
    if not resolved.glyph_path:
        return ""
    vb = resolved.glyph_viewbox or "0 0 640 640"
    from hyperweave.render.templates import render_template

    return render_template(
        "components/glyph-inline.svg.j2",
        {
            "glyph_viewbox": vb,
            "glyph_path": resolved.glyph_path,
            "glyph_mode": glyph_mode,
            "glyph_fill_color": glyph_fill_color,
        },
    )


def _aria_title(spec: ComposeSpec) -> str:
    if spec.title and spec.value:
        return f"{spec.title}: {spec.value}"
    if spec.title:
        return spec.title
    return f"HyperWeave {spec.type} artifact"


def _aria_desc(spec: ComposeSpec) -> str:
    parts = [f"A {spec.type} artifact"]
    if spec.genome_id:
        parts.append(f"using {spec.genome_id} genome")
    if spec.state != ArtifactStatus.ACTIVE:
        parts.append(f"in {spec.state} state")
    return ", ".join(parts) + "."


def _build_metadata_xml(
    spec: ComposeSpec,
    resolved: ResolvedArtifact,
    artifact_id: str,
) -> str:
    if spec.metadata_tier == 0:
        return ""
    from hyperweave.render.templates import render_template

    context = {
        "artifact_id": artifact_id,
        "spec_type": spec.type,
        "series": spec.series,
        "now": datetime.now(UTC).isoformat(),
        "width": resolved.width,
        "height": resolved.height,
        "category": resolved.category,
        "genome_id": spec.genome_id,
        "profile_id": resolved.profile_id,
        "divider_variant": spec.divider_variant,
        "platform": spec.platform,
        "motion": resolved.motion,
        "state": spec.state,
        "regime": spec.regime,
        "metadata_tier": spec.metadata_tier,
        "intent": spec.intent,
        "approach": spec.approach,
        "tradeoffs": spec.tradeoffs,
    }
    return render_template("components/metadata.xml.j2", context)
