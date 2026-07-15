#!/usr/bin/env python3
"""Generate the Surface Modes proof matrix — every variant x surface, per frame.

Surface Modes projects one genome palette three ways (plate / inlay / twin); this
script renders the full cross-product for the primer genome so the projection can
be reviewed and regression-checked. For each surface-capable frame it emits:

* the three surfaces (plate, inlay, twin) for all eight primer variants — 24
  cells per frame; and
* the two baked twin faces (light, dark) per variant — 16 face renders per frame.

Outputs land under ``outputs/proofset/primer/surface/<frame>/`` as
``<variant>-<surface>[-<face>].svg``, plus a gallery HTML per frame that embeds
every inlay and twin over BOTH a light and a dark host panel (the dual-host
practice from the surface-modes prototypes) so the theme-borrowing reads at a
glance.

Two verification halves, per the plan's split:

* CI gate — ``tests/compose/test_surface_matrix.py`` runs pure-Python per-cell
  invariants (far-palette AA, status-invariance, digest distinctness, twin-face
  hex agreement). No browser.
* Browser pass — ``scripts/raster_verify.py --scheme both`` rasterizes the inlays
  under emulated light + dark schemes into contact sheets. Manual / nightly, not
  CI (rsvg ignores ``var()`` and ``@media``, so adaptive cells are browser-only).

Adaptive cells (inlay, twin) are NEVER rasterized through rsvg here — they carry
``@media (prefers-color-scheme)`` that only a real browser honors. The baked twin
faces are plain plates and rasterize fine.

The ``FRAMES`` list is the extension point: the diagram frame joins as one entry
once its templates honor ``surface_ground`` / ``surface_adapt`` (WC-2b-ii). Adding
it there generates its cells and gallery with zero other changes.

Usage:
    uv run python scripts/generate_surface_matrix.py
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from hyperweave.compose.engine import compose  # noqa: E402
from hyperweave.core.models import ComposeSpec  # noqa: E402

_OUT = _ROOT / "outputs" / "proofset" / "primer" / "surface"

# The eight primer variants, canonical order (matches the genome roster).
_VARIANTS = ("noir", "carbon", "space", "anvil", "porcelain", "cream", "dusk", "petrol")

# The three surfaces as (slug, ground, palette). Faces are emitted separately.
_SURFACES = (
    ("plate", "opaque", "fixed"),
    ("inlay", "bare", "adaptive"),
    ("twin", "opaque", "adaptive"),
)


def _matrix_ir(variant: str) -> dict[str, Any]:
    """A per-variant table (VARIED SPECS): the 8-variant sweep also sweeps
    structure — numeric-heat density, check columns, label length, row count —
    so the review sees the surface behavior across compositions, not one spec
    re-inked eight ways. Every shape still exercises the surface-sensitive
    roles: numeric heat, identity-hue label column, header/footer chrome.
    """
    shapes: dict[int, dict[str, Any]] = {
        0: {  # label + numeric + check (the original proof shape)
            "columns": [
                {"id": "model", "label": "MODEL", "role": "label"},
                {"id": "score", "label": "SCORE", "role": "data", "kind": "numeric"},
                {"id": "pass", "label": "PASS", "role": "data", "kind": "check"},
            ],
            "rows": [
                {"label": "alpha", "cells": [{"value": 91}, {"value": True}]},
                {"label": "beta", "cells": [{"value": 84}, {"value": True}]},
                {"label": "gamma", "cells": [{"value": 62}, {"value": False}]},
            ],
        },
        1: {  # numeric-dense: three heat columns, four rows
            "columns": [
                {"id": "run", "label": "RUN", "role": "label"},
                {"id": "p50", "label": "P50", "role": "data", "kind": "numeric"},
                {"id": "p95", "label": "P95", "role": "data", "kind": "numeric"},
                {"id": "p99", "label": "P99", "role": "data", "kind": "numeric"},
            ],
            "rows": [
                {"label": "ingest", "cells": [{"value": 12}, {"value": 48}, {"value": 95}]},
                {"label": "resolve", "cells": [{"value": 8}, {"value": 21}, {"value": 40}]},
                {"label": "compose", "cells": [{"value": 31}, {"value": 77}, {"value": 128}]},
                {"label": "deliver", "cells": [{"value": 5}, {"value": 14}, {"value": 22}]},
            ],
        },
        2: {  # long identity labels + mixed kinds
            "columns": [
                {"id": "svc", "label": "SERVICE", "role": "label"},
                {"id": "cov", "label": "COVERAGE", "role": "data", "kind": "numeric"},
                {"id": "ok", "label": "GATE", "role": "data", "kind": "check"},
            ],
            "rows": [
                {"label": "telemetry-collector", "cells": [{"value": 97}, {"value": True}]},
                {"label": "surface-projection", "cells": [{"value": 88}, {"value": True}]},
            ],
        },
        3: {  # sparse two-by-two
            "columns": [
                {"id": "k", "label": "KEY", "role": "label"},
                {"id": "v", "label": "VALUE", "role": "data", "kind": "numeric"},
            ],
            "rows": [
                {"label": "nodes", "cells": [{"value": 16}]},
                {"label": "edges", "cells": [{"value": 24}]},
            ],
        },
    }
    shape = shapes[_VARIANTS.index(variant) % len(shapes)]
    return {"title": "Surface Modes", "subtitle": f"primer proof · {variant}", **shape}


def _diagram_ir(variant: str) -> dict[str, Any]:
    """A per-variant topology (VARIED SPECS): the 8-variant sweep rotates
    through eight topologies, so the surface review doubles as a structural
    sweep. Every spec keeps the surface-sensitive roles in play: card + hero
    backgrounds (surface_alt/signal), connector palette, desc (ink_muted).
    """
    shapes: dict[str, dict[str, Any]] = {
        "dag": {
            "topology": "dag",
            "nodes": [
                {"id": "in", "label": "Ingest", "desc": "source"},
                {"id": "proc", "label": "Process", "role": "hero"},
                {"id": "out", "label": "Deliver", "desc": "sink"},
            ],
            "edges": [{"source": "in", "target": "proc"}, {"source": "proc", "target": "out"}],
        },
        "hub": {
            "topology": "hub",
            "nodes": [
                {"id": "core", "label": "Registry", "role": "hero"},
                {"id": "a", "label": "Extract", "desc": "read"},
                {"id": "b", "label": "Verify"},
                {"id": "c", "label": "Compose", "desc": "emit"},
                {"id": "d", "label": "Query"},
            ],
            "edges": [
                {"source": "core", "target": "a", "role": "out"},
                {"source": "core", "target": "b", "role": "out"},
                {"source": "c", "target": "core", "role": "in"},
                {"source": "d", "target": "core", "role": "in"},
            ],
        },
        "sequence": {
            "topology": "sequence",
            "nodes": [{"id": "cli", "label": "CLI"}, {"id": "core", "label": "Core"}, {"id": "st", "label": "Store"}],
            "edges": [
                {"source": "cli", "target": "core", "label": "compose", "kind": "call"},
                {"source": "core", "target": "st", "label": "put", "kind": "call"},
                {"source": "st", "target": "core", "label": "digest", "kind": "return"},
            ],
        },
        "lanes": {
            "topology": "lanes",
            "nodes": [
                {"id": "a", "label": "Fetch", "category": "Source"},
                {"id": "b", "label": "Parse", "category": "Transform"},
                {"id": "c", "label": "Shape", "category": "Transform"},
                {"id": "d", "label": "Store", "category": "Sink"},
            ],
            "edges": [
                {"source": "a", "target": "b"},
                {"source": "b", "target": "c"},
                {"source": "c", "target": "d"},
            ],
        },
        "pipeline": {
            "topology": "pipeline",
            "nodes": [
                {"id": "s", "label": "Spec"},
                {"id": "r", "label": "Resolve", "role": "hero"},
                {"id": "c", "label": "Compose"},
                {"id": "d", "label": "Deliver"},
            ],
            "edges": [
                {"source": "s", "target": "r"},
                {"source": "r", "target": "c"},
                {"source": "c", "target": "d"},
            ],
        },
        "convergence": {
            "topology": "convergence",
            "nodes": [
                {"id": "a", "label": "CLI", "desc": "typer"},
                {"id": "b", "label": "HTTP", "desc": "fastapi"},
                {"id": "c", "label": "MCP", "desc": "fastmcp"},
                {"id": "core", "label": "Dispatch", "role": "hero"},
            ],
            "edges": [
                {"source": "a", "target": "core"},
                {"source": "b", "target": "core"},
                {"source": "c", "target": "core"},
            ],
        },
        "state-machine": {
            "topology": "state-machine",
            "nodes": [
                {"id": "idle", "label": "Idle"},
                {"id": "run", "label": "Running", "role": "hero"},
                {"id": "done", "label": "Done"},
            ],
            "edges": [
                {"source": "idle", "target": "run", "label": "start"},
                {"source": "run", "target": "done", "label": "finish"},
                {"source": "done", "target": "idle", "label": "reset"},
            ],
        },
        "fanout": {
            "topology": "fanout",
            "nodes": [
                {"id": "hub", "label": "Genome", "role": "hero"},
                {"id": "a", "label": "Badge"},
                {"id": "b", "label": "Matrix"},
                {"id": "c", "label": "Diagram"},
                {"id": "d", "label": "Card"},
            ],
            "edges": [
                {"source": "hub", "target": "a"},
                {"source": "hub", "target": "b"},
                {"source": "hub", "target": "c"},
                {"source": "hub", "target": "d"},
            ],
        },
    }
    order = ("dag", "hub", "sequence", "lanes", "pipeline", "convergence", "state-machine", "fanout")
    shape = shapes[order[_VARIANTS.index(variant) % len(order)]]
    return {"title": "Surface Modes", "subtitle": f"primer proof · {variant}", **shape}


# Frame roster. Each entry: (frame_type, IR-builder). Matrix + diagram are the two
# Surface-Modes frames (the allowlist in surface-modes.yaml); both honor the
# surface context. Keep in lockstep with tests/compose/test_surface_matrix.py.
_FRAMES: tuple[tuple[str, Any], ...] = (("matrix", _matrix_ir), ("diagram", _diagram_ir))


def _render(frame: str, variant: str, ground: str, palette: str, face: str, ir: dict[str, Any]) -> str:
    return compose(
        ComposeSpec(
            type=frame,
            genome_id="primer",
            variant=variant,
            ground=ground,
            palette=palette,
            surface_face=face,
            **{frame: ir},
        )
    ).svg


def _cell_name(variant: str, surface: str, face: str = "") -> str:
    return f"{variant}-{surface}-{face}.svg" if face else f"{variant}-{surface}.svg"


def generate() -> dict[str, list[Path]]:
    """Render every cell + face for every frame; return the paths written by frame."""
    written: dict[str, list[Path]] = {}
    for frame, ir_builder in _FRAMES:
        frame_dir = _OUT / frame
        frame_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []

        for variant in _VARIANTS:
            ir = ir_builder(variant)  # varied specs: structure sweeps with the variant
            # The three surfaces.
            for surface, ground, palette in _SURFACES:
                svg = _render(frame, variant, ground, palette, "", ir)
                dest = frame_dir / _cell_name(variant, surface)
                dest.write_text(svg)
                paths.append(dest)
            # The two baked twin faces (plain plates).
            for face in ("light", "dark"):
                svg = _render(frame, variant, "opaque", "fixed", face, ir)
                dest = frame_dir / _cell_name(variant, "twin", face)
                dest.write_text(svg)
                paths.append(dest)

        _write_gallery(frame, frame_dir)
        print(f"{frame}: {len(paths)} cells + faces -> {frame_dir.relative_to(_ROOT)}")
        written[frame] = paths
    return written


# ── Gallery: every inlay + twin over a light AND a dark host panel ─────────


_GALLERY_CSS = """
:root { --mono: 'JetBrains Mono', ui-monospace, monospace;
        --sys: 'Inter', -apple-system, system-ui, sans-serif; }
html[data-theme="light"] { --bg:#ffffff; --fg:#1f2328; --muted:#59636e; --border:#d1d9e0; --panel:#f6f8fa; }
html[data-theme="dark"]  { --bg:#0d1117; --fg:#e6edf3; --muted:#9198a1; --border:#30363d; --panel:#161b22; }
* { box-sizing: border-box; }
html, body { margin: 0; }
body { background: var(--bg); color: var(--fg); font-family: var(--sys); line-height: 1.5;
       transition: background .35s, color .35s; }
.top { position: sticky; top: 0; z-index: 9; background: var(--bg); border-bottom: 1px solid var(--border);
       padding: 16px 28px; display: flex; align-items: center; gap: 16px; }
.top h1 { font-size: 16px; margin: 0; }
.top .note { color: var(--muted); font-size: 13px; }
button { font: 600 13px var(--sys); padding: 6px 14px; border: 1px solid var(--border);
         border-radius: 6px; background: var(--panel); color: var(--fg); cursor: pointer; }
main { padding: 28px; display: grid; gap: 28px; align-items: start;
       grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); }
figure { margin: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
figure img { width: 100%; display: block; }
figcaption { padding: 8px 12px; font: 500 12px var(--mono); color: var(--muted);
             border-top: 1px solid var(--border); }
/* Each cell hosts the SAME artifact over a light and a dark ground so the
   theme-borrow (inlay) and the scheme flip (twin) are both visible at once. */
.hosts { display: grid; grid-template-columns: 1fr 1fr; }
.host-light { background: #ffffff; }
.host-dark  { background: #0d1117; }
.host { padding: 18px; display: flex; align-items: center; justify-content: center; }
"""

_GALLERY_JS = """
const btn = document.getElementById('toggle');
btn.addEventListener('click', () => {
  const el = document.documentElement;
  el.dataset.theme = el.dataset.theme === 'light' ? 'dark' : 'light';
});
"""


def _write_gallery(frame: str, frame_dir: Path) -> None:
    """Emit gallery.html embedding each inlay + twin over both host grounds.

    Plate cells are theme-blind by definition, so the gallery focuses on the two
    adaptive surfaces — the ones whose whole point is to react to the host. Each
    artifact is shown twice, over a fixed white ground and a fixed dark ground, so
    a reviewer sees the inlay borrow each ground and the twin flip its scheme
    within one row (the browser's own prefers-color-scheme drives the flip; the
    page toggle re-themes the surrounding chrome).
    """
    cells: list[str] = []
    for variant in _VARIANTS:
        for surface in ("inlay", "twin"):
            svg_name = _cell_name(variant, surface)
            src = (frame_dir / svg_name).resolve().as_uri()
            alt = f"{variant} {surface}"
            cells.append(
                f'<figure><div class="hosts">'
                f'<div class="host host-light"><img src="{src}" loading="lazy" alt="{alt} on light"></div>'
                f'<div class="host host-dark"><img src="{src}" loading="lazy" alt="{alt} on dark"></div>'
                f"</div><figcaption>{html.escape(variant)} · {surface}</figcaption></figure>"
            )

    doc = (
        "<!doctype html>\n"
        '<html lang="en" data-theme="light">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>primer surface modes — {html.escape(frame)}</title>\n"
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&'
        'family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">\n'
        f"<style>{_GALLERY_CSS}</style>\n</head>\n<body>\n"
        '<div class="top">'
        f"<h1>primer · surface modes · {html.escape(frame)}</h1>"
        '<span class="note">each cell: the same artifact over a light and a dark host ground '
        "(inlay borrows · twin flips via prefers-color-scheme)</span>"
        '<button id="toggle">toggle page theme</button></div>\n'
        f"<main>\n{chr(10).join(cells)}\n</main>\n"
        f"<script>{_GALLERY_JS}</script>\n</body>\n</html>\n"
    )
    _sweep_gallery_cells(doc)
    (frame_dir / "gallery.html").write_text(doc)


def _sweep_gallery_cells(doc: str) -> None:
    """Bug-g sweep: no gallery cell renders more than one artifact's content
    region. A <figure> is one cell — it shows ONE artifact (the same file
    over a light and a dark host ground). Two distinct srcs in one cell, or
    a host holding more than one embed, is the ghost-stack defect; fail the
    emit rather than publish it."""
    for cell in re.findall(r"<figure>.*?</figure>", doc, flags=re.S):
        srcs = re.findall(r'<img src="([^"]+)"', cell)
        if len(srcs) != 2 or len(set(srcs)) != 1:
            raise AssertionError(f"gallery cell embeds {len(set(srcs))} artifacts ({len(srcs)} imgs) — one allowed")
        for host in re.findall(r'<div class="host [^"]*">(.*?)</div>', cell, flags=re.S):
            if host.count("<img") != 1:
                raise AssertionError("gallery host ground must hold exactly one embed")


def main() -> int:
    generate()
    print("\nGallery per frame at outputs/proofset/primer/surface/<frame>/gallery.html")
    print(
        "Browser pass: uv run python scripts/raster_verify.py --scheme both "
        "outputs/proofset/primer/surface/matrix/*.svg"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
