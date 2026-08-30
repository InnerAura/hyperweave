"""The transactional compose answer — ``respond=report``, schema ``report/1``.

One bounded document instead of three commands: what composed, where it
lives, what the compiler advised, whether the bytes are intact, and what to
do next — never the SVG itself. The same builder serves CLI, HTTP, and MCP so
the shape cannot drift between surfaces.

Identity fields (``spec_id`` · ``render_id`` · ``artifact_hash``) are
RESERVED and deliberately omitted until the identity model mints them —
today's envelope id never ships under those names; the schema version exists
so they can be added later under parse-old / emit-new.

Named ``report``, not ``receipt``: the receipt is this product's telemetry
frame (``hw compose receipt session.jsonl``), and one word must not carry
both meanings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

REPORT_SCHEMA = "report/1"


def build_report(
    *,
    svg: str,
    url: str,
    envelope: Mapping[str, Any],
    width: int,
    height: int,
    genome: str,
    variant: str,
    diagnostics: Sequence[Mapping[str, Any]] = (),
    warnings: Sequence[str] = (),
    proof: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the ``report/1`` document from a composed surface response.

    ``ok`` is the integrity verdict (payload hash + container well-formedness)
    — never a claim about visual quality; that is the proof's job, and the
    proof rides in whole under ``proof`` when the caller asked for one
    (``null`` is the honest value everywhere else — a missing capability is
    reported, not faked).
    """
    from hyperweave.verbs.verify import verify

    v = verify(svg)
    artifact: dict[str, Any] = {
        "envelope_id": str(envelope.get("id", "")),
        "url": url,
        "width": width,
        "height": height,
        "genome": genome,
        "variant": variant,
    }
    if envelope.get("pattern"):
        artifact["pattern"] = envelope["pattern"]
    return {
        "schema": REPORT_SCHEMA,
        "ok": bool(v.hash_valid and v.well_formed),
        "artifact": artifact,
        "integrity": {"hash_valid": v.hash_valid, "well_formed": v.well_formed},
        "diagnostics": [dict(d) for d in diagnostics],
        "warnings": list(warnings),
        "proof": dict(proof) if proof is not None else None,
        "next": [
            "hw verify <url-or-file>",
            "hw transform <url-or-file> --patch-json '[...]' --intent '<why>'",
            "hw diff <a> <b>",
        ],
    }
