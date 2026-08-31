"""The proof projection — the inspection record beside a composed artifact.

The law this module enforces: **the inspected artifact is the delivered
artifact.** A proof derives every field from the exact composed bytes it is
handed — it re-solves nothing and alters no spec field to make projection
possible. Where a projection cannot represent something (an adaptive face, a
motion channel with no sampling path, a missing ``[raster]`` extra) the record
says so in a field and the surface reports "not inspected", never "inspected".
The recorded failure this pins: an agent flipped ``motion_register`` to make
inspection possible and graded a 1507x280 delivery against a 2059x380
substitute.

The record is ``proof/1`` (schema-versioned per the roadmap's parse-old /
emit-new policy; the transactional receipt embeds it later). Verdicts stay
separate — schema · composition · layout · projection well-formedness ·
integrity — never collapsed into one word. gzip size is a property of the RUN,
not the artifact, until the determinism work lands; the record says so beside
the number.
"""

from __future__ import annotations

import gzip
import re
from typing import TYPE_CHECKING, Any

from hyperweave.core.errors import HwError
from hyperweave.formats import FormatId, project, raster_available
from hyperweave.formats.ansi import read_region_sidecar

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

PROOF_SCHEMA = "proof/1"

_VIEWBOX = re.compile(r'<svg\b[^>]*\bviewBox="([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)"')
_FONT_MODE = re.compile(r'data-hw-fonts="([^"]+)"')
_FONT_DATA = re.compile(r"url\(data:font/[a-z0-9+-]+;base64,([A-Za-z0-9+/=]+)\)")
# Loadable external references — the self-containment law says there are none.
# xmlns declarations are names, not fetches, and never match these shapes.
_EXTERNAL = re.compile(r"""(?:href|xlink:href)\s*=\s*["'](https?://[^"']+)|url\(\s*["']?(https?://[^"')]+)|@import""")
_ANIMATES = re.compile(r"@keyframes|<animate")


def _external_references(svg: str) -> list[str]:
    out: list[str] = []
    for m in _EXTERNAL.finditer(svg):
        out.append(m.group(1) or m.group(2) or "@import")
    return out


def build_proof(
    svg: str, *, diagnostics: Sequence[Mapping[str, Any]] = (), warnings: Sequence[str] = ()
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Build the ``proof/1`` record plus its sidecar file bytes.

    Pure over the delivered bytes: the caller supplies the composed SVG and the
    compose run's diagnostics/warnings verbatim; nothing here re-solves. Returns
    ``(record, files)`` where ``files`` maps a filename suffix (``static.svg``,
    ``png``) to bytes — the surface owns paths and writing, the record's
    ``file`` fields are filled by whoever writes.
    """
    files: dict[str, bytes] = {}
    record: dict[str, Any] = {"schema": PROOF_SCHEMA}

    # ── Measured geometry — read from the delivered bytes, never re-solved ──
    vb = _VIEWBOX.search(svg)
    geometry: dict[str, Any] = {}
    if vb:
        w, h = float(vb.group(3)), float(vb.group(4))
        geometry = {
            "viewBox": f"{vb.group(1)} {vb.group(2)} {vb.group(3)} {vb.group(4)}",
            "width": w,
            "height": h,
            "aspect": round(w / h, 2) if h else None,
        }
    geometry["regions"] = read_region_sidecar(svg)
    record["geometry"] = geometry

    # ── Integrity (payload hash + container well-formedness, independent) ──
    from hyperweave.verbs.verify import verify

    v = verify(svg)
    record["artifact"] = {"envelope_id": v.expected_id, "payload_schema": v.schema}
    integrity = (
        "pass" if (v.hash_valid and v.well_formed) else f"fail — hash_valid={v.hash_valid} well_formed={v.well_formed}"
    )

    # ── Resting frame — the static projection of THESE bytes, or the honest
    # reason there isn't one. An adaptive artifact bakes its LIGHT face (the
    # universal base every renderer without scheme support serves), and the
    # record names the face inspected — the proof path must never be weaker
    # than the export path it certifies. ──
    projection_verdict = "pass"
    static: str | None = None
    adaptive = 'data-hw-adapt="adaptive"' in svg
    face = "light" if adaptive else ""
    try:
        proj = project(svg, FormatId.SVG_STATIC, face=face)
        static = proj.data.decode("utf-8")
        files["static.svg"] = proj.data
        record["resting_frame"] = {"available": True, "diagnostics": dict(proj.diagnostics)}
        if adaptive:
            record["resting_frame"]["face"] = (
                "light — the adaptive artifact's base face; the dark branch is not pictured"
            )
    except HwError as exc:
        record["resting_frame"] = {"available": False, "reason": exc.message, "fix": exc.fix}
        projection_verdict = "not inspected — " + exc.message

    # ── Raster — a missing extra is a first-class outcome, not a fallback. ──
    if static is None:
        record["raster"] = {"available": False, "reason": "no resting frame to rasterize"}
    elif raster_available():
        try:
            record["raster"] = {"available": True, "format": "png"}
            files["png"] = project(svg, FormatId.PNG, face=face).data
        except HwError as exc:
            record["raster"] = {"available": False, "reason": exc.message, "fix": exc.fix}
    else:
        record["raster"] = {
            "available": False,
            "reason": "the [raster] extra is not installed",
            "fix": "install hyperweave[raster]",
        }

    # ── Motion — sampled at the phi beats where the artifact's own inline
    # choreography channels allow it; drop, never fake, everywhere else. An
    # adaptive artifact (no resting frame) is never flattened for sampling. ──
    if static is not None:
        from xml.etree import ElementTree as ET

        from hyperweave.formats.sampling import sample_choreography

        try:
            sampled = sample_choreography(svg)
        except (HwError, ET.ParseError) as exc:
            sampled = None
            record["motion"] = {"sampled": False, "reason": f"sampling failed: {exc}"}
        if sampled is not None:
            motion_record, frames = sampled
            record["motion"] = motion_record
            files.update(frames)
    if "motion" not in record:
        if static is None:
            record["motion"] = {"sampled": False, "reason": "no static projection to sample from"}
        elif _ANIMATES.search(svg):
            record["motion"] = {
                "sampled": False,
                "reason": (
                    "no time-sampling path for this artifact's motion channels; "
                    "the resting frame is the reviewable state"
                ),
            }
        else:
            record["motion"] = {"sampled": False, "reason": "artifact is static"}

    # ── Diagnostics and warnings, verbatim ──
    record["diagnostics"] = [dict(d) for d in diagnostics]
    record["warnings"] = list(warnings)

    # ── Resource inventory ──
    fm = _FONT_MODE.search(svg)
    font_mode = fm.group(1) if fm else ""
    font_bytes = sum(len(m.group(1)) * 3 // 4 - m.group(1).count("=") for m in _FONT_DATA.finditer(svg))
    externals = _external_references(svg)
    record["resources"] = {
        "font_mode": font_mode,
        "font_bytes": font_bytes,
        "external_references": externals,
        "artifact_bytes": len(svg.encode("utf-8")),
        "gzip_bytes": len(gzip.compress(svg.encode("utf-8"))),
        "gzip_note": "a property of this run, not the artifact — byte identity across runs is not yet guaranteed",
    }

    # Self-containment follows the artifact's OWN declared delivery: embed and
    # system promise zero external references, while cdn declares its font
    # fetch up front — the expected font import reports as the disclosed
    # tradeoff it is, and anything beyond it still fails.
    if font_mode == "cdn":
        undeclared = [e for e in externals if e != "@import" and "fonts.googleapis" not in e]
        self_contained = (
            "declared — cdn fonts (needs network at view time)"
            if not undeclared
            else f"fail — {len(undeclared)} external references beyond the declared cdn fonts"
        )
    else:
        self_contained = "pass" if not externals else f"fail — {len(externals)} external references"

    # ── Verdicts, separate and never collapsed ──
    record["verdicts"] = {
        "schema": "pass — the spec validated at compose",
        "composition": "pass — the artifact composed",
        "layout": f"{len(diagnostics)} advisories" if diagnostics else "clean",
        "projection_well_formed": projection_verdict,
        "integrity": integrity,
        "self_contained": self_contained,
    }
    return record, files
