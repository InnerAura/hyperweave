"""Choreography sampling — ordered review frames at the phi beats.

A ``turn`` loop is reviewed as ``turn``: each frame bakes the choreography
channels' exact values at one beat of the artifact's own cycle, so the
reviewer sees states the animation actually passes through — never a
substitute artifact composed with different fields.

Scope is the engine's own inline choreography channels — the
``style="animation:hw-<uid>-chN <D>s …"`` declarations whose ``@keyframes``
blocks the choreography compiler emitted (numeric ``stroke-dashoffset`` /
``opacity`` stops). Class-driven march channels and SMIL riders have no
per-element sampling path and are listed under ``not_sampled`` — drop, never
fake. Values between stops interpolate linearly; per-stop easing functions
are not simulated, and the record discloses that.
"""

from __future__ import annotations

import itertools
import re
from typing import Any
from xml.etree import ElementTree as ET

from hyperweave.formats.static import run_passes_counted

PHI_BEATS = (1.618, 2.618, 4.236, 6.854)
"""The motion grammar's own timing ladder — the beats a reviewer samples at."""

_INLINE_ANIM = re.compile(r"animation:\s*(hw-[\w]+-ch\d+)\s+([\d.]+)s[^;\"']*;?")
_KEYFRAMES_HEAD = re.compile(r"@keyframes\s+(hw-[\w]+-ch\d+)\s*\{")
_STOP = re.compile(r"([\d.]+)%\s*\{([^}]*)\}")
_NUMERIC_DECL = re.compile(r"(stroke-dashoffset|opacity)\s*:\s*(-?[\d.]+)")
_STYLE_ATTR = re.compile(r'style="([^"]*)"')


def _keyframes_bodies(svg: str) -> list[tuple[str, str]]:
    """Every channel ``@keyframes`` block as ``(name, inner_body)``, extracted
    by brace walking — a regex anchored on formatting silently merged all
    channels into the first block's body when the emitter wrote them on one
    line, leaving every channel but the first unsampled."""
    out: list[tuple[str, str]] = []
    for m in _KEYFRAMES_HEAD.finditer(svg):
        depth, i = 1, m.end()
        while i < len(svg) and depth:
            if svg[i] == "{":
                depth += 1
            elif svg[i] == "}":
                depth -= 1
            i += 1
        out.append((m.group(1), svg[m.end() : i - 1]))
    return out


def _channel_stops(svg: str) -> dict[str, list[tuple[float, dict[str, float]]]]:
    """Per-channel ordered ``(percent, {prop: value})`` stops from the
    artifact's own ``@keyframes`` blocks. Duplicate percents (the engine's
    easing-boundary idiom) keep the last declaration, matching CSS."""
    out: dict[str, list[tuple[float, dict[str, float]]]] = {}
    for name, body in _keyframes_bodies(svg):
        stops: dict[float, dict[str, float]] = {}
        for pct, decls in _STOP.findall(body):
            props = {p: float(v) for p, v in _NUMERIC_DECL.findall(decls)}
            if props:
                stops.setdefault(float(pct), {}).update(props)
        if stops:
            out[name] = sorted(stops.items())
    return out


def _value_at(stops: list[tuple[float, dict[str, float]]], prop: str, pct: float) -> float | None:
    """Linear interpolation of ``prop`` at ``pct`` over the channel's stops."""
    pts = [(p, d[prop]) for p, d in stops if prop in d]
    if not pts:
        return None
    if pct <= pts[0][0]:
        return pts[0][1]
    for (p0, v0), (p1, v1) in itertools.pairwise(pts):
        if p0 <= pct <= p1:
            span = p1 - p0
            return v0 if span == 0 else v0 + (v1 - v0) * (pct - p0) / span
    return pts[-1][1]


def _bake_frame(svg: str, beat: float, stops: dict[str, list[tuple[float, dict[str, float]]]]) -> str:
    """One frame: every inline channel declaration replaced by its exact
    sampled property values at ``beat`` seconds into that channel's cycle."""

    def _attr(m: re.Match[str]) -> str:
        def _decl(dm: re.Match[str]) -> str:
            name, dur = dm.group(1), float(dm.group(2))
            ch = stops.get(name)
            if ch is None:
                return dm.group(0)  # no sampling path — the strip parks it
            local = (beat % dur) / dur * 100.0
            baked = [
                f"{prop}:{_value_at(ch, prop, local):g}"
                for prop in ("stroke-dashoffset", "opacity")
                if _value_at(ch, prop, local) is not None
            ]
            return ";".join(baked) + ";" if baked else ""

        return f'style="{_INLINE_ANIM.sub(_decl, m.group(1))}"'

    return _STYLE_ATTR.sub(_attr, svg)


def sample_choreography(svg: str) -> tuple[dict[str, Any], dict[str, bytes]] | None:
    """Sample the artifact's inline choreography channels at the phi beats.

    Returns ``(motion_record, frames)`` — frames keyed ``beat-<t>s.svg``, each
    a parsed-verified static projection with the channels baked at that beat —
    or ``None`` when the artifact carries no inline channel (the caller keeps
    its honest "not sampled" record).
    """
    channels = {name: float(dur) for name, dur in _INLINE_ANIM.findall(svg)}
    if not channels:
        return None
    stops = _channel_stops(svg)
    cycle = max(channels.values())

    not_sampled: list[str] = []
    if "<animate" in svg:
        not_sampled.append("SMIL riders (parked by the static strip)")
    unstoppped = sorted(set(channels) - set(stops))
    if unstoppped:
        not_sampled.append(f"{len(unstoppped)} channels without numeric stops")

    frames: dict[str, bytes] = {}
    beats: list[str] = []
    for beat in PHI_BEATS:
        frame = _bake_frame(svg, beat, stops)
        static, _counts = run_passes_counted(frame, ["vars", "noanim"])
        ET.fromstring(static)  # each frame obeys the projection postcondition
        frames[f"beat-{beat:g}s.svg"] = static.encode("utf-8")
        beats.append(f"{beat:g}s")

    record: dict[str, Any] = {
        "sampled": True,
        "cycle_s": cycle,
        "beats": beats,
        "channels": len(channels),
        "interpolation": "linear between the channel's own stops; per-stop easing functions are not simulated",
    }
    if not_sampled:
        record["not_sampled"] = not_sampled
    return record, frames
