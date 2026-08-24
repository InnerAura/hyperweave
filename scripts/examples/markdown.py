"""The small vocabulary gallery documents are written in.

Every emitter used to build its page by appending raw strings to a list, which
is why four near-identical genome READMEs drifted apart in their spacing, their
rule placement and their image-row grouping. A handful of named moves keeps the
pages one document family, and keeps the image link derived from the artifact
record rather than retyped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scripts.examples.manifest import Artifact


class Doc:
    """A markdown page under construction.

    Blank-line discipline lives here rather than in every caller: methods emit
    their own trailing blank, and :meth:`text` collapses runs so a section that
    ends with a rule and one that does not produce the same spacing.
    """

    def __init__(self, title: str) -> None:
        self._lines: list[str] = []
        self.h1(title)

    def h1(self, text: str) -> Doc:
        return self._block(f"# {text}")

    def h2(self, text: str) -> Doc:
        return self._block(f"## {text}")

    def h3(self, text: str) -> Doc:
        return self._block(f"### {text}")

    def para(self, *chunks: str) -> Doc:
        """One paragraph. Chunks join with a space — so a long sentence can be
        written across several source lines without smuggling a hard break in."""
        return self._block(" ".join(c for c in chunks if c))

    def italic(self, text: str) -> Doc:
        return self._block(f"_{text}_") if text else self

    def rule(self) -> Doc:
        return self._block("---")

    def raw(self, text: str) -> Doc:
        return self._block(text)

    def bullets(self, items: Iterable[str]) -> Doc:
        rendered = [f"- {item}" for item in items]
        return self._block("\n".join(rendered)) if rendered else self

    def row(self, artifacts: Iterable[Artifact], *, alt: str = "") -> Doc:
        """Images on ONE line so a markdown renderer lays them side by side.

        Link targets come straight off the artifact records — the gallery
        document cannot reference a file the gallery did not render.
        """
        # Default alt is the filename stem — what the artifact IS, without the
        # directory prefix that the record id carries for uniqueness.
        cells = [f"![{alt or art.rel.rsplit('/', 1)[-1].removesuffix('.svg')}]({art.rel})" for art in artifacts]
        return self._block(" ".join(cells)) if cells else self

    def image(self, artifact: Artifact, *, alt: str = "") -> Doc:
        return self.row([artifact], alt=alt)

    def details(self, summary: str, body: str) -> Doc:
        return self._block(f"<details><summary>{summary}</summary>\n\n{body.rstrip()}\n\n</details>")

    def _block(self, text: str) -> Doc:
        self._lines.append(text)
        return self

    def text(self) -> str:
        return "\n\n".join(self._lines) + "\n"

    def write(self, path: str | object) -> None:
        from pathlib import Path

        target = Path(str(path))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.text())
