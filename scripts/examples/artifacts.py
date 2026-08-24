"""The `/a/` namespace — standalone artifacts that belong to no genome.

Five generics (`block`, `current`, `takeoff`, `void`, `zeropoint`) that do NOT
theme to a genome: their templates hardcode their own colours and ignore the
genome dict by design. That is why they are not in any genome's `dividers`
whitelist and why `/v1/divider/{slug}/{genome}` refuses them with a 404 that
names their real address.

Currently the five editorial dividers (`block`, `current`, `takeoff`, `void`,
`zeropoint`) served at `/a/inneraura/dividers/<slug>`. They do NOT theme to a
genome — their templates hardcode their own colours and ignore the genome dict
by design — which is why they are in no genome's `dividers` whitelist and why
`/v1/divider/{slug}/{genome}` refuses them with a 404 naming their real address.

Named for the namespace rather than for dividers because the namespace is the
thing that will grow: anything served under `/a/` that is a standalone artifact
rather than a genome's rendering of one belongs here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.examples.manifest import Gallery
from scripts.examples.markdown import Doc
from scripts.examples.render import OUTPUTS, spec

if TYPE_CHECKING:
    from pathlib import Path

ARTIFACTS_ROOT = OUTPUTS / "artifacts"

# The five generics, with what each one is for.
DIVIDERS: tuple[tuple[str, str], ...] = (
    ("block", "a solid bar — the heaviest stop"),
    ("current", "a flowing rule — motion without direction"),
    ("takeoff", "an ascending rule — a section that lifts"),
    ("void", "negative space held open — a pause, not a mark"),
    ("zeropoint", "the origin rule — the default when none is named"),
)

# The genome is a formality: these templates paint their own colours. Brutalist
# is passed because compose() requires *a* genome, not because it changes them.
_CARRIER_GENOME = "brutalist"

# HTTP only. `/v1/divider/{slug}/{genome}` serves genome-themed slugs and
# answers these five with a 404 artifact naming their real address — deliberate
# behaviour, so the gallery records it rather than counting it as a gap.
#
# The CLI and MCP compose them normally: neither goes through that route, and
# `compose divider --divider-variant block` is a legitimate request. Declaring
# them unreachable there too would have been a lie in the audit's favour — the
# whole point of writing reasons down is that "not checked" and "checked and
# fine" stay distinguishable, which only holds if the reasons are true.
_HTTP_ROUTE_REFUSES = (
    "the /v1/divider/ route serves genome-themed slugs only and answers these with a 404 "
    "artifact naming /a/inneraura/dividers/<slug> — unreachable there BY DESIGN"
)


def build_gallery() -> Gallery:
    gallery = Gallery("artifacts", ARTIFACTS_ROOT, title="Standalone Artifacts — the `/a/` namespace")
    for slug, what in DIVIDERS:
        gallery.add(
            f"dividers/{slug}.svg",
            spec("divider", _CARRIER_GENOME, divider_variant=slug),
            caption=what,
            unreachable={"http": _HTTP_ROUTE_REFUSES},
        )
    return gallery


def emit(gallery: Gallery) -> Path:
    doc = Doc(f"HyperWeave {gallery.title}")
    doc.para(
        "Five rules that belong to no genome. Their templates carry their own colour, so passing",
        "a genome changes nothing — which is why they live at `/a/inneraura/dividers/<slug>`",
        "rather than `/v1/divider/{slug}/{genome}`, and why that route answers them with a 404",
        "artifact that names the right address instead of theming something un-themeable.",
    )
    doc.rule()
    for slug, what in DIVIDERS:
        doc.h3(f"`{slug}`")
        doc.para(what)
        doc.image(gallery.get(f"dividers/{slug}.svg"))
    doc.h2("Cross-reference")
    doc.bullets(
        [
            "[Proofset index](../README.md) — every gallery",
            "[genomes](../genomes/) — the themed dividers each genome declares",
        ]
    )
    path = gallery.root / "README.md"
    doc.write(path)
    return path
