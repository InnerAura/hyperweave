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
      "bold_expansion_factor": 1.0,
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

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parents[2]
FONTS_DIR = ROOT / "src" / "hyperweave" / "data" / "fonts"
METRICS_DIR = ROOT / "src" / "hyperweave" / "data" / "font-metrics"

# ASCII printable characters we shipped in inter.json (space through ~).
SUPPORTED_ASCII = [chr(c) for c in range(0x20, 0x7F)]


def load_font_from_b64(path: Path) -> TTFont:
    """Decode a base64-encoded WOFF2 payload and return a TTFont."""
    raw_b64 = path.read_text()
    return TTFont(BytesIO(base64.b64decode(raw_b64)))


def extract_widths_and_bearings(
    font: TTFont, baseline_size_px: int
) -> tuple[dict[str, int], dict[str, list[int]], dict[str, list[int]]]:
    """Return per-char (advance_widths, ink_bearings, vertical_bounds).

    Advance widths follow the original schema — tenths-of-pixels at
    ``baseline_size_px``. Ink bearings are returned as
    ``{char: [lsb_tenths, rsb_tenths]}`` where:

    * ``lsb`` is the distance from the glyph's origin to the leftmost
      visible ink (left side bearing in the OpenType sense)
    * ``rsb`` is the distance from the rightmost visible ink to the
      advance width (right side bearing)

    These let the text-measurement layer compute *visible-ink width* as
    ``advance - first_char.lsb - last_char.rsb`` — the corrected width
    that places downstream cursor work (badge seam placement, stat card
    bio_x derivation) at the actual visible end of text, not at the
    advance position which includes invisible trailing side-bearing.

    Whitespace glyphs (no ink) return ``[0, advance]`` so subtracting
    them produces zero visible width — correct behavior for an
    all-whitespace string.
    """
    cmap = font.getBestCmap()
    hmtx = font["hmtx"]
    glyph_set = font.getGlyphSet()
    units_per_em = font["head"].unitsPerEm
    scale = baseline_size_px / units_per_em
    widths: dict[str, int] = {}
    bearings: dict[str, list[int]] = {}
    vertical_bounds: dict[str, list[int]] = {}
    for ch in SUPPORTED_ASCII:
        codepoint = ord(ch)
        if codepoint not in cmap:
            continue
        glyph_name = cmap[codepoint]
        advance_design_units, _lsb_design = hmtx[glyph_name]
        widths[ch] = round(advance_design_units * scale * 10)

        # Compute visible-ink bounds via BoundsPen. Whitespace glyphs draw
        # nothing; pen.bounds is None — treat as "no visible ink" so the
        # entire advance is left+right bearing (rsb consumes the advance).
        pen = BoundsPen(glyph_set)
        try:
            glyph_set[glyph_name].draw(pen)
        except Exception:
            # Defensive: a malformed glyph shouldn't crash the extraction.
            bearings[ch] = [0, widths[ch]]
            vertical_bounds[ch] = [0, 0]
            continue
        if pen.bounds is None:
            bearings[ch] = [0, widths[ch]]
            vertical_bounds[ch] = [0, 0]
            continue
        xmin, _ymin, xmax, _ymax = pen.bounds
        lsb_px_at_baseline = xmin * scale  # ink-left from glyph origin
        rsb_px_at_baseline = (advance_design_units - xmax) * scale  # advance - ink-right
        bearings[ch] = [round(lsb_px_at_baseline * 10), round(rsb_px_at_baseline * 10)]
        vertical_bounds[ch] = [round(_ymin * scale * 10), round(_ymax * scale * 10)]
    return widths, bearings, vertical_bounds


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
    bearings: dict[str, list[int]] | None = None,
    vertical_bounds: dict[str, list[int]] | None = None,
    widths_by_weight: dict[str, dict[str, int]] | None = None,
    bearings_by_weight: dict[str, dict[str, list[int]]] | None = None,
    vertical_bounds_by_weight: dict[str, dict[str, list[int]]] | None = None,
) -> dict[str, object]:
    """Build the JSON dict matching inter.json schema (plus registry fields).

    ``bearings`` is a v0.3.9 addition for per-glyph ink-width measurement
    (used by ``measure_text_ink_width`` in core/text.py). Optional —
    loaders that predate the field fall back to advance-width behavior.
    """
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
    if bearings:
        result["bearings"] = bearings
    if vertical_bounds:
        result["vertical_bounds"] = vertical_bounds
    if widths_by_weight:
        result["widths_by_weight"] = widths_by_weight
    if bearings_by_weight:
        result["bearings_by_weight"] = bearings_by_weight
    if vertical_bounds_by_weight:
        result["vertical_bounds_by_weight"] = vertical_bounds_by_weight
    return result


# Known font configs. Add entries here to extend.
FONT_CONFIGS: dict[str, dict[str, object]] = {
    "inter": {
        "family": "Inter",
        "baseline_size_px": 11,
        "bold_expansion_factor": 1.0,
        "aliases": ["inter", "system-ui", "sans-serif", "-apple-system", "blinkmacsystemfont", "segoe ui"],
        "is_monospace": False,
        "char_width_px": 0.0,
        "metric_weights": [400, 700, 800, 900],
    },
    "orbitron": {
        "family": "Orbitron",
        "baseline_size_px": 20,
        "bold_expansion_factor": 1.0,
        "aliases": ["orbitron"],
        "is_monospace": False,
        "char_width_px": 0.0,
        "metric_weights": [400, 700, 800, 900],
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
        "bold_expansion_factor": 1.0,
        "aliases": ["chakra petch", "chakra-petch"],
        "is_monospace": False,
        "char_width_px": 0.0,
        "metric_weights": [400, 700, 900],
        "metric_weight_sources": {
            "400": "chakra-petch",
            "700": "chakra-petch",
            "900": "chakra-petch",
        },
    },
    "barlow-condensed-900": {
        "family": "Barlow Condensed",
        "baseline_size_px": 18,  # dominant rendered size in brutalist strip value text
        "bold_expansion_factor": 1.0,  # 900 is the heaviest weight shipped; no further expansion
        "aliases": ["barlow condensed", "barlow-condensed", "barlow condensed 900"],
        "is_monospace": False,
        "char_width_px": 0.0,
        "metric_weights": [400, 700, 900],
        "metric_weight_sources": {
            "400": "barlow-condensed-700",
            "700": "barlow-condensed-700",
            "900": "barlow-condensed-900",
        },
    },
}


def load_metric_font_for_weight(slug: str, base_font: TTFont, config: dict[str, object], weight_int: int) -> TTFont:
    """Return the font face used to extract metrics for ``weight_int``.

    Variable fonts are instantiated by axis value. Static families can declare
    ``metric_weight_sources`` to map weights to bundled font slugs.
    """
    weight_sources = config.get("metric_weight_sources")
    if isinstance(weight_sources, dict):
        source_slug = str(weight_sources.get(str(weight_int), slug))
        source_path = FONTS_DIR / f"{source_slug}.b64"
        if not source_path.exists():
            raise FileNotFoundError(f"Missing font source for weight {weight_int}: {source_path}")
        return load_font_from_b64(source_path)
    if "fvar" in base_font:
        return instantiateVariableFont(base_font, {"wght": weight_int}, inplace=False)
    return base_font


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
    widths, bearings, vertical_bounds = extract_widths_and_bearings(font, baseline)
    widths_by_weight: dict[str, dict[str, int]] = {}
    bearings_by_weight: dict[str, dict[str, list[int]]] = {}
    vertical_bounds_by_weight: dict[str, dict[str, list[int]]] = {}
    metric_weights = config.get("metric_weights")
    if isinstance(metric_weights, list):
        for weight in metric_weights:
            weight_int = int(weight)
            weight_font = load_metric_font_for_weight(slug, font, config, weight_int)
            weight_widths, weight_bearings, weight_vertical_bounds = extract_widths_and_bearings(weight_font, baseline)
            key = str(weight_int)
            widths_by_weight[key] = weight_widths
            bearings_by_weight[key] = weight_bearings
            vertical_bounds_by_weight[key] = weight_vertical_bounds

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
        bearings=bearings,
        vertical_bounds=vertical_bounds,
        widths_by_weight=widths_by_weight,
        bearings_by_weight=bearings_by_weight,
        vertical_bounds_by_weight=vertical_bounds_by_weight,
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
