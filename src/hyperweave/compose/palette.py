"""Cellular paradigm palette resolution.

Builds the structured ``cellular_palette`` context dict consumed by automata's
cellular-* templates, replacing the flat ``variant_blue_*`` / ``variant_purple_*``
genome fields the templates read pre-v0.3.

Two modes:

* **Solo** — ``?variant=teal``: ``primary`` resolves from ``variant_tones[teal]``,
  ``secondary`` mirrors ``primary``, ``bridge`` is synthesized from primary's
  cellular_cells, ``is_paired`` False. This lets bifamily templates (strip,
  marquee-overlay, chart) read ``cellular_palette.secondary.cellular_cells``
  without an ``is_paired`` guard and get sensible single-tone behavior
  automatically.

* **Paired (URL grammar)** — ``?variant=teal&pair=violet``: ``primary`` resolves
  from ``variant_tones[teal]``, ``secondary`` from ``variant_tones[violet]``,
  ``bridge`` is synthesized from primary + secondary cellular_cells[0:2],
  ``is_paired`` True. Any solo tone composes with any other solo tone.

The pre-v0.3.0-grammar dedicated ``variant_pairs`` dict (with hand-curated
bridge entries like violet-teal/bone-steel) was removed in the grammar
refactor. The bridge is now always synthesized from cellular_cells, which
gives every (primary, pair) combination a deterministic dissolve-divider
appearance without authoring effort.

Lives in its own module rather than expanding ``compose/resolver.py`` (already
2,673 LOC against the 400-line ceiling per architecture review C5).
"""

from __future__ import annotations

from typing import Any


def resolve_cellular_palette(
    genome: dict[str, Any],
    resolved_variant: str,
    pair: str = "",
) -> dict[str, Any]:
    """Resolve cellular_palette context dict for the active variant + pair.

    Returns a dict with keys ``primary``, ``secondary``, ``bridge``, ``is_paired``,
    ``divider_color``, ``subtitle_color``:

    * ``primary``: a 14-key tone dict (rim_stops, cellular_cells, area_tiers,
      chart_levels, dormant_range, label_slab, seam_mid, label_text, value_text,
      canvas_top, canvas_bottom, info_accent, mid_accent, header_band) from
      ``genome.variant_tones[resolved_variant]``. Empty dict when the genome
      declares no variant_tones at all (non-cellular genomes).
    * ``secondary``: another tone dict; mirrors primary in solo mode, resolves
      to ``genome.variant_tones[pair]`` when ``pair`` is set.
    * ``bridge``: 4-key dict (primary_main, primary_alt, secondary_main,
      secondary_alt) synthesized from primary + secondary cellular_cells[0:2].
    * ``is_paired``: True only when ``pair`` is non-empty and resolves to a
      valid tone; lets templates branch on fusion-vs-solo when needed (e.g.,
      divider's bifamily bridge zone only renders in paired mode).

    Validation is upstream: ``validate_genome_variants`` in
    ``compose/validate_paradigms.py`` ensures every tone has all 14 fields.
    This resolver additionally validates ``pair`` against ``variant_tones`` —
    an unknown pair slug raises ValueError with the same shape as the variant
    whitelist error.

    Empty resolved_variant or genomes without variant_tones return an empty
    palette dict — non-cellular genomes pay zero cost for the unconditional
    setdefault at the dispatcher.

    :raises ValueError: if ``pair`` is non-empty but not a key of
        ``genome.variant_tones``.
    """
    tones = genome.get("variant_tones") or {}

    if not resolved_variant or not tones:
        return {
            "primary": {},
            "secondary": {},
            "bridge": None,
            "is_paired": False,
        }

    # Pair grammar: ``?variant=teal&pair=violet`` resolves primary from teal,
    # secondary from violet. Permissive on non-cellular genomes (handled by
    # the early return above when tones is empty), strict on automata: an
    # unknown pair slug raises just like an unknown primary variant does.
    if pair:
        if pair not in tones:
            available = sorted(tones.keys())
            raise ValueError(
                f"pair '{pair}' not in genome.variant_tones {available}; "
                "the pair URL parameter must reference a valid solo tone"
            )
        secondary_name = pair
        is_paired = True
    else:
        secondary_name = resolved_variant
        is_paired = False

    primary = tones.get(resolved_variant) or {}
    secondary = tones.get(secondary_name) or primary

    # Synthesize the bridge from cellular_cells[0:2] of each tone. Solo mode
    # produces a mirrored bridge (secondary == primary) so the dissolve divider
    # still has a 4-color transition palette to work with. Paired mode produces
    # a true cross-tone bridge.
    p_cells = primary.get("cellular_cells", [])
    s_cells = secondary.get("cellular_cells", [])
    if len(p_cells) >= 2 and len(s_cells) >= 2:
        bridge = {
            "primary_main": p_cells[0],
            "primary_alt": p_cells[1],
            "secondary_main": s_cells[0],
            "secondary_alt": s_cells[1],
        }
    else:
        bridge = None

    # Derive variant-aware accent fields from the primary tone. The HTML
    # specimens render the strip's metric-cell dividers in the variant's
    # deepest-saturated cellular cell (cellular_cells[0]) and subtitles in
    # the variant's seam_mid — neither maps to a static genome-level field.
    # These derivations let the resolver dispatcher override variant-blind
    # ctx keys (strip_divider_color, ink_sub) for cellular paradigm without
    # requiring a parallel variant_overrides block on automata.json.
    divider_color = p_cells[0] if p_cells else ""
    subtitle_color = primary.get("seam_mid", "")

    return {
        "primary": primary,
        "secondary": secondary,
        "bridge": bridge,
        "is_paired": is_paired,
        "divider_color": divider_color,
        "subtitle_color": subtitle_color,
    }
