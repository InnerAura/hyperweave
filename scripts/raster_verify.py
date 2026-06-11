"""Raster-verify HyperWeave SVGs via Chromium (Playwright).

rsvg-convert/cairosvg silently drop ``var(--dna-*)``, woff2 ``@font-face``,
and media queries — never use them for acceptance. This script screenshots
each SVG in a real Chromium at 2x, plus a reduced-motion pass and (for the
first file) a forced-colors pass, and exits non-zero on any page error.

Usage:
    python scripts/raster_verify.py [glob_or_paths ...]
    # default: outputs/proofset/primer/matrix/*.svg -> outputs/raster/matrix/

Playwright is a dev-only dependency (same harness as render_demo_video.py);
run under an interpreter that has it installed.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GLOB = ROOT / "outputs" / "proofset" / "primer" / "matrix"
OUT_DIR = ROOT / "outputs" / "raster" / "matrix"


async def raster(paths: list[Path]) -> int:
    from playwright.async_api import async_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
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
            await element.screenshot(path=str(OUT_DIR / f"{path.stem}.png"))

            await page.emulate_media(reduced_motion="reduce")
            await page.goto(path.resolve().as_uri())
            await page.locator("svg").screenshot(path=str(OUT_DIR / f"{path.stem}_reduced-motion.png"))
            await page.emulate_media(reduced_motion="no-preference")

            if i == 0:
                await page.emulate_media(forced_colors="active")
                await page.goto(path.resolve().as_uri())
                await page.locator("svg").screenshot(path=str(OUT_DIR / f"{path.stem}_forced-colors.png"))
                await page.emulate_media(forced_colors="none")

            print(f"  rastered {path.stem}")

        await browser.close()

    if errors:
        print("\nRENDER ERRORS:")
        for error in errors:
            print(f"  {error}")
        return 1
    print(f"\n{len(paths)} SVGs rastered clean -> {OUT_DIR}")
    return 0


def main() -> int:
    args = sys.argv[1:]
    if args:
        paths = sorted(p for a in args for p in (Path().glob(a) if "*" in a else [Path(a)]))
    else:
        paths = sorted(DEFAULT_GLOB.glob("*.svg"))
    if not paths:
        print(f"no SVGs found (looked in {DEFAULT_GLOB})")
        return 1
    return asyncio.run(raster(paths))


if __name__ == "__main__":
    raise SystemExit(main())
