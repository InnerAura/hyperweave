"""CSS assembler -- builds the optimal CSS bundle for each artifact type."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from hyperweave.core.enums import FrameType, MotionId

if TYPE_CHECKING:
    from hyperweave.core.models import ResolvedArtifact

# Frame types that use badge/strip state machine + status indicator animations
_STATEFUL_FRAMES: frozenset[str] = frozenset({FrameType.BADGE, FrameType.STRIP})

# Frame types that render provider/identity glyphs and need glyph-specific
# chromatic roles. These roles are not state-machine roles: stats and charts
# also consume them in their header identity slots.
_GLYPH_FRAMES: frozenset[str] = frozenset({FrameType.BADGE, FrameType.STRIP, FrameType.STATS, FrameType.CHART})

# Frame types that use bridge hw-* class mappings
_BRIDGE_FRAMES: frozenset[str] = frozenset({FrameType.BADGE, FrameType.STRIP, FrameType.ICON})

# Marquee frame types — need frame_fill, status colors, ink tiers
_MARQUEE_FRAMES: frozenset[str] = frozenset({FrameType.MARQUEE_HORIZONTAL})


# Font embedding gate: per-(genome_id, frame_type) lookup against the YAML
# config at ``data/font-embedding.yaml``. Replaces the v0.3.5 frozenset
# table that was keyed only by frame_type — which meant the brutalist
# badge embedded the genome's full font list (~28KB of unused Barlow
# Condensed base64) because the genome declared Barlow for stats/strip/
# chart and the badge frame's allowlist passed it through.
#
# The genome-aware lookup lets the brutalist badge embed only JetBrains
# Mono (the one font its CSS classes actually reference) while the
# brutalist stats card continues to embed all three fonts it needs.
# Adding a new (genome, frame) binding is a YAML edit only (Invariant 12).
def fonts_for_frame(frame_type: str, genome_id: str = "") -> frozenset[str]:
    """Return the font slugs to embed for ``(frame_type, genome_id)``.

    When ``genome_id`` matches a row in ``font-embedding.yaml``'s
    ``genomes`` block, returns that row's per-frame list. Otherwise
    falls back to ``defaults.<frame_type>`` — an empty list in v0.3.7,
    matching icon/divider semantics for callers without resolved genome
    context (e.g. ``_error_badge``).

    The composer further intersects this with the genome's declared
    ``fonts`` list at ``compose/context.py:_load_font_faces``, so a slug
    listed here that the genome does not declare is a noop.
    """
    from hyperweave.config.loader import load_font_embedding

    embedding = load_font_embedding()
    genome_block = embedding["genomes"].get(genome_id) if genome_id else None
    if isinstance(genome_block, dict) and frame_type in genome_block:
        slugs = genome_block.get(frame_type) or []
    else:
        slugs = embedding["defaults"].get(frame_type) or []
    return frozenset(slugs)


def frame_needs_fonts(frame_type: str, genome_id: str = "") -> bool:
    """Per-(frame_type, genome_id) font-loading gate. Returns True when
    any fonts should be embedded — used by context-builder to gate the
    ``data-hw-fonts="self-contained"`` SVG-root attribute and the
    ``hw:css-modules`` debug comment.
    """
    return bool(fonts_for_frame(frame_type, genome_id))


# Genome fields that signal a telemetry skin (presence-gates the tool-color CSS block)
_TELEMETRY_GENOME_FIELDS: tuple[str, ...] = (
    "tool_explore",
    "tool_execute",
    "tool_mutate",
    "tool_coordinate",
    "tool_reflect",
)


# Field-to-CSS-var mappings extracted from genome_to_css() so compute_variant_inline_style()
# can share the same translation table. Variant overrides are sparse dicts whose keys are
# genome-field names; the assembler looks each one up across these mappings to emit --dna-*
# declarations on the SVG root. Adding a new genome field that participates in chrome-style
# variant overrides means adding it to one of these tables — single source of truth.

_CORE_CSS_MAPPING: list[tuple[str, str]] = [
    # Surfaces
    ("surface_0", "--dna-surface"),
    ("surface_1", "--dna-surface-alt"),
    ("surface_2", "--dna-surface-deep"),
    # Inks
    ("ink", "--dna-ink-primary"),
    ("ink_secondary", "--dna-ink-muted"),
    ("ink_on_accent", "--dna-ink-on-accent"),
    ("ink_bright", "--dna-ink-bright"),
    ("ink_sub", "--dna-ink-sub"),
    # Signals
    ("accent", "--dna-signal"),
    ("accent_complement", "--dna-signal-dim"),
    # Component-specific (chrome diamond — single-responsibility, no aliasing)
    ("diamond_stroke", "--dna-diamond-stroke"),
    ("diamond_housing", "--dna-diamond-housing"),
    # Borders
    ("stroke", "--dna-border"),
    ("border_tint", "--dna-border-tint"),
    ("stroke_opacity", "--dna-stroke-opacity"),
    # Seam (brutalist light-scholar INK-SEAM-INK middle bar; brutalist strip
    # seam accent)
    ("seam_color", "--dna-seam-color"),
    # Brand panel inset fill (brutalist strip — dark variant brand panel
    # solid tone; light variants use panel_gradient_stops + url(#panel) instead).
    ("brand_panel_fill", "--dna-brand-panel-fill"),
    # Chart title-zone background tone — per-variant tinted-paper hex captured
    # from the v0.3.2 brutalist light chart prototype. Pulse #ECDBC0
    # warm cream, depth #DFE3EB cool gray-blue, signal #DAE0D4 cool sage, etc.
    # Defaults to surface-deep when a variant doesn't declare its own.
    ("chart_title_bg", "--dna-chart-title-bg"),
    # Shadow / Glow
    ("shadow_color", "--dna-shadow-color"),
    ("shadow_opacity", "--dna-shadow-opacity"),
    ("glow", "--dna-glow"),
    # Geometry
    ("corner", "--dna-corner"),
    # Rhythm
    ("rhythm_base", "--dna-rhythm-base"),
    # Extended palette (used by templates)
    ("bg", "--dna-bg"),
    ("bg_alt", "--dna-bg-alt"),
    ("brand_text", "--dna-brand-text"),
]

_STATEFUL_CSS_MAPPING: list[tuple[str, str]] = [
    ("accent_signal", "--dna-status-passing-core"),
    ("accent_warning", "--dna-status-warning-core"),
    ("accent_error", "--dna-status-failing-core"),
    ("rhythm_slow", "--dna-rhythm-slow"),
    ("rhythm_fast", "--dna-rhythm-fast"),
    ("density", "--dna-density"),
    ("metric_text", "--dna-metric-text"),
    ("label_text", "--dna-label-text"),
    ("seam_gap", "--dna-seam-gap"),
    ("badge_value_text", "--dna-badge-value-text"),
    ("badge_pass_sep", "--dna-badge-pass-sep"),
    ("badge_pass_core", "--dna-badge-pass-core"),
    ("badge_warn_color", "--dna-badge-warn-color"),
    ("material_specular", "--dna-material-specular"),
    ("material_roughness", "--dna-material-roughness"),
]

_GLYPH_CSS_MAPPING: list[tuple[str, str]] = [
    ("glyph_inner", "--dna-glyph-inner"),
]

_MARQUEE_CSS_MAPPING: list[tuple[str, str]] = [
    ("frame_fill", "--dna-frame-fill"),
    ("accent_signal", "--dna-status-passing-core"),
    ("accent_warning", "--dna-status-warning-core"),
    ("accent_error", "--dna-status-failing-core"),
    ("ink_secondary", "--dna-ink-secondary"),
    ("ink_on_accent", "--dna-ink-on-accent"),
    ("label_text", "--dna-label-text"),
]

_TELEMETRY_CSS_MAPPING: list[tuple[str, str]] = [
    ("accent_signal", "--dna-status-passing-core"),
    ("accent_warning", "--dna-status-warning-core"),
    ("accent_error", "--dna-status-failing-core"),
    ("ink_sub", "--dna-ink-tertiary"),
    ("label_text", "--dna-ink-ghost"),
    ("border_tint", "--dna-border-div"),
    ("tool_explore", "--dna-tool-explore"),
    ("tool_execute", "--dna-tool-execute"),
    ("tool_mutate", "--dna-tool-mutate"),
    ("tool_coordinate", "--dna-tool-coordinate"),
    ("tool_reflect", "--dna-tool-reflect"),
    # Receipt compositor tokens (v0.2.21)
    ("pill_outer_bg", "--dna-pill-outer-bg"),
    ("pill_outer_stroke", "--dna-pill-outer-stroke"),
    ("pill_inner_bg", "--dna-pill-inner-bg"),
    ("pill_text", "--dna-pill-text"),
    ("pill_rule_top", "--dna-pill-rule-top"),
    ("pill_rule_bottom", "--dna-pill-rule-bottom"),
    ("glyph_fill", "--dna-glyph-fill"),
    ("card_border", "--dna-card-border"),
    ("card_border_top", "--dna-card-border-top"),
    ("card_inner_glyph", "--dna-card-inner-glyph"),
    ("card_top_highlight_color", "--dna-card-top-highlight"),
]

_FONT_CSS_MAPPING: list[tuple[str, str]] = [
    ("font_display", "--dna-font-display"),
    ("font_mono", "--dna-font-mono"),
]

# Multi-target lookup: one genome field may emit MULTIPLE --dna-* CSS vars
# because the four mappings (core/stateful/marquee/telemetry) name the same
# concept differently across frame types. For example, `ink_secondary` maps
# to --dna-ink-muted in core (stats/chart/icon) AND --dna-ink-secondary in
# marquee. Similarly `label_text` maps to --dna-label-text (stateful) AND
# --dna-ink-ghost (telemetry). Without multi-target emission, a variant
# override on ink_secondary would only update ONE of those vars — leaving
# stats CSS classes that reference --dna-ink-muted reading the base
# genome's emerald instead of the variant's accent-light.
#
# `_ALL_CSS_MAPPING_KEYS` is the set of fields that have ANY mapping; used
# to detect which override entries are chromatic vs structural (e.g.
# substrate_kind / panel_gradient_stops have no CSS var representation).
_ALL_CSS_MAPPING: dict[str, list[str]] = {}
for _mapping in (
    _CORE_CSS_MAPPING,
    _STATEFUL_CSS_MAPPING,
    _GLYPH_CSS_MAPPING,
    _MARQUEE_CSS_MAPPING,
    _TELEMETRY_CSS_MAPPING,
    _FONT_CSS_MAPPING,
):
    for _field, _prop in _mapping:
        if _field not in _ALL_CSS_MAPPING:
            _ALL_CSS_MAPPING[_field] = []
        if _prop not in _ALL_CSS_MAPPING[_field]:
            _ALL_CSS_MAPPING[_field].append(_prop)


def compute_variant_inline_style(genome: dict[str, Any], resolved_variant: str) -> str:
    """Return CSS declarations for the SVG-root style attribute (chrome variant overrides).

    Reads ``genome["variant_overrides"][resolved_variant]`` — a sparse dict like
    ``{"surface_0": "#020E12", "ink": "#C8F0E8"}`` — translates each key via
    ``_ALL_CSS_MAPPING``, and emits a string like
    ``"--dna-surface:#020E12; --dna-ink-primary:#C8F0E8;"``.

    Returns ``""`` when the genome has no ``variant_overrides`` for this variant
    (including the bare/flagship case). An empty string suppresses the
    ``style="..."`` attribute entirely in ``document.svg.j2`` so URLs without
    overrides remain byte-equal to pre-v0.3 output.

    Unknown genome-field keys silently skip — the Pydantic field validator on
    ``GenomeSpec.variant_overrides`` catches typos at config-load time, so this
    branch only fires on fields that are deliberately structural (no CSS-var
    representation).

    Values are HTML-attribute-escaped (``"``, ``<``, ``>``) to prevent
    inline-style attribute injection from a malicious genome JSON.
    """
    if not resolved_variant:
        return ""
    overrides = (genome.get("variant_overrides") or {}).get(resolved_variant) or {}
    if not overrides:
        return ""

    declarations: list[str] = []
    for field, value in overrides.items():
        props = _ALL_CSS_MAPPING.get(field)
        if not props or not value:
            continue
        safe = str(value).replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
        # Emit one declaration per target CSS var. Fields with multiple
        # targets (ink_secondary, label_text) fan out so every consumer
        # reads the variant's override instead of the base genome value.
        for prop in props:
            declarations.append(f"{prop}:{safe};")
    return " ".join(declarations)


def assemble_css(resolved: ResolvedArtifact, frame_type: str = "") -> dict[str, str]:
    """Assemble frame-aware CSS for an artifact.

    Only includes CSS layers that the specific frame type actually uses:
    - genome DNA variables → ALL frames
    - bridge classes → badge, strip, icon
    - expression layer → badge, strip
    - status animations → badge, strip only
    - accessibility → ALL frames
    - motion CSS → only when motion != static
    """
    genome = resolved.genome
    if not frame_type:
        frame_type = resolved.frame_template.replace("frames/", "").replace(".svg.j2", "")
    motion_id = resolved.motion

    css: dict[str, str] = {
        "genome": genome_to_css(genome, frame_type),
        "accessibility": _load_css_file("accessibility.css"),
    }

    # Bridge classes — only for frames that use hw-* semantic classes
    if frame_type in _BRIDGE_FRAMES:
        css["bridge"] = _load_css_file("bridge.css")
    else:
        css["bridge"] = ""

    # Expression layer — badge/strip get full; others get nothing
    # (badge state machine, living value thresholds, typography classes)
    if frame_type in _STATEFUL_FRAMES:
        css["expression"] = _load_css_file("expression.css")
    else:
        css["expression"] = ""

    # Status indicator animations — only badge/strip have .hw-logic-bit
    if frame_type in _STATEFUL_FRAMES:
        css["status"] = _load_css_file("status.css")
    else:
        css["status"] = ""

    # Motion CSS — only when a motion is active
    css["motion"] = _load_motion_css(motion_id) if motion_id != MotionId.STATIC else ""

    return css


def genome_to_css(genome: dict[str, Any], frame_type: str = "") -> str:
    """Convert genome JSON fields to CSS custom properties.

    Frame-aware: badge/strip-only variables are excluded from other frame types.
    Consumes the module-level mapping constants so compute_variant_inline_style()
    shares the same translation table — adding a new genome chromatic field that
    participates in chrome-style variant overrides means adding it to one of the
    mapping tables once.
    """
    # Build the frame-aware mapping by combining the core mapping with the
    # appropriate frame-specific extension. Telemetry skin is presence-gated:
    # any genome declaring tool_* fields gets the tool-class + status-color +
    # extended-ink mappings regardless of frame.
    mapping: list[tuple[str, str]] = list(_CORE_CSS_MAPPING)
    if frame_type in _GLYPH_FRAMES:
        mapping.extend(_GLYPH_CSS_MAPPING)
    if frame_type in _STATEFUL_FRAMES:
        mapping.extend(_STATEFUL_CSS_MAPPING)
    elif frame_type in _MARQUEE_FRAMES:
        mapping.extend(_MARQUEE_CSS_MAPPING)
    elif any(genome.get(f) for f in _TELEMETRY_GENOME_FIELDS):
        mapping.extend(_TELEMETRY_CSS_MAPPING)

    lines = ["svg, :root {"]

    for field, prop in mapping:
        val = genome.get(field)
        if val:  # skip empty/None — lets CSS var() fallbacks activate
            lines.append(f"  {prop}: {val};")

    for field, prop in _FONT_CSS_MAPPING:
        val = genome.get(field)
        if val:  # skip empty — lets CSS var() fallbacks activate
            lines.append(f"  {prop}: {val};")

    if "sep" not in genome and "stroke" in genome:
        lines.append(f"  --dna-sep: {genome['stroke']};")

    if "status_delta_positive" not in genome:
        lines.append("  --dna-status-delta-positive: #22C55E;")
    if "status_delta_negative" not in genome:
        lines.append("  --dna-status-delta-negative: #DC2626;")

    lines.append("}")

    # Telemetry typography utility classes — used by receipt + rhythm-strip
    # templates (class="s ink1", "m ink2", etc.). Gated by the same telemetry-skin
    # presence check so badge/strip/icon don't carry these unused selectors.
    if any(genome.get(f) for f in _TELEMETRY_GENOME_FIELDS):
        lines.extend(
            [
                ".m { font-family: var(--dna-font-mono); }",
                ".s { font-family: var(--dna-font-display); }",
                ".ink1 { fill: var(--dna-ink-primary); }",
                ".ink2 { fill: var(--dna-ink-muted); }",
                ".ink3 { fill: var(--dna-ink-tertiary); }",
                "@media (forced-colors: active) { text { fill: CanvasText; } }",
            ]
        )

    # Light mode overrides
    light = genome.get("light_mode")
    if light and isinstance(light, dict):
        lm_map: list[tuple[str, str]] = [
            ("surface", "--dna-surface"),
            ("surface", "--dna-surface-top"),
            ("surface_alt", "--dna-surface-alt"),
            ("surface_deep", "--dna-surface-deep"),
            ("surface", "--dna-bg"),
            ("surface_alt", "--dna-bg-alt"),
            ("ink", "--dna-ink"),
            ("ink", "--dna-ink-primary"),
            ("ink", "--dna-ink-dark"),
            ("ink_muted", "--dna-ink-muted"),
            ("ink_muted", "--dna-ink-sub"),
            ("ink_ghost", "--dna-ink-ghost"),
            ("border", "--dna-border"),
            ("border", "--dna-border-div"),
            ("sep", "--dna-sep"),
        ]
        lines.append("@media (prefers-color-scheme: light) {")
        lines.append("  svg {")
        for field, prop in lm_map:
            val = light.get(field)
            if val is not None:
                lines.append(f"    {prop}: {val};")
        lines.append("  }")
        lines.append("}")

    return "\n".join(lines)


def _load_css_file(filename: str) -> str:
    css_path = _css_dir() / filename
    if css_path.exists():
        return css_path.read_text()
    return f"/* {filename} not found */"


def _load_motion_css(motion_id: str) -> str:
    try:
        from hyperweave.render.motion import get_motion_css

        compatible: list[str] = []
        return get_motion_css(motion_id, compatible)
    except (ImportError, Exception):
        return ""


def _css_dir() -> Path:
    try:
        from hyperweave.config.settings import get_settings

        return get_settings().data_dir / "css"
    except (ImportError, Exception):
        return Path(__file__).parent.parent / "data" / "css"
