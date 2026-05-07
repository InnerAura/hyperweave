"""Genome schema validation."""

from __future__ import annotations

import re
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# Golden ratio for rhythm validation
PHI: float = 1.618033988749895
PHI_TOLERANCE: float = 0.15  # 15% tolerance on rhythm ratios

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_RGBA_RE = re.compile(r"^rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(,\s*[0-9.]+\s*)?\)$")


def _is_hex(value: str) -> bool:
    return bool(_HEX_RE.match(value))


def _is_color(value: str) -> bool:
    """True for hex (``#RRGGBB``) or rgb/rgba (``rgba(R,G,B,A)``) values.

    Genomes that participate in atmospheric layering (v0.2.23 codex skin)
    declare translucent rgba surfaces so a backdrop gradient can bleed
    through. Genomes that don't atmosphere-layer keep using hex.
    """
    return _is_hex(value) or bool(_RGBA_RE.match(value))


def _parse_duration(value: str) -> float:
    v = value.strip().lower()
    if v.endswith("ms"):
        return float(v[:-2]) / 1000.0
    if v.endswith("s"):
        return float(v[:-1])
    return float(v)


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
    accent_signal: str = Field(description="Status passing color (hex)")
    accent_warning: str = Field(description="Status warning color (hex)")
    accent_error: str = Field(description="Status error/failing color (hex)")

    # -- Structure --
    stroke: str = Field(description="Border/stroke color (hex)")
    shadow_color: str = Field(description="Shadow color (hex)")
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
    # the v9 codex specimen's ``codex-atmo`` gradient (linear top-left → bottom-right).
    atmosphere_stops: list[dict[str, str]] = Field(
        default_factory=list,
        description="Linear gradient stops painted full-canvas behind the substrate",
    )
    atmosphere_blooms: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Radial gradient overlays painted between atmosphere and substrate. "
            "Each entry: {id, cx, cy, r, stops: [{offset, color, opacity}]}. "
            "Sourced from v9 codex ``bloom-cool`` and ``bloom-violet``."
        ),
    )
    card_top_highlight: bool = Field(
        default=False,
        description=(
            "When True, paint a 32px white→transparent linear gradient over the "
            "card's top edge (glass-edge highlight; v9 codex specimen)."
        ),
    )
    card_inset: int = Field(
        default=0,
        description="Substrate inset in px when atmosphere_stops is active (v9 codex uses 6px)",
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
    dividers: list[str] = Field(
        default_factory=list,
        description=(
            "Genome-themed divider slugs allowed on /v1/divider/{slug}/{genome}. Editorial generics "
            "(block, current, takeoff, void, zeropoint) are NOT in this list — they live at /a/inneraura/."
        ),
    )

    # -- Automata variant palettes (bifamily genomes with teal/amethyst axis) --
    # Automata specimens establish two parallel chromatic palettes with the
    # same structural architecture. Cellular paradigm requires both populated;
    # monofamily artifacts (badges/icons) pick one via ComposeSpec.variant.
    variant_blue_rim_stops: list[dict[str, str]] = Field(
        default_factory=list, description="Blue-family rim gradient stops (7-stop metallic bezel)"
    )
    variant_blue_pattern_cells: list[str] = Field(
        default_factory=list, description="Blue-family cellular substrate trio [solid, mid, deep]"
    )
    variant_blue_seam_mid: str = Field(default="", description="Blue-family seam gradient mid color")
    variant_blue_label_slab_fill: str = Field(default="", description="Blue-family label slab fill (deep teal-black)")
    variant_blue_label_text: str = Field(default="", description="Blue-family label text color")
    variant_blue_value_text: str = Field(default="", description="Blue-family value text color (bright teal)")
    variant_blue_canvas_top: str = Field(default="", description="Blue-family value slab gradient top")
    variant_blue_canvas_bottom: str = Field(default="", description="Blue-family value slab gradient bottom")

    variant_purple_rim_stops: list[dict[str, str]] = Field(
        default_factory=list, description="Purple-family rim gradient stops (7-stop amethyst bezel)"
    )
    variant_purple_pattern_cells: list[str] = Field(
        default_factory=list, description="Purple-family cellular substrate trio [solid, mid, deep]"
    )
    variant_purple_seam_mid: str = Field(default="", description="Purple-family seam gradient mid color")
    variant_purple_label_slab_fill: str = Field(
        default="", description="Purple-family label slab fill (deep amethyst-black)"
    )
    variant_purple_label_text: str = Field(default="", description="Purple-family label text color")
    variant_purple_value_text: str = Field(default="", description="Purple-family value text color (bright amethyst)")
    variant_purple_canvas_top: str = Field(default="", description="Purple-family value slab gradient top")
    variant_purple_canvas_bottom: str = Field(default="", description="Purple-family value slab gradient bottom")

    # Bifamily bridge (used by divider + flanking compositions — static-baked palette)
    variant_bifamily_bridge_teal_mid: str = Field(
        default="", description="Bifamily-bridge teal midtone (divider cells)"
    )
    variant_bifamily_bridge_teal_deep: str = Field(default="", description="Bifamily-bridge teal deep (divider cells)")
    variant_bifamily_bridge_amethyst_core: str = Field(
        default="", description="Bifamily-bridge amethyst core (divider cells)"
    )
    variant_bifamily_bridge_amethyst_bright: str = Field(
        default="", description="Bifamily-bridge amethyst bright (divider cells)"
    )

    # Cellular pulse animation config (paradigm infrastructure)
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
    treemap_accent_side: str = Field(
        default="top",
        description="Treemap row accent direction: 'top' (1.5px full-width bar) or 'left' (4px full-height bar)",
    )

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
        if "static" not in v:
            msg = "compatible_motions must include 'static'"
            raise ValueError(msg)
        return v

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
