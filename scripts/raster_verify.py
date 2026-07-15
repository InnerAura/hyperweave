"""Raster-verify HyperWeave SVGs via Chromium (Playwright).

rsvg-convert/cairosvg silently drop ``var(--dna-*)``, woff2 ``@font-face``,
and media queries — never use them for acceptance. This script screenshots
each SVG in a real Chromium at 2x, plus a reduced-motion pass and (for the
first file) a forced-colors pass, and exits non-zero on any page error.

The output directory follows the input: proofset inputs mirror their frame
directory (``outputs/proofset/primer/diagram`` -> ``outputs/raster/diagram``),
anything else lands under ``outputs/raster/<parent-dir-name>/``.

Usage:
    python scripts/raster_verify.py [glob_or_paths ...]
    # default: outputs/proofset/primer/matrix/*.svg -> outputs/raster/matrix/
    python scripts/raster_verify.py --contact-sheet
    # one PNG grid of EVERY proofset artifact -> outputs/raster/contact-sheet.png
    python scripts/raster_verify.py --scheme both outputs/proofset/primer/surface/matrix/*.svg
    # + a light AND dark emulated-color-scheme capture per artifact (the surface-
    #   modes adaptive check — inlay/twin only flip in a real browser)

Playwright is a dev-only dependency (same harness as render_demo_video.py);
run under an interpreter that has it installed.
"""

from __future__ import annotations

import asyncio
import glob as globlib
import html
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLOB = ROOT / "outputs" / "proofset" / "primer" / "matrix"
PROOFSET_ROOT = ROOT / "outputs" / "proofset"
CONTACT_SHEET = ROOT / "outputs" / "raster" / "contact-sheet.png"


def out_dir_for(paths: list[Path]) -> Path:
    """Mirror proofset frame dirs; name arbitrary dirs after their parent."""
    parent = paths[0].resolve().parent
    try:
        rel = parent.relative_to(PROOFSET_ROOT)
        # proofset/<genome>/<frame>/... -> raster/<frame>/...
        tail = rel.parts[1:] if len(rel.parts) > 1 else rel.parts
        return ROOT / "outputs" / "raster" / Path(*tail)
    except ValueError:
        return ROOT / "outputs" / "raster" / parent.name


async def raster(paths: list[Path], *, scheme: str = "") -> int:
    from playwright.async_api import async_playwright

    out_dir = out_dir_for(paths)
    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(device_scale_factor=2)
        page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
        page.on(
            "console",
            lambda msg: errors.append(f"console.{msg.type}: {msg.text}") if msg.type == "error" else None,
        )

        for i, path in enumerate(paths):
            await page.goto(path.resolve().as_uri())
            element = page.locator("svg")
            # Let one-shot entrance animations settle (the diagram frame's
            # 0.618s fade) so the normal pass captures the steady state;
            # looping motion stays live by design.
            await page.wait_for_timeout(900)
            await element.screenshot(path=str(out_dir / f"{path.stem}.png"))

            # Surface Modes: --scheme both captures each artifact under an emulated
            # light AND dark color scheme (light|dark captures just one). This is
            # the ONLY way to see an adaptive (inlay/twin) artifact flip — its
            # @media (prefers-color-scheme) block fires in a real browser, never in
            # rsvg. Suffixed _scheme-light / _scheme-dark.
            schemes = ("light", "dark") if scheme == "both" else ((scheme,) if scheme else ())
            for cs in schemes:
                await page.emulate_media(color_scheme=cs)
                await page.goto(path.resolve().as_uri())
                await page.wait_for_timeout(400)
                await page.locator("svg").screenshot(path=str(out_dir / f"{path.stem}_scheme-{cs}.png"))
            if schemes:
                await page.emulate_media(color_scheme="no-preference")

            await page.emulate_media(reduced_motion="reduce")
            await page.goto(path.resolve().as_uri())
            await page.locator("svg").screenshot(path=str(out_dir / f"{path.stem}_reduced-motion.png"))
            await page.emulate_media(reduced_motion="no-preference")

            if i == 0:
                await page.emulate_media(forced_colors="active")
                await page.goto(path.resolve().as_uri())
                await page.locator("svg").screenshot(path=str(out_dir / f"{path.stem}_forced-colors.png"))
                await page.emulate_media(forced_colors="none")

            print(f"  rastered {path.stem}")

        await browser.close()

    if errors:
        print("\nRENDER ERRORS:")
        for error in errors:
            print(f"  {error}")
        return 1
    print(f"\n{len(paths)} SVGs rastered clean -> {out_dir}")
    return 0


async def contact_sheet(paths: list[Path]) -> int:
    """One full-page screenshot of every artifact in a captioned grid,
    grouped by frame directory — the at-a-glance regression surface."""
    from playwright.async_api import async_playwright

    groups: dict[str, list[Path]] = {}
    for p in paths:
        try:
            key = str(p.resolve().parent.relative_to(PROOFSET_ROOT))
        except ValueError:
            key = p.resolve().parent.name
        groups.setdefault(key, []).append(p)

    cells: list[str] = [
        "<style>body{background:#101216;font:12px/1.4 -apple-system,sans-serif;color:#9aa3ad;margin:24px}"
        "h2{color:#e8eaed;font-size:15px;margin:36px 0 12px;border-bottom:1px solid #2a2e35;padding-bottom:6px}"
        ".grid{display:flex;flex-wrap:wrap;gap:18px}"
        "figure{margin:0;width:430px}figure img{width:430px;display:block;background:#fff;border-radius:4px}"
        "figcaption{padding:5px 2px 0;word-break:break-all}</style>"
    ]
    for key in sorted(groups):
        cells.append(f"<h2>{html.escape(key)} · {len(groups[key])}</h2><div class='grid'>")
        for p in sorted(groups[key]):
            cells.append(
                f"<figure><img src='{p.resolve().as_uri()}' loading='eager'>"
                f"<figcaption>{html.escape(p.stem)}</figcaption></figure>"
            )
        cells.append("</div>")

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
        fh.write("".join(cells))
        sheet_html = Path(fh.name)

    CONTACT_SHEET.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": 1400, "height": 900})
        await page.goto(sheet_html.as_uri())
        await page.wait_for_timeout(1500)  # entrance fades + font decode
        await page.screenshot(path=str(CONTACT_SHEET), full_page=True)
        await browser.close()
    sheet_html.unlink()
    print(f"{len(paths)} artifacts -> {CONTACT_SHEET}")
    return 0


def expand(args: list[str]) -> list[Path]:
    paths: list[Path] = []
    for a in args:
        if any(ch in a for ch in "*?["):
            paths.extend(Path(m) for m in globlib.glob(a, recursive=True))
        else:
            paths.append(Path(a))
    return sorted(p for p in paths if p.suffix == ".svg")


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--contact-sheet":
        rest = args[1:] or [str(PROOFSET_ROOT / "**" / "*.svg")]
        paths = expand(rest)
        if not paths:
            print("no SVGs found for the contact sheet")
            return 1
        return asyncio.run(contact_sheet(paths))
    # --scheme both: add a light + dark emulated-color-scheme capture per artifact
    # (the surface-modes adaptive check). Consumed here, stripped before glob expand.
    scheme = ""
    if "--scheme" in args:
        idx = args.index("--scheme")
        scheme = args[idx + 1] if idx + 1 < len(args) else ""
        if scheme not in ("both", "light", "dark"):
            print("--scheme takes: both | light | dark")
            return 1
        args = args[:idx] + args[idx + 2 :]
    paths = expand(args) if args else sorted(DEFAULT_GLOB.glob("*.svg"))
    if not paths:
        print(f"no SVGs found (looked in {DEFAULT_GLOB})")
        return 1
    return asyncio.run(raster(paths, scheme=scheme))


if __name__ == "__main__":
    raise SystemExit(main())
