"""Chromatic coverage validator (v0.3.2).

Scope: substrate-dispatch genomes (brutalist) must declare every base-genome
chromatic field on every variant_override that declares ANY chromatic field.
Prevents the emerald-bleed bug class where a variant overrides surface/ink/
accent but inherits brand_text/badge_value_text/etc. from the base genome,
producing visually mixed palettes (carbon variant rendering with emerald
brand_text=#A7F3D0 instead of carbon's intended cool gray-purple).

Three independent invariants:
1. Brutalist passes the validator at config load (regression check for the
   post-backfill state).
2. The validator fails loud when a substrate-dispatch variant omits a
   base-declared chromatic field (the original bug).
3. The flagship case (variant declaring only `substrate_kind` with zero
   chromatic overrides) is exempt — it deliberately inherits the entire base
   palette and represents the canonical flagship variant.
4. Non-substrate-dispatch genomes (chrome) skip the chromatic coverage check
   even when they have partial overrides — they use a different variant
   identity model and aren't subject to this contract in v0.3.2.
"""

from __future__ import annotations

import pytest

from hyperweave.compose.validate_paradigms import validate_genome_variants
from hyperweave.config.loader import ConfigLoader


@pytest.fixture(scope="module")
def loaded() -> ConfigLoader:
    loader = ConfigLoader()
    loader.load()
    return loader


def test_brutalist_passes_chromatic_coverage(loaded: ConfigLoader) -> None:
    brutalist = loaded.genome_specs["brutalist"]
    validate_genome_variants(brutalist)  # raises if any variant fails


def test_brutalist_flagship_declares_full_palette(loaded: ConfigLoader) -> None:
    """v0.3.3 architecture: celadon flagship declares the full chromatic palette
    with semantic field hierarchy. `surface_0` is the genome-wide canvas/ground
    tone (used by strip canvas, stats canvas, badge RIGHT panel). The badge's
    elevated LEFT panel sources from `brand_panel_fill` instead — a badge/strip-
    semantic field that does not leak into the genome-wide canvas. `label_text`
    holds the muted-accent tone consumed by strip metric labels via
    `--dna-label-text`; the badge label routes through `--dna-ink-primary`
    (=ink) for the cream-tier prototype tone. Field decoupling is what allows
    badge and strip to both pull from celadon's palette without one frame's
    visual needs corrupting the other's substrate."""
    from hyperweave.compose.validate_paradigms import _CHROMATIC_FIELDS

    brutalist = loaded.genome_specs["brutalist"]
    celadon = brutalist.variant_overrides["celadon"]
    declared_chromatic = set(celadon.keys()) & _CHROMATIC_FIELDS
    base_chromatic = {f for f in _CHROMATIC_FIELDS if getattr(brutalist, f, "")}
    missing = base_chromatic - declared_chromatic
    assert not missing, (
        f"Celadon flagship must declare all base chromatic fields with prototype values; missing {sorted(missing)}"
    )
    # Spot-check key prototype hex values
    assert celadon["accent"].lower() == "#48a870", (
        f"celadon.accent must be prototype's muted-ceramic-green #48A870; got {celadon['accent']}"
    )
    assert celadon["surface_0"].lower() == "#06140c", (
        f"celadon.surface_0 must be the canvas/ground tone #06140C — used by strip canvas, stats "
        f"canvas, and badge RIGHT panel. The elevated badge LEFT panel sources from brand_panel_fill, "
        f"not surface_0; got {celadon['surface_0']}"
    )
    assert celadon["surface_2"].lower() == "#0e2818", (
        f"celadon.surface_2 must be the intermediate tone #0E2818; got {celadon['surface_2']}"
    )
    assert celadon["brand_panel_fill"].lower() == "#102818", (
        f"celadon.brand_panel_fill must be the elevated panel tone #102818 (used by badge LEFT panel "
        f"via --dna-brand-panel-fill, strip brand panel, stats card header); got {celadon['brand_panel_fill']}"
    )
    assert celadon["label_text"].lower() == "#308858", (
        f"celadon.label_text must be the muted-accent tone #308858 — consumed by strip metric labels via "
        f"--dna-label-text. Badge label routes through --dna-ink-primary (=ink #D8F0E0) instead, so this "
        f"value never bleeds into the badge; got {celadon['label_text']}"
    )
    assert celadon["ink"].lower() == "#d8f0e0", (
        f"celadon.ink must be the cream-tier #D8F0E0 (consumed by badge label via --dna-ink-primary "
        f"per the v16 prototype); got {celadon['ink']}"
    )


def test_brutalist_carbon_brand_text_not_emerald(loaded: ConfigLoader) -> None:
    brutalist = loaded.genome_specs["brutalist"]
    carbon = brutalist.variant_overrides["carbon"]
    assert "brand_text" in carbon, "carbon must declare brand_text (chromatic coverage contract)"
    assert carbon["brand_text"].lower() != "#a7f3d0", (
        f"carbon.brand_text inherited base genome's emerald palette (#A7F3D0); "
        f"got {carbon['brand_text']!r}. This is the original emerald-bleed bug."
    )


def test_brutalist_pulse_brand_text_paper(loaded: ConfigLoader) -> None:
    brutalist = loaded.genome_specs["brutalist"]
    pulse = brutalist.variant_overrides["pulse"]
    assert pulse["brand_text"].lower() == pulse["surface_0"].lower(), (
        f"pulse light variant's brand_text should equal surface_0 (paper) for text on dark panel; "
        f"got brand_text={pulse['brand_text']} surface_0={pulse['surface_0']}"
    )


def test_validator_catches_missing_chromatic_field(loaded: ConfigLoader) -> None:
    """The validator fails loud when a substrate-dispatch variant omits a
    base-declared chromatic field — the original emerald-bleed bug pattern."""
    brutalist = loaded.genome_specs["brutalist"]

    broken = brutalist.model_copy(deep=True)
    broken.variant_overrides["carbon"] = dict(broken.variant_overrides["carbon"])
    del broken.variant_overrides["carbon"]["brand_text"]

    with pytest.raises(ValueError, match="brand_text"):
        validate_genome_variants(broken)


def test_chrome_skips_chromatic_coverage(loaded: ConfigLoader) -> None:
    """Chrome's variants use partial overrides by design (no substrate_kind);
    the validator must skip the chromatic coverage check for non-substrate
    genomes so v0.3.2's stricter contract doesn't retroactively break chrome."""
    chrome = loaded.genome_specs["chrome"]
    validate_genome_variants(chrome)  # raises if validator over-reaches into chrome
