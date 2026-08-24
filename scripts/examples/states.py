"""The badge state-indicator gallery — shape dispatch across the paradigms.

The indicator is a configurable shape: `square`, `circle` or `diamond`,
defaulted per paradigm and overridable per request via `?state_glyph_shape=`.
Primer is the exception — its indicator is a state-KEYED animated mark
(`status-glyph`: ping / throb / shake), its own system rather than a geometric,
so it has one shape and the override does not apply.

Which genomes take the geometric override is READ from the paradigm's
`badge.indicator_shape` (primer declares `status-glyph`, chrome `diamond`,
brutalist and automata leave it empty for the geometric default) rather than
listed here. The per-variant substrate labels are read from genome config too:
the previous emitter spelled out `("celadon", "dark — emerald phosphor")` as a
third copy of strings that already live in `variant_phenomenology` and
`variant_overrides[v].substrate_kind`.

What IS declared here is the sample: which three variants of a 22-variant
genome are worth putting side by side. That is an editorial choice, not a
derivable fact.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hyperweave.config.loader import load_genomes, load_paradigms
from hyperweave.core.enums import ArtifactStatus
from scripts.examples.manifest import Gallery
from scripts.examples.markdown import Doc
from scripts.examples.render import OUTPUTS, spec

if TYPE_CHECKING:
    from pathlib import Path

STATES_ROOT = OUTPUTS / "states"

# The three states worth comparing side by side — one healthy, two degraded.
# building/offline are in every genome gallery's own state row; the point here
# is the shape and its colour, which these three separate cleanly.
STATES: tuple[ArtifactStatus, ...] = (
    ArtifactStatus.PASSING,
    ArtifactStatus.WARNING,
    ArtifactStatus.CRITICAL,
)

# The geometric shapes the `?state_glyph_shape=` override selects between.
GEOMETRIC: tuple[str, ...] = ("square", "circle", "diamond")

# Three variants per genome, chosen to span its chromatic range. Editorial —
# a 22-variant genome cannot show every variant against every shape and stay
# readable. Labels are NOT written here; they come from genome config.
SAMPLE: dict[str, tuple[str, ...]] = {
    "brutalist": ("celadon", "ember", "archive"),
    "chrome": ("horizon", "moth", "abyssal"),
    "automata": ("teal", "violet", "amber"),
    "primer": ("porcelain", "noir", "carbon"),
}


def _shapes_for(cfg: Any) -> tuple[str, ...]:
    """The shapes this genome's badge can show.

    A paradigm declaring its own non-geometric indicator (primer's
    `status-glyph`) has exactly one; every other paradigm accepts the
    request-time override across all three.
    """
    paradigm = load_paradigms().get(cfg.paradigms.get("badge", "default"))
    declared = paradigm.badge.indicator_shape if paradigm else ""
    return (declared,) if declared == "status-glyph" else GEOMETRIC


def _label(cfg: Any, variant: str) -> str:
    """A variant's one-line identity, with its substrate when it has one."""
    substrate = str((cfg.variant_overrides.get(variant) or {}).get("substrate_kind", ""))
    identity = cfg.variant_phenomenology.get(variant, "")
    if substrate and identity:
        return f"{substrate} — {identity}"
    return substrate or identity


def build_gallery() -> Gallery:
    """Declare every badge in the shape matrix.

    Per genome: each shape it supports x its three sample variants x three
    states, so both the shape dispatch AND the per-variant indicator colour
    are comparable in one scroll.
    """
    gallery = Gallery("states", STATES_ROOT, title="Badge State-Indicator Matrix")
    genomes = load_genomes()
    for genome, variants in SAMPLE.items():
        cfg = genomes[genome]
        for shape in _shapes_for(cfg):
            for variant in variants:
                for status in STATES:
                    gallery.add(
                        f"{genome}/{shape}/{variant}_{status.value}.svg",
                        spec(
                            "badge",
                            genome,
                            "BUILD",
                            status.value,
                            status.value,
                            "github",
                            variant=variant,
                            state_glyph_shape=shape,
                        ),
                    )
    return gallery


def emit(gallery: Gallery) -> Path:
    """Compose the gallery's README from its artifact records."""
    genomes = load_genomes()
    doc = Doc(f"HyperWeave {gallery.title}")
    doc.para(
        "The badge state indicator is a configurable shape — `square`, `circle` or `diamond` —",
        "with a per-paradigm default that `?state_glyph_shape=` overrides. Primer is the",
        "exception: its indicator is a state-KEYED animated mark (`status-glyph` — ping / throb /",
        "shake per state), its own system rather than a geometric, so it shows that one shape.",
    )
    doc.para(
        "Each shape below is a 3x3 grid — three variants down, passing / warning / critical",
        "across — so the shape dispatch and the per-variant indicator colour read together.",
    )
    doc.para(
        "A geometric forced onto a paradigm that does not own it (brutalist + `diamond`) draws",
        "the ring and bit but not the housing, because the housing routes through chrome's",
        "`--dna-diamond-*` variables. That is the cross-paradigm truth, not a broken render.",
    )
    doc.rule()

    for genome, variants in SAMPLE.items():
        cfg = genomes[genome]
        doc.h2(genome)
        for shape in _shapes_for(cfg):
            doc.h3(f"shape = `{shape}`")
            for variant in variants:
                doc.raw(f"**`{variant}`** — {_label(cfg, variant)}")
                doc.row([gallery.get(f"{genome}/{shape}/{variant}_{s.value}.svg") for s in STATES])

    doc.h2("Cross-reference")
    doc.bullets(
        [
            "[Proofset index](../README.md) — every gallery",
            *[f"[{g} genome](../genomes/{g}/README.md) — the full variant matrix" for g in SAMPLE],
        ]
    )
    path = gallery.root / "README.md"
    doc.write(path)
    return path
