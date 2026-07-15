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
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
# src/ for the package; the scripts dir itself so ``generate_proofset`` (not a
# package — there is no scripts/__init__.py) imports as a top-level module.
sys.path.insert(0, str(_ROOT / "src"))
sys.path.insert(0, str(_ROOT / "scripts"))

# The receipt data contract + real-transcript discovery live in the proofset
# generator; import them so the two surfaces can never drift on the shape of a
# receipt payload or on how a "real" transcript is chosen.
from generate_proofset import (  # noqa: E402
    MOCK_RECEIPT_PAYLOAD,
    _load_real_telemetry,
    _real_codex_transcripts,
    _real_transcripts,
)

from hyperweave.compose.engine import compose  # noqa: E402
from hyperweave.core.models import ComposeSpec  # noqa: E402

_OUT = _ROOT / "assets" / "examples" / "telemetry"

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


# Embedded woff2 base64 payloads carry a subsetter creation timestamp (and
# fontTools compression is not bit-stable), so two renders of identical content
# differ only inside the font blob. Strip it before comparing so the recipe
# rewrites a specimen ONLY when its real content changed — keeping git status a
# signal, not font-churn noise. (Same discipline the proofset uses when diffing.)
_FONT_BLOB = re.compile(r"data:[^;]*;base64,[A-Za-z0-9+/=]+")


def _structural(svg: str) -> str:
    return _FONT_BLOB.sub("FONT", svg)


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Re-render the committed telemetry example receipts.")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Dev-only: render the shared MOCK payload instead of per-harness transcripts (do not commit).",
    )
    args = parser.parse_args()
    refresh(mock=args.mock)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
