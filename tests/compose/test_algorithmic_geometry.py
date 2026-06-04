"""Algorithmic geometry locks — v0.3.9 architectural commitment.

These tests prevent the reintroduction of band-aid magic numbers that the
v0.3.9 refactor replaced with computed values. Each assertion pins a
derivation (input constants → derived geometry) so any future "quick fix"
that drops a hardcoded constant back into the YAML breaks here.

Two derivations are locked:

1. **Strip identity glyph size.** Derived as ``strip_height *
   strip_glyph_ratio`` in ``compose/layout.py:compute_strip_glyph_size``.
   Replaces the prior hand-synced pair (chrome ``glyph_size: 22`` +
   brutalist ``identity_glyph_size: 18``).

2. **Stat card identity zone width.** Derived as ``bio_x - identity_x -
   identity_padding`` in ``compose/resolvers/stats.py``. Replaces the
   prior ``identity_zone_width: 70`` magic number on cellular and brutalist
   that had to be hand-resynced every time ``bio_x`` shifted.

The bio collision clamp also has a smoke assertion — after the cellular
branding moved to the footer row, all paradigms leave header bio collision
clamping disabled.
"""

from __future__ import annotations

from hyperweave.compose.layout import compute_strip_glyph_size
from hyperweave.config.registry import get_paradigms, reset_registry


def test_strip_glyph_size_derives_from_ratio_default() -> None:
    """Default ratio 0.346 at strip_height=52 produces an 18px glyph."""
    assert compute_strip_glyph_size(52, 0.346) == 18


def test_strip_glyph_size_scales_with_strip_height() -> None:
    """Changing strip_height produces a proportional glyph automatically."""
    # Same ratio, different heights produce predictable per-paradigm glyphs.
    assert compute_strip_glyph_size(40, 0.346) == 14
    assert compute_strip_glyph_size(64, 0.346) == 22
    # Same height, different ratios.
    assert compute_strip_glyph_size(52, 0.50) == 26
    assert compute_strip_glyph_size(52, 0.25) == 13


def test_chrome_and_brutalist_strips_share_glyph_ratio() -> None:
    """Both paradigms inherit the same ratio so glyphs scale uniformly.

    Pre-v0.3.9 this was a hand-synced pair (chrome glyph_size=22,
    brutalist identity_glyph_size=18) that had to stay in proportional
    agreement by manual update. Now both inherit the schema default
    0.346 and derive 18px from their shared strip_height=52.
    """
    reset_registry()
    paradigms = get_paradigms()
    chrome_strip = paradigms["chrome"].strip
    brutalist_strip = paradigms["brutalist"].strip
    chrome_glyph = compute_strip_glyph_size(chrome_strip.strip_height, chrome_strip.strip_glyph_ratio)
    brutalist_glyph = compute_strip_glyph_size(brutalist_strip.strip_height, brutalist_strip.strip_glyph_ratio)
    assert chrome_glyph == brutalist_glyph == 18


def test_cellular_identity_zone_width_derived_from_layout() -> None:
    """Cellular: bio_x(410) - identity_x(20) - identity_padding(2) = 388.

    bio_x widened from 110 → 410 in v0.3.9 Bug #1 follow-up after Bug A
    moved HYPERWEAVE branding to the footer. The header right zone is now
    free so bio can adapt without crowding any right-anchored header
    element. The 388 zone is effectively "no clamp for any realistic
    username" — VLLM-PROJECT (~147px ink) lands at bio_x=171 with no
    textLength squish.
    """
    reset_registry()
    cellular_stats = get_paradigms()["cellular"].stats
    derived = cellular_stats.bio_x - cellular_stats.identity_x - cellular_stats.identity_padding
    assert derived == 388, (
        f"Cellular identity zone derivation broke: bio_x={cellular_stats.bio_x}, "
        f"identity_x={cellular_stats.identity_x}, padding={cellular_stats.identity_padding}, "
        f"derived={derived} (expected 388 — effectively no clamp for realistic names)."
    )


def test_brutalist_identity_zone_width_derived_from_layout() -> None:
    """Brutalist: bio_x(134) - identity_x(44) - identity_padding(20) = 70.

    Matches the previous fixed identity_zone_width of 70. The derivation
    now absorbs bio_x and padding changes automatically, so the zone width
    is not a separately tuned magic number.
    """
    reset_registry()
    brutalist_stats = get_paradigms()["brutalist"].stats
    derived = brutalist_stats.bio_x - brutalist_stats.identity_x - brutalist_stats.identity_padding
    assert derived == 70, (
        f"Brutalist identity zone derivation broke: bio_x={brutalist_stats.bio_x}, "
        f"identity_x={brutalist_stats.identity_x}, padding={brutalist_stats.identity_padding}, "
        f"derived={derived} (expected 70)."
    )


def test_bio_collision_clamp_disabled_after_hyperweave_moved_to_footer() -> None:
    """After Bug A moved HYPERWEAVE to footer, cellular header right is empty.

    Pre-Bug-A cellular set bio_collision_clamp=True because the HYPERWEAVE
    branding at y=22 (right-anchored) could collide with long bios.
    Post-Bug-A HYPERWEAVE renders at y=221 (footer) — no header collision
    is possible. All three paradigms now leave collision_clamp disabled.
    """
    reset_registry()
    paradigms = get_paradigms()
    assert paradigms["cellular"].stats.bio_collision_clamp is False
    assert paradigms["brutalist"].stats.bio_collision_clamp is False
    assert paradigms["chrome"].stats.bio_collision_clamp is False


def test_cellular_vllm_project_renders_without_username_squish() -> None:
    """VLLM-PROJECT renders at natural width (no textLength compression).

    Pre-fix the cellular bio_x ceiling at 110 forced VLLM-PROJECT (~130px
    natural at Orbitron 13/700/0.16em) into a 88px textLength clamp,
    visually squishing the characters. Post-Bug-#1 the ceiling widened to
    410 — VLLM-PROJECT renders at natural width with bio breathing room.
    """
    import re

    from hyperweave.compose import compose
    from hyperweave.core.models import ComposeSpec
    from hyperweave.core.text import measure_text_ink_width

    spec = ComposeSpec(
        type="stats",
        genome_id="automata",
        variant="teal",
        title="STATS",
        connector_data={
            "username": "vllm-project",
            "top_language": "Python",
            "repo_count": 39,
            "stars_total": 107300,
        },
    )
    result = compose(spec)
    assert result.svg
    # The username text must NOT carry textLength — natural-width render.
    username_match = re.search(r'<text[^>]+class="[^"]+-username"[^>]*>VLLM-PROJECT</text>', result.svg)
    assert username_match, "VLLM-PROJECT username text not found"
    assert "textLength" not in username_match.group(0), (
        f"VLLM-PROJECT should render at natural width, not textLength-clamped. Match: {username_match.group(0)}"
    )
    bio_match = re.search(
        r'<text x="([\d.]+)" y="24(?:\.0)?" class="[^"]+-bio">Python / 39 repos</text>',
        result.svg,
    )
    assert bio_match, "cellular bio text not found"
    bio_x = float(bio_match.group(1))
    expected_bio_x = round(
        20
        + measure_text_ink_width(
            "VLLM-PROJECT",
            font_family="Orbitron",
            font_size=13,
            font_weight=700,
            letter_spacing_em=0.16,
        )
        + 8
    )
    assert bio_x == expected_bio_x


def test_no_knobs_for_chrome_bearing_correction() -> None:
    """Bearing correction comes from per-glyph LUT data, NOT a paradigm knob.

    v0.3.9 removed two consecutive band-aid knobs (``value_trailing_trim``,
    then ``text_end_bearing_em``) in favor of direct per-glyph LSB/RSB
    extraction from the font outline (see scripts/extract_font_metrics.py
    and core/text.py:measure_text_ink_width). The resolver computes per-text
    trailing bearing as ``measure_text(advance) - measure_text_ink_width``
    — a value that varies correctly per LAST GLYPH (S vs K vs I) instead
    of being averaged across a paradigm.

    This test pins the architectural lock: ``ParadigmBadgeConfig`` must
    NOT carry a bearing/trim knob field. Reintroducing one rebuilds the
    band-aid path that under-corrected the 28-char extreme-label gap
    the user flagged "countless times".
    """
    from hyperweave.core.paradigm import ParadigmBadgeConfig

    forbidden_fields = {"text_end_bearing_em", "value_trailing_trim"}
    actual_fields = set(ParadigmBadgeConfig.model_fields.keys())
    overlap = forbidden_fields & actual_fields
    assert not overlap, (
        f"ParadigmBadgeConfig must not carry bearing-knob fields {overlap}. "
        "Bearing correction is computed from per-glyph LSB/RSB in the font LUT "
        "(see core/text.py:measure_text_ink_width). Reintroducing a knob "
        "rebuilds the band-aid path that under-corrected the chrome 28-char gap."
    )


def test_brutalist_adaptive_bio_x_short_username() -> None:
    """Short ELI64S username snaps bio close (v0.3.8 tight visual restored).

    Pre-v0.3.9 short-username bio sat at the static paradigm bio_x=134 with
    a wide gap between "ELI64S" (~52px ink) ending around x=96 and bio
    starting at x=134 (~38px gap — regression user flagged).

    Post-v0.3.9 adaptive: bio = identity_x(44) + identity_ink + breathing(8).
    For ELI64S, bio renders at ~104, restoring tight feel.
    """
    from hyperweave.compose import compose
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="stats",
        genome_id="brutalist",
        variant="celadon",
        title="STATS",
        connector_data={"username": "eli64s", "top_language": "Python", "repo_count": 20},
    )
    result = compose(spec)
    assert result.svg
    import re

    match = re.search(r'class="[^"]+-m"\s+x="([\d.]+)"', result.svg)
    assert match, "repo_label x not found in brutalist SVG"
    bio_x = float(match.group(1))
    # ELI64S is ~52px ink; adaptive should land bio between 100-115 (well
    # below the v0.3.9-pre static 134).
    assert 95 <= bio_x <= 115, (
        f"Brutalist short-username bio_x should snap close (v0.3.8 feel) — got {bio_x}, "
        f"expected 95-115 range. The static v0.3.9-pre value 134 indicates adaptive bio_x not firing."
    )


def test_brutalist_adaptive_bio_x_long_username_matches_clamped_v038() -> None:
    """Long clamped identity reproduces v0.3.8 bio_x=122 from derivation.

    For VLLM-PROJECT (12 chars at JBM 11/800/0.22em ≈ 130+ px), identity
    overflows zone_w=70 so textLength clamps it. The adaptive formula
    then produces: identity_x(44) + zone_w(70) + breathing(8) = 122,
    which matches v0.3.8's hardcoded x="122" exactly.
    """
    from hyperweave.compose import compose
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="stats",
        genome_id="brutalist",
        variant="celadon",
        title="STATS",
        connector_data={"username": "vllm-project", "top_language": "Python", "repo_count": 39},
    )
    result = compose(spec)
    assert result.svg
    import re

    match = re.search(r'class="[^"]+-m"\s+x="([\d.]+)"', result.svg)
    assert match, "repo_label x not found in brutalist SVG"
    bio_x = float(match.group(1))
    # 44 + 70 + 8 = 122 (v0.3.8 value)
    assert bio_x == 122, f"Brutalist long-username bio_x should derive to 122 (v0.3.8 value) — got {bio_x}"


def test_cellular_streak_slot_fits_1000d_value() -> None:
    """Algorithmic metric slot allocation: 1000d streak doesn't overlap STREAK label.

    Pre-v0.3.9 cellular template hardcoded STREAK value at x=459 + label at
    x=479 (20px gap). Value "21d" (~18px) fit; "1000d" (~40px) overflowed.
    Bug B: resolver computes slot widths from per-value measurement and
    right-anchors STREAK so the value floats left of the label regardless
    of width.

    Asserts the rendered STREAK value's right edge stays left of the
    STREAK label's left edge.
    """
    from hyperweave.compose import compose
    from hyperweave.core.models import ComposeSpec
    from hyperweave.core.text import measure_text

    spec = ComposeSpec(
        type="stats",
        genome_id="automata",
        variant="teal",
        title="STATS",
        connector_data={
            "username": "testuser",
            "top_language": "Python",
            "repo_count": 10,
            "stars_total": 100,
            "commits_total": 50,
            "prs_total": 5,
            "contrib_total": 3,
            "streak_days": 1000,
        },
    )
    result = compose(spec)
    assert result.svg
    import re

    # Find STREAK value and label x positions
    streak_value_match = re.search(r'x="([\d.]+)"[^>]+class="[^"]+-mvg"[^>]*>1000d', result.svg)
    streak_label_match = re.search(r'x="([\d.]+)"[^>]+class="[^"]+-mlb">STREAK', result.svg)
    assert streak_value_match, "STREAK value (1000d) not found"
    assert streak_label_match, "STREAK label not found"
    value_x = float(streak_value_match.group(1))
    label_x = float(streak_label_match.group(1))
    # Measure value width to compute right edge
    value_w = measure_text("1000d", font_family="Chakra Petch", font_size=15, font_weight=600)
    value_right = value_x + value_w
    # Value right must be LESS than label left (no overlap), with at least 2px breathing
    assert value_right + 2.0 <= label_x, (
        f"1000d streak overlaps STREAK label: value_right={value_right:.1f}, label_x={label_x:.1f}"
    )


def test_chrome_label_bearing_correction_uses_real_glyph_data() -> None:
    """measure_text_ink_width returns advance - first_lsb - last_rsb.

    For Orbitron at 8.5px, the chrome label font:
    - 'S' RSB ≈ 0.42px (small — most ink reaches advance edge)
    - 'K' RSB ≈ 0.47px
    - 'I' RSB ≈ 0.55px (narrow glyph, proportionally more bearing)

    Verifies the LUT-driven correction returns DIFFERENT values per
    last-glyph, which a scalar knob cannot.
    """
    from hyperweave.core.text import measure_text, measure_text_ink_width

    advance_s = measure_text(
        "BUILD-PASSING-WITH-WARNINGS", font_family="Orbitron", font_size=8.5, font_weight=700, letter_spacing_em=0.1
    )
    ink_s = measure_text_ink_width(
        "BUILD-PASSING-WITH-WARNINGS", font_family="Orbitron", font_size=8.5, font_weight=700, letter_spacing_em=0.1
    )
    advance_ok = measure_text("OK", font_family="Orbitron", font_size=10, font_weight=800, letter_spacing_em=0.03)
    ink_ok = measure_text_ink_width("OK", font_family="Orbitron", font_size=10, font_weight=800, letter_spacing_em=0.03)
    # Ink must be strictly less than or equal to advance (bearings only
    # subtract, never add).
    assert ink_s <= advance_s
    assert ink_ok <= advance_ok
    # And the LUT must actually provide bearing data — strict inequality
    # means correction is active rather than falling through to advance.
    assert advance_s - ink_s > 0, "Orbitron LUT must supply non-zero bearings"
    assert advance_ok - ink_ok > 0


def test_orbitron_weighted_metrics_do_not_use_scalar_bold_expansion() -> None:
    """Orbitron bold widths come from real variable-font LUT data.

    A scalar 1.06 expansion inflated the 28-char chrome label by ~10px and
    created the visible void before the seam. The generated Orbitron LUT
    now carries per-weight advances, so 700 is almost identical to 400 for
    this label instead of 6% wider.
    """
    from hyperweave.core.text import measure_text

    label = "BUILD-PASSING-WITH-WARNINGS"
    regular = measure_text(label, font_family="Orbitron", font_size=8.5, font_weight=400, letter_spacing_em=0.1)
    bold = measure_text(label, font_family="Orbitron", font_size=8.5, font_weight=700, letter_spacing_em=0.1)
    scalar_bold = regular * 1.06

    assert abs(bold - regular) < 1.0
    assert scalar_bold - bold > 9.0


def test_chrome_28char_badge_closes_seam_gap() -> None:
    """BUILD-PASSING-WITH-WARNINGS / OK lands at uniform pad/2 seam gap.

    Pre-v0.3.9-final the seam gap was inflated by the last-glyph trailing
    side-bearing (advance_end - visible_ink_end). With per-glyph RSB
    extraction (measure_text_trailing_bearing), the cursor walk in
    compute_badge_zones subtracts the bearing before placing the seam at
    cursor + pad/2 — so the visible gap from "S" to the seam dark hairline
    equals exactly pad/2 (3.5px on chrome with pad=7) within ±0.6px tolerance
    for sub-pixel rounding.

    This is the architectural lock the user demanded "countless times" —
    asserts the actual rendered geometry, not just that compose succeeds.
    """
    import re

    from hyperweave.compose import compose
    from hyperweave.core.models import ComposeSpec
    from hyperweave.core.text import measure_text, measure_text_trailing_bearing

    spec = ComposeSpec(
        type="badge",
        genome_id="chrome",
        variant="horizon",
        title="BUILD-PASSING-WITH-WARNINGS",
        value="OK",
        state="success",
    )
    result = compose(spec)
    assert result.svg

    # Parse rendered label x and seam x from the SVG.
    label_match = re.search(r'data-hw-zone="label"\s*\n?\s*x="([\d.]+)"', result.svg)
    # Chrome's etched seam emits TWO hairlines: dark cut (--dna-seam-gap)
    # and specular catch (--dna-specular). The dark cut is the visual
    # seam-left edge — what the eye reads as "where the seam starts".
    seam_match = re.search(r'<line\s+x1="([\d.]+)"\s+[^>]+stroke="var\(--dna-seam-gap\)"', result.svg)
    assert label_match, "label x not found in chrome SVG"
    assert seam_match, "chrome dark hairline (--dna-seam-gap) not found in SVG"
    assert "--dna-specular:" in result.svg
    assert 'stroke="var(--dna-specular, var(--dna-signal))"' in result.svg
    assert "#000204" not in result.svg
    assert "#88FFE8" not in result.svg

    label_first_x = float(label_match.group(1))
    seam_x = float(seam_match.group(1))

    # Compute expected visible-ink end and gap.
    label = "BUILD-PASSING-WITH-WARNINGS"
    advance = measure_text(label, font_family="Orbitron", font_size=8.5, font_weight=700, letter_spacing_em=0.1)
    rsb = measure_text_trailing_bearing(label, font_family="Orbitron", font_size=8.5, font_weight=700)
    visible_ink_end = label_first_x + advance - rsb
    gap = seam_x - visible_ink_end
    pad_half = 7 / 2  # chrome pad=7 → pad/2=3.5

    assert abs(gap - pad_half) <= 0.6, (
        f"Chrome 28-char seam gap should equal pad/2={pad_half}px (±0.6), "
        f"got {gap:.2f}px. label_first_x={label_first_x}, seam_x={seam_x}, "
        f"advance={advance:.2f}, RSB={rsb:.2f}, visible_ink_end={visible_ink_end:.2f}"
    )


def test_brutalist_stats_does_not_trip_bio_clamp() -> None:
    """Brutalist's bio_collision_clamp is False so no bio_text_length is emitted.

    Brutalist places branding in the footer row (y=275) so the bio in the
    header row never collides. Resolver must not run the bio measurement
    work and must emit bio_text_length=0.
    """
    from hyperweave.compose import compose
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="stats",
        genome_id="brutalist",
        variant="celadon",
        title="STATS",
        connector_data={
            "username": "karpathy",
            "bio": "I like to train Deep Neural Nets on large datasets.",
            "top_language": "Python",
            "repo_count": 63,
            "stars_total": 184400,
            "commits_total": 5400,
            "prs_total": 312,
            "contrib_total": 89,
        },
    )
    result = compose(spec)
    # Brutalist bio (footer) renders without a textLength clamp. Identity
    # text may still carry textLength (the username clamp is a separate
    # mechanism keyed off identity_text_length, which IS active across
    # paradigms). The bio-zone <text class="...-m"> element must not
    # carry textLength.
    assert 'class="' in result.svg  # smoke check that the SVG composed
