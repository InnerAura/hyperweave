#!/usr/bin/env python3
"""Extract per-codepoint advance widths from bundled WOFF2 fonts.

HyperWeave bundles fonts as base64-encoded WOFF2 in
``src/hyperweave/data/fonts/*.b64`` (so the whole font registry ships
as plain-text files, diffable in git). This script decodes each font,
reads its ``hmtx`` table via ``fontTools``, and emits a JSON file at
``src/hyperweave/data/font-metrics/{slug}.json`` matching the existing
``inter.json`` schema:

    {
      "font_family": "Orbitron",
      "baseline_size_px": 20,
      "units": "tenths_of_pixels",
      "bold_expansion_factor": 1.06,
      "fallback_width": 110,
      "widths": { " ": 78, "A": 145, ... }
    }

The baseline size is chosen close to the font's dominant rendered size
in HyperWeave (20px for Orbitron in stats hero values, 11px for
Inter in badge labels). Widths are stored in tenths-of-pixels at the
baseline size, so a glyph of 145 tenths at baseline 20px renders as
14.5px wide at 20px and ~7.25px wide at 10px (linear scaling).

Usage:
    uv run python scripts/extract_font_metrics.py orbitron --baseline 20
    uv run python scripts/extract_font_metrics.py jetbrains-mono --baseline 11
    uv run python scripts/extract_font_metrics.py --all
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONTS_DIR = ROOT / "src" / "hyperweave" / "data" / "fonts"
METRICS_DIR = ROOT / "src" / "hyperweave" / "data" / "font-metrics"

# ASCII printable characters we shipped in inter.json (space through ~).
SUPPORTED_ASCII = [chr(c) for c in range(0x20, 0x7F)]


def load_font_from_b64(path: Path) -> TTFont:
    """Decode a base64-encoded WOFF2 payload and return a TTFont."""
    raw_b64 = path.read_text()
    return TTFont(BytesIO(base64.b64decode(raw_b64)))


def extract_widths(font: TTFont, baseline_size_px: int) -> dict[str, int]:
    """Return char -> width-in-tenths-of-pixels-at-baseline dict.

    Uses the font's ``cmap`` to map each supported ASCII codepoint to a
    glyph name, then reads the glyph's ``hmtx`` advance width in
    font-design units. Units are converted to pixels at
    ``baseline_size_px`` via ``units_per_em``, then scaled by 10 to
    match the ``tenths_of_pixels`` convention in ``inter.json``.
    """
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    units_per_em = font["head"].unitsPerEm
    widths: dict[str, int] = {}
    for ch in SUPPORTED_ASCII:
        codepoint = ord(ch)
        if codepoint not in cmap:
            continue
        glyph_name = cmap[codepoint]
        advance_design_units, _lsb = hmtx[glyph_name]
        advance_px_at_baseline = advance_design_units * baseline_size_px / units_per_em
        widths[ch] = round(advance_px_at_baseline * 10)
    return widths


def compute_fallback_width(widths: dict[str, int]) -> int:
    """Median-ish fallback width for codepoints outside the supported set."""
    if not widths:
        return 60
    sorted_widths = sorted(widths.values())
    return sorted_widths[len(sorted_widths) // 2]


def emit_metrics_json(
    family: str,
    baseline_size_px: int,
    widths: dict[str, int],
    bold_expansion_factor: float,
    aliases: list[str],
    is_monospace: bool = False,
    char_width_px: float = 0.0,
) -> dict[str, object]:
    """Build the JSON dict matching inter.json schema (plus registry fields)."""
    result: dict[str, object] = {
        "font_family": family,
        "baseline_size_px": baseline_size_px,
        "units": "tenths_of_pixels",
        "bold_expansion_factor": bold_expansion_factor,
        "fallback_width": compute_fallback_width(widths),
        "aliases": aliases,
        "is_monospace": is_monospace,
        "char_width_px": char_width_px,
        "widths": widths,
    }
    return result


# Known font configs. Add entries here to extend.
FONT_CONFIGS: dict[str, dict[str, object]] = {
    "orbitron": {
        "family": "Orbitron",
        "baseline_size_px": 20,
        "bold_expansion_factor": 1.06,
        "aliases": ["orbitron"],
        "is_monospace": False,
        "char_width_px": 0.0,
    },
    "jetbrains-mono": {
        "family": "JetBrains Mono",
        "baseline_size_px": 11,
        "bold_expansion_factor": 1.0,  # true monospace — no bold width change
        "aliases": ["jetbrains mono", "jetbrains-mono", "sf mono", "menlo", "monospace"],
        "is_monospace": True,
        # char_width_px populated below from extracted widths (median).
        "char_width_px": 0.0,
    },
    "chakra-petch": {
        "family": "Chakra Petch",
        "baseline_size_px": 12,  # dominant rendered size in automata badge value text
        "bold_expansion_factor": 1.04,
        "aliases": ["chakra petch", "chakra-petch"],
        "is_monospace": False,
        "char_width_px": 0.0,
    },
}


def extract_one(slug: str) -> Path:
    """Extract one font to ``data/font-metrics/{slug}.json``."""
    if slug not in FONT_CONFIGS:
        raise ValueError(f"Unknown font slug '{slug}'. Known: {sorted(FONT_CONFIGS)}")
    config = FONT_CONFIGS[slug]
    b64_path = FONTS_DIR / f"{slug}.b64"
    if not b64_path.exists():
        raise FileNotFoundError(f"Missing font source: {b64_path}")

    font = load_font_from_b64(b64_path)
    baseline = int(config["baseline_size_px"])
    widths = extract_widths(font, baseline)

    char_width_px = float(config["char_width_px"])
    is_mono = bool(config["is_monospace"])
    if is_mono and char_width_px == 0.0 and widths:
        # Monospace: all chars have the same advance; pick the first mapped width.
        advance_tenths = next(iter(widths.values()))
        char_width_px = advance_tenths / 10.0

    data = emit_metrics_json(
        family=str(config["family"]),
        baseline_size_px=baseline,
        widths=widths,
        bold_expansion_factor=float(config["bold_expansion_factor"]),
        aliases=list(config["aliases"]),  # type: ignore[arg-type]
        is_monospace=is_mono,
        char_width_px=char_width_px,
    )

    out_path = METRICS_DIR / f"{slug}.json"
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slugs", nargs="*", help="Font slugs to extract (e.g. orbitron jetbrains-mono).")
    parser.add_argument("--all", action="store_true", help="Extract every font in FONT_CONFIGS.")
    args = parser.parse_args()

    if args.all:
        slugs = sorted(FONT_CONFIGS.keys())
    elif args.slugs:
        slugs = args.slugs
    else:
        parser.print_help()
        return 1

    for slug in slugs:
        out = extract_one(slug)
        sys.stdout.write(f"  wrote {out.relative_to(ROOT)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
