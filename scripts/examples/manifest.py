"""What a gallery contains — declared once, rendered and documented from that.

An :class:`Artifact` binds an output path to the :class:`ComposeSpec` that
produces it. A :class:`Gallery` is the ordered set of them under one output
root, plus the document composed from it.

The point of the split is that a document can never describe an artifact that
was not rendered, and a render can never go undocumented: both read this. The
previous arrangement built the same filename twice — once in the renderer's
``_write(var_dir / f"badge_pypi_{variant}_default.svg", svg)`` and again in the
README emitter's ``f"![badge](proofset/{g}/variants/badge_pypi_{v}_default.svg)"``
— and papered over the gap with ``if path.exists()`` probes, so a rename showed
up as a silently-dropped section or a broken image.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from pathlib import Path

    from hyperweave.core.models import ComposeSpec


@dataclass(frozen=True)
class Artifact:
    """One rendered file and the spec behind it.

    ``rel`` is relative to the gallery root, which is also how the document
    links to it — the document sits at that root, so the link a reader clicks
    and the path on disk are the same string.

    ``unreachable`` maps a surface label ("cli" | "http" | "mcp") to the reason
    that surface cannot address this artifact. A surface gap must be WRITTEN
    DOWN, never merely skipped: the sweep prints these as an audit, so "not
    checked" and "checked and fine" are never confusable. Mirrors the rule
    ``surfaces/registry.py:register()`` applies to capabilities without an MCP
    tool.

    ``prerendered`` marks an artifact whose bytes came from a network-dependent
    path that already wrote them (the live stats and star-chart cards). The
    sweep leaves those alone: re-rendering would re-fetch, and comparing a
    freshly-fetched value against a pinned one would report a divergence that
    is a connector's clock rather than a parity defect.
    """

    id: str
    rel: str
    spec: ComposeSpec
    caption: str = ""
    unreachable: Mapping[str, str] = field(default_factory=dict)
    prerendered: bool = False

    def path_under(self, root: Path) -> Path:
        return root / self.rel


class Gallery:
    """An ordered artifact set under one output root.

    Ordering is declaration order, which is also reading order in the emitted
    document — so the code that declares a section reads in the same sequence
    as the page.
    """

    def __init__(self, name: str, root: Path, *, title: str = "") -> None:
        self.name = name
        self.root = root
        self.title = title or name
        self._artifacts: list[Artifact] = []
        self._by_rel: dict[str, Artifact] = {}

    def add(
        self,
        rel: str,
        spec: ComposeSpec,
        *,
        id: str = "",
        caption: str = "",
        unreachable: Mapping[str, str] | None = None,
        prerendered: bool = False,
    ) -> Artifact:
        """Declare an artifact. Returns it so a caller can link it immediately.

        Canonicalizes the spec first: a route may derive a field the caller
        left empty (the icon routes name the artifact after its glyph), and a
        spec that skipped that step renders one thing directly and another
        through its own URL. Canonicalizing at declaration means the artifact
        on disk is the one every surface agrees on.

        Re-declaring the same ``rel`` is an error rather than a silent
        overwrite — two specs writing one path is how a gallery loses a cell.
        """
        from hyperweave.surfaces.addressing import canonical_spec

        if rel in self._by_rel:
            raise ValueError(f"{self.name}: {rel} already declared by artifact {self._by_rel[rel].id!r}")
        artifact = Artifact(
            id=id or rel.replace("/", "-").removesuffix(".svg"),
            rel=rel,
            spec=canonical_spec(spec),
            caption=caption,
            unreachable=dict(unreachable or {}),
            prerendered=prerendered,
        )
        self._artifacts.append(artifact)
        self._by_rel[rel] = artifact
        return artifact

    def get(self, rel: str) -> Artifact:
        """The artifact at ``rel``. KeyError names the gallery — a document
        asking for something never declared is a bug in the declaration, and
        should say which gallery it looked in."""
        try:
            return self._by_rel[rel]
        except KeyError:
            raise KeyError(f"{self.name} has no artifact at {rel!r}") from None

    def __iter__(self) -> Iterator[Artifact]:
        return iter(self._artifacts)

    def __len__(self) -> int:
        return len(self._artifacts)

    @property
    def artifacts(self) -> Sequence[Artifact]:
        return tuple(self._artifacts)
