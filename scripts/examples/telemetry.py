"""The receipt gallery — one session, rendered as a document.

Receipts speak the primer genome; the chromatic variant is a free choice. The
agent runtime sets only the identity glyph and wordmark, never a theme, so the
gallery reads as two kinds of section: each harness's own size range in ONE
colour (size is the variable, not the palette), then one real session swept
across all eight variants plus raw (colour is the variable, content is fixed).

Every receipt renders a REAL transcript. The artifact set is therefore
machine-dependent, and the gallery is DECLARED from what discovery returned
rather than from a fixed roster — a hardcoded list would cite five receipts on a
checkout that has two, and a synthetic filler would put numbers on the page that
no reader can tell apart from measured ones.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scripts.examples.manifest import Gallery
from scripts.examples.markdown import Doc
from scripts.examples.render import OUTPUTS, spec

if TYPE_CHECKING:
    from pathlib import Path

TELEMETRY_ROOT = OUTPUTS / "telemetry"

# Each harness renders its size range in one colour, so the range reads as size
# rather than as three palettes. Claude Code in cream, Codex in porcelain — two
# harnesses, two session shapes, by design.
HARNESS_VARIANT: dict[str, str] = {"claude": "cream", "codex": "porcelain"}

# The chromatic showcase: every primer variant plus the raw genome's thermal
# register-tape, all on ONE payload so the only difference is colour.
SHOWCASE_VARIANTS: tuple[str, ...] = (
    "porcelain",
    "cream",
    "noir",
    "carbon",
    "space",
    "anvil",
    "dusk",
    "petrol",
)

# A receipt carries a whole transcript. HTTP has no image route for that (a
# path cannot hold it) and the CLI takes a file rather than an inline payload —
# both stated in data/config/url-grammar.yaml and addressing's CLI table, so
# the sweep reports them without a per-artifact declaration here.


def build_gallery(sessions: dict[str, list[tuple[str, dict[str, Any]]]]) -> Gallery:
    """Declare the receipts.

    ``sessions`` maps a harness name to its discovered ``(label, payload)``
    pairs, already parsed and cost-bucketed by the caller — discovery reaches
    into local agent history, which is a machine concern rather than a gallery
    one.

    Every receipt here renders a REAL session. The chromatic showcase used to
    run on the synthetic payload because one mock can be built to exercise all
    three reset kinds and three models at once — but a showcase of invented
    numbers is a showcase of nothing, and the coverage argument does not survive
    the fact that a reader cannot tell which cells are real. With no discoverable
    transcript the showcase is empty and says so.
    """
    gallery = Gallery("telemetry", TELEMETRY_ROOT, title="Telemetry — Receipt Tour")

    for harness, variant in HARNESS_VARIANT.items():
        for label, payload in sessions.get(harness, [])[:5]:
            gallery.add(
                f"{harness}/{label}.svg",
                spec("receipt", "primer", variant=variant, telemetry_data=payload),
                caption=f"{harness} session — {label}",
            )

    # The chromatic showcase: ONE real session across every variant, so the only
    # difference down the section is colour. The costliest discovered session
    # carries the most structure to look at.
    showcase = _showcase_payload(sessions)
    if showcase is not None:
        for variant in SHOWCASE_VARIANTS:
            gallery.add(
                f"showcase/{variant}.svg",
                spec("receipt", "primer", variant=variant, telemetry_data=showcase),
            )
        gallery.add("showcase/raw.svg", spec("receipt", "raw", telemetry_data=showcase))
    return gallery


def _showcase_payload(sessions: dict[str, list[tuple[str, dict[str, Any]]]]) -> dict[str, Any] | None:
    """The richest REAL session to run the chromatic sweep on, or None.

    Cost is the proxy for structure: a costlier session ran longer, touched more
    tools and more models, so it fills more of the receipt. Returns None when
    nothing was discovered — the section then states its absence instead of
    substituting synthetic numbers.
    """
    every = [payload for harness in sessions.values() for _label, payload in harness]
    if not every:
        return None
    return max(every, key=lambda p: float(p.get("cost_usd") or 0.0))


def emit(gallery: Gallery) -> Path:
    """Compose the receipt tour from its artifact records."""
    doc = Doc(f"HyperWeave {gallery.title}")
    doc.para(
        "Receipts speak the **primer** genome; the chromatic variant is a free choice. The agent",
        "runtime sets only the identity glyph and wordmark, never a theme — so each harness shows",
        "its size range in one colour, and the chromatic range gets its own section.",
    )
    doc.rule()

    for harness, variant in HARNESS_VARIANT.items():
        found = [a for a in gallery if a.rel.startswith(f"{harness}/")]
        if not found:
            doc.h2(f"{harness} — size range")
            doc.para(
                f"No {harness} transcript was discoverable on this machine, so this section is",
                "empty rather than filled with mock data wearing a real session's label.",
            )
            continue
        doc.h2(f"{harness} — size range ({variant})")
        doc.para(f"{len(found)} sessions, ascending in cost. Size is the variable; the palette is fixed.")
        for artifact in found:
            doc.h3(artifact.rel.rsplit("/", 1)[-1].removesuffix(".svg"))
            doc.image(artifact)

    doc.rule()
    doc.h2("Chromatic showcase")
    if not any(a.rel.startswith("showcase/") for a in gallery):
        doc.para(
            "No transcript was discoverable on this machine, so there is nothing real to sweep",
            "across the palette. The section is empty rather than filled with invented numbers — a",
            "showcase a reader cannot trust is worse than no showcase.",
        )
    else:
        doc.para(
            "ONE real session across every primer variant plus the raw genome's thermal",
            "register-tape. The costliest discovered session, because cost is the proxy for",
            "structure — a longer run touched more tools and more models, so it fills more of the",
            "receipt. Every number below came off an actual transcript.",
        )
        for variant in SHOWCASE_VARIANTS:
            doc.h3(f"`{variant}`")
            doc.image(gallery.get(f"showcase/{variant}.svg"))
        doc.h3("`raw`")
        doc.para("A till receipt is one typeface — monospace end to end, no Inter.")
        doc.image(gallery.get("showcase/raw.svg"))

    doc.h2("Cross-reference")
    doc.bullets(
        [
            "[Proofset index](../README.md) — every gallery",
            "[primer genome](../genomes/primer/README.md) — the substrate matrix receipts ride",
        ]
    )
    path = gallery.root / "README.md"
    doc.write(path)
    return path
