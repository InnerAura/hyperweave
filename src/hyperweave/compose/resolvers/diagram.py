"""Diagram frame resolver — coerce → cap/legality → solve → project.

Mirrors ``resolvers/matrix.py``: returns ``{"width", "height", "template",
"context"}`` and never touches SVG. The solver works in symbolic hues
(``@flow{i}`` / ``@signal`` / ``@signal2``) and accent INDICES; this
resolver substitutes the genome's ``diagram_flow`` palette and accent
family into the frozen records, so layout stays genome-blind and the
templates stamp literal values (gradients) or palette classes (dots,
branches, particles).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from hyperweave.compose.diagram import compute_diagram_layout
from hyperweave.compose.diagram.chrome import VOICE_CLASSES, resolve_node_glyph
from hyperweave.compose.diagram.contrast import apply_glyph_contrast
from hyperweave.compose.diagram.input import coerce_diagram_input
from hyperweave.compose.diagram.project import (
    PAYLOAD_SCHEMA,
    derive_subvariant,
    diagram_desc,
    diagram_envelope_data,
    diagram_payload_json,
    to_markdown,
)
from hyperweave.config.loader import load_diagram_config, load_glyphs
from hyperweave.core.matrix import GlyphTint
from hyperweave.core.paradigm import MatrixVoice, ParadigmDiagramConfig

if TYPE_CHECKING:
    from hyperweave.compose.diagram.records import DiagramLayout, GradientSpec
    from hyperweave.core.diagram import DiagramSpec
    from hyperweave.core.models import ComposeSpec

_MOTION_VOCAB = {
    "dash": "dash-march",
    "particle": "directional-particle",
    "beam": "gradient-window-beam",
    "flow": "laminar-gradient-current",
}


def resolve_diagram(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    paradigm_spec: Any = None,
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve a diagram artifact into template + frame context."""
    paradigms_map = genome.get("paradigms") or {}
    if "diagram" not in paradigms_map:
        raise ValueError(
            f"diagram frame is not supported by genome '{genome.get('id', spec.genome_id)}' "
            "(no paradigms.diagram entry)"
        )
    cfg: ParadigmDiagramConfig = (
        paradigm_spec.diagram
        if paradigm_spec is not None and hasattr(paradigm_spec, "diagram")
        else ParadigmDiagramConfig()
    )
    engine = load_diagram_config()
    glyphs = load_glyphs()
    dspec = coerce_diagram_input(spec.connector_data, spec)
    palette = [str(h) for h in (genome.get("diagram_flow") or [])] or [str(genome.get("accent", "#888888"))]
    selections = _glyph_selections(dspec, spec, genome)
    layout = compute_diagram_layout(
        dspec,
        paradigm=cfg,
        engine=engine,
        palette_len=len(palette),
        composite_only=spec.performance == "composite-only",
        chrome=spec.chrome,
        glyph_registry=glyphs,
        glyph_selections=selections,
    )
    layout = _substitute_hues(layout, palette, genome)
    layout = apply_glyph_contrast(
        layout,
        genome=genome,
        registry=glyphs,
        engine=engine,
        rebuild=lambda glyph_id, tint, cx, cy, size: resolve_node_glyph(
            glyph_id, glyphs, tint, cx=cx, cy=cy, size=size
        ),
    )
    subvariant = derive_subvariant(dspec)
    payload_json = diagram_payload_json(dspec, layout.rendered)

    context: dict[str, Any] = {
        "diagram_layout": layout,
        "diagram_chrome": spec.chrome,
        "diagram_cfg": cfg,
        "viewbox_w": layout.width,
        "viewbox_h": layout.height,
        "diagram_flow": palette,
        "diagram_style": _style_params(engine),
        "diagram_voices": _voice_params(cfg),
        "diagram_glyph_gradients": _used_glyph_gradients(layout, glyphs),
        "payload_json": payload_json,
        "payload_schema": PAYLOAD_SCHEMA,
        "diagram_envelope_data": diagram_envelope_data(dspec),
        "diagram_intent": spec.intent or f"topology diagram: {dspec.title or dspec.topology.value}",
        "markdown_shadow": to_markdown(dspec),
        "title_text": dspec.title or f"{dspec.topology.value} diagram",
        "desc_text": diagram_desc(dspec, subvariant=subvariant),
        "data_hw_subvariant": subvariant,
        "data_hw_topology": dspec.topology.value,
        "performance_tier": layout.rendered.performance,
        "motion_vocabulary": _motion_vocabulary(layout),
        "diagram_title": dspec.title,
        "diagram_text_surface": _text_surface(layout),
    }
    return {
        "width": layout.display_w,
        "height": layout.display_h,
        "template": "frames/diagram.svg.j2",
        "context": context,
    }


def _glyph_selections(dspec: DiagramSpec, spec: ComposeSpec, genome: dict[str, Any]) -> tuple[GlyphTint, ...]:
    """The tint selection chain: per-slot > artifact IR > caller param >
    genome per-frame default > ink. Degradation through what each registry
    entry carries happens at placement; the rendered mode lands in the
    payload's ``rendered.glyph_tint``."""
    frame_default = spec.glyph_tint or str((genome.get("glyph_tint") or {}).get("diagram", "")) or "ink"
    artifact = dspec.glyph_tint or GlyphTint(frame_default)
    return tuple(node.glyph_tint or artifact for node in dspec.nodes)


def _substitute_hues(layout: DiagramLayout, palette: list[str], genome: dict[str, Any]) -> DiagramLayout:
    """Rewrite symbolic gradient hues into genome hex.

    ``@flow{i}`` -> the flow palette slot; ``@signal`` -> the genome
    accent; ``@signal2`` -> the beam's second identity hue — the flow
    palette's second slot (the canon's blue -> violet drama; accent_deep
    sat too close to the accent on porcelain to read as two hues)."""
    signal = str(genome.get("accent", "#888888"))
    signal2 = palette[1 % len(palette)] if len(palette) > 1 else signal

    def hue(token: str) -> str:
        if token == "@signal":
            return signal
        if token == "@signal2":
            return signal2
        if token.startswith("@flow"):
            idx = int(token[5:])
            return palette[idx % len(palette)]
        return token

    new_gradients: list[GradientSpec] = []
    for g in layout.gradients:
        stops = tuple(replace(s, color=hue(s.color)) for s in g.stops)
        new_gradients.append(replace(g, stops=stops))
    return replace(layout, gradients=tuple(new_gradients))


def _style_params(engine: dict[str, Any]) -> dict[str, Any]:
    """The scalar style constants the defs CSS stamps (engine-config
    sourced; the chassis paints arrive as --dna-* roles instead)."""
    conn = engine["connector"]
    track = engine["track"]
    beam = engine["beam"]
    flow = engine["flow"]
    entrance = engine["entrance"]
    return {
        "stroke_width": conn["stroke_width"],
        "dash": conn["dash"],
        "linecap": conn["linecap"],
        "ants_dur": conn["ants_dur"],
        "ants_offset_to": conn["ants_offset_to"],
        "march_opacity": track["march_opacity"],
        "tube_opacity": track["tube_opacity"],
        "tube_reduced_opacity": track["tube_reduced_opacity"],
        "halo_blur": beam["halo_blur"],
        "flow_halo_blur": flow["halo_blur"],
        "fade_dur": entrance["fade_dur"],
        "fade_ease": entrance["fade_ease"],
    }


def _voice_params(cfg: ParadigmDiagramConfig) -> list[dict[str, Any]]:
    """Type-voice CSS parameters — the same family/size/weight tuples the
    solver measured with (the chrome VOICE_CLASSES registry is the single
    coupling point)."""

    def stack(family: str) -> str:
        if family == "Inter":
            return "var(--dna-font-display, 'Inter', system-ui, sans-serif)"
        return "var(--dna-font-mono, 'JetBrains Mono', ui-monospace, monospace)"

    out: list[dict[str, Any]] = []
    for name, attr in VOICE_CLASSES:
        voice = getattr(cfg, attr)
        assert isinstance(voice, MatrixVoice)
        out.append(
            {
                "name": name,
                "stack": stack(voice.family),
                "size": voice.size,
                "weight": voice.weight,
                "tracking": voice.tracking_em,
            }
        )
    return out


def _used_glyph_gradients(layout: DiagramLayout, glyphs: dict[str, Any]) -> list[dict[str, Any]]:
    """One linearGradient def per brand-gradient mark the layout placed."""
    ids: list[str] = []
    for node in layout.nodes:
        if node.glyph is not None and node.glyph.gradient and node.glyph.gradient not in ids:
            ids.append(node.glyph.gradient)
    gradients: list[dict[str, Any]] = []
    for glyph_id in ids:
        gradient = (glyphs.get(glyph_id) or {}).get("gradient")
        if isinstance(gradient, dict):
            gradients.append({"id": glyph_id, **gradient})
    return gradients


def _motion_vocabulary(layout: DiagramLayout) -> str:
    """Specimen-derived motion names for ``hw:motion vocabulary``."""
    names: list[str] = []
    replay = layout.layout_slug == "sequence"
    for m, c in zip(layout.rendered.edge_motion, layout.connectors, strict=False):
        if c.inert:
            continue
        word = _MOTION_VOCAB.get(m, m)
        if m == "particle" and replay:
            word = "ordered-replay-particle"
        if word not in names:
            names.append(word)
        if c.track == "dash-march" and "dash-march" not in names:
            names.append("dash-march")
    return " ".join(names) if names else "static"


def _text_surface(layout: DiagramLayout) -> list[str]:
    """Every string the SVG renders — feeds the font subsetter."""
    strings: list[str] = []
    if layout.header.title is not None:
        strings.append(layout.header.title.text)
    if layout.header.subtitle is not None:
        strings.append(layout.header.subtitle.text)
    for n in layout.nodes:
        strings.append(n.label.text)
        strings.extend(line.text for line in n.desc_lines)
        if n.short is not None:
            strings.append(n.short.text)
        if n.tag is not None:
            strings.append(n.tag.text)
    for c in layout.connectors:
        if c.label is not None:
            strings.append(c.label.text)
    strings.extend(op.text for op in layout.operators)
    if layout.legend is not None:
        strings.append(layout.legend.text)
    if layout.footer is not None:
        strings.append(layout.footer.text)
    return [s for s in strings if s]
