#!/usr/bin/env python3
"""Fetch the CORE glyph set (generic-UI marks) from lucide-static.

The brand registry (``glyphs.json``, Simple Icons-derived fills) covers
company marks; this script builds its sibling ``glyphs-core.json`` — the
generic systems vocabulary a diagram node's ``kind`` resolves against
(database, queue, gateway, ...). Source is the Lucide icon set (ISC
license), pinned to one release so a re-run is byte-stable; attribution
lands in the repo-root ``NOTICE``.

Lucide icons are 24x24 STROKE geometry (2px, round caps/joins). The glyph
pipeline renders them through the new stroke channel (``stroke: 2`` on the
registry entry); non-path primitives (circle/rect/line/polyline/ellipse)
are converted to path data here so an entry is always ``paths: [d, ...]``.

Re-run only to change the curated set or bump the pin — the JSON is
committed, the network is a build-time tool, never a runtime dependency.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "src" / "hyperweave" / "data" / "registries" / "glyphs-core.json"
_NOTICE = _ROOT / "NOTICE"

_PIN = "0.525.0"
_CDN = f"https://unpkg.com/lucide-static@{_PIN}/icons/{{name}}.svg"

# The curated systems-diagram vocabulary (~70 marks). Slugs are Lucide names
# at the pinned release; the registry key IS the slug — a DiagramNode.kind
# of "database" resolves the "database" entry.
NAMES = [
    # infrastructure
    "database",
    "server",
    "cloud",
    "globe",
    "cpu",
    "memory-stick",
    "hard-drive",
    "network",
    "router",
    "radio-tower",
    "container",
    "layers",
    "boxes",
    "box",
    "package",
    "archive",
    "folder",
    "workflow",
    "component",
    "puzzle",
    "plug",
    "cable",
    "table",
    "list",
    "layout-grid",
    # code + files
    "terminal",
    "code",
    "braces",
    "file",
    "file-text",
    "file-code",
    "git-branch",
    "git-merge",
    "git-commit-horizontal",
    # security + identity
    "lock",
    "key",
    "shield",
    "shield-check",
    "user",
    "users",
    "bot",
    "fingerprint",
    # signals + state
    "bell",
    "triangle-alert",
    "circle-alert",
    "blend",
    "check",
    "circle-check",
    "columns-2",
    "dna",
    "files",
    "frame",
    "hash",
    "triangle",
    "waves",
    "circle-x",
    "info",
    "activity",
    "gauge",
    "zap",
    "flame",
    "heart-pulse",
    # time
    "timer",
    "clock",
    "calendar",
    "hourglass",
    # motion of data
    "send",
    "mail",
    "inbox",
    "message-square",
    "download",
    "upload",
    "refresh-cw",
    "repeat",
    "shuffle",
    "link",
    "external-link",
    "funnel",
    # observation + tools
    "search",
    "eye",
    "settings",
    "wrench",
    "chart-bar",
    "chart-line",
    "chart-pie",
    # places + things
    "house",
    "building-2",
    "factory",
    "truck",
    "rocket",
    "compass",
    "map-pin",
    "tag",
    "flag",
    "bookmark",
    "star",
    "sun",
    "moon",
    "droplet",
    "leaf",
    "battery",
    "power",
    "camera",
    "image",
    "mic",
    "play",
    "pause",
]

_SVG_NS = "{http://www.w3.org/2000/svg}"
_NUM = r"[-+]?[0-9]*\.?[0-9]+"


def _f(el: ET.Element, attr: str, default: float = 0.0) -> float:
    return float(el.get(attr, default) or default)


def _fmt(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _element_to_d(el: ET.Element) -> str:
    """Convert a Lucide primitive to path data (geometry-identical)."""
    tag = el.tag.removeprefix(_SVG_NS)
    if tag == "path":
        return el.get("d", "")
    if tag == "line":
        x1, y1, x2, y2 = (_f(el, a) for a in ("x1", "y1", "x2", "y2"))
        return f"M{_fmt(x1)} {_fmt(y1)}L{_fmt(x2)} {_fmt(y2)}"
    if tag in ("polyline", "polygon"):
        pts = re.findall(_NUM, el.get("points", ""))
        pairs = [(float(a), float(b)) for a, b in zip(pts[::2], pts[1::2], strict=True)]
        if not pairs:
            return ""
        d = f"M{_fmt(pairs[0][0])} {_fmt(pairs[0][1])}" + "".join(f"L{_fmt(x)} {_fmt(y)}" for x, y in pairs[1:])
        return d + ("Z" if tag == "polygon" else "")
    if tag == "circle":
        cx, cy, r = _f(el, "cx"), _f(el, "cy"), _f(el, "r")
        return (
            f"M{_fmt(cx - r)} {_fmt(cy)}"
            f"A{_fmt(r)} {_fmt(r)} 0 1 0 {_fmt(cx + r)} {_fmt(cy)}"
            f"A{_fmt(r)} {_fmt(r)} 0 1 0 {_fmt(cx - r)} {_fmt(cy)}"
        )
    if tag == "ellipse":
        cx, cy, rx, ry = _f(el, "cx"), _f(el, "cy"), _f(el, "rx"), _f(el, "ry")
        return (
            f"M{_fmt(cx - rx)} {_fmt(cy)}"
            f"A{_fmt(rx)} {_fmt(ry)} 0 1 0 {_fmt(cx + rx)} {_fmt(cy)}"
            f"A{_fmt(rx)} {_fmt(ry)} 0 1 0 {_fmt(cx - rx)} {_fmt(cy)}"
        )
    if tag == "rect":
        x, y, w, h = _f(el, "x"), _f(el, "y"), _f(el, "width"), _f(el, "height")
        rx = _f(el, "rx")
        if rx <= 0:
            return f"M{_fmt(x)} {_fmt(y)}h{_fmt(w)}v{_fmt(h)}h{_fmt(-w)}Z"
        return (
            f"M{_fmt(x + rx)} {_fmt(y)}h{_fmt(w - 2 * rx)}"
            f"a{_fmt(rx)} {_fmt(rx)} 0 0 1 {_fmt(rx)} {_fmt(rx)}v{_fmt(h - 2 * rx)}"
            f"a{_fmt(rx)} {_fmt(rx)} 0 0 1 {_fmt(-rx)} {_fmt(rx)}h{_fmt(-(w - 2 * rx))}"
            f"a{_fmt(rx)} {_fmt(rx)} 0 0 1 {_fmt(-rx)} {_fmt(-rx)}v{_fmt(-(h - 2 * rx))}"
            f"a{_fmt(rx)} {_fmt(rx)} 0 0 1 {_fmt(rx)} {_fmt(-rx)}Z"
        )
    raise ValueError(f"unhandled Lucide primitive <{tag}>")


def fetch(name: str) -> dict[str, object]:
    with urllib.request.urlopen(_CDN.format(name=name), timeout=20) as resp:
        svg = resp.read().decode("utf-8")
    root = ET.fromstring(svg)
    paths = [d for el in root.iter() if el.tag != root.tag and (d := _element_to_d(el))]
    if not paths:
        raise ValueError(f"{name}: no geometry")
    return {"viewBox": "0 0 24 24", "stroke": 2, "paths": paths}


_NOTICE_TEXT = f"""HyperWeave — third-party asset attribution

Core glyph set (src/hyperweave/data/registries/glyphs-core.json)
  Derived from Lucide v{_PIN} (https://lucide.dev), ISC License.
  Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022
  as part of Feather (MIT). All other copyright (c) for Lucide are held
  by Lucide Contributors 2022.
  Geometry converted to path data by scripts/fetch_core_glyphs.py;
  no visual modifications.

Brand glyph registry (src/hyperweave/data/registries/glyphs.json)
  Brand marks sourced from their owners' published brand assets via the
  Simple Icons collection (https://simpleicons.org, CC0-1.0). Trademarks
  remain property of their respective owners.
"""


def main() -> int:
    print(f"fetch-core-glyphs: lucide-static@{_PIN}, {len(NAMES)} marks")
    entries: dict[str, dict[str, object]] = {}
    misses: list[str] = []
    for name in NAMES:
        try:
            entries[name] = fetch(name)
        except Exception as exc:
            misses.append(f"{name}: {exc}")
    if misses:
        print("MISSES (fix the curated list):")
        for m in misses:
            print(f"  {m}")
        return 1
    _OUT.write_text(json.dumps(entries, indent=1, sort_keys=True) + "\n")
    print(f"  wrote {_OUT.relative_to(_ROOT)} ({len(entries)} entries)")
    _NOTICE.write_text(_NOTICE_TEXT)
    print(f"  wrote {_NOTICE.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
