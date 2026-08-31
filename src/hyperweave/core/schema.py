"""Genome schema validation."""

from __future__ import annotations

import math
import re
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

# Golden ratio for rhythm validation
PHI: float = 1.618033988749895
PHI_TOLERANCE: float = 0.15  # 15% tolerance on rhythm ratios

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
# RGB channels are bounded 0-255 and alpha 0-1: an out-of-gamut
# ``rgba(999,999,999,9)`` is not a color a renderer can honor, and accepting
# one let an unrenderable paint through the genome boundary.
_RGB_CHANNEL = r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)"
_ALPHA = r"(?:0|1|0?\.\d+|1\.0+)"
_RGBA_RE = re.compile(rf"^rgba?\(\s*{_RGB_CHANNEL}\s*,\s*{_RGB_CHANNEL}\s*,\s*{_RGB_CHANNEL}\s*(?:,\s*{_ALPHA}\s*)?\)$")
# One CSS <time> grammar for every duration field: a finite, non-negative
# number with an explicit unit. NaN, infinity, negatives, and unitless values
# are excluded by construction — ``rhythm_base="nan"`` used to reach
# ``--dna-rhythm-base: nan`` and poison every derived rhythm.
_CSS_TIME_RE = re.compile(r"^\d+(?:\.\d+)?(?:ms|s)$")


def is_slug(value: str) -> bool:
    """The shared identifier grammar for values that reach markup as-is."""
    return bool(_SLUG_RE.match(value))


def _is_hex(value: str) -> bool:
    return bool(_HEX_RE.match(value))


def _is_color(value: str) -> bool:
    """True for hex (``#RRGGBB``) or in-gamut rgb/rgba (``rgba(R,G,B,A)``).

    Genomes that participate in atmospheric layering (v0.2.23 codex skin)
    declare translucent rgba surfaces so a backdrop gradient can bleed
    through. Genomes that don't atmosphere-layer keep using hex.
    """
    return _is_hex(value) or bool(_RGBA_RE.match(value))


def _is_css_time(value: str) -> bool:
    """A duration token this codebase can do arithmetic on.

    Grammar alone is not enough: ``"1e400"`` is excluded by the pattern, but a
    long-enough literal decimal still overflows to ``inf`` in ``float()``, and
    a zero base divides by zero when the phi ladder derives from it. The
    parsed magnitude must therefore be finite and strictly positive — every
    one of these fields is an animation PERIOD, where zero means "no clock",
    not "instant".
    """
    v = value.strip().lower()
    if not _CSS_TIME_RE.match(v):
        return False
    seconds = float(v[:-2]) / 1000.0 if v.endswith("ms") else float(v[:-1])
    return math.isfinite(seconds) and seconds > 0.0


def _parse_duration(value: str) -> float:
    """Seconds from a CSS ``<time>`` token, under the single duration grammar.

    :raises ValueError: for anything outside that grammar — the arithmetic
        below (phi ladders, rhythm derivatives) is only meaningful on a
        finite, strictly positive duration.
    """
    v = value.strip().lower()
    if not _is_css_time(v):
        msg = f"expected a finite positive CSS time like '2.618s' or '400ms', got {value!r}"
        raise ValueError(msg)
    return float(v[:-2]) / 1000.0 if v.endswith("ms") else float(v[:-1])


# -- Injection-boundary leaf grammars (P0 genome_override hardening) --
# A genome value lands raw in a <style> block or an SVG attribute
# (autoescape=False), so every value must be grammar-valid for its sink
# BEFORE it reaches the assembler. These grammars bound the whole GenomeSpec
# surface; the recursive sweep below them is defense in depth over the
# free-form dicts, never the boundary itself.

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
# Case-tolerant identifier for tokens that are labels rather than dispatch
# slugs (``stratum`` ships "002-TRIBE"): still bounded to identifier
# characters so it cannot break the attribute it lands in.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_PERCENT_RE = re.compile(r"^\d+(\.\d+)?%$")
_NUMBER_RE = re.compile(r"^-?\d+(\.\d+)?$")
_CSS_LENGTH_RE = re.compile(r"^-?\d+(\.\d+)?(px|em|rem|%)?$")
# One font family: bare identifier run (leading '-' covers -apple-system) or a
# SINGLE-quoted name. Double quotes are excluded deliberately: the stack lands
# inside a double-quoted `stack="..."` metadata attribute, so permitting them
# would let a lawful stack break its own attribute.
_FONT_FAMILY = r"(?:-?[A-Za-z][A-Za-z0-9 _-]*|'[A-Za-z0-9 _-]+')"
_FONT_STACK_RE = re.compile(rf"^\s*{_FONT_FAMILY}(\s*,\s*{_FONT_FAMILY})*\s*$")
# CSS/markup breakout vectors forbidden in every string leaf regardless of
# field class: element/entity syntax, control chars, external fetches,
# escapes that smuggle any of the former past a character check.
_CSS_DANGEROUS_RE = re.compile(r"[<>\\\x00-\x1f]|url\s*\(|@import", re.IGNORECASE)
# The strict default additionally forbids declaration/block/string breakout.
# ``&`` is here because a genome value reaches CSS and inline styles inside an
# XML document: an unescaped ``&`` parses as an entity reference, so "x&y" made
# the composed SVG unparseable (`undefined entity`) from a value that had
# passed validation.
_STRICT_EXTRA_RE = re.compile(r"[\"';{}&]")

# String fields whose value is a font stack (controlled quotes + commas).
# Covers the flat fields, typography-cascade keys, and variant overrides of
# either — classified by the nearest dict key during the sweep.
_FONT_STACK_KEYS = frozenset({"font_display", "font_mono", "scholar_heading_font", "hero_font", "mono_font"})
# Documentation prose (never enters a render path): quotes/semicolons allowed,
# markup and fetch vectors still forbidden.
_PROSE_FIELDS = frozenset({"name", "variant_phenomenology"})

# ── Variant-override contract ───────────────────────────────────────────────
# A sparse override is merged into the genome AFTER model validation, so every
# key it may carry needs a declared kind — otherwise nested structures ride in
# as raw dicts governed only by the character sweep (a gradient stop with
# offset "x&y" broke the composed SVG; a role color "notacolor" emitted invalid
# CSS). Keys the GenomeSpec model already owns validate through the model; the
# table below closes the remaining vocabulary. Anything unlisted is refused.
#
# CONTROL-PLANE keys are refused outright: a variant may restyle the artifact,
# never re-identify it. `{"id": "other"}` in an override changed the emitted
# data-hw-genome away from the requested genome; profile/paradigms/variants/
# compatible_motions likewise select dispatch, policy and topology rather than
# color.
VARIANT_CONTROL_PLANE_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "name",
        "profile",
        "category",
        "paradigms",
        "variants",
        "flagship_variant",
        "variant_overrides",
        "variant_tones",
        "variant_phenomenology",
        "compatible_motions",
        "roles",
        "fonts",
        "dividers",
        "stratum",
        "default_surface",
    }
)

# kind -> the value grammar each non-GenomeSpec override key must satisfy.
VARIANT_EXTRA_KINDS: dict[str, str] = {
    "brand_panel_fill": "color",
    "chart_title_bg": "color",
    "region_fill": "color",
    "region_stroke": "color",
    "seam_color": "color",
    "receipt_area_fill": "color",
    "receipt_dim_ink": "color",
    "receipt_eyebrow": "color",
    "receipt_grid_ink": "color",
    "receipt_label_ink": "color",
    "receipt_signal": "color",
    "receipt_track": "color",
    "receipt_track_stroke": "color",
    "receipt_value_ink": "color",
    "stroke_opacity": "unit_number",
    "substrate_kind": "substrate",
    "panel_gradient_stops": "stops",
    "receipt_ramp": "color_list",
    "diagram_dark": "color_map_roles",
    "diagram_faces": "face_map",
}

_SUBSTRATE_KINDS: frozenset[str] = frozenset({"light", "dark"})

# Per-LEAF paint policy for heterogeneous role maps. A blanket kind on
# ``diagram_dark`` was wrong in the same way one universal grammar was wrong at
# the top level: the map mixes edge washes that are legitimately translucent
# with the semantic ink the diagram reads by. ``ink`` at alpha 0.0001 emitted
# --dna-ink-primary as effectively invisible text while the artifact stayed
# valid XML and kept claiming WCAG-AA. Only the washes below may carry alpha;
# every other role — declared or added later — defaults to opaque.
_ROLE_MAP_TRANSLUCENT_LEAVES: dict[str, frozenset[str]] = {
    "diagram_dark": frozenset({"border", "edge_faint", "edge_hi", "edge_lo", "edge_mid"}),
}


# ── Paint policy ────────────────────────────────────────────────────────────
# One grammar for every colour field was too permissive in the other
# direction: `badge_value_text = "transparent"` (or any zero-alpha rgba)
# passed while the artifact still declared a11y="WCAG-AA" — an invisible
# semantic value. The model already drew this distinction (ink and accents
# require opaque hex because alpha blending destroys readability; only
# specific receipt/pill layers document `transparent` as meaningful), so the
# policy is per field, and OPAQUE is the default a new field inherits.
#
# translucent: atmospheric layers that legitimately let a backdrop through —
#   the surfaces and stroke `validate_surface_colors` already documents, plus
#   border_tint, which ships rgba in the corpus.
_TRANSLUCENT_PAINT_FIELDS: frozenset[str] = frozenset({"surface_0", "surface_1", "surface_2", "stroke", "border_tint"})
# optional: layers whose own description documents `transparent` as the way to
#   render the element absent (the receipt card frame and pill chrome).
_OPTIONAL_PAINT_FIELDS: frozenset[str] = frozenset(
    {
        "card_border",
        "card_border_top",
        "pill_outer_bg",
        "pill_outer_stroke",
        "pill_rule_top",
        "pill_rule_bottom",
    }
)


def paint_kind(field: str) -> str:
    """The paint policy for a chromatic field: opaque | translucent | optional."""
    if field in _OPTIONAL_PAINT_FIELDS:
        return "optional"
    if field in _TRANSLUCENT_PAINT_FIELDS:
        return "translucent"
    return "opaque"


def is_paint(value: object, kind: str = "opaque") -> bool:
    """Whether ``value`` is a lawful paint under ``kind``.

    ``opaque`` admits hex and fully-opaque rgb(a); ``translucent`` admits any
    in-gamut alpha; ``optional`` additionally admits the ``transparent``
    keyword. A zero-alpha rgba is refused wherever ``transparent`` is, because
    the two are the same claim written differently.
    """
    if not isinstance(value, str):
        return False
    if kind == "optional" and value == "transparent":
        return True
    if _is_hex(value):
        return True
    if not _RGBA_RE.match(value):
        return False
    alpha = float(value.rsplit(",", 1)[-1].strip(" )")) if value.count(",") >= 3 else 1.0
    if kind == "opaque":
        return alpha >= 1.0
    if kind == "translucent":
        # A zero-alpha atmospheric layer is invisible, which is what `optional`
        # exists to express — here it is a mistake, not a request.
        return alpha > 0.0
    return True


def _is_paint(value: object) -> bool:
    """Back-compat leaf check used by gradient stops (which legitimately fade
    to transparent)."""
    return isinstance(value, str) and (_is_color(value) or value == "transparent")


def check_override_value(key: str, kind: str, value: object, where: str) -> list[str]:
    """Violations for one typed override value. Empty list means lawful."""
    if kind in {"color", "color_translucent"}:
        paint = "translucent" if kind == "color_translucent" else "opaque"
        return [] if is_paint(value, paint) else [f"{where}.{key}: expected {paint} paint, got {value!r}"]
    if kind == "unit_number":
        return [] if _is_opacity(value) else [f"{where}.{key}: expected a 0-1 number token, got {value!r}"]
    if kind == "substrate":
        return (
            []
            if value in _SUBSTRATE_KINDS
            else [f"{where}.{key}: expected one of {sorted(_SUBSTRATE_KINDS)}, got {value!r}"]
        )
    if kind == "stops":
        if not isinstance(value, list):
            return [f"{where}.{key}: expected a list of gradient stops, got {type(value).__name__}"]
        return [p for i, stop in enumerate(value) for p in _check_gradient_stop(stop, f"{where}.{key}[{i}]")]
    if kind == "color_list":
        if not isinstance(value, list):
            return [f"{where}.{key}: expected a list of colors, got {type(value).__name__}"]
        return [
            f"{where}.{key}[{i}]: expected opaque paint, got {item!r}"
            for i, item in enumerate(value)
            if not is_paint(item)
        ]
    if kind in {"color_map", "color_map_roles"}:
        if not isinstance(value, dict):
            return [f"{where}.{key}: expected a role->color map, got {type(value).__name__}"]
        washes = _ROLE_MAP_TRANSLUCENT_LEAVES.get(key, frozenset()) if kind == "color_map_roles" else frozenset()
        problems = []
        for role, paint in value.items():
            leaf = "translucent" if role in washes else "opaque"
            if not is_paint(paint, leaf):
                problems.append(f"{where}.{key}.{role}: expected {leaf} paint, got {paint!r}")
        return problems
    if kind == "face_map":
        if not isinstance(value, dict):
            return [f"{where}.{key}: expected a face->role map, got {type(value).__name__}"]
        problems: list[str] = []
        for face, roles in value.items():
            if face not in _SUBSTRATE_KINDS:
                problems.append(f"{where}.{key}: unknown face {face!r}")
                continue
            problems.extend(check_override_value(face, "color_map", roles, f"{where}.{key}"))
        return problems
    return [f"{where}.{key}: no validation kind declared"]


# ── The chromatic field registry ────────────────────────────────────────────
# Every ``str`` field on GenomeSpec is a paint UNLESS it is named below. Stated
# as a complement on purpose: a colour field added later is validated by
# default, where an explicit allowlist would silently leave it unchecked —
# which is exactly how 73 chromatic fields (highlight_color, diamond_stroke,
# frame_fill, the state/status/pill/receipt families …) stayed unvalidated
# while only a dozen carried a grammar. `test_every_genome_string_field_has_a
# _grammar` holds the partition total.
_NON_CHROMATIC_STR_FIELDS: frozenset[str] = frozenset(
    {
        # identity / dispatch — slug or token grammars
        "id",
        "name",
        "profile",
        "category",
        "stratum",
        "icon_variant",
        "default_surface",
        "flagship_variant",
        "state_glyph_shape",
        # geometry + timing + material — their own grammars
        "glow",
        "corner",
        "density",
        "rhythm_base",
        "rhythm_slow",
        "rhythm_fast",
        "shadow_opacity",
        "highlight_opacity",
        "cellular_pattern_opacity",
        "cellular_pulse_base_duration",
        "cellular_pulse_fast_duration",
        "material_specular",
        "material_roughness",
        # typography — font-stack grammar
        "font_display",
        "font_mono",
        "scholar_heading_font",
    }
)


def chromatic_fields() -> frozenset[str]:
    """Every GenomeSpec field whose value is a paint."""
    str_fields: frozenset[str] = frozenset(
        name for name, field in GenomeSpec.model_fields.items() if field.annotation is str
    )
    return str_fields - _NON_CHROMATIC_STR_FIELDS


_STOP_KEYS = frozenset({"offset", "color", "opacity"})
_BLOOM_KEYS = frozenset({"id", "cx", "cy", "r", "stops"})


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return value == value and abs(value) != float("inf")
    return isinstance(value, str) and bool(_NUMBER_RE.match(value))


def _is_offset(value: object) -> bool:
    if isinstance(value, str) and _PERCENT_RE.match(value):
        return True
    return _is_finite_number(value)


def _is_opacity(value: object) -> bool:
    if not _is_finite_number(value):
        return False
    return 0.0 <= float(str(value)) <= 1.0


def _check_gradient_stop(stop: object, where: str) -> list[str]:
    """Violation lines for one ``{offset, color[, opacity]}`` gradient stop."""
    if not isinstance(stop, dict):
        return [f"{where}: gradient stop must be a dict, got {type(stop).__name__}"]
    problems = [f"{where}: unknown stop key '{k}'" for k in stop if k not in _STOP_KEYS]
    if not _is_offset(stop.get("offset")):
        problems.append(f"{where}: offset must be a percent ('50%') or number token, got {stop.get('offset')!r}")
    color = stop.get("color")
    if not (isinstance(color, str) and (_is_color(color) or color == "transparent")):
        problems.append(f"{where}: color must be #RRGGBB / rgba(...) / transparent, got {color!r}")
    if "opacity" in stop and not _is_opacity(stop["opacity"]):
        problems.append(f"{where}: opacity must be a 0-1 number token, got {stop['opacity']!r}")
    return problems


# Canonical badge state-indicator shapes. Each maps to a
# templates/frames/badge/indicators/<shape>-indicator.j2 partial. Shared by
# GenomeSpec.state_glyph_shape, ComposeSpec.state_glyph_shape, ParadigmBadgeConfig
# .indicator_shape, and the variant-override validator — one source of truth so
# a slug can never reach the include dispatch without a partial behind it.
INDICATOR_SHAPES: frozenset[str] = frozenset({"square", "circle", "diamond"})


# -- Field-to-CSS mapping for the core genome properties --
_CORE_CSS_MAP: dict[str, str] = {
    "surface_0": "--dna-surface",
    "surface_1": "--dna-surface-alt",
    "surface_2": "--dna-surface-deep",
    "ink": "--dna-ink-primary",
    "ink_secondary": "--dna-ink-muted",
    "ink_on_accent": "--dna-ink-on-accent",
    "accent": "--dna-signal",
    "accent_complement": "--dna-signal-dim",
    "accent_signal": "--dna-status-passing-core",
    "accent_warning": "--dna-status-warning-core",
    "accent_error": "--dna-status-failing-core",
    "stroke": "--dna-border",
    "shadow_color": "--dna-shadow-color",
    "shadow_opacity": "--dna-shadow-opacity",
    "glow": "--dna-glow",
    "corner": "--dna-corner",
    "rhythm_base": "--dna-rhythm-base",
    "rhythm_slow": "--dna-rhythm-slow",
    "rhythm_fast": "--dna-rhythm-fast",
    "density": "--dna-density",
}

_EXTENDED_CSS_MAP: dict[str, str] = {
    "bg": "--dna-bg",
    "bg_alt": "--dna-bg-alt",
    "ink_bright": "--dna-ink-bright",
    "ink_sub": "--dna-ink-sub",
    "brand_text": "--dna-brand-text",
    "metric_text": "--dna-metric-text",
    "label_text": "--dna-label-text",
    "border_tint": "--dna-border-tint",
    "glyph_inner": "--dna-glyph-inner",
    "seam_gap": "--dna-seam-gap",
    "badge_value_text": "--dna-badge-value-text",
    "badge_pass_sep": "--dna-badge-pass-sep",
    "badge_warn_color": "--dna-badge-warn-color",
}

_MATERIAL_CSS_MAP: dict[str, str] = {
    "material_specular": "--dna-material-specular",
    "material_roughness": "--dna-material-roughness",
}


class GenomeSpec(BaseModel):
    """Complete genome definition with validation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # -- Identity --
    id: str = Field(description="Genome slug (e.g. 'brutalist')")
    name: str = Field(description="Human-readable name")
    category: str = Field(description="'dark' or 'light'")
    profile: str = Field(description="Profile ID reference (e.g. 'brutalist')")
    roles: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Semantic token grouping (accent / surface / ink / status -> token-name "
            "lists) — recoloring by intent instead of hex archaeology; pure data, "
            "zero rendering logic."
        ),
    )
    glyph_tint: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Per-frame default glyph fill selection (ink | brand | full), "
            "e.g. {'matrix': 'brand'}. Callers override via ComposeSpec "
            "glyph_tint; per-slot IR declarations outrank both. Frames "
            "absent from the dict default to ink."
        ),
    )

    # -- Surfaces --
    surface_0: str = Field(description="Primary surface color (hex)")
    surface_1: str = Field(description="Alternate surface color (hex)")
    surface_2: str = Field(description="Deep surface color (hex)")

    # -- Inks --
    ink: str = Field(description="Primary ink/text color (hex)")
    ink_secondary: str = Field(description="Secondary/muted ink color (hex)")
    ink_on_accent: str = Field(description="Ink on accent backgrounds (hex)")

    # -- Accents --
    accent: str = Field(description="Primary accent/signal color (hex)")
    accent_complement: str = Field(description="Complement accent (hex)")
    diamond_stroke: str = Field(
        default="",
        description=(
            "Chrome diamond ring stroke color (hex). Single-responsibility var "
            "consumed by --dna-diamond-stroke; eliminates --dna-signal-dim "
            "aliasing collisions on the chrome status indicator."
        ),
    )
    diamond_housing: str = Field(
        default="",
        description=(
            "Chrome diamond recessed housing fill color (hex). Single-responsibility "
            "var consumed by --dna-diamond-housing; pairs with diamond_stroke."
        ),
    )
    accent_signal: str = Field(description="Status passing color (hex)")
    accent_warning: str = Field(description="Status warning color (hex)")
    accent_error: str = Field(description="Status error/failing color (hex)")
    diagram_flow: list[str] = Field(
        default_factory=list,
        description=(
            "Diagram flow-accent cycle (hex). OPTIONAL: derived from the "
            "variant accent by default (compose/diagram/palette.py) — slot 0 "
            "is the accent (the spine), slots 1+ an in-family tint ramp lanes "
            "read as category tints. Author an explicit 3-8 distinct #RRGGBB "
            "palette only to opt out of derivation."
        ),
    )
    diagram_conn_muted: str = Field(
        default="",
        description=(
            "Quiet neutral (hex) for the muted-connector knob — static/dash "
            "wires draw in this tone when connector_palette=muted (flowing "
            "particles keep the flow accent). Required at config load when a "
            "diagram genome ships connector_palette=muted support."
        ),
    )

    # -- Structure --
    stroke: str = Field(description="Border/stroke color (hex)")
    shadow_color: str = Field(description="Shadow color (hex)")
    diagram_shadow_color: str = Field(
        default="",
        description=(
            "Diagram drop-shadow tint (hex) — a neutral slate distinct from the "
            "shared shadow_color other frames use. Empty defers to shadow_color."
        ),
    )
    shadow_opacity: str = Field(description="Shadow opacity (e.g. '0.08')")
    glow: str = Field(default="0px", description="Glow radius (CSS value)")
    corner: str = Field(description="Corner radius (CSS value)")

    # -- Rhythm --
    rhythm_base: str = Field(description="Base animation duration (CSS)")
    rhythm_slow: str = Field(default="", description="Slow rhythm (phi * base)")
    rhythm_fast: str = Field(default="", description="Fast rhythm (base / phi)")

    # -- Density --
    density: str = Field(description="Visual density multiplier")

    # -- Motion --
    compatible_motions: list[str] = Field(description="Allowed motion primitives for this genome")

    # -- Extended palette (optional, empty string = not set) --
    bg: str = Field(default="", description="Bridge allele: background")
    bg_alt: str = Field(default="", description="Bridge allele: alt background")
    ink_bright: str = Field(default="", description="Bridge allele: bright ink")
    ink_sub: str = Field(default="", description="Bridge allele: sub ink")
    brand_text: str = Field(default="", description="Brand text color")
    metric_text: str = Field(default="", description="Metric text color")
    label_text: str = Field(default="", description="Label text color")
    border_tint: str = Field(default="", description="Border tint for wells")
    glyph_inner: str = Field(default="", description="Glyph inner detail color")
    seam_gap: str = Field(default="", description="Seam gap fill between halves")
    frame_fill: str = Field(default="", description="Outer frame fill (darker than surface)")
    badge_value_text: str = Field(default="", description="Badge value text color")
    badge_pass_sep: str = Field(default="", description="Badge passing separator")
    badge_pass_core: str = Field(default="", description="Badge passing indicator inner fill (brighter than ring)")
    badge_warn_color: str = Field(default="", description="Badge warning override")

    # -- Material (optional) --
    material_specular: str = Field(default="", description="Specular intensity")
    material_roughness: str = Field(default="", description="Surface roughness")

    # -- Atmospheric backdrop (optional, v0.2.23) --
    # When non-empty, the receipt renders a full-canvas linear gradient as the
    # backdrop and insets the substrate card by ``card_inset`` pixels so the
    # atmosphere is visible as a colored ring around the card. Sourced from
    # the codex receipt specimen's ``codex-atmo`` gradient (linear top-left → bottom-right).
    atmosphere_stops: list[dict[str, str]] = Field(
        default_factory=list,
        description="Linear gradient stops painted full-canvas behind the substrate",
    )
    atmosphere_blooms: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Radial gradient overlays painted between atmosphere and substrate. "
            "Each entry: {id, cx, cy, r, stops: [{offset, color, opacity}]}. "
            "Sourced from the codex receipt specimen's ``bloom-cool`` and ``bloom-violet``."
        ),
    )
    card_top_highlight: bool = Field(
        default=False,
        description=(
            "When True, paint a 32px <color>→transparent linear gradient over the "
            "card's top edge (glass-edge highlight; the codex receipt specimen). The color "
            "is ``card_top_highlight_color`` (required when this is True) — NOT "
            "ink, which is text tone and turns the edge into a dark wash on light "
            "skins."
        ),
    )
    card_top_highlight_color: str = Field(
        default="",
        description=(
            "Surface-light color for the card top-edge glass highlight, emitted "
            "as --dna-card-top-highlight. Required (non-empty) when "
            "card_top_highlight is True; enforced by _require_card_top_highlight_color."
        ),
    )
    card_inset: int = Field(
        default=0,
        description="Substrate inset in px when atmosphere_stops is active (the codex receipt specimen uses 6px)",
    )

    # -- Badge state-indicator shape (optional) --
    state_glyph_shape: str = Field(
        default="",
        description=(
            "Genome/variant default state-indicator shape: '' (defer to paradigm), "
            "'square', 'circle', or 'diamond'. Selects indicators/<shape>-indicator.j2. "
            "Overrides the paradigm default; overridden by request-time "
            "?state_glyph_shape=. Light brutalist variants set 'circle'."
        ),
    )

    # -- Chrome profile rendering (optional) --
    envelope_stops: list[dict[str, str]] = Field(
        default_factory=list, description="Chrome envelope gradient stops [{offset, color}]"
    )
    well_top: str = Field(default="", description="Chrome well gradient top color")
    well_bottom: str = Field(default="", description="Chrome well gradient bottom color")
    icon_well_top: str = Field(
        default="",
        description=(
            "Icon-specific well gradient top color (v0.2.16+). Lets the icon's small "
            "radial well use a more saturated navy than the wider marquee/strip well "
            "without forcing the same hex on every frame. Empty falls back to well_top."
        ),
    )
    icon_well_bottom: str = Field(
        default="",
        description="Icon-specific well gradient bottom color. Empty falls back to well_bottom.",
    )
    chrome_icon_inner_stroke: str = Field(
        default="",
        description="Chrome icon inner hairline color separating the envelope bezel from the well.",
    )
    chrome_icon_top_accent: str = Field(
        default="",
        description="Chrome square-icon top accent hairline color.",
    )
    highlight_color: str = Field(default="", description="Top highlight line color")
    highlight_opacity: str = Field(default="0.08", description="Top highlight opacity")
    chrome_text_gradient: list[dict[str, str]] = Field(
        default_factory=list, description="Chrome text gradient stops for title text"
    )
    hero_text_gradient: list[dict[str, str]] = Field(
        default_factory=list, description="Hero value text gradient stops (icy silver for chrome)"
    )

    # -- Path B variant grammar (v0.2.19) --
    # Genome-declared whitelist for ComposeSpec.variant. Empty list = no variant
    # axis (validated at resolve-time, not Pydantic field-validator). flagship_variant
    # is the genome's default when spec.variant=="" and paradigm has no per-frame
    # default. Together these enable adding variants without Python edits — same
    # extensibility story Invariant 12 brought to paradigms.
    variants: list[str] = Field(
        default_factory=list,
        description="Allowed values for ComposeSpec.variant. Empty = no variant axis.",
    )
    flagship_variant: str = Field(
        default="",
        description="Default variant when spec.variant is empty and no paradigm default exists.",
    )
    default_surface: str = Field(
        default="",
        description=(
            "Preferred surface preset (plate | inlay | twin) when the caller "
            "requests none. Applies only on surface-mode frames (matrix, "
            "diagram); everywhere else it silently resolves plate. Empty = plate."
        ),
    )
    variant_overrides: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Per-variant genome-field overrides. Keys are variant slugs (must subset "
            "of variants[]); values are sparse genome-field dicts. Two effects: (1) the "
            "assembler emits CSS-var-mappable fields as inline style on SVG root, (2) the "
            "resolver merges the dict into the genome before render so templates reading "
            "baked fields directly (envelope_stops, well_top, etc.) also see the variant. "
            "Values can be any genome-field shape: str (hex), list[dict[str, str]] "
            "(gradient stops), dict (light_mode, etc.). Used by chrome-style holistic "
            "palette swaps. Automata-style compositional tones use variant_tones."
        ),
    )
    variant_tones: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description=(
            "Tone primitive palette (automata-style compositional). Keys are tone slugs "
            "(violet, teal, bone, etc.); values declare 14 chromatic fields per tone "
            "(rim_stops, cellular_cells, area_tiers, chart_levels, dormant_range, label_slab, "
            "seam_mid, label_text, value_text, canvas_top, canvas_bottom, info_accent, "
            "mid_accent, header_band). Resolved into cellular_palette context dict by "
            "compose/palette.py. Pairing is expressed at request time via the URL grammar "
            "modifier ?variant=primary&pair=secondary, which composes any two tones."
        ),
    )
    variant_phenomenology: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Per-variant phenomenological/aesthetic identity statements. Documents the "
            "naming philosophy ('afterimage = the optical echo persisting...'). Lives in "
            "genome config (not per-artifact metadata) so the same description applies "
            "regardless of which frame type renders the variant. Optional."
        ),
    )

    # -- Ontological classification (v0.3.2) --
    # Ring/stratum identifier consumed by the `hw:stratum` metadata field.
    # Brutalist sits in Ring 002-TRIBE; future genomes declare their own.
    stratum: str = Field(
        default="",
        description="Ring/ontology classification emitted as hw:stratum (e.g. '002-TRIBE').",
    )

    # -- Substrate-aware typography (v0.3.2) --
    # Light substrate templates pair Barlow Condensed headings with JetBrains Mono
    # body/data text. Empty falls back to `hero_font` from typography cascade.
    scholar_heading_font: str = Field(
        default="",
        description=(
            "Heading font stack for light-substrate templates (brutalist strip grammar). Pairs with "
            "mono_font for body. Empty falls back to typography.hero_font."
        ),
    )
    dividers: list[str] = Field(
        default_factory=list,
        description=(
            "Genome-themed divider slugs allowed on /v1/divider/{slug}/{genome}. Editorial generics "
            "(block, current, takeoff, void, zeropoint) are NOT in this list — they live at /a/inneraura/."
        ),
    )

    # -- Cellular pulse animation config (paradigm infrastructure) --
    # The 22 flat variant_blue_*/variant_purple_*/variant_bifamily_bridge_*
    # fields previously declared here moved into the v0.3.0 compositional
    # schema: variant_tones (tone primitives) consumed via cellular_palette
    # by the resolver rather than reading flat fields, so the schema stays
    # compact regardless of how many tones a genome ships.
    cellular_pulse_base_duration: str = Field(
        default="", description="Cellular pattern pulse base duration (e.g. '6s')"
    )
    cellular_pulse_fast_duration: str = Field(
        default="", description="Cellular pattern pulse fast duration (phi-derived, e.g. '3s')"
    )
    cellular_pattern_opacity: str = Field(default="", description="Cellular pattern group opacity (e.g. '0.78')")

    # -- State palette (per-status core + bright pair; promoted to top-level
    # so every genome can populate state-badge variants. Default "" keeps
    # current brutalist/chrome unchanged until backfilled.) --
    state_passing_core: str = Field(default="", description="State=passing core color (e.g. emerald-400)")
    state_passing_bright: str = Field(default="", description="State=passing bright value-text color")
    state_warning_core: str = Field(default="", description="State=warning core color (e.g. amber-400)")
    state_warning_bright: str = Field(default="", description="State=warning bright value-text color")
    state_critical_core: str = Field(default="", description="State=critical core color (e.g. red-400)")
    state_critical_bright: str = Field(default="", description="State=critical bright value-text color")
    state_building_core: str = Field(default="", description="State=building core color (e.g. violet-400)")
    state_building_bright: str = Field(default="", description="State=building bright value-text color")
    state_offline_core: str = Field(default="", description="State=offline core color (e.g. slate-400)")
    state_offline_bright: str = Field(default="", description="State=offline bright value-text color")

    # -- Status-glyph badge indicator fills (primer). Universal CI-semantic disc
    # colours for the per-state status icon; substrate-invariant (green/amber/red
    # read on light AND dark). Building uses the variant accent at render time;
    # housing uses surface/border. Default "" leaves other genomes unaffected. --
    badge_status_passing: str = Field(default="", description="Status-glyph passing core fill (CI green)")
    badge_status_warning: str = Field(default="", description="Status-glyph warning disc fill (CI amber)")
    badge_status_critical: str = Field(default="", description="Status-glyph critical disc fill (CI red)")
    badge_status_offline: str = Field(default="", description="Status-glyph offline dim core fill")
    status_knockout: str = Field(default="", description="Status-glyph symbol knockout (cross/bang) fill")
    badge_status_critical_rim: str = Field(
        default="", description="Status-glyph critical disc rim stroke (deepened red)"
    )
    badge_status_warning_rim: str = Field(
        default="", description="Status-glyph warning disc rim stroke (deepened amber)"
    )
    badge_status_critical_knockout: str = Field(
        default="", description="Status-glyph critical X knockout (light, reads on red disc)"
    )
    badge_status_warning_knockout: str = Field(
        default="", description="Status-glyph warning ! knockout (dark, reads on amber disc)"
    )
    strip_status_dot: str = Field(
        default="", description="Strip ACTIVE live-dot, substrate-harmonized green (distinct from accent_signal)"
    )

    # -- Diagram health-channel status dot fills (primer). A flat card-corner
    # disc (dep-audit's health channel) — unlike the badge status-glyph above,
    # a diagram is a single adaptive document (light+dark in ONE svg via
    # @media), so this pair genuinely swaps per substrate rather than staying
    # invariant: pp-tree-radial-v2.svg/pp-tree-v2.svg cite light #DC2626/
    # #F59E0B, dark #F87171/#FBBF24. Default "" leaves other genomes unaffected. --
    diagram_status_warning: str = Field(default="", description="Health-dot outdated fill, light substrate (amber)")
    diagram_status_warning_dark: str = Field(
        default="", description="Health-dot outdated fill, dark substrate (amber-400)"
    )
    diagram_status_critical: str = Field(default="", description="Health-dot vulnerable fill, light substrate (red)")
    diagram_status_critical_dark: str = Field(
        default="", description="Health-dot vulnerable fill, dark substrate (red-400)"
    )
    # -- Loop-family chromatic roles (the loop corpus'
    # chromatic_compile: hues are genome TOKENS, the composer computes
    # nothing). Deliberation lives in decision-question TEXT only — never the
    # frame (the anchor's law); the complement is WIRE-GRADE on the light
    # face (edges and markers only; a discard station's name takes secondary
    # ink, not this). Separate channels from the status pair above — sharing
    # a hex would collide deliberation with health (visual-channel-collision).
    # Default "" leaves other genomes unaffected. --
    diagram_deliberation: str = Field(
        default="", description="Decision-question text ink, light substrate (the loop family's deliberation hue)"
    )
    diagram_deliberation_dark: str = Field(
        default="", description="Decision-question text ink, dark substrate (lifted one ladder rung)"
    )
    diagram_complement: str = Field(
        default="", description="Discard/revert wire+marker stroke, light substrate (accent-complement, wire-grade)"
    )
    diagram_complement_dark: str = Field(
        default="", description="Discard/revert wire+marker stroke, dark substrate (lifted for dark legibility)"
    )
    accent_deep: str = Field(
        default="", description="Deep accent (darker than accent): chart hero value + line-gradient end stop"
    )

    fonts: list[str] = Field(
        default_factory=lambda: ["jetbrains-mono"],
        description="Font slugs to embed as base64 WOFF2 (e.g. 'orbitron', 'jetbrains-mono')",
    )
    light_mode: dict[str, str] | None = Field(default=None, description="Light mode color overrides")

    # -- Icon variant (optional) --
    icon_variant: str = Field(default="", description="Icon rendering variant (e.g. 'binary-opposition')")

    # -- Typography (optional, genome can override default font stacks) --
    font_display: str = Field(default="", description="Display font stack")
    font_mono: str = Field(default="", description="Monospace font stack")

    # -- Tool-class colors (telemetry frames only, optional) --
    tool_explore: str = Field(default="", description="Tool class color: explore (Read, Glob, Grep)")
    tool_execute: str = Field(default="", description="Tool class color: execute (Bash)")
    tool_mutate: str = Field(default="", description="Tool class color: mutate (Edit, Write)")
    tool_coordinate: str = Field(default="", description="Tool class color: coordinate (Agent, Task)")
    tool_reflect: str = Field(default="", description="Tool class color: reflect")

    # -- Receipt compositor tokens (telemetry skins only, v0.2.21) --
    # Per-element pill / glyph / card-frame surface that lets receipt.svg.j2
    # stay branch-free. Values can be ``"transparent"`` to render the element
    # invisibly without a template conditional. Non-telemetry genomes leave
    # these empty (default="") and the assembler skips emitting the CSS vars.
    pill_outer_bg: str = Field(default="", description="Receipt pill base panel fill (layered skins) or transparent")
    pill_outer_stroke: str = Field(default="", description="Receipt pill base frame stroke or transparent")
    pill_inner_bg: str = Field(default="", description="Receipt pill phosphor / inner fill")
    pill_text: str = Field(default="", description="Receipt pill label text color")
    pill_rule_top: str = Field(default="", description="Receipt pill top hairline color or transparent")
    pill_rule_bottom: str = Field(default="", description="Receipt pill bottom hairline color or transparent")
    pill_rx: int = Field(default=4, description="Receipt pill corner radius (0=square, 11=full pill)")
    glyph_fill: str = Field(default="", description="Provider glyph (Claude/Codex) outer path fill")
    card_border: str = Field(default="", description="Receipt card outer border stroke or transparent")
    card_border_top: str = Field(default="", description="Receipt card top accent stripe color or transparent")
    card_inner_glyph: str = Field(default="", description="Codex glyph inner cutout fill (typically surface)")

    # -- Paradigm dispatch (Principle 26: three-layer taxonomy) --
    # Maps FrameType enum value -> paradigm slug. Resolver uses this to pick
    # templates/frames/{frame_type}/{paradigm}-content.j2 at render time.
    # Missing entries default to "default". Grows freely within a profile.
    paradigms: dict[str, str] = Field(
        default_factory=dict,
        description="Frame-type -> paradigm-name dispatch map (Principle 26)",
    )

    # -- Structural cascade (Principle 24: templates read these as context) --
    # Values: stroke_linejoin, data_point_shape, data_layout, fill_density,
    # shape_rendering, etc. Consumed by chart_engine + frame resolvers.
    structural: dict[str, Any] = Field(
        default_factory=dict,
        description="Structural rendering hints (stroke_linejoin, data_point_shape, etc.)",
    )

    # -- Typographic cascade (optional, nested override for font roles) --
    typography: dict[str, Any] = Field(
        default_factory=dict,
        description="Typography hints: hero_font, mono_font, weight_hierarchy, etc.",
    )

    # -- Material cascade (optional, surface/depth/filter hints) --
    material: dict[str, Any] = Field(
        default_factory=dict,
        description="Material hints: surface (matte/gloss), depth, filter_chain",
    )

    # -- Text metrics (optional, per-zone width factors for empirical calibration) --
    # The text-measurement LUT is Inter-calibrated; genomes that render with wider
    # fonts (e.g. Orbitron 900 for chrome badge values) declare a
    # -- Kinetic cascade (optional, motion timing + compatible vocab) --
    motion_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Motion config: timing_base, energy_range, entrance, pulse",
    )

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in ("dark", "light"):
            msg = f"category must be 'dark' or 'light', got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator(
        "surface_0",
        "surface_1",
        "surface_2",
        "stroke",
    )
    @classmethod
    def validate_surface_colors(cls, v: str) -> str:
        """Surfaces and strokes accept hex OR rgba — rgba enables atmospheric
        translucency in genomes layered over a backdrop gradient (v0.2.23 codex).
        """
        if not _is_color(v):
            msg = f"Expected hex (#RRGGBB) or rgba(...) color, got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator(
        "ink",
        "ink_secondary",
        "ink_on_accent",
        "accent",
        "accent_complement",
        "accent_signal",
        "accent_warning",
        "accent_error",
        "shadow_color",
    )
    @classmethod
    def validate_hex_colors(cls, v: str) -> str:
        """Ink and accent colors must be hex — rgba would alpha-blend text
        into the backdrop, which destroys readability."""
        if not _is_hex(v):
            msg = f"Expected hex color (#RRGGBB), got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("compatible_motions")
    @classmethod
    def validate_motions_include_static(cls, v: list[str]) -> list[str]:
        """Static is mandatory, and every id must be a slug.

        A motion id reaches ``data-hw-motion`` on the root element, so an
        entity-bearing id (``x&y``) produced malformed XML from a genome that
        had passed validation. Registry membership is checked by the battery
        (``validate_genome_motions``), which owns registry lookups.
        """
        if "static" not in v:
            msg = "compatible_motions must include 'static'"
            raise ValueError(msg)
        bad = [motion for motion in v if not _SLUG_RE.match(motion)]
        if bad:
            msg = f"compatible_motions ids must match {_SLUG_RE.pattern}; got {bad}"
            raise ValueError(msg)
        return v

    @field_validator("state_glyph_shape")
    @classmethod
    def validate_state_glyph_shape(cls, v: str) -> str:
        """Empty (defer to paradigm) or one of the canonical indicator shapes.

        Bounds the slug at load so it can never reach the
        ``indicators/<shape>-indicator.j2`` include without a partial behind it.
        """
        if v and v not in INDICATOR_SHAPES:
            msg = f"state_glyph_shape must be empty or one of {sorted(INDICATOR_SHAPES)}, got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("id")
    @classmethod
    def validate_id_slug(cls, v: str) -> str:
        """The id lands in ``data-hw-genome``/``data-hw-chromatic`` attributes —
        bound it to a slug so attribute breakout is impossible at the source."""
        if not _SLUG_RE.match(v):
            msg = f"id must match {_SLUG_RE.pattern}, got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("atmosphere_stops", "envelope_stops", "chrome_text_gradient", "hero_text_gradient")
    @classmethod
    def validate_gradient_stops(cls, v: list[dict[str, str]], info: ValidationInfo) -> list[dict[str, str]]:
        """Each stop is a closed ``{offset, color[, opacity]}`` record; values
        are grammar-checked because they interpolate into gradient markup raw."""
        problems = [p for i, stop in enumerate(v) for p in _check_gradient_stop(stop, f"{info.field_name}[{i}]")]
        if problems:
            raise ValueError("; ".join(problems))
        return v

    @field_validator("atmosphere_blooms")
    @classmethod
    def validate_atmosphere_blooms(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Each bloom is a closed ``{id, cx, cy, r, stops}`` record."""
        problems: list[str] = []
        for i, bloom in enumerate(v):
            where = f"atmosphere_blooms[{i}]"
            if not isinstance(bloom, dict):
                problems.append(f"{where}: must be a dict")
                continue
            problems.extend(f"{where}: unknown key '{k}'" for k in bloom if k not in _BLOOM_KEYS)
            bloom_id = bloom.get("id")
            if not (isinstance(bloom_id, str) and _SLUG_RE.match(bloom_id)):
                problems.append(f"{where}: id must be a slug, got {bloom_id!r}")
            for axis in ("cx", "cy", "r"):
                if not _is_offset(bloom.get(axis)):
                    problems.append(f"{where}: {axis} must be a number or percent token, got {bloom.get(axis)!r}")
            for j, stop in enumerate(bloom.get("stops") or []):
                problems.extend(_check_gradient_stop(stop, f"{where}.stops[{j}]"))
        if problems:
            raise ValueError("; ".join(problems))
        return v

    @field_validator("light_mode")
    @classmethod
    def validate_light_mode(cls, v: dict[str, str] | None) -> dict[str, str] | None:
        """Light-mode overrides emit into a raw CSS block — colors only."""
        for key, value in (v or {}).items():
            if not (isinstance(value, str) and (_is_color(value) or value == "transparent")):
                msg = f"light_mode.{key} must be #RRGGBB / rgba(...) / transparent, got {value!r}"
                raise ValueError(msg)
        return v

    @field_validator("font_display", "font_mono", "scholar_heading_font")
    @classmethod
    def validate_font_stack(cls, v: str, info: ValidationInfo) -> str:
        """A font stack is the one place quotes and commas are lawful — and
        the grammar permits nothing else."""
        if v and not _FONT_STACK_RE.match(v):
            msg = f"{info.field_name} must be a comma-list of (optionally quoted) family names, got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator(
        "shadow_opacity",
        "highlight_opacity",
        "density",
        "cellular_pattern_opacity",
        "material_specular",
        "material_roughness",
    )
    @classmethod
    def validate_number_token(cls, v: str, info: ValidationInfo) -> str:
        if v and not _is_finite_number(v):
            msg = f"{info.field_name} must be a finite number token, got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("glow", "corner")
    @classmethod
    def validate_css_length(cls, v: str, info: ValidationInfo) -> str:
        if v and not _CSS_LENGTH_RE.match(v):
            msg = f"{info.field_name} must be a CSS length token (e.g. '4px', '0'), got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator(
        "rhythm_base",
        "rhythm_slow",
        "rhythm_fast",
        "cellular_pulse_base_duration",
        "cellular_pulse_fast_duration",
    )
    @classmethod
    def validate_duration_token(cls, v: str, info: ValidationInfo) -> str:
        """Every duration field takes the same finite, non-negative CSS-time
        grammar — these values reach ``--dna-rhythm-*`` and template clocks
        verbatim, where ``nan``/``inf``/``-5s``/``5`` render as broken timing
        rather than failing."""
        if v and not _is_css_time(v):
            msg = f"{info.field_name} must be a CSS duration like '6s' or '400ms', got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("variants")
    @classmethod
    def validate_variant_slugs(cls, v: list[str]) -> list[str]:
        """A variant slug reaches ``<hw:variant>`` and ``data-hw-*`` attributes
        as-is; an unlawful one (``x&y``) produced malformed XML, breaking
        Invariant 14 on an artifact that had passed validation."""
        bad = [slug for slug in v if not _SLUG_RE.match(slug)]
        if bad:
            msg = f"variants must match {_SLUG_RE.pattern}; got {bad}"
            raise ValueError(msg)
        return v

    @field_validator("flagship_variant", "default_surface", "icon_variant")
    @classmethod
    def validate_optional_slug(cls, v: str, info: ValidationInfo) -> str:
        if v and not _SLUG_RE.match(v):
            msg = f"{info.field_name} must match {_SLUG_RE.pattern}, got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("stratum")
    @classmethod
    def validate_token(cls, v: str, info: ValidationInfo) -> str:
        if v and not _TOKEN_RE.match(v):
            msg = f"{info.field_name} must match {_TOKEN_RE.pattern}, got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("variant_overrides", "variant_tones", "variant_phenomenology", "paradigms", "glyph_tint")
    @classmethod
    def validate_slug_keyed_map(cls, v: dict[str, Any], info: ValidationInfo) -> dict[str, Any]:
        """Keys of every variant-/frame-keyed map are slugs. ``paradigms``
        values are slugs too: they interpolate straight into a template include
        path, so ``"../../document"`` escaped the template root and surfaced as
        a late TemplateNotFound instead of a refusal."""
        bad_keys = [key for key in v if not _SLUG_RE.match(str(key))]
        if bad_keys:
            msg = f"{info.field_name} keys must match {_SLUG_RE.pattern}; got {bad_keys}"
            raise ValueError(msg)
        if info.field_name == "paradigms":
            bad_values = [val for val in v.values() if not _SLUG_RE.match(str(val))]
            if bad_values:
                msg = f"paradigms values must match {_SLUG_RE.pattern}; got {bad_values}"
                raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _validate_chromatic_fields(self) -> GenomeSpec:
        """Every chromatic field is a paint, from the one canonical registry.

        Only a dozen colour fields carried a validator; the rest were plain
        ``str``. ``highlight_color = "x&y"`` reached the root inline style and
        broke XML parsing, and ``frame_fill = "notacolor"`` emitted invalid CSS
        — both through the base genome AND through a variant override, which
        delegates its typing to this model.
        """
        problems = []
        for name in sorted(chromatic_fields()):
            value = getattr(self, name, "")
            kind = paint_kind(name)
            if value and not is_paint(value, kind):
                problems.append(f"{name}: expected {kind} paint, got {value!r}")
        if problems:
            raise ValueError("genome carries invalid colors:\n  " + "\n  ".join(problems))
        return self

    @model_validator(mode="after")
    def _reject_css_dangerous_leaves(self) -> GenomeSpec:
        """Defense-in-depth sweep over every string leaf (P0 injection net).

        The typed grammars above are the boundary; this sweep catches the
        free-form cascade dicts (``typography``, ``structural``, ``material``,
        ``motion_config``, ``variant_overrides``, …) whose values also reach
        raw CSS. Three field classes: font-stack keys re-run the stack grammar
        wherever they appear; documentation prose (``name``,
        ``variant_phenomenology``) may carry quotes/semicolons but never
        markup or fetch vectors; everything else takes the strict set.
        """
        problems: list[str] = []

        def walk(value: object, path: str, top: str, key: str) -> None:
            if isinstance(value, dict):
                for k, v in value.items():
                    walk(v, f"{path}.{k}", top, str(k))
            elif isinstance(value, list):
                for i, v in enumerate(value):
                    walk(v, f"{path}[{i}]", top, key)
            elif isinstance(value, str) and value:
                if _CSS_DANGEROUS_RE.search(value):
                    problems.append(f"{path}: forbidden markup/CSS content in {value!r}")
                elif key in _FONT_STACK_KEYS:
                    if not _FONT_STACK_RE.match(value):
                        problems.append(f"{path}: not a lawful font stack: {value!r}")
                elif top not in _PROSE_FIELDS and _STRICT_EXTRA_RE.search(value):
                    problems.append(f"{path}: forbidden character (quote/semicolon/brace) in {value!r}")

        for field_name, value in self.__dict__.items():
            walk(value, field_name, field_name, field_name)
        if problems:
            raise ValueError("genome carries unsafe values:\n  " + "\n  ".join(problems))
        return self

    @model_validator(mode="after")
    def compute_rhythm_derivatives(self) -> GenomeSpec:
        """Compute rhythm_slow and rhythm_fast from base if not provided."""
        base = _parse_duration(self.rhythm_base)
        slow = self.rhythm_slow
        fast = self.rhythm_fast

        if not slow:
            object.__setattr__(self, "rhythm_slow", f"{base * PHI:.3f}s")
        else:
            actual = _parse_duration(slow)
            expected = base * PHI
            ratio = abs(actual - expected) / expected
            if ratio > PHI_TOLERANCE:
                msg = (
                    f"rhythm_slow ({slow}) deviates {ratio:.0%} from "
                    f"phi * base ({expected:.3f}s). Limit: {PHI_TOLERANCE:.0%}."
                )
                raise ValueError(msg)

        if not fast:
            object.__setattr__(self, "rhythm_fast", f"{base / PHI:.3f}s")
        else:
            actual = _parse_duration(fast)
            expected = base / PHI
            ratio = abs(actual - expected) / expected
            if ratio > PHI_TOLERANCE:
                msg = (
                    f"rhythm_fast ({fast}) deviates {ratio:.0%} from "
                    f"base / phi ({expected:.3f}s). Limit: {PHI_TOLERANCE:.0%}."
                )
                raise ValueError(msg)

        return self

    @model_validator(mode="after")
    def _require_card_top_highlight_color(self) -> GenomeSpec:
        """Fail loud when the card top-highlight gate is on but its color is unset.

        ``card_top_highlight`` toggles a gradient that sources
        ``--dna-card-top-highlight``. With no ``card_top_highlight_color`` the
        token never emits and the CSS var resolves empty — a silent broken edge
        (the v0.3.10→v0.3.13 codex regression, where the edge fell through to
        ink and rendered a dark wash). Enforce the pair at load so a future
        genome can't flip the gate without supplying the surface-light color.
        """
        if self.card_top_highlight and not self.card_top_highlight_color:
            msg = (
                f"Genome '{self.id}' sets card_top_highlight=True but leaves "
                "card_top_highlight_color empty — the glass-edge gradient would "
                "render no color. Declare card_top_highlight_color (a surface-light "
                "hex, e.g. '#FFFFFF')."
            )
            raise ValueError(msg)
        return self

    def genome_to_css(self) -> dict[str, str]:
        """Return the complete field-name to CSS-property mapping."""
        result: dict[str, str] = {}
        result.update(_CORE_CSS_MAP)
        result.update(_EXTENDED_CSS_MAP)
        result.update(_MATERIAL_CSS_MAP)
        return result

    def to_css_vars(self) -> dict[str, str]:
        """Return dict of CSS custom property name to value."""
        mapping = self.genome_to_css()
        result: dict[str, str] = {}
        for field_name, css_prop in mapping.items():
            value = str(getattr(self, field_name, ""))
            if value:
                result[css_prop] = value
        return result
