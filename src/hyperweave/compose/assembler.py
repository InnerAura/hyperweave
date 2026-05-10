"""CSS assembler -- builds the optimal CSS bundle for each artifact type."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from hyperweave.core.enums import FrameType, MotionId

if TYPE_CHECKING:
    from hyperweave.core.models import ResolvedArtifact

# Frame types that use badge/strip state machine + status indicator animations
_STATEFUL_FRAMES: frozenset[str] = frozenset({FrameType.BADGE, FrameType.STRIP})

# Frame types that use bridge hw-* class mappings
_BRIDGE_FRAMES: frozenset[str] = frozenset({FrameType.BADGE, FrameType.STRIP, FrameType.ICON})

# Marquee frame types — need frame_fill, status colors, ink tiers
_MARQUEE_FRAMES: frozenset[str] = frozenset({FrameType.MARQUEE_HORIZONTAL})

# Per-frame font allowlist: maps each frame type to the font slugs that frame's
# templates actually render. Frames absent from the dict embed zero fonts (icon,
# divider). This is a refinement of the pre-v0.3.0 binary gate (frozenset of
# frame names): the dict shape lets each frame declare exactly the slugs it
# needs, so a marquee carrying only Orbitron text doesn't ship JetBrains Mono
# and Chakra Petch base64 payloads it never references.
#
# Slugs match the keys in ``data/fonts/{slug}.b64`` and the entries in genome
# ``fonts`` lists. The intersection of the genome's font list and a frame's
# allowed slugs is what actually gets embedded.
#
# Per-frame allocation rationale:
# - BADGE / STRIP / RECEIPT / RHYTHM_STRIP / MASTER_CARD / CATALOG: full 3-font
#   set — these frames render mixed typography (mono labels, display values,
#   chakra-petch metrics).
# - STATS: full 3-font set — Chakra Petch for metric values, Orbitron for
#   username/title, JetBrains Mono for labels.
# - CHART: Orbitron (header zone) + JetBrains Mono (axis labels). Chart never
#   renders Chakra Petch — saving ~13KB per chart artifact.
# - MARQUEE_HORIZONTAL: Orbitron only. Cellular marquee scroll text is Orbitron
#   11px 700 with no other typography. Saving ~55KB per marquee artifact.
# - ICON / DIVIDER: not in dict — zero fonts. Glyph-only rendering, no <text>
#   elements.
_NEEDS_FONTS: dict[str, frozenset[str]] = {
    FrameType.BADGE: frozenset({"jetbrains-mono", "orbitron", "chakra-petch"}),
    FrameType.STRIP: frozenset({"jetbrains-mono", "orbitron", "chakra-petch"}),
    FrameType.STATS: frozenset({"jetbrains-mono", "orbitron", "chakra-petch"}),
    FrameType.CHART: frozenset({"jetbrains-mono", "orbitron"}),
    FrameType.MARQUEE_HORIZONTAL: frozenset({"orbitron"}),
    FrameType.RECEIPT: frozenset({"jetbrains-mono", "orbitron", "chakra-petch"}),
    FrameType.RHYTHM_STRIP: frozenset({"jetbrains-mono", "orbitron", "chakra-petch"}),
    FrameType.MASTER_CARD: frozenset({"jetbrains-mono", "orbitron", "chakra-petch"}),
    FrameType.CATALOG: frozenset({"jetbrains-mono", "orbitron", "chakra-petch"}),
}


def frame_needs_fonts(frame_type: str) -> bool:
    """Per-frame font-loading gate. Returns True if any fonts should be
    embedded for this frame type. Frames absent from the ``_NEEDS_FONTS`` dict
    return False — icon and divider render glyph-only with no ``<text>``
    elements, so embedding fonts in them is pure payload waste.
    """
    return frame_type in _NEEDS_FONTS


def fonts_for_frame(frame_type: str) -> frozenset[str]:
    """Return the set of font slugs allowed for embedding in ``frame_type``'s
    templates. Empty set for frames that don't render text. The font loader
    intersects this with the genome's declared font list so genomes that don't
    declare a slug still skip it even if the frame allows it."""
    return _NEEDS_FONTS.get(frame_type, frozenset())


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
    ("glyph_inner", "--dna-glyph-inner"),
    ("seam_gap", "--dna-seam-gap"),
    ("badge_value_text", "--dna-badge-value-text"),
    ("badge_pass_sep", "--dna-badge-pass-sep"),
    ("badge_pass_core", "--dna-badge-pass-core"),
    ("badge_warn_color", "--dna-badge-warn-color"),
    ("material_specular", "--dna-material-specular"),
    ("material_roughness", "--dna-material-roughness"),
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
]

_FONT_CSS_MAPPING: list[tuple[str, str]] = [
    ("font_display", "--dna-font-display"),
    ("font_mono", "--dna-font-mono"),
]

# Flat lookup spanning every (genome_field → css_var) pair we know how to emit.
# Used by compute_variant_inline_style() to translate sparse override dicts into
# CSS declarations. Conflicts (e.g. accent_signal appears in stateful, marquee,
# telemetry) collapse to the first occurrence — they all map to the same --dna-*
# property anyway, so the duplication is benign.
_ALL_CSS_MAPPING: dict[str, str] = {
    field: prop
    for mapping in (
        _CORE_CSS_MAPPING,
        _STATEFUL_CSS_MAPPING,
        _MARQUEE_CSS_MAPPING,
        _TELEMETRY_CSS_MAPPING,
        _FONT_CSS_MAPPING,
    )
    for field, prop in mapping
}


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
        prop = _ALL_CSS_MAPPING.get(field)
        if prop is None or not value:
            continue
        safe = str(value).replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
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

    # Telemetry typography utility classes — used by receipt + rhythm-strip + master-card
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
