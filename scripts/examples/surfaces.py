"""Render every declared artifact through every surface that can address it.

Invariant 9 says CLI, HTTP and MCP have feature parity. A test can assert that
on a handful of specs; this makes it continuous over the whole corpus — each
gallery artifact is composed directly, fetched by its own URL, invoked through
the real `hyperweave compose` parser, and called as `hw_compose`, and the four
results must be byte-identical after volatile-fragment scrubbing.

That was previously unaffordable. Reaching an artifact over HTTP meant writing
its URL by hand, so parity covered the 204 specs someone had written three
addresses for and skipped the ~1100 gallery artifacts entirely. With
``surfaces/addressing.py`` projecting the addresses, coverage is a loop.

**A gap must be stated.** An artifact a surface genuinely cannot express
(pre-resolved data tokens, an inline genome override, a frame with no image
route) is recorded with its reason and printed in the audit. Nothing is
silently skipped — the difference between "checked and identical" and "never
checked" has to survive into the report, or a ✅ runs ahead of reality.

Only the direct render is kept on disk: it IS the gallery artifact. A surface
that diverges gets its bytes written beside it as
``<name>.<surface>-diverged.svg`` so the difference can be looked at, which is
the only moment the extra file is worth its size.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from hyperweave.surfaces.addressing import (
    Unaddressable,
    normalize_artifact,
    spec_to_cli_argv,
    spec_to_mcp_args,
    spec_to_url,
)
from scripts.examples.render import render, write

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from scripts.examples.manifest import Artifact, Gallery

# Direct is not optional — it produces the bytes the gallery ships. The other
# three are the parity witnesses.
DIRECT = "direct"
WITNESSES: tuple[str, ...] = ("cli", "http", "mcp")
ALL_SURFACES: tuple[str, ...] = (DIRECT, *WITNESSES)


@dataclass
class Coverage:
    """Per-artifact outcome of the sweep."""

    artifact_id: str
    matched: list[str] = field(default_factory=list)
    diverged: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    errored: dict[str, str] = field(default_factory=dict)

    @property
    def clean(self) -> bool:
        return not self.diverged and not self.errored


@dataclass
class Report:
    """The sweep's result — countable, and printable as an audit."""

    gallery: str
    rendered: int = 0
    coverage: list[Coverage] = field(default_factory=list)

    @property
    def divergences(self) -> list[tuple[str, str]]:
        return [(c.artifact_id, s) for c in self.coverage for s in c.diverged]

    @property
    def errors(self) -> list[tuple[str, str, str]]:
        return [(c.artifact_id, s, why) for c in self.coverage for s, why in c.errored.items()]

    def checks(self, surface: str) -> int:
        return sum(1 for c in self.coverage if surface in c.matched)

    def skips(self) -> dict[str, list[tuple[str, str]]]:
        """surface -> [(artifact_id, reason)] — the addressability audit."""
        grouped: dict[str, list[tuple[str, str]]] = {}
        for cov in self.coverage:
            for surface, reason in cov.skipped.items():
                grouped.setdefault(surface, []).append((cov.artifact_id, reason))
        return grouped

    def summary(self) -> str:
        checked = " · ".join(f"{s} {self.checks(s)}" for s in WITNESSES)
        tail = f", {len(self.divergences)} DIVERGED" if self.divergences else ""
        return f"{self.gallery}: {self.rendered} artifacts · surface-checked {checked}{tail}"

    def audit_lines(self) -> list[str]:
        """One line per distinct (surface, reason) with how many artifacts hit it.

        Grouped rather than listed per artifact: 300 strips sharing one missing
        CLI flag is one fact, and printing it 300 times buries the other gaps.
        """
        counts: dict[tuple[str, str], int] = {}
        for surface, entries in self.skips().items():
            for _artifact_id, reason in entries:
                counts[surface, reason] = counts.get((surface, reason), 0) + 1
        return [
            f"  [{surface}] {count} artifact(s) — {reason}"
            for (surface, reason), count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]


def _cli_render(argv: Sequence[str]) -> str:
    """Run the REAL `hyperweave compose` parser in-process.

    Typer's CliRunner, not a direct call to the underlying function: per the
    Guard Law the surface under test is the command line a user types, so the
    argv has to survive real parsing. In-process because 1000+ subprocess
    spawns would put this sweep out of reach.
    """
    from typer.testing import CliRunner

    from hyperweave.cli import app as cli_app

    result = CliRunner().invoke(cli_app, ["compose", *argv])
    if result.exit_code != 0:
        raise RuntimeError(f"exit {result.exit_code}: {(result.output or '').strip()[:200]}")
    return result.stdout


async def sweep(
    gallery: Gallery,
    *,
    witnesses: Iterable[str] = WITNESSES,
    http_base_url: str = "",
    mcp: Any = None,
) -> Report:
    """Render every artifact in ``gallery`` and check the requested witnesses.

    ``witnesses`` empty renders direct-only — the fast path for iterating on a
    gallery's content. HTTP needs a running server's base URL, MCP an open
    client; a witness whose transport was not supplied is recorded as skipped
    with that as the reason, so a partial run never reads as a clean one.
    """
    wanted = tuple(witnesses)
    report = Report(gallery=gallery.name)

    for artifact in gallery:
        cov = Coverage(artifact_id=artifact.id)
        if artifact.prerendered:
            # Bytes already on disk from a live-data path. Re-rendering would
            # re-fetch, so a mismatch would report a connector's clock rather
            # than a parity defect — stated, not silently passed over.
            reason = "rendered from live connector data; re-fetching would compare two different moments"
            cov.skipped = dict.fromkeys(wanted, reason)
            report.coverage.append(cov)
            continue

        svg = render(artifact.spec)
        write(artifact.path_under(gallery.root), svg)
        report.rendered += 1
        expected = normalize_artifact(svg)

        for surface in wanted:
            declared = artifact.unreachable.get(surface)
            if declared:
                cov.skipped[surface] = declared
                continue
            try:
                actual = await _witness(surface, artifact, http_base_url, mcp)
            except Unaddressable as exc:
                cov.skipped[surface] = exc.reason
                continue
            except _TransportMissing as exc:
                cov.skipped[surface] = str(exc)
                continue
            except Exception as exc:
                cov.errored[surface] = f"{type(exc).__name__}: {exc}"
                continue
            if normalize_artifact(actual) == expected:
                cov.matched.append(surface)
            else:
                cov.diverged.append(surface)
                _write_divergence(gallery.root, artifact, surface, actual)
        report.coverage.append(cov)

    return report


class _TransportMissing(RuntimeError):
    """A witness was requested without the transport it needs."""


async def _witness(surface: str, artifact: Artifact, http_base_url: str, mcp: Any) -> str:
    if surface == "cli":
        return await asyncio.to_thread(_cli_render, spec_to_cli_argv(artifact.spec))
    if surface == "http":
        import httpx

        if not http_base_url:
            raise _TransportMissing("no HTTP server base URL supplied to the sweep")
        url = spec_to_url(artifact.spec, base_url=http_base_url)
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        if "X-HW-Error-Code" in response.headers:
            raise RuntimeError(f"served an error artifact ({response.headers['X-HW-Error-Code']}) for {url}")
        return response.text
    if surface == "mcp":
        if mcp is None:
            raise _TransportMissing("no MCP client supplied to the sweep")
        from scripts.examples.harness import unwrap_mcp_svg

        result = await mcp.call_tool("hw_compose", {**spec_to_mcp_args(artifact.spec), "respond": "svg"})
        return unwrap_mcp_svg(result)
    raise ValueError(f"unknown surface {surface!r}")


def _write_divergence(root: Path, artifact: Artifact, surface: str, svg: str) -> None:
    """Keep the diverging bytes next to the artifact so the diff is lookable-at."""
    write(root / f"{artifact.rel.removesuffix('.svg')}.{surface}-diverged.svg", svg)
