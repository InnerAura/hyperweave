"""One browsable page over every family document — `topologies/index.html`.

The exhibits are markdown because markdown is what GitHub renders, but reading
twelve of them means twelve files, each a few hundred lines of prose wrapped
around figures the reader actually came for. This composes the same documents
into one page: a tab per family, the whole document in one vertical scroll, the
figures inline exactly as the markdown lays them out.

Nothing is authored here. The page is COMPOSED from the `README_<FAMILY>.md`
files on disk, so a family that gains a document gains a tab and a family that
loses one loses its tab — there is no list to keep in step. The figures are
referenced by the same relative paths the markdown uses, so an SVG re-rendered
after this page was built shows its new bytes on the next reload; only the prose
is baked, and every `diagrams` run rebuilds it.

Run: ``uv run python -m scripts.examples.topologies.viewer`` (via
``just topology-viewer``), or as the last step of ``just diagrams``.
"""

from __future__ import annotations

import html
import pathlib
import re
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

if TYPE_CHECKING:
    from collections.abc import Iterator

_REPO = pathlib.Path(__file__).resolve().parents[3]
_TEMPLATES = pathlib.Path(__file__).parent / "templates"

PAGE = "index.html"
"""Written into the document directory itself, so every `../renders/...` path a
family document already carries resolves from the page without rewriting."""

# Raw tags a document is allowed to spend. The exhibits use `<sub>` for the
# identity line under a figure; everything else that looks like a tag is text
# and stays text — `bound-hostile-labels` has a literal `<angles>` in its
# heading, and a renderer that swallowed it would hide the very thing that
# figure exists to prove.
_RAW_TAGS = ("sub", "/sub", "br", "b", "/b", "i", "/i", "em", "/em", "strong", "/strong")

_CODE = re.compile(r"`([^`]+)`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*([^*\n]+)\*(?!\*)")
_UNDERSCORE_ITALIC = re.compile(r"(?<![_\w])_([^_\n]+)_(?![_\w])")
_FENCE = re.compile(r"^```")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_FAMILY_DOC = re.compile(r"^README_([A-Z0-9_]+)\.md$")


def _href(target: str) -> str:
    """A link to a SIBLING family document is a link to a tab.

    The exhibits cross-reference each other by filename, which is right in the
    markdown and wrong here — following it would drop the reader out of the page
    into raw markdown. Everything else (the gallery index, the specimen board)
    still points at the file, because those documents are not tabs on this page.
    """
    match = _FAMILY_DOC.match(target)
    return f"#{match.group(1).lower().replace('_', '-')}" if match else target


def _inline(text: str) -> str:
    """Markdown's inline vocabulary, in the one order that survives itself.

    Code spans come out FIRST and go back in LAST: a span holding `**` or a
    pipe is content, and every later rule would otherwise read it as markup.
    Escaping sits between the two, so prose can never smuggle a tag in while
    the allowlisted ones above still render.
    """
    spans: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        spans.append(match.group(1))
        return f"\x00{len(spans) - 1}\x00"

    out = _CODE.sub(_stash, text)
    out = html.escape(out)
    for tag in _RAW_TAGS:
        out = out.replace(f"&lt;{tag}&gt;", f"<{tag}>")
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _ITALIC.sub(r"<em>\1</em>", out)
    out = _UNDERSCORE_ITALIC.sub(r"<em>\1</em>", out)
    out = _LINK.sub(lambda m: f'<a href="{_href(m.group(2))}">{m.group(1)}</a>', out)
    for index, span in enumerate(spans):
        out = out.replace(f"\x00{index}\x00", f"<code>{html.escape(span)}</code>")
    return out


def _plain(text: str) -> str:
    """Heading text with its markup taken off — what an outline entry reads as."""
    out = _CODE.sub(r"\1", text)
    out = _BOLD.sub(r"\1", out)
    return _ITALIC.sub(r"\1", out).strip()


def _slug(text: str) -> str:
    return _SLUG_STRIP.sub("-", _plain(text).lower()).strip("-") or "section"


def _images(line: str) -> list[dict[str, str]]:
    """The images on a line, if the line is NOTHING BUT images.

    A figure row is its own block — the exhibits write one image per line and
    the genome galleries write several side by side, and both should lay out as
    figures rather than as a paragraph that happens to contain pictures.
    """
    if not line.lstrip().startswith("!["):
        return []
    if _IMAGE.sub("", line).strip():
        return []
    return [{"alt": alt, "src": src} for alt, src in _IMAGE.findall(line)]


def _measure(root: pathlib.Path, image: dict[str, str], missing: list[str]) -> dict[str, str]:
    """Stamp a figure with the render's own width and height.

    288 lazily-loaded figures with no reserved box means the page grows under
    the reader as they stream in — and a deep link into section 5 lands in
    section 3, because everything above it got taller after the jump. The
    render already carries its size; carrying it onto the ``img`` reserves the
    box before a byte of the SVG arrives.
    """
    target = root / image["src"]
    if not target.exists():
        missing.append(image["src"])
        return image
    head = target.read_text()[:1200]
    width = re.search(r'\bwidth="([\d.]+)"', head)
    height = re.search(r'\bheight="([\d.]+)"', head)
    if width and height:
        return {**image, "w": width.group(1), "h": height.group(1)}
    # A render that pins no rendered size still declares its viewBox, and the
    # ratio is what reserves the box once `height: auto` scales it.
    box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', head)
    return {**image, "w": box.group(1), "h": box.group(2)} if box else image


def _table(rows: list[str]) -> dict[str, Any]:
    """A pipe table. Row two is the alignment rule and carries no content."""

    def cells(row: str) -> list[str]:
        return [_inline(c.strip()) for c in row.strip().strip("|").split("|")]

    body = rows[2:] if len(rows) > 1 and set(rows[1].replace("|", "").strip()) <= set("-: ") else rows[1:]
    return {"kind": "table", "head": cells(rows[0]), "rows": [cells(r) for r in body]}


def _blocks(source: str) -> Iterator[dict[str, Any]]:
    """Markdown to a block list — structure in Python, markup in the template.

    Deliberately narrow: it reads the vocabulary `scripts/examples/markdown.py`
    can emit plus the fences and tables the exhibits write by hand. Anything
    wider would be a markdown library, and this page does not need one.
    """
    lines = source.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        if _FENCE.match(line):
            i += 1
            start = i
            while i < len(lines) and not _FENCE.match(lines[i]):
                i += 1
            yield {"kind": "code", "text": "\n".join(lines[start:i])}
            i += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2)
            yield {
                "kind": "heading",
                "level": level,
                "html": _inline(text),
                "text": _plain(text),
                "id": _slug(text),
            }
            i += 1
            continue

        figures = _images(line)
        if figures:
            yield {"kind": "figures", "images": figures}
            i += 1
            continue

        if line.startswith("|"):
            start = i
            while i < len(lines) and lines[i].startswith("|"):
                i += 1
            yield _table(lines[start:i])
            continue

        if line.startswith("> "):
            start = i
            while i < len(lines) and lines[i].startswith("> "):
                i += 1
            yield {"kind": "quote", "html": _inline(" ".join(x[2:] for x in lines[start:i]))}
            continue

        if line.startswith("- "):
            items: list[str] = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(_inline(lines[i][2:]))
                i += 1
            yield {"kind": "list", "items": items}
            continue

        if line.strip() == "---":
            yield {"kind": "rule"}
            i += 1
            continue

        start = i
        while i < len(lines) and lines[i].strip() and not _stops_a_paragraph(lines[i]):
            i += 1
        yield {"kind": "para", "html": _inline(" ".join(x.strip() for x in lines[start:i]))}


def _stops_a_paragraph(line: str) -> bool:
    """A line that opens some other block, so a paragraph must end before it."""
    return bool(
        _HEADING.match(line)
        or _FENCE.match(line)
        or _images(line)
        or line.startswith(("|", "> ", "- "))
        or line.strip() == "---"
    )


def read(path: pathlib.Path, missing: list[str]) -> dict[str, Any]:
    """One family document as a tab: its blocks, its outline, its figure count."""
    slug = path.stem.removeprefix("README_").lower().replace("_", "-")
    root = path.parent
    blocks = list(_blocks(path.read_text()))
    title = next((b["text"] for b in blocks if b["kind"] == "heading" and b["level"] == 1), slug)
    body = [b for b in blocks if not (b["kind"] == "heading" and b["level"] == 1)]
    for block in body:
        if block["kind"] == "figures":
            block["images"] = [_measure(root, image, missing) for image in block["images"]]
    return {
        "slug": slug,
        "title": title,
        "blocks": body,
        "outline": [{"id": b["id"], "text": b["text"]} for b in body if b["kind"] == "heading" and b["level"] == 2],
        "figures": sum(len(b["images"]) for b in body if b["kind"] == "figures"),
        "source": path.name,
    }


def build(root: pathlib.Path) -> pathlib.Path:
    """Compose every `README_<FAMILY>.md` under ``root`` into one tabbed page."""
    documents = sorted(root.glob("README_*.md"))
    if not documents:
        raise SystemExit(f"no family documents under {root} — run `just diagrams` first")
    missing: list[str] = []
    families = sorted((read(p, missing) for p in documents), key=lambda f: f["slug"])
    # A document citing a figure that is not on disk means its gallery has not
    # been rebuilt since the document was. Said out loud, not swallowed: the
    # page would otherwise show a silent gap where a proof belongs.
    for gone in missing:
        print(f"  MISSING FIGURE {gone} — rerun `just diagrams` for that family")
    env = Environment(loader=FileSystemLoader(str(_TEMPLATES)), undefined=StrictUndefined, autoescape=True)
    page = root / PAGE
    page.write_text(
        env.get_template("topologies.html.j2").render(
            families=families,
            figures=sum(f["figures"] for f in families),
        )
    )
    return page


def main() -> int:
    page = build(_REPO / "outputs" / "diagrams" / "topologies")
    print(f"{page.relative_to(_REPO)} — {page.stat().st_size // 1024}kb")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
