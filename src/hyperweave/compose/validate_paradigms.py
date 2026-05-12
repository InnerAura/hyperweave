"""Genome/paradigm cross-validation at the compose/load boundary.

This module enforces that any genome opting into a paradigm declares
every genome field that paradigm requires. It deliberately lives
outside :mod:`hyperweave.core.schema` so ``GenomeSpec`` remains
self-contained — the cross-cutting check needs ParadigmSpec data loaded
from config, which would create a circular dependency if embedded as a
Pydantic ``@model_validator`` on ``GenomeSpec``.

Invoked once at load time by :class:`hyperweave.config.loader.ConfigLoader`
after both ``load_genomes()`` and ``load_paradigms()`` have populated
their caches. Raises ``ValueError`` with a structured message listing
every ``(paradigm_slug, required_field)`` violation across the genome
so a single run surfaces the complete remediation list.

Also validates the v0.3.0 variant grammar self-consistency:
``variant_overrides`` keys must subset ``variants[]`` (chrome-style holistic
swaps); ``variant_tones`` entries must have all 14 chromatic keys
(automata-style compositional tones — 11 base shape fields plus the three
accent stops info_accent / mid_accent / header_band). Pairing is expressed
at request time via the URL grammar modifier ``?variant=primary&pair=secondary``
and composes any two solo tones; the legacy ``variant_pairs`` config entry
was removed in the grammar refactor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hyperweave.core.paradigm import ParadigmSpec
    from hyperweave.core.schema import GenomeSpec


# Fields that define a variant's chromatic identity. Curated subset of the
# fields the assembler maps to --dna-* CSS vars (assembler._ALL_CSS_MAPPING):
# only true color/material-identity fields are listed here. Non-chromatic
# fields the assembler also emits (motion timing, font stacks, opacity
# numerics, semantic state colors like accent_signal/warning/error) are
# excluded — variants legitimately inherit those from the base genome by
# design (function-over-identity for state semantics; numeric/typographic
# coherence for the rest). Adding a new variant-identity-carrying field
# means updating both `assembler._ALL_CSS_MAPPING` and this set.
_CHROMATIC_FIELDS: frozenset[str] = frozenset(
    {
        # Substrate / canvas
        "surface_0",
        "surface_1",
        "surface_2",
        "bg",
        "bg_alt",
        "frame_fill",
        # Ink layers
        "ink",
        "ink_secondary",
        "ink_on_accent",
        "ink_bright",
        "ink_sub",
        # Accent / signal
        "accent",
        "accent_complement",
        # Borders / strokes
        "stroke",
        "border_tint",
        # Texts (per-role)
        "brand_text",
        "metric_text",
        "label_text",
        "glyph_inner",
        # Seam (light-scholar INK-SEAM-INK + dark badge seam-gap)
        "seam_color",
        "seam_gap",
        # Badge state-machine chromatic surfaces
        "badge_value_text",
        "badge_pass_sep",
        "badge_pass_core",
        # Shadow tint
        "shadow_color",
    }
)


# Required keys for every entry in genome.variant_tones (automata-style tone primitive).
# Each tone declares its full chromatic shape — derivation discarded the
# perceptual lightness curves authors hand-tuned for value_text and canvas_bottom,
# so explicit-over-derived is the v0.3.0 contract.
#
# ``area_tiers`` (5-color brightest→darkest list) drives the star-chart cellular
# fill brightness gradient and the stat-card heatmap intensity mapping.
#
# ``info_accent`` / ``mid_accent`` / ``header_band`` are the three accent stops
# introduced for the v0.3.0 visual refresh: info_accent is the saturated
# brand-bright stop (stat-card username, chart title, marquee text, icon glyph);
# mid_accent is the 70%-saturated mid stop (marquee hairlines, icon mid cells,
# icon borders, chart axis labels at lower opacity); header_band is the dark
# mid-band tone for the chart's HUD-style header rect and the icon's dormant
# cells. All three are explicit per-tone — algorithmic derivation can't capture
# the perceptual difference between e.g. amber's #B89800 mid stop and teal's
# #1A6A7E mid stop.
_TONE_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "rim_stops",
        "cellular_cells",
        "area_tiers",
        "chart_levels",
        "dormant_range",
        "label_slab",
        "seam_mid",
        "label_text",
        "value_text",
        "canvas_top",
        "canvas_bottom",
        "info_accent",
        "mid_accent",
        "header_band",
    }
)

# Accent fields that must be pairwise distinct within a tone (info_accent
# != mid_accent != header_band). Catches copy-paste tone definitions where
# all three were set to the same value. Tuple ordering is stable so error
# messages list pairs in a consistent order.
_TONE_ACCENT_KEYS: tuple[str, ...] = ("info_accent", "mid_accent", "header_band")

# header_band must differ from canvas_top and canvas_bottom; if it matches the
# canvas color, the chart's header zone renders invisible against the surface.
_TONE_HEADER_BAND_DISTINCT_FROM: tuple[str, ...] = ("canvas_top", "canvas_bottom")

# Expected length of the area_tiers list (brightest → darkest). Pinned at 5 to
# match the v2 specimen's 5-band brightness mapping (used by stat card heatmap).
_AREA_TIERS_LENGTH: int = 5

# Expected length of the chart_levels list (darkest → brightest). Pinned at 6
# to match the cellular automata chart's 6-level discrete brightness palette.
_CHART_LEVELS_LENGTH: int = 6

# Expected length of the dormant_range list. Pinned at 2: [low, high] near-black
# bounds for the chart's dormant cell substrate (background under the curve clip).
_DORMANT_RANGE_LENGTH: int = 2

# Valid substrate_kind values for v0.3.2 brutalist substrate-dispatch variants.
# Each variant in a substrate-aware genome must declare one of these so the
# template dispatcher (`frames/{type}/brutalist-` ~ substrate_kind ~ "-content.j2")
# resolves to a real file. Light variants additionally require panel_gradient_stops
# (the dark academic panel inset) and seam_color (the INK-SEAM-INK middle bar).
_SUBSTRATE_KINDS: frozenset[str] = frozenset({"dark", "light"})

# Minimum number of gradient stops for the light-scholar dark academic panel
# (header rect background, language strip background). Two-stop linear gradient
# top→bottom is the minimum producing the depth-effect the prototype specifies.
_PANEL_GRADIENT_MIN_STOPS: int = 2


def validate_genome_against_paradigms(
    genome: GenomeSpec,
    paradigms: dict[str, ParadigmSpec],
) -> None:
    """Assert that ``genome`` declares every field required by its paradigms.

    Walks the set of paradigm slugs referenced by ``genome.paradigms``;
    for each slug, looks up ``ParadigmSpec.requires_genome_fields`` and
    checks that ``getattr(genome, field)`` is non-empty (truthy). Empty
    strings and empty lists are treated as missing — they are the shape
    the old ``| default(...)`` fallbacks were activating on.

    Unknown paradigm slugs are silently skipped; they dispatch to the
    ``default`` paradigm at render time, which has no requirements.

    :raises ValueError: if any paradigm declares a requirement the genome
        does not fulfill. Message enumerates every violation in one pass.
    """
    declared_slugs = set((genome.paradigms or {}).values())

    missing: dict[str, list[str]] = {}
    for slug in declared_slugs:
        paradigm = paradigms.get(slug)
        if paradigm is None:
            continue
        for field in paradigm.requires_genome_fields:
            value = getattr(genome, field, None)
            if not value:
                missing.setdefault(slug, []).append(field)

    if missing:
        lines = [f"  paradigm '{slug}' requires: {', '.join(fields)}" for slug, fields in sorted(missing.items())]
        raise ValueError(f"Genome '{genome.id}' opts into paradigms with missing required fields:\n" + "\n".join(lines))


def validate_genome_variants(genome: GenomeSpec) -> None:
    """Assert genome's variant grammar is internally self-consistent.

    Two independent checks, each contributing a structured violation line so
    a single run surfaces the complete remediation list:

    1. **Chrome-style holistic overrides.** Every key in ``variant_overrides``
       must appear in the ``variants[]`` whitelist. A stray override entry is
       a route a user can never reach but the JSON pretends to support — fail
       loud rather than ship the dead config.

    2. **Automata-style tone primitives.** Every entry in ``variant_tones``
       must declare all 14 chromatic keys (the original 11-field shape plus
       info_accent / mid_accent / header_band added for the v0.3.0 visual
       refresh). Plus pairwise-distinct accent stops and header_band distinct
       from canvas_top/canvas_bottom — both rules catch degenerate definitions
       that would render visually broken artifacts. Every entry in
       ``variants[]`` must be reachable via ``variant_tones`` so the resolver's
       whitelist can never accept a slug that resolves to nothing renderable.

    Pairing is no longer expressed as a dedicated config entry — the URL
    grammar modifier ``?variant=primary&pair=secondary`` composes any two
    solo tones at request time. The legacy ``variant_pairs`` dict and its
    hand-curated bridge entries were removed in v0.3.0; this validator no
    longer enforces shape on that field. The resolver's bridge synthesis in
    ``compose/palette.py:resolve_cellular_palette`` derives the dissolve
    divider's transition palette from each tone's ``cellular_cells[0:2]``.

    Empty fields are skipped: a chrome.json without ``variant_tones`` doesn't
    trigger the tone shape check; an automata.json without ``variant_overrides``
    doesn't trigger the override-subset check. Each genome only pays for the
    grammar it opts into.

    :raises ValueError: if any check fails. Message enumerates every violation
        in one pass so a single config-load surfaces the complete fix list.
    """
    violations: list[str] = []

    variants_set = set(genome.variants or [])

    # Check 1: variant_overrides keys ⊆ variants[]
    if genome.variant_overrides:
        unknown = set(genome.variant_overrides.keys()) - variants_set
        if unknown:
            violations.append(
                f"  variant_overrides has keys not in variants[]: {sorted(unknown)} (variants={sorted(variants_set)})"
            )

        # Substrate-dispatch opt-in flag: any override declaring substrate_kind
        # signals this genome uses substrate-aware template dispatch (v0.3.2+).
        # Used by both the chromatic coverage check and the substrate-dispatch
        # self-consistency check below.
        opts_in_substrate = any(
            isinstance(ov, dict) and "substrate_kind" in ov for ov in genome.variant_overrides.values()
        )

        # Chromatic coverage contract (per CLAUDE.md): a variant_override that
        # declares ANY chromatic field must declare EVERY chromatic field the
        # base genome declares. The resolver merges base + variant_overrides
        # naively (base fields inherit through), which silently regresses
        # variant identity for fields the override forgets — e.g. the v0.3.2
        # brutalist emerald-bleed bug where carbon overrode surface/ink/accent
        # but inherited the base genome's emerald brand_text=#A7F3D0 because
        # the override did not re-declare it. A flagship variant declaring
        # ZERO chromatic fields (e.g. celadon: {"substrate_kind": "dark"}) is
        # exempt — it deliberately inherits the entire base palette.
        #
        # SCOPE: this check is enabled only for genomes opting into substrate
        # dispatch (v0.3.2+ brutalist; future light/dark-aware genomes). Legacy
        # genomes (chrome, automata) use partial overrides by design — their
        # variant identity is carried by a smaller set of fields and the
        # missing-field inheritance is intentional. Extending the contract to
        # those genomes requires authoring full per-variant palettes for each
        # of their variants (a v0.3.3+ task scoped separately from this fix).
        if opts_in_substrate:
            base_chromatic = {f for f in _CHROMATIC_FIELDS if getattr(genome, f, "")}
            for variant_slug, override in genome.variant_overrides.items():
                if not isinstance(override, dict):
                    continue
                declared_chromatic = set(override.keys()) & _CHROMATIC_FIELDS
                if not declared_chromatic:
                    # Flagship case: zero chromatic overrides, inherit base verbatim.
                    continue
                missing_chromatic = base_chromatic - declared_chromatic
                if missing_chromatic:
                    violations.append(
                        f"  variant_overrides['{variant_slug}'] declares chromatic fields but is missing: "
                        f"{sorted(missing_chromatic)} — partial chromatic overrides silently inherit base "
                        f"values (chromatic coverage contract: override all base chromatic fields or none)"
                    )

        # Substrate-dispatch self-consistency (v0.3.2): if ANY override declares
        # substrate_kind the genome opts into substrate-aware template dispatch,
        # and EVERY override must declare it consistently. Light variants need
        # the dark academic panel gradient + INK-SEAM-INK seam color; dark
        # variants must NOT declare panel gradient (catches misclassification —
        # accidentally tagging a dark variant as light would route it to the
        # light template with no panel).
        if opts_in_substrate:
            for variant_slug, override in genome.variant_overrides.items():
                if not isinstance(override, dict):
                    continue
                substrate_kind = override.get("substrate_kind")
                if not substrate_kind:
                    violations.append(
                        f"  variant_overrides['{variant_slug}'] missing required 'substrate_kind' "
                        f"(genome uses substrate dispatch — all overrides must declare 'dark' or 'light')"
                    )
                    continue
                if substrate_kind not in _SUBSTRATE_KINDS:
                    violations.append(
                        f"  variant_overrides['{variant_slug}'].substrate_kind={substrate_kind!r} "
                        f"must be one of {sorted(_SUBSTRATE_KINDS)}"
                    )
                    continue
                if substrate_kind == "light":
                    panel_stops = override.get("panel_gradient_stops")
                    if not isinstance(panel_stops, list) or len(panel_stops) < _PANEL_GRADIENT_MIN_STOPS:
                        violations.append(
                            f"  variant_overrides['{variant_slug}'] substrate_kind='light' requires "
                            f"'panel_gradient_stops' with ≥{_PANEL_GRADIENT_MIN_STOPS} stops"
                        )
                    if not override.get("seam_color"):
                        violations.append(
                            f"  variant_overrides['{variant_slug}'] substrate_kind='light' requires 'seam_color' "
                            f"(INK-SEAM-INK divider middle bar)"
                        )
                elif substrate_kind == "dark" and "panel_gradient_stops" in override:
                    violations.append(
                        f"  variant_overrides['{variant_slug}'] substrate_kind='dark' must NOT declare "
                        f"'panel_gradient_stops' (panel is a light-substrate-only construct)"
                    )

    # Check 2: variant_tones structural shape
    tones_set: set[str] = set()
    if genome.variant_tones:
        for tone_slug, tone_dict in genome.variant_tones.items():
            tones_set.add(tone_slug)
            if not isinstance(tone_dict, dict):
                violations.append(f"  variant_tones['{tone_slug}'] must be a dict, got {type(tone_dict).__name__}")
                continue
            tone_keys = set(tone_dict.keys())
            missing_keys = _TONE_REQUIRED_KEYS - tone_keys
            if missing_keys:
                violations.append(f"  variant_tones['{tone_slug}'] missing required keys: {sorted(missing_keys)}")
            else:
                # area_tiers length check: 5 brightness bands, brightest → darkest.
                area_tiers = tone_dict.get("area_tiers")
                if isinstance(area_tiers, list) and len(area_tiers) != _AREA_TIERS_LENGTH:
                    violations.append(
                        f"  variant_tones['{tone_slug}'].area_tiers must have exactly "
                        f"{_AREA_TIERS_LENGTH} colors (brightest→darkest); got {len(area_tiers)}"
                    )
                # chart_levels length check: 6 discrete brightness bands, darkest → brightest.
                chart_levels = tone_dict.get("chart_levels")
                if isinstance(chart_levels, list) and len(chart_levels) != _CHART_LEVELS_LENGTH:
                    violations.append(
                        f"  variant_tones['{tone_slug}'].chart_levels must have exactly "
                        f"{_CHART_LEVELS_LENGTH} colors (darkest→brightest); got {len(chart_levels)}"
                    )
                # dormant_range length check: 2 near-black bounds [low, high].
                dormant_range = tone_dict.get("dormant_range")
                if isinstance(dormant_range, list) and len(dormant_range) != _DORMANT_RANGE_LENGTH:
                    violations.append(
                        f"  variant_tones['{tone_slug}'].dormant_range must have exactly "
                        f"{_DORMANT_RANGE_LENGTH} colors [low, high]; got {len(dormant_range)}"
                    )

                # Accent fields pairwise-distinct check. info_accent / mid_accent /
                # header_band describe perceptually distinct stops; if any pair
                # collides, the tone visually loses one of its semantic layers.
                accent_values = {k: tone_dict.get(k) for k in _TONE_ACCENT_KEYS if tone_dict.get(k)}
                seen_normalized: dict[str, str] = {}
                for k, v in accent_values.items():
                    norm = str(v).lower()
                    prior = seen_normalized.get(norm)
                    if prior:
                        violations.append(
                            f"  variant_tones['{tone_slug}'].{k}={v!r} duplicates "
                            f"{prior}={v!r}; accent stops must be pairwise distinct"
                        )
                    else:
                        seen_normalized[norm] = k

                # header_band must differ from canvas stops. If header_band ==
                # canvas_bottom (or canvas_top), the chart's HUD-style header
                # rect renders invisible against the canvas surface.
                header_band = tone_dict.get("header_band")
                if header_band:
                    for canvas_key in _TONE_HEADER_BAND_DISTINCT_FROM:
                        canvas_val = tone_dict.get(canvas_key)
                        if canvas_val and str(header_band).lower() == str(canvas_val).lower():
                            violations.append(
                                f"  variant_tones['{tone_slug}'].header_band={header_band!r} "
                                f"matches {canvas_key}={canvas_val!r}; header band must be "
                                f"visible against the canvas"
                            )

    # Reachability: every variants[] entry must resolve via tones. Pairing is
    # expressed at request time via the URL grammar modifier (?pair=...) and
    # composes any two solo tones, so there is no separate reachability set
    # for paired entries.
    if variants_set and tones_set:
        unreachable = variants_set - tones_set
        if unreachable:
            violations.append(
                f"  variants[] entries unreachable via variant_tones: {sorted(unreachable)} (tones={sorted(tones_set)})"
            )

    if violations:
        raise ValueError(f"Genome '{genome.id}' has variant grammar violations:\n" + "\n".join(violations))
