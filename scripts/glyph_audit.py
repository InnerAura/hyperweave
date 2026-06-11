"""Glyph registry geometry audit — every path must live inside its viewBox.

Run after any registry rebuild (requires Playwright Chromium, e.g. via the
pyenv interpreter). Renders every entry's mono path and every color_paths
master in a browser, measures the true bounding box with getBBox(), and
fails when a drawing escapes its declared viewBox or fills almost none of
it. This is the check a non-blank raster audit cannot do: a mark drawn at
2x scale still has pixels — it is just the wrong glyph everywhere it ships
(the v0.4.0-alpha.2 vscode/slack corruption shipped exactly that way).
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "src" / "hyperweave" / "data" / "glyphs.json"

ESCAPE_TOLERANCE = 0.02  # fraction of the viewBox's long side
MIN_COVERAGE = 0.4  # a mark filling under 40% of its box is suspicious
MAX_COVERAGE = 1.05


def main() -> int:
    from playwright.sync_api import sync_playwright

    glyphs = json.loads(REGISTRY.read_text())
    # (label, [d, ...], viewBox) — masters keep one element per subpath,
    # exactly as the renderer emits them. Joining them into one path would
    # change semantics: a leading relative moveto with implicit linetos
    # (`m6.6 66.85 3.85 6.65c…`) cannot be safely uppercased.
    subjects: list[tuple[str, list[str], str]] = []
    for key, entry in glyphs.items():
        subjects.append((key, [entry["path"]], str(entry["viewBox"])))
        master = entry.get("color_paths")
        if isinstance(master, dict):
            subjects.append((f"{key}:color", [p["d"] for p in master["paths"]], str(master["viewBox"])))

    html = (
        "<svg xmlns='http://www.w3.org/2000/svg'>"
        + "".join(
            f"<g id='g-{i}'>" + "".join(f'<path d="{d}"/>' for d in ds) + "</g>"
            for i, (_, ds, _) in enumerate(subjects)
        )
        + "</svg>"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
        fh.write(html)
        page_path = fh.name

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.goto(f"file://{page_path}")
        boxes = page.evaluate(
            "() => Array.from(document.querySelectorAll('g'),"
            " el => { const b = el.getBBox(); return [b.x, b.y, b.width, b.height]; })"
        )
        browser.close()

    failures: list[str] = []
    for (label, _, viewbox), (bx, by, bw, bh) in zip(subjects, boxes, strict=True):
        vx, vy, vw, vh = (float(v) for v in viewbox.split())
        long_side = max(vw, vh)
        escape = (
            max(0.0, vx - bx) + max(0.0, vy - by) + max(0.0, (bx + bw) - (vx + vw)) + max(0.0, (by + bh) - (vy + vh))
        )
        coverage = max(bw / vw, bh / vh) if vw and vh else 0.0
        if escape > ESCAPE_TOLERANCE * long_side or not (MIN_COVERAGE <= coverage <= MAX_COVERAGE):
            failures.append(
                f"  {label}: viewBox={viewbox!r} bbox=({bx:.1f},{by:.1f},{bw:.1f},{bh:.1f}) coverage={coverage:.2f}"
            )

    if failures:
        print(f"{len(failures)} glyph geometry violation(s):")
        print("\n".join(failures))
        return 1
    print(f"{len(subjects)} drawings audited (mono + color masters) — all contained in their viewBoxes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
