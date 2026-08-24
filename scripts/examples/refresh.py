#!/usr/bin/env python3
"""Re-render the committed telemetry example receipts with the current code.

``assets/examples/telemetry/`` holds a small hand-curated set of session-receipt
specimens (cream / porcelain / raw) that the README and docs embed. They drift
whenever the receipt template, the telemetry contract, or the primer genome
changes — a parser or shadow fix lands in the pipeline but the committed
specimen still shows the old shape until someone re-renders it. This script IS
that re-render, wired to ``just refresh-examples`` so it's a one-command chore
before a release rather than a manual compose-and-copy dance.

The curated set is TWO HARNESSES, TWO SESSION SHAPES by design: cream = a
Claude Code session, porcelain = a Codex session, raw = a Claude Code session
on the raw genome. Each specimen refreshes from ITS OWN harness's largest
discovered transcript; a harness with no discoverable transcript SKIPS its
specimens loudly (the committed file stays) — the set is never flattened onto
one payload. ``--mock`` renders the shared ``MOCK_RECEIPT_PAYLOAD`` instead
(dev-only; it prints a do-not-commit warning).

The receipt embeds a ``<hw:created>`` timestamp, so the clock is pinned to a
fixed instant — otherwise every run would differ only in that timestamp and the
recipe would never be idempotent. Same input + same code → same bytes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[2]
# src/ for the package; the repo root so `scripts.*` imports as a package.
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT))

from hyperweave.compose.diagram.input import resolve_diagram_preset  # noqa: E402
from hyperweave.compose.engine import compose  # noqa: E402
from hyperweave.core.models import ComposeSpec  # noqa: E402
from hyperweave.surfaces.addressing import normalize_artifact  # noqa: E402
from hyperweave.verbs.parse import extract_embedded  # noqa: E402
from hyperweave.verbs.transform import transform  # noqa: E402

# The receipt data contract + real-transcript discovery live in the proofset
# generator; import them so the two surfaces can never drift on the shape of a
# receipt payload or on how a "real" transcript is chosen.
from scripts.examples.proofset import (  # noqa: E402
    MOCK_RECEIPT_PAYLOAD,
    _load_real_telemetry,
    _real_codex_transcripts,
    _real_transcripts,
)

_OUT = _ROOT / "assets" / "examples" / "telemetry"
_DIAGRAMS_OUT = _ROOT / "assets" / "examples" / "diagrams"
_MATRICES_OUT = _ROOT / "assets" / "examples" / "matrices"

# A fixed instant so the embedded <hw:created> stamp is stable across runs —
# the recipe is idempotent (re-run with no code change ⇒ byte-identical files).
_PINNED_CLOCK = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)

# The committed specimen set: (filename, genome, variant, harness source).
# Two harnesses, two session shapes BY DESIGN — cream shows a Claude Code
# session, porcelain a Codex one; raw is the Claude session on the raw genome.
_SPECIMENS: tuple[tuple[str, str, str, str], ...] = (
    ("receipt_cream.svg", "primer", "cream", "claude"),
    ("receipt_porcelain.svg", "primer", "porcelain", "codex"),
    ("receipt_raw.svg", "raw", "", "claude"),
)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
        return _PINNED_CLOCK


# Two renders of identical CONTENT still differ in their per-render identity:
# the embedded woff2 carries a subsetter timestamp (and fontTools compression is
# not bit-stable), the element-id prefix is a fresh UID, and the version string
# comes from git describe. Compare through the package's volatile-fragment
# scrub so the recipe rewrites a specimen ONLY when something a reader could
# notice changed — keeping `git status` after a refresh a signal rather than
# noise. The same predicate the cross-surface parity sweep uses.
#
# _FONT_BLOB stays: it is broader than the package regex (any base64 data URI,
# not just woff2), which the older hand-authored specimens still need.
_FONT_BLOB = re.compile(r"data:[^;]*;base64,[A-Za-z0-9+/=]+")


def _structural(svg: str) -> str:
    return normalize_artifact(_FONT_BLOB.sub("FONT", svg))


def _harness_payload(source: str) -> tuple[dict[str, Any], str] | None:
    """The largest usable transcript FOR ONE HARNESS, or None (skip loudly).

    The discoverers already drop subagent sidechains and sub-floor files;
    the loader is format-aware for both harness transcript shapes."""
    discover = _real_transcripts if source == "claude" else _real_codex_transcripts
    candidates = sorted(
        (p for _label, p in discover() if p.is_file()),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    for path in candidates:
        payload = _load_real_telemetry(path)
        if payload is not None:
            return payload, f"live:{source}:{path.name}"
    return None


def refresh(mock: bool = False) -> list[Path]:
    """Re-render the telemetry specimens; return the paths written.

    Each specimen refreshes from ITS OWN harness (the curated two-harness
    contract). A harness with no discoverable transcript skips its specimens
    and the committed files stay — the set is never flattened onto one
    payload (that defect shipped once: three renders of the same mock)."""
    _OUT.mkdir(parents=True, exist_ok=True)
    payload_of: dict[str, tuple[dict[str, Any], str] | None] = {}
    for source in {src for _f, _g, _v, src in _SPECIMENS}:
        payload_of[source] = (MOCK_RECEIPT_PAYLOAD, "mock") if mock else _harness_payload(source)
        if payload_of[source] is None:
            print(f"  no usable {source} transcript found — skipping its specimens", file=sys.stderr)
    if mock:
        print("refresh-examples: MOCK payload — dev render only, do NOT commit", file=sys.stderr)

    written: list[Path] = []
    with patch("hyperweave.compose.context.datetime", _FrozenDatetime):
        for filename, genome, variant, source in _SPECIMENS:
            resolved = payload_of.get(source)
            if resolved is None:
                print(f"  skipped {filename} ({source} transcript unavailable)")
                continue
            payload, provenance = resolved
            svg = compose(ComposeSpec(type="receipt", genome_id=genome, variant=variant, telemetry_data=payload)).svg
            dest = _OUT / filename
            rel = dest.relative_to(_ROOT)
            # Skip the write when only the font blob would churn — the specimen's
            # real content is unchanged, so leave the committed file untouched.
            if dest.exists() and _structural(dest.read_text()) == _structural(svg):
                print(f"  unchanged {rel} ({provenance})")
                continue
            dest.write_text(svg)
            written.append(dest)
            print(f"  wrote {rel} ({len(svg):,} bytes, {provenance})")
    if not written:
        print("  all specimens already current (content unchanged)")
    return written


# The README's one-transform story, verbatim: compose the parent preset, then
# grow it through the artifact itself. Minting BOTH in one pass is the point —
# the shipped child once went stale against a re-rendered parent (its lineage
# parent_id no longer resolved), so parent and child now leave this function
# together or not at all.
_SERVICE_PATCH: list[dict[str, Any]] = [
    {
        "op": "add",
        "path": "/nodes/-",
        "value": {"id": "billing", "label": "Billing", "desc": "invoices", "glyph": "stripe"},
    },
    {"op": "add", "path": "/edges/-", "value": {"source": "gateway", "target": "billing", "relation": "assert"}},
    {
        "op": "add",
        "path": "/edges/-",
        "value": {
            "source": "billing",
            "target": "postgres",
            "label": "writes",
            "label_style": "chip",
            "relation": "assert",
            "exit": "bottom",
            "entry": "right",
        },
    },
]


# ...and then turn the same graph on its side. One field, one op: `orientation`
# is an ordinary spec field, so rotation needs no verb of its own — it is a
# structure-preserving edit, which is why the child keeps the parent's pinned
# rank order and the reader's map survives the turn.
_ROTATE_PATCH: list[dict[str, Any]] = [{"op": "add", "path": "/orientation", "value": "vertical"}]


# Preset-named README diagram assets minted by plain compose, with the
# README's own documented flags: (preset, file stem, variant).
# A fourth field names spec keys to DROP before minting. The verb-algebra
# figure sits under its own README heading, so the artifact's own title and
# subtitle would print the same words twice, 48px above a section that just
# said them.
_DIAGRAM_SINGLES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("dag-providers", "frontier-serving", "noir", ()),
    ("pipeline-row", "mcp-gateway", "space", ()),
    ("hub-zones", "verb-algebra-hub", "porcelain", ("title", "subtitle")),
    # tree-health had no entry here, so the README's dependency-audit pair was
    # the one committed asset with no generator behind it — and it drifted: the
    # shipped file was 532x722 PORTRAIT while the engine now solves the same
    # preset at 1023x722 landscape. A README asset that nothing re-mints is a
    # hand-maintained copy pretending to be output.
    ("tree-health", "tree-health", "porcelain", ()),
)

# Each asset ships as a light/dark PAIR (``<stem>-light.svg`` /
# ``<stem>-dark.svg``) that the README embeds through <picture>, rather than
# as one inlay carrying an internal @media query. GitHub serves README images
# through Camo as a plain <img>, and a prefers-color-scheme query INSIDE an
# SVG loaded that way follows the reader's OS, not the GitHub theme toggle —
# so the builtin-adaptive artifact showed a light diagram to a dark-themed
# reader on a light-mode machine. <picture> resolves against the same signal
# GitHub's own theme uses. The artifacts stay bare (transparent): the dark
# file is only ever served to a dark surface, so it has nothing to paint over.
_FACES: tuple[str, ...] = ("light", "dark")


def _face(preset_spec: dict[str, Any], variant: str, face: str) -> str:
    """One BAKED face of a diagram — palette committed, ground still bare."""
    return compose(
        ComposeSpec(
            type="diagram",
            genome_id="primer",
            variant=variant,
            ground="bare",
            palette="fixed",
            surface_face=face,
            diagram=preset_spec,
        )
    ).svg


def refresh_diagrams() -> list[Path]:
    """Re-mint the README's preset-named diagram assets: the transform chain
    (parent via compose with the README's own flags, then two real ``transform``
    calls: grow the graph, then turn it) plus the compose-only singles, pinned
    clock for idempotence. Every asset is minted once per face, and each link
    is derived from the artifact of ITS OWN FACE, so every lineage entry chains
    to something that actually exists."""
    _DIAGRAMS_OUT.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    with patch("hyperweave.compose.context.datetime", _FrozenDatetime):
        minted: list[tuple[str, str]] = []
        mesh = resolve_diagram_preset("dag-mesh")
        for face in _FACES:
            parent = _face(mesh, "porcelain", face)
            child = transform(parent, _SERVICE_PATCH, ts=_PINNED_CLOCK.isoformat())
            if child.lineage[-1]["parent_id"] != child.parent_id:
                raise RuntimeError(f"transform lineage does not chain to the {face} parent just minted")
            turned = transform(child.svg, _ROTATE_PATCH, ts=_PINNED_CLOCK.isoformat())
            if turned.lineage[-1]["parent_id"] != turned.parent_id or turned.parent_id != child.new_id:
                raise RuntimeError(f"rotate lineage does not chain to the {face} child just minted")
            # The third figure ships in NOIR, on purpose: the README's third step
            # changes two independent things, and a reader should be able to see
            # both. The turn came from the patch above, through the artifact; the
            # dress comes from re-rendering that same spec under another variant,
            # which is the whole claim that structure and look are separate
            # pointers. Same spec, same lineage, different look.
            turned_spec = extract_embedded(turned.svg).payload["spec"]
            minted += [
                (f"service-dependencies-{face}.svg", parent),
                (f"service-dependencies-billing-{face}.svg", child.svg),
                (f"service-dependencies-vertical-{face}.svg", _face(turned_spec, "noir", face)),
            ]
        for preset, stem, variant, drop in _DIAGRAM_SINGLES:
            spec = {k: v for k, v in resolve_diagram_preset(preset).items() if k not in drop}
            minted += [(f"{stem}-{face}.svg", _face(spec, variant, face)) for face in _FACES]
        for filename, svg in minted:
            dest = _DIAGRAMS_OUT / filename
            rel = dest.relative_to(_ROOT)
            if dest.exists() and _structural(dest.read_text()) == _structural(svg):
                print(f"  unchanged {rel}")
                continue
            dest.write_text(svg)
            written.append(dest)
            print(f"  wrote {rel} ({len(svg):,} bytes)")
    return written


# The committed matrix assets the README embeds, and the recipe that mints each:
# (spec file stem, output stem, variant, surface axes). A `faces` entry ships a
# light/dark PAIR through <picture>; a single face ships one adaptive inlay.
#
# Every spec here was recovered from its own artifact's `hw:payload` — these
# tables had no source in the repo at all, only a rendered SVG and, for one of
# them, a JSON file in gitignored `outputs/`. That is the same defect
# refresh_diagrams() was written to fix: an asset nothing re-mints is a
# hand-maintained copy pretending to be output, and it drifts silently.
# Each variant below is READ OFF the committed artifact's own <hw:variant>, not
# chosen here: the benchmark pair ships on `cream`, and a recipe that guessed
# `porcelain` would have quietly repalettied a README image on the next refresh.
_MATRIX_SPECIMENS: tuple[tuple[str, str, str, str, str, tuple[str, ...]], ...] = (
    # (spec stem, output stem, variant, ground, palette, faces)
    ("frontier-benchmarks", "frontier-benchmarks", "cream", "opaque", "fixed", ("light", "dark")),
    ("format-comparison-inlay", "hw-format-comparison-matrix-inlay", "porcelain", "bare", "adaptive", ()),
    ("data-connectors-inlay", "hw-data-connectors-matrix-inlay", "porcelain", "bare", "adaptive", ()),
)


def refresh_matrices() -> list[Path]:
    """Re-mint the README's committed matrix assets from their specs.

    Same discipline as the receipts and diagrams: pinned clock, structural
    comparison so a run that changes nothing rewrites nothing, and a loud
    failure rather than a silent skip if a spec goes missing.

    `assets/examples/matrices/format-comparison.svg` is deliberately absent
    from the recipe — it carries no `hw:payload`, so there is nothing to
    re-mint it from. It needs a spec authored before it can join.
    """
    _MATRICES_OUT.mkdir(parents=True, exist_ok=True)
    specs_dir = _MATRICES_OUT / "specs"
    written: list[Path] = []
    with patch("hyperweave.compose.context.datetime", _FrozenDatetime):
        for spec_stem, out_stem, variant, ground, palette, faces in _MATRIX_SPECIMENS:
            spec_path = specs_dir / f"{spec_stem}.json"
            if not spec_path.exists():
                raise FileNotFoundError(f"matrix spec {spec_path} is missing — the asset cannot be re-minted")
            payload = json.loads(spec_path.read_text())
            for face in faces or ("",):
                svg = compose(
                    ComposeSpec(
                        type="matrix",
                        genome_id="primer",
                        variant=variant,
                        matrix=payload,
                        ground=ground,
                        palette=palette,
                        surface_face=face,
                    )
                ).svg
                dest = _MATRICES_OUT / (f"{out_stem}-{face}.svg" if face else f"{out_stem}.svg")
                rel = dest.relative_to(_ROOT)
                if dest.exists() and _structural(dest.read_text()) == _structural(svg):
                    print(f"  unchanged {rel}")
                    continue
                dest.write_text(svg)
                written.append(dest)
                print(f"  wrote {rel} ({len(svg):,} bytes)")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-render the committed example artifacts from their specs.")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Dev-only: render the shared MOCK payload instead of per-harness transcripts (do not commit).",
    )
    args = parser.parse_args()
    refresh(mock=args.mock)
    refresh_diagrams()
    refresh_matrices()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
