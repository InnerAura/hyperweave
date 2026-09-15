"""The shared skeleton every per-family exhibit is built on.

Lifted verbatim from the dag exhibit, which was the first and for a while the
only one. Every family renders the same way — porcelain light, baked, bare
ground, so a viewer's theme cannot flip an exhibit — and every family's document
is COMPOSED from its renders rather than written beside them.

What is shared is the vocabulary, not the content: a section, an exhibit entry,
a refusal rendered as evidence, the render scale a figure came out at. What a
family SHOWS — its axes, its scenarios, the capability edges worth pinning, the
caps worth provoking — is the family's own, and lives in its module.

`dag` is the deep template: seven sections built over a review wave. A family
that has not been through that yet runs :func:`build_story_exhibit`, which shows
its real stories and grades their composition; it deepens toward the dag shape
as its axes get pinned rather than pretending to be there already.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from hyperweave.compose.engine import compose
from hyperweave.core.diagram import DiagramCapacityError, DiagramInputError
from scripts.examples.render import gallery_spec

if TYPE_CHECKING:
    import pathlib

# One geometry, one face, every family. Baked porcelain light: `palette=fixed`
# plus an explicit `surface_face` means the artifact carries its own scheme, so
# an exhibit reads the same in a dark editor as in a light preview pane.
FACE: dict[str, Any] = {
    "genome_id": "primer",
    "variant": "porcelain",
    "ground": "bare",
    "palette": "fixed",
    "surface_face": "light",
}

Exhibit = tuple[str, str, dict[str, Any]]
"""(slug, one-line what-it-shows, DiagramSpec dict)."""


def render(out: pathlib.Path, slug: str, spec: dict[str, Any], section: str) -> str:
    """Compose one figure into ``<out>/<section>/<slug>.svg``; return the SVG.

    A spec naming marks gets the anatomy that can carry them: most chassis have
    no glyph slot by default, so a bare `kind`/`glyph` declaration would render
    nothing and the exhibit would silently show a card where it promised a mark.
    """
    if "node_style" not in spec and any(n.get("kind") or n.get("glyph") for n in spec.get("nodes", [])):
        spec = {**spec, "node_style": "card+glyph"}
    svg = compose(gallery_spec(type="diagram", diagram=spec, **FACE)).svg
    (out / section).mkdir(parents=True, exist_ok=True)
    (out / section / f"{slug}.svg").write_text(svg)
    return svg


def refusal(spec: dict[str, Any]) -> str:
    """The refusal sentence a cap produces — or a finding that it did not bite.

    Boundaries are shown as EVIDENCE: the literal message a caller receives.
    A cap that stopped refusing is a change to the contract, so it is reported
    in the document rather than passing quietly.
    """
    try:
        compose(gallery_spec(type="diagram", diagram=spec, **FACE))
    except (DiagramCapacityError, DiagramInputError) as exc:
        return str(exc)
    except Exception as exc:
        return f"UNEXPECTED {type(exc).__name__}: {exc}"
    return "NO REFUSAL — the cap did not bite"


def section(lines: list[str], title: str, blurb: str) -> None:
    lines += [f"## {title}", "", blurb, ""]


def exhibit(
    lines: list[str],
    out: pathlib.Path,
    slug: str,
    what: str,
    spec: dict[str, Any],
    sect: str,
    *,
    note: str = "",
) -> int:
    """Render a figure and write its entry. Returns 1, so callers can sum."""
    render(out, slug, spec, sect)
    lines += [f"#### `{slug}` — {spec.get('title', slug)}", "", what, ""]
    if note:
        lines += [f"*{note}*", ""]
    # The document lives in `topologies/` while the renders live in
    # `renders/topologies/<family>/` — the image path must climb across
    # (dag's own duplicate helper always did; the shared one silently
    # wrote a section-relative path that resolved to nothing).
    lines += [f"![{slug}](../renders/topologies/{out.name}/{sect}/{slug}.svg)", ""]
    return 1


def scale_of(svg: str) -> str:
    """The render scale a figure came out at (rendered width / viewBox width).

    Worth showing per figure: a family whose scales wander is one whose sizing
    is reacting to content instead of holding a figure-level constant.
    """
    box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg)
    width = re.search(r'\bwidth="([\d.]+)"', svg)
    if not box or not width:
        return "?"
    return f"{float(width.group(1)) / float(box.group(1)):.3f}"


# topology slug -> [(gallery dir, filename, title, one-line why it is here)].
# A topology directory is the GESTALT view of that topology: everything the
# system can show about it, in one scroll. Renders that belong to a family but
# are owned by a gallery organised on a different axis — the card+label board is
# about a node style and happens to draw a hub; the specimen board is about
# recreation fidelity and covers nine families — would otherwise be invisible to
# someone auditing that family. A cross-link does not fix that: the reviewer
# wants to SEE them together, not be told where else to look.
_ELSEWHERE: dict[str, list[tuple[str, str, str, str]]] = {}


def register_elsewhere(topology: str, gallery: str, filename: str, title: str, why: str) -> None:
    """Record a render that belongs to ``topology`` but lives in another gallery."""
    if topology and topology != "?":
        _ELSEWHERE.setdefault(topology, []).append((gallery, filename, title, why))


def _elsewhere_section(topology: str) -> list[str]:
    """Renders of this topology owned by a gallery on a different axis.

    Embedded, not linked. A reviewer auditing a family wants the whole family in
    one scroll — being told that a fourteenth hub exists in another document is
    the same as not being told. Paths reach back up out of the family directory,
    so the images resolve without a second copy on disk.
    """
    found = _ELSEWHERE.get(topology) or []
    if not found:
        return []
    lines = [
        "---",
        "",
        f"## Also this topology ({len(found)})",
        "",
        "Renders that belong to this family but are owned by a gallery organised on a different",
        "axis — a node style, a recreation board, a palette sweep. Shown here so the family reads",
        "in one scroll rather than being scattered across documents.",
        "",
    ]
    for gallery, filename, title, why in found:
        lines += [
            f"#### {title}",
            "",
            f"`{gallery}` — {why}",
            "",
            f"![{title}](../renders/{gallery}/{filename})",
            "",
        ]
    return lines
