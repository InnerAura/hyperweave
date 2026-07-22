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

import re
from typing import TYPE_CHECKING

from hyperweave.core.schema import INDICATOR_SHAPES

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
# match the stat-card specimen's 5-band brightness mapping.
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

# Every token a hand-authored diagram twin face (``diagram_faces.{light,dark}``)
# must carry — genome field names, sourced verbatim from verb-algebra-primer-*.
# The adaptive emit path (surface_modes.authored_diagram_faces) PREFERS these
# over flip computation, so a half-declared face would silently ship a partial
# palette; fail loud at config load instead (P5 chroma contract). Keys map to
# --dna-* via the assembler / surface_modes _VAR_NAMES tables.
_DIAGRAM_FACE_TOKENS: frozenset[str] = frozenset(
    {
        "surface_0",
        "surface_1",
        "surface_2",
        "ink",
        "ink_secondary",
        "ink_bright",
        "accent",
        "accent_text",
        "stroke",
        "diagram_conn_muted",
        "region_fill",
        "region_stroke",
    }
)


def validate_font_embedding(
    genome_specs: dict[str, GenomeSpec],
    font_embedding: dict[str, object],
    available_slugs: frozenset[str],
) -> None:
    """Assert ``data/config/font-embedding.yaml`` is internally consistent.

    Four checks, each contributing structured violation lines so a single
    config-load surfaces the complete remediation list:

    1. **Slug existence.** Every slug mentioned in ``defaults`` or
       ``genomes.<id>.<frame>`` must exist as ``data/fonts/<slug>.b64``
       paired with ``<slug>.meta.json``. Typos and stale slugs fail loud
       rather than silently embed nothing.
    2. **Genome identity.** Every key in ``genomes`` must be a loaded
       genome id (``brutalist``, ``chrome``, ``automata``, ...). A row
       keyed off ``brutlist`` ships dead config.
    3. **Genome `fonts` subset.** Every entry in
       ``genomes.<id>.<frame>`` must appear in that genome's declared
       ``fonts`` list. Slugs absent from the genome list silently drop
       at intersection time (``compose/context.py:_load_font_faces``);
       failing here surfaces the misconfig at startup instead.
    4. **`non_embedded_locales` shape.** Must be a list of strings.
       Runtime consumer is deferred (v0.3.7 is documentation only) but
       structural validation here prevents the field from being a
       silently-broken dict.

    :raises ValueError: if any check fails. Message enumerates every
        violation in one pass so a single config-load surfaces the
        complete fix list.
    """
    violations: list[str] = []

    defaults = font_embedding.get("defaults") or {}
    genomes_block = font_embedding.get("genomes") or {}
    locales = font_embedding.get("non_embedded_locales") or []

    if not isinstance(defaults, dict):
        violations.append(f"  'defaults' must be a mapping, got {type(defaults).__name__}")
        defaults = {}
    if not isinstance(genomes_block, dict):
        violations.append(f"  'genomes' must be a mapping, got {type(genomes_block).__name__}")
        genomes_block = {}

    # Check 1 + 2: per-row slug existence + genome identity.
    def _check_row(label: str, frame_type: str, slugs: object) -> list[str]:
        row_violations: list[str] = []
        if not isinstance(slugs, list):
            row_violations.append(f"  {label}.{frame_type} must be a list, got {type(slugs).__name__}")
            return row_violations
        for slug in slugs:
            if not isinstance(slug, str):
                row_violations.append(f"  {label}.{frame_type} contains non-string entry {slug!r}")
                continue
            if slug not in available_slugs:
                row_violations.append(
                    f"  {label}.{frame_type} references unknown font slug {slug!r} "
                    f"(no data/fonts/{slug}.b64 + .meta.json pair)"
                )
        return row_violations

    for frame_type, slugs in defaults.items():
        violations.extend(_check_row("defaults", frame_type, slugs))

    for genome_id, frames in genomes_block.items():
        if genome_id not in genome_specs:
            violations.append(f"  genomes.{genome_id!r} is not a loaded genome (known: {sorted(genome_specs.keys())})")
            continue
        if not isinstance(frames, dict):
            violations.append(f"  genomes.{genome_id} must be a mapping, got {type(frames).__name__}")
            continue
        genome_declared = set(genome_specs[genome_id].fonts or [])
        for frame_type, slugs in frames.items():
            row_violations = _check_row(f"genomes.{genome_id}", frame_type, slugs)
            violations.extend(row_violations)
            # Check 3: subset of genome.fonts (only if the row itself is well-formed
            # and references valid slugs — otherwise the cascade error obscures the
            # subset violation).
            if not row_violations and isinstance(slugs, list):
                missing = set(slugs) - genome_declared
                if missing:
                    violations.append(
                        f"  genomes.{genome_id}.{frame_type} references slugs not in "
                        f"{genome_id}.fonts={sorted(genome_declared)}: {sorted(missing)} — "
                        f"these would silently drop at intersection time"
                    )

    # Check 4: non_embedded_locales shape.
    if not isinstance(locales, list):
        violations.append(f"  'non_embedded_locales' must be a list, got {type(locales).__name__}")
    else:
        for entry in locales:
            if not isinstance(entry, str):
                violations.append(f"  non_embedded_locales contains non-string entry {entry!r}")

    if violations:
        raise ValueError("data/config/font-embedding.yaml has violations:\n" + "\n".join(violations))


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

        # state_glyph_shape override bound — ungated so chrome/automata variant
        # overrides are covered too (not just substrate-dispatch genomes). Variant
        # overrides are free-form dicts that bypass GenomeSpec field validation, so
        # a typo'd shape would otherwise reach the indicators/<shape> include with
        # no partial behind it. Empty/absent is fine (defers to the cascade).
        for variant_slug, override in genome.variant_overrides.items():
            if not isinstance(override, dict):
                continue
            shape = override.get("state_glyph_shape")
            if shape and shape not in INDICATOR_SHAPES:
                violations.append(
                    f"  variant_overrides['{variant_slug}'].state_glyph_shape={shape!r} "
                    f"must be one of {sorted(INDICATOR_SHAPES)}"
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

        # Authored diagram twin faces: if a variant declares diagram_faces, BOTH
        # faces must be present and each must carry the full token set. The
        # adaptive emit path prefers these over flip computation, so a partial
        # face would silently render a half palette — fail loud at load instead.
        for variant_slug, override in genome.variant_overrides.items():
            if not isinstance(override, dict):
                continue
            faces = override.get("diagram_faces")
            if faces is None:
                continue
            if not isinstance(faces, dict) or set(faces.keys()) != {"light", "dark"}:
                got = sorted(faces.keys()) if isinstance(faces, dict) else type(faces).__name__
                violations.append(
                    f"  variant_overrides['{variant_slug}'].diagram_faces must declare exactly "
                    f"'light' and 'dark' (got {got})"
                )
                continue
            for face_name, face in faces.items():
                if not isinstance(face, dict):
                    violations.append(
                        f"  variant_overrides['{variant_slug}'].diagram_faces['{face_name}'] must be a dict"
                    )
                    continue
                missing_tokens = _DIAGRAM_FACE_TOKENS - set(face.keys())
                if missing_tokens:
                    violations.append(
                        f"  variant_overrides['{variant_slug}'].diagram_faces['{face_name}'] missing tokens: "
                        f"{sorted(missing_tokens)}"
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

    # Check 3: diagram flow palette (active only when the genome opts into the
    # diagram frame). The flow cycle is DERIVED from the variant accent by
    # default (compose/diagram/palette.py) — deriving makes the leak this
    # contract once guarded against (one variant's cycle copied onto another)
    # structurally impossible, so diagram_flow is now OPTIONAL. A genome MAY
    # still author an explicit palette to opt out; when present (base or
    # variant), it must be 3-8 pairwise-distinct #RRGGBB entries.
    if "diagram" in (genome.paradigms or {}):
        import re as _re

        def _flow_violations(label: str, palette: object) -> None:
            if not palette:
                return  # empty/absent = derived from the accent (the default)
            if not isinstance(palette, list) or not 3 <= len(palette) <= 8:
                violations.append(f"  {label}: diagram_flow must carry 3-8 entries, got {palette!r}")
                return
            for hexv in palette:
                if not isinstance(hexv, str) or not _re.fullmatch(r"#[0-9A-Fa-f]{6}", hexv):
                    violations.append(f"  {label}: diagram_flow entry {hexv!r} is not #RRGGBB")
            lowered = [str(hexv).lower() for hexv in palette]
            if len(set(lowered)) != len(lowered):
                violations.append(f"  {label}: diagram_flow entries must be pairwise distinct, got {palette}")

        _flow_violations(f"genome '{genome.id}'", list(genome.diagram_flow or []))
        for v_slug, override in (genome.variant_overrides or {}).items():
            if isinstance(override, dict) and "diagram_flow" in override:
                _flow_violations(f"variant_overrides['{v_slug}']", override.get("diagram_flow"))

        # Muted-connector knob (connector_palette=muted): the neutral wire tone.
        # A diagram genome ships it so the knob never silently no-ops; every
        # variant that declares chromatic fields must redeclare its muted tone
        # too (the flow palette now derives, but the muted wire is a genuine
        # per-variant neutral that the derivation does not produce).
        def _muted_violations(label: str, value: object) -> None:
            if not isinstance(value, str) or not _re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
                violations.append(f"  {label}: diagram_conn_muted must be #RRGGBB (got {value!r})")

        _muted_violations(f"genome '{genome.id}'", genome.diagram_conn_muted)
        for v_slug, override in (genome.variant_overrides or {}).items():
            if not isinstance(override, dict):
                continue
            if (set(override.keys()) & _CHROMATIC_FIELDS) and "diagram_conn_muted" not in override:
                violations.append(
                    f"  variant_overrides['{v_slug}'] declares chromatic fields but no diagram_conn_muted "
                    f"(the muted wire tone must be redeclared per variant)"
                )
            elif "diagram_conn_muted" in override:
                _muted_violations(f"variant_overrides['{v_slug}']", override.get("diagram_conn_muted"))

    # Check 4: receipt palette fields (active only when the genome opts into the
    # receipt frame). The receipt's tool-spend ramp, cost-by-model segment ramp,
    # and context-load area-fill/signal draw from per-variant palette fields, NOT
    # chassis constants. The dispatcher merges variant_overrides over the base
    # naively, so a variant that forgets the ramp silently renders an empty one —
    # the "variant looks identical to base" bug. Every variant override must
    # declare the full receipt palette so the failure surfaces at config load.
    if "receipt" in (genome.paradigms or {}):
        import re as _re2

        _ramp_len = 5
        _receipt_hex_fields = (
            "receipt_area_fill",
            "receipt_signal",
            "receipt_track",
            "receipt_track_stroke",
            "receipt_grid_ink",
            "receipt_eyebrow",
            "receipt_label_ink",
            "receipt_value_ink",
            "receipt_dim_ink",
        )

        def _receipt_violations(label: str, override: dict[str, object]) -> None:
            ramp = override.get("receipt_ramp")
            if not isinstance(ramp, list) or len(ramp) != _ramp_len:
                violations.append(
                    f"  {label}: receipt_ramp must be a list of {_ramp_len} #RRGGBB tiers "
                    f"(brightest→dimmest), got {ramp!r}"
                )
            else:
                for hexv in ramp:
                    if not isinstance(hexv, str) or not _re2.fullmatch(r"#[0-9A-Fa-f]{6}", hexv):
                        violations.append(f"  {label}: receipt_ramp tier {hexv!r} is not #RRGGBB")
            for fieldname in _receipt_hex_fields:
                value = override.get(fieldname)
                if not isinstance(value, str) or not _re2.fullmatch(r"#[0-9A-Fa-f]{6}", value):
                    violations.append(
                        f"  {label}: {fieldname} must be #RRGGBB (got {value!r}) — "
                        f"the receipt draws this per-variant, never from a chassis constant"
                    )

        # Every variant override carries the full receipt palette. A receipt
        # genome with no variant overrides would need the palette on the base,
        # but primer (the only receipt genome) keys all 8 variants — so the
        # per-override contract is the load-bearing one.
        for v_slug, override in (genome.variant_overrides or {}).items():
            if isinstance(override, dict):
                _receipt_violations(f"variant_overrides['{v_slug}']", override)

    if violations:
        raise ValueError(f"Genome '{genome.id}' has variant grammar violations:\n" + "\n".join(violations))


# Palette fields the Surface Modes projection MUST find on every variant of a
# surface-capable genome to compute a coherent adaptive far face: a ground, the
# ink, the accent, and substrate_kind (which picks the flip direction). Border
# and on-accent degrade gracefully, so they are not gated. This is the "vellum
# lands with zero code" contract — a new genome that declares these on each
# variant inherits inlay/twin for free; one that forgets fails loud at load
# rather than rendering a half-adaptive artifact at request time.
_SURFACE_REQUIRED_VARIANT_FIELDS: tuple[str, ...] = ("surface_0", "ink", "accent", "substrate_kind")


def validate_genome_surface_contract(genome: GenomeSpec, surface_frames: frozenset[str]) -> None:
    """Assert a surface-capable genome satisfies the Surface Modes supply contract.

    A genome is surface-capable when it opts into a frame in the Surface Modes
    allowlist (``surface_frames`` — matrix/diagram today, read from
    ``data/config/surface-modes.yaml``). For such a genome, every variant override
    must declare the role fields the adaptive projection needs
    (:data:`_SURFACE_REQUIRED_VARIANT_FIELDS`). Genomes that opt into no
    surface-capable frame are skipped entirely (chrome/automata/brutalist pay
    nothing). A surface-capable genome with NO variant overrides must instead
    carry the fields on the base — primer keys all eight variants, so the
    per-variant contract is the load-bearing one there.

    :raises ValueError: enumerating every missing (variant, field) in one pass.
    """
    opts_in_surface = bool(set((genome.paradigms or {}).keys()) & surface_frames)
    if not opts_in_surface:
        return

    violations: list[str] = []
    overrides = genome.variant_overrides or {}
    if overrides:
        for variant_slug, override in overrides.items():
            if not isinstance(override, dict):
                continue
            for field in _SURFACE_REQUIRED_VARIANT_FIELDS:
                if not override.get(field):
                    violations.append(
                        f"  variant_overrides['{variant_slug}'] missing '{field}' "
                        f"(surface-capable genome — every variant must carry the surface role fields)"
                    )
    else:
        for field in _SURFACE_REQUIRED_VARIANT_FIELDS:
            if field == "substrate_kind":
                # a no-variant genome derives direction from its category
                if not (getattr(genome, "category", "") or ""):
                    violations.append("  base genome missing 'category' (needed to pick the flip direction)")
                continue
            if not getattr(genome, field, ""):
                violations.append(f"  base genome missing surface role field '{field}'")

    if violations:
        raise ValueError(
            f"Genome '{genome.id}' opts into a surface-capable frame but breaks the Surface Modes "
            f"supply contract:\n" + "\n".join(violations)
        )


def validate_genome_roles(genome: GenomeSpec) -> None:
    """Assert the genome's role grouping is present and resolvable.

    Every genome ships a ``roles`` dict (accent / surface / ink / status →
    token lists) and every listed token must exist as a truthy field on this
    genome — a role naming a phantom token would turn recolor-by-intent into a
    silent no-op. Empty lists are legal (raw carries no status marks); a
    missing or empty dict is not.
    """
    violations: list[str] = []
    if not genome.roles:
        violations.append("  genome declares no 'roles' grouping (accent / surface / ink / status)")
    for role, tokens in genome.roles.items():
        for token in tokens:
            if not (getattr(genome, token, None) or ""):
                violations.append(f"  role '{role}' names token '{token}', not a field on this genome")
    if violations:
        raise ValueError(f"Genome '{genome.id}' role grouping is broken:\n" + "\n".join(violations))


_CHROMATIC_VALUE = re.compile(r"^#|^rgba?\(|^linear-gradient|^radial-gradient")


def validate_genome_chromatic_coverage(genome: GenomeSpec) -> None:
    """The reverse of :func:`validate_genome_roles`: every chromatic token is
    claimed by SOME role. An unassigned token is invisible to intent-driven
    tools (recolor-by-role would silently skip it) — fail loud at config load,
    matching the chromatic-coverage doctrine.
    """
    assigned = {token for tokens in genome.roles.values() for token in tokens}
    violations = [
        f"  chromatic token '{key}' is claimed by no role"
        for key, value in genome.model_dump().items()
        if key != "roles" and isinstance(value, str) and _CHROMATIC_VALUE.match(value) and key not in assigned
    ]
    if violations:
        raise ValueError(f"Genome '{genome.id}' chromatic coverage is broken:\n" + "\n".join(violations))
