"""Parse an SVG document into neutral, engine-agnostic facts.

Works identically on hand-authored specimens, engine renders,
and future benchmark submissions: element geometry from attributes, per-class
style facts (dasharray / animation) from the merged ``<style>`` text, embedded
``hw:payload`` JSON, ``hw:spatial-notes`` prose, and root ``data-hw-*`` attrs.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    w: float
    h: float
    rx: float
    cls: str
    dashed: bool

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass(frozen=True, slots=True)
class Circle:
    cx: float
    cy: float
    r: float
    cls: str
    has_motion: bool


@dataclass(frozen=True, slots=True)
class PathEl:
    d: str
    cls: str
    own_cls: str
    marker_end: bool
    dashed: bool
    animated: bool

    def endpoints(self) -> tuple[tuple[float, float], tuple[float, float]] | None:
        pts = _path_points(self.d)
        if len(pts) < 2:
            return None
        return pts[0], pts[-1]


@dataclass(frozen=True, slots=True)
class TextEl:
    x: float
    y: float
    anchor: str
    cls: str
    content: str


@dataclass(frozen=True, slots=True)
class GlyphGroup:
    """A translate-transform <g> holding a handful of drawn primitives — the
    identity-mark signature both vocabularies share (specimen ``-gi`` groups,
    engine translate+scale glyph groups, brand-fill logo groups). The
    ceiling (16) sits above the heaviest specimen identity mark
    (flywheel-orbit's 14-primitive phase glyph) and below decor wrappers."""

    own_cls: str
    children: int


@dataclass(frozen=True, slots=True)
class BeamGradFact:
    """One animated linearGradient (a beam window): the structural recipe
    facts ``law_beam`` grades — clock, staged keyTimes window, easing,
    spread, and whether both end stops hit true-zero opacity. Structural on
    purpose: per-edge chord gradients legitimately replace a hand file's
    shared-horizontal economy, so coordinates are never compared."""

    gid: str
    dur: str
    keytimes: str
    has_keysplines: bool
    spread: str
    calc_mode: str
    end_opacities: tuple[float, float]

    def window(self) -> tuple[float, float] | None:
        """The staged (start, end) pair from a 4-point hold-sweep-hold
        keyTimes; None when the shape differs."""
        parts = self.keytimes.split(";")
        if len(parts) != 4:
            return None
        try:
            return (round(float(parts[1]), 4), round(float(parts[2]), 4))
        except ValueError:
            return None


@dataclass(slots=True)
class Facts:
    viewbox: tuple[float, float, float, float]
    width: float | None
    height: float | None
    rects: list[Rect] = field(default_factory=list)
    circles: list[Circle] = field(default_factory=list)
    paths: list[PathEl] = field(default_factory=list)
    texts: list[TextEl] = field(default_factory=list)
    style_text: str = ""
    payload: dict[str, object] | None = None
    spatial_notes: str = ""
    glyph_groups: list[GlyphGroup] = field(default_factory=list)
    payload_text: str = ""
    root_attrs: dict[str, str] = field(default_factory=dict)
    smil_motion_count: int = 0
    has_keyframes: bool = False
    css_animation_used: bool = False
    beam_gradients: list[BeamGradFact] = field(default_factory=list)

    @property
    def vb_w(self) -> float:
        return self.viewbox[2]

    @property
    def vb_h(self) -> float:
        return self.viewbox[3]

    @property
    def display_scale(self) -> float | None:
        """Rendered px per viewBox unit (width axis)."""
        if self.width is None or self.vb_w <= 0:
            return None
        return self.width / self.vb_w

    @property
    def animated(self) -> bool:
        """True only when animation is USED: SMIL present, or some element
        carries a class whose rule animates. Specimens embed the shared kit
        stylesheet (keyframes defined) even when nothing rides them."""
        if self.smil_motion_count > 0:
            return True
        return self.css_animation_used


_NUM = re.compile(r"-?\d*\.?\d+(?:e[+-]?\d+)?", re.I)
_CMD = re.compile(r"([MLHVCSQTAZ])([^MLHVCSQTAZ]*)", re.I)

# Coordinates consumed per segment, per command letter (uppercase form).
_ARITY = {"M": 2, "L": 2, "T": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "A": 7, "Z": 0}


def _path_points(d: str) -> list[tuple[float, float]]:
    """The ABSOLUTE points a path visits — a real mini-interpreter over the
    SVG path grammar (relative commands tracked via the cursor), so both the
    hand-authored specimens' relative glyphwork/dendrograms and the engine's
    absolute connectors measure identically. Control points are ignored;
    only on-path endpoints are collected."""
    pts: list[tuple[float, float]] = []
    cx = cy = 0.0
    start = (0.0, 0.0)
    for m in _CMD.finditer(d):
        letter = m.group(1)
        cmd = letter.upper()
        rel = letter.islower()
        nums = [float(n) for n in _NUM.findall(m.group(2))]
        arity = _ARITY[cmd]
        if cmd == "Z":
            cx, cy = start
            pts.append((cx, cy))
            continue
        if arity == 0 or (arity and len(nums) < arity):
            continue
        for i in range(0, len(nums) - arity + 1, arity):
            seg = nums[i : i + arity]
            if cmd == "H":
                cx = cx + seg[0] if rel else seg[0]
            elif cmd == "V":
                cy = cy + seg[0] if rel else seg[0]
            else:
                x, y = seg[-2], seg[-1]
                cx = cx + x if rel else x
                cy = cy + y if rel else y
            if cmd == "M" and i == 0:
                start = (cx, cy)
            pts.append((cx, cy))
    out: list[tuple[float, float]] = []
    for p in pts:
        if not out or (abs(out[-1][0] - p[0]) > 1e-9 or abs(out[-1][1] - p[1]) > 1e-9):
            out.append(p)
    return out


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


_CLASS_RULE = re.compile(r"\.([\w-]+)\s*(?:,\s*\.[\w-]+\s*)*\{([^}]*)\}")


def _class_style_maps(style_text: str) -> tuple[set[str], set[str]]:
    """Class names whose CSS rule carries a stroke-dasharray / an animation.

    Handles comma-selector groups by re-scanning the selector list.
    """
    dashed: set[str] = set()
    animated: set[str] = set()
    for block in re.finditer(r"([^{}]+)\{([^}]*)\}", style_text):
        selectors, body = block.group(1), block.group(2)
        names = re.findall(r"\.([\w-]+)", selectors)
        if not names:
            continue
        if "stroke-dasharray" in body:
            dashed.update(names)
        if re.search(r"(?<![\w-])animation(?:-duration)?\s*:", body):
            animated.update(names)
    return dashed, animated


def _f(el: ET.Element, name: str, default: float = 0.0) -> float:
    raw = el.get(name)
    if raw is None:
        return default
    m = _NUM.search(raw)
    return float(m.group(0)) if m else default


_PAYLOAD_RE = re.compile(r"<hw:payload[^>]*><!\[CDATA\[(.*?)\]\]></hw:payload>", re.DOTALL)


def parse_svg(svg: str) -> Facts:
    root = ET.fromstring(svg)
    payload_m = _PAYLOAD_RE.search(svg)
    vb_raw = root.get("viewBox", "0 0 0 0")
    vb_nums = [float(n) for n in _NUM.findall(vb_raw)][:4]
    while len(vb_nums) < 4:
        vb_nums.append(0.0)
    width = _attr_px(root.get("width"))
    height = _attr_px(root.get("height"))

    style_parts: list[str] = []
    payload: dict[str, object] | None = None
    spatial_notes = ""
    facts = Facts(
        viewbox=(vb_nums[0], vb_nums[1], vb_nums[2], vb_nums[3]),
        width=width,
        height=height,
        root_attrs={k: v for k, v in root.attrib.items() if k.startswith("data-")},
        payload_text=(payload_m.group(1) if payload_m else ""),
    )

    for el in root.iter():
        tag = _local(el.tag)
        if tag == "style" and el.text:
            style_parts.append(el.text)
        elif tag == "payload" and el.text:
            try:
                loaded = json.loads(el.text)
                if isinstance(loaded, dict):
                    payload = loaded
            except ValueError:
                payload = None
        elif tag == "spatial-notes" and el.text:
            spatial_notes = " ".join(el.text.split())
        elif tag in ("animateMotion", "animateTransform", "animate"):
            # Every SMIL kind counts as rendered motion (honesty.motion-flag):
            # a beam's gradientTransform sweep is real animation — the beam reference
            # specimens declare motion="animated" on exactly that basis.
            facts.smil_motion_count += 1
        elif tag == "linearGradient":
            anim = next((c for c in el if _local(c.tag) == "animateTransform"), None)
            if anim is not None:
                stops = [c for c in el if _local(c.tag) == "stop"]

                def _op(stop: ET.Element) -> float:
                    try:
                        return float(stop.get("stop-opacity", "1"))
                    except ValueError:
                        return 1.0

                facts.beam_gradients.append(
                    BeamGradFact(
                        gid=el.get("id") or "",
                        dur=anim.get("dur") or "",
                        keytimes=anim.get("keyTimes") or "",
                        has_keysplines=anim.get("keySplines") is not None,
                        spread=el.get("spreadMethod") or "",
                        calc_mode=anim.get("calcMode") or "",
                        end_opacities=((_op(stops[0]), _op(stops[-1])) if stops else (1.0, 1.0)),
                    )
                )

    facts.style_text = "\n".join(style_parts)
    facts.has_keyframes = "@keyframes" in facts.style_text
    facts.payload = payload
    facts.spatial_notes = spatial_notes
    dashed_cls, animated_cls = _class_style_maps(facts.style_text)

    def any_cls_names(names: str, pool: set[str]) -> bool:
        return any(c in pool for c in names.split())

    def walk(el: ET.Element, inherited: str) -> None:
        tag = _local(el.tag)
        if tag in ("defs", "metadata"):
            return  # geometry census never looks inside defs/metadata
        own = el.get("class") or ""
        if own and any_cls_names(own, animated_cls):
            facts.css_animation_used = True
        cls = (inherited + " " + own).strip()
        _collect(el, tag, cls, own)
        for child in el:
            walk(child, cls)

    def _collect(el: ET.Element, tag: str, cls: str, own: str) -> None:
        if tag == "g":
            tf = el.get("transform") or ""
            prim = [c for c in el if _local(c.tag) in ("path", "circle", "rect", "line")]
            # The identity-mark signature: a small group of drawn primitives,
            # placed EITHER by a translate transform (engine, most specimens)
            # OR by absolute coordinates under a glyph-family class (the hub
            # specimen's bare `-gi` groups). Big wrappers (entrance groups,
            # whole-figure groups) have many children and never census.
            glyph_classed = any(h in own for h in ("-gi", "-gia", "-gf", "-gm", "-mgi", "-hgi", "-hg"))
            if (tf.startswith("translate") or glyph_classed) and 1 <= len(prim) <= 16 and len(prim) == len(list(el)):
                facts.glyph_groups.append(GlyphGroup(own_cls=own, children=len(prim)))
        if tag == "rect":
            facts.rects.append(
                Rect(
                    x=_f(el, "x"),
                    y=_f(el, "y"),
                    w=_f(el, "width"),
                    h=_f(el, "height"),
                    rx=_f(el, "rx"),
                    cls=cls,
                    dashed=("stroke-dasharray" in (el.get("style") or ""))
                    or el.get("stroke-dasharray") is not None
                    or any_cls_names(own, dashed_cls),
                )
            )
        elif tag == "circle":
            has_motion = any(_local(c.tag) == "animateMotion" for c in el)
            facts.circles.append(
                Circle(cx=_f(el, "cx"), cy=_f(el, "cy"), r=_f(el, "r"), cls=cls, has_motion=has_motion)
            )
        elif tag == "path":
            d = el.get("d") or ""
            if d:
                facts.paths.append(
                    PathEl(
                        d=d,
                        cls=cls,
                        own_cls=own,
                        marker_end=el.get("marker-end") is not None,
                        dashed=el.get("stroke-dasharray") is not None or any_cls_names(own, dashed_cls),
                        animated=any_cls_names(own, animated_cls),
                    )
                )
        elif tag == "text":
            content = "".join(el.itertext()).strip()
            facts.texts.append(
                TextEl(
                    x=_f(el, "x"),
                    y=_f(el, "y"),
                    anchor=el.get("text-anchor") or "start",
                    cls=cls,
                    content=content,
                )
            )

    walk(root, "")
    return facts


def _attr_px(raw: str | None) -> float | None:
    if raw is None or raw.strip().endswith("%"):
        return None  # fluid width — no fixed display size
    m = _NUM.search(raw)
    return float(m.group(0)) if m else None


_HEX_TOKEN = re.compile(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})")


def css_tokens(style_text: str) -> tuple[dict[str, str], dict[str, str]]:
    """(base-scope, dark-scope) custom-property → hex maps.

    The dark scope is every ``@media (prefers-color-scheme: dark)`` block;
    the base scope is everything outside them. Later declarations win.
    """
    dark_spans: list[tuple[int, int]] = []
    for m in re.finditer(r"@media[^{]*prefers-color-scheme:\s*dark[^{]*\{", style_text):
        depth = 1
        i = m.end()
        while i < len(style_text) and depth:
            if style_text[i] == "{":
                depth += 1
            elif style_text[i] == "}":
                depth -= 1
            i += 1
        dark_spans.append((m.start(), i))

    def in_dark(pos: int) -> bool:
        return any(a <= pos < b for a, b in dark_spans)

    base: dict[str, str] = {}
    dark: dict[str, str] = {}
    for m in _HEX_TOKEN.finditer(style_text):
        target = dark if in_dark(m.start()) else base
        target[m.group(1)] = m.group(2).upper()
    return base, dark
