#!/usr/bin/env python3
"""Generate HW-compliant versions of all specimen SVGs.

For each specimen SVG in specs/components/ and specs/motion/:
  1. Do NOT modify originals
  2. Create hw-compliant/ subfolder within each specimen's directory
  3. Regenerate with full HyperWeave v8.0 protocol scaffolding
  4. ZERO visual changes

Usage:
    python3 scripts/generate_hw_compliant.py
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"


def _has_hw_metadata(svg: str) -> bool:
    """Check if SVG already has HW protocol metadata."""
    return "hw:artifact" in svg and "xmlns:hw" in svg and 'role="img"' in svg


def _has_reduced_motion(svg: str) -> bool:
    return "prefers-reduced-motion" in svg


def _has_color_scheme(svg: str) -> bool:
    return "prefers-color-scheme" in svg


def _extract_viewbox(svg: str) -> str:
    m = re.search(r'viewBox="([^"]+)"', svg, re.IGNORECASE)
    return m.group(1) if m else "0 0 800 220"


def _extract_dims(svg: str) -> tuple[str, str]:
    """Extract width/height from SVG, preserving original values exactly."""
    w = re.search(r'width="([^"]+)"', svg)
    h = re.search(r'height="([^"]+)"', svg)
    return (w.group(1) if w else "800", h.group(1) if h else "220")


def _extract_svg_tag(svg: str) -> tuple[str, str]:
    """Split into the opening <svg ...> tag and everything after."""
    m = re.match(r"(<svg[^>]*>)(.*)", svg, re.DOTALL)
    if m:
        return m.group(1), m.group(2)
    return "<svg>", svg


def _augment_svg_tag(tag: str, attrs: dict[str, str]) -> str:
    """Add attributes to an existing <svg ...> tag without replacing originals.

    Preserves ALL original attributes (xmlns, viewBox, width, height, etc.).
    Only ADDS attributes that don't already exist in the tag.
    """
    for key, val in attrs.items():
        # Skip if attribute already exists
        if f"{key}=" in tag or f"{key} =" in tag:
            continue
        # Insert before the closing >
        tag = tag.rstrip(">").rstrip() + f'\n     {key}="{val}">'
        # Fix: ensure single closing >
        tag = tag.replace(">>", ">")
    return tag


def _infer_type(path: Path) -> str:
    """Infer artifact type from directory structure."""
    parts = str(path).lower()
    if "divider" in parts:
        return "divider"
    if "icon" in parts:
        return "icon"
    if "banner" in parts or "holofoil" in parts:
        return "banner"
    if "marquee" in parts:
        return "marquee"
    if "border-frame" in parts:
        return "motion-primitive"
    if "kinetic-typography" in parts:
        return "kinetic-typography"
    return "specimen"


def _infer_motion_id(path: Path) -> str:
    """Infer motion ID from filename."""
    name = path.stem.lower()
    mapping = {
        "002-chromatic-pulse": "chromatic-pulse",
        "003-corner-trace": "corner-trace",
        "004-dual-orbit": "dual-orbit",
        "020-quantum-entanglement": "entanglement",
        "rim-runners": "rimrun",
        "banner_bars": "bars",
        "banner_broadcast": "broadcast",
        "banner_cascade": "cascade",
        "banner_convergence": "converge",
        "banner_drop": "drop",
        "crash": "crash",
        "chromatic_impact_physics": "impact",
        "quantum_tunneling_breach": "breach",
        "pulse": "pulse",
        "z_axis_illusion_via_exponential_scale_blur_convergence": "collapse",
    }
    return mapping.get(name, name)


def _slug(path: Path) -> str:
    return path.stem.lower().replace(" ", "-").replace("_", "-")


def _check_cim(svg: str) -> tuple[bool, str]:
    """Check CIM compliance and return waiver if needed."""
    non_cim_indicators = []
    if "stop-color" in svg and "animate" in svg.lower():
        non_cim_indicators.append("stop-color animation")
    if "stroke-dashoffset" in svg and "animate" in svg.lower():
        non_cim_indicators.append("stroke-dashoffset animation")
    if "stroke-width" in svg and "<animate" in svg.lower() and "stroke-width" in svg.split("<animate")[1][:200]:
        non_cim_indicators.append("stroke-width animation")
    if "letter-spacing" in svg and "animate" in svg.lower():
        non_cim_indicators.append("letter-spacing animation")
    if "stdDeviation" in svg and "animate" in svg.lower():
        non_cim_indicators.append("filter blur animation")
    if "baseFrequency" in svg and "animate" in svg.lower():
        non_cim_indicators.append("turbulence animation")
    if "clip-path" in svg and "@keyframes" in svg:
        non_cim_indicators.append("clip-path animation")
    # Check for animated gradients
    if re.search(r'<animate[^>]*attributeName="x[12]"', svg, re.IGNORECASE):
        non_cim_indicators.append("gradient coordinate animation")

    if non_cim_indicators:
        return False, f"Non-CIM: {', '.join(non_cim_indicators)}"
    return True, ""


def wrap_specimen(src: Path) -> str:
    """Wrap a raw specimen SVG with HW v8.0 protocol scaffolding.

    CRITICAL: The original <svg> tag's xmlns, viewBox, width, height are
    preserved EXACTLY. We only ADD new attributes (xmlns:hw, role,
    aria-labelledby, data-hw-*). Never replace existing ones.
    """
    svg = src.read_text(encoding="utf-8").strip()

    # Already compliant — add only missing layers
    if _has_hw_metadata(svg):
        if not _has_reduced_motion(svg):
            svg = _inject_reduced_motion(svg)
        if not _has_color_scheme(svg):
            svg = _inject_color_scheme(svg)
        return svg

    # Raw specimen — full protocol wrap
    artifact_id = str(uuid.uuid4())
    uid = f"hw-{artifact_id[:8]}"
    now = datetime.now(UTC).isoformat()
    w, h = _extract_dims(svg)
    art_type = _infer_type(src)
    slug = _slug(src)
    motion_id = _infer_motion_id(src) if "motion" in str(src) else "static"
    cim_ok, cim_waiver = _check_cim(svg)

    # Extract the original <svg ...> tag and inner content
    svg_tag, inner = _extract_svg_tag(svg)
    if inner.rstrip().endswith("</svg>"):
        inner = inner.rstrip()[:-6]

    # Augment the ORIGINAL tag — preserve xmlns, viewBox, width, height
    augmented = _augment_svg_tag(
        svg_tag,
        {
            "xmlns:hw": "https://hyperweave.dev/hw/v8.0",
            "role": "img",
            "aria-labelledby": f"{uid}-title {uid}-desc",
            "data-hw-id": artifact_id,
            "data-hw-frame": art_type,
            "data-hw-chromatic": "adaptive",
            "data-hw-motion": motion_id,
        },
    )

    perf = "composite-only" if cim_ok else "paint-ok"
    cim_str = "true" if cim_ok else "false"
    tradeoffs = "CIM-compliant: uses only compositor-friendly properties." if cim_ok else f"CIM waiver: {cim_waiver}"

    return f'''{augmented}

  <title id="{uid}-title">{slug} -- HyperWeave Specimen</title>
  <desc id="{uid}-desc">HW-compliant version of {src.name}. Type: {art_type}. Zero visual changes from original.</desc>

  <metadata>
    <hw:artifact id="{artifact_id}" type="{art_type}" series="specimens" version="1.0.0"
                 xmlns:hw="https://hyperweave.dev/hw/v8.0">
      <hw:provenance>
        <hw:generator>HyperWeave Specimen Wrapper v0.1 (InnerAura Labs)</hw:generator>
        <hw:created>{now}</hw:created>
        <hw:human-directed>true</hw:human-directed>
        <hw:source-file>{src.relative_to(ROOT)}</hw:source-file>
      </hw:provenance>
      <hw:spec size="{w}x{h}" performance="{perf}"
               theme="adaptive" a11y="WCAG-AA"/>
      <hw:composition>
        <hw:frame>{art_type}</hw:frame>
        <hw:environment motion="{motion_id}" status="active"/>
      </hw:composition>
      <hw:aesthetic>
        <hw:motion vocabulary="{motion_id}" cim-compliant="{cim_str}"/>
      </hw:aesthetic>
      <hw:reasoning>
        <hw:intent>Specimen artifact wrapped with HW v8.0 protocol for Layer 1 editorial publishing.</hw:intent>
        <hw:approach>Zero-visual-change wrapping: original SVG preserved, HW metadata injected around it.</hw:approach>
        <hw:tradeoffs>{tradeoffs}</hw:tradeoffs>
      </hw:reasoning>
    </hw:artifact>
  </metadata>

  <style>
    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
      }}
      animate, animateTransform, animateMotion, set {{
        display: none !important;
      }}
    }}
    @media (prefers-color-scheme: light) {{
      svg {{ --hw-scheme: light; }}
    }}
    @media (prefers-color-scheme: dark) {{
      svg {{ --hw-scheme: dark; }}
    }}
  </style>

  <!-- Original specimen content (zero visual changes) -->
  <g data-hw-zone="specimen-content">
{_indent(inner, 4)}
  </g>

</svg>'''


def _inject_reduced_motion(svg: str) -> str:
    """Inject prefers-reduced-motion into existing compliant SVG."""
    rm_block = """
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
      }
      animate, animateTransform, animateMotion, set {
        display: none !important;
      }
    }"""
    # Try to inject into existing <style> block
    if "<style>" in svg:
        return svg.replace("<style>", f"<style>{rm_block}", 1)
    # Or add before </svg>
    return svg.replace("</svg>", f"<style>{rm_block}</style>\n</svg>")


def _inject_color_scheme(svg: str) -> str:
    """Inject prefers-color-scheme into existing compliant SVG."""
    cs_block = """
    @media (prefers-color-scheme: light) { svg { --hw-scheme: light; } }
    @media (prefers-color-scheme: dark) { svg { --hw-scheme: dark; } }"""
    if "</style>" in svg:
        return svg.replace("</style>", f"{cs_block}\n</style>", 1)
    return svg


def _indent(text: str, spaces: int) -> str:
    """Indent every line by N spaces."""
    pad = " " * spaces
    return "\n".join(f"{pad}{line}" if line.strip() else line for line in text.splitlines())


def generate() -> None:
    total = 0
    dirs = [
        SPECS / "components" / "dividers",
        SPECS / "components" / "icons",
        SPECS / "components" / "banners",
        SPECS / "components" / "marquees",
        SPECS / "motion" / "motion-border-frames",
        SPECS / "motion" / "motion-kinetic-typography",
    ]

    for d in dirs:
        if not d.exists():
            continue
        svgs = sorted(d.glob("*.svg"))
        if not svgs:
            continue

        out_dir = d / "hw-compliant"
        out_dir.mkdir(exist_ok=True)

        for src in svgs:
            wrapped = wrap_specimen(src)
            out = out_dir / src.name
            out.write_text(wrapped, encoding="utf-8")
            total += 1

            cim_ok, _ = _check_cim(wrapped)
            already = _has_hw_metadata(src.read_text())
            status = "copy" if already else "wrap"
            cim_tag = "CIM" if cim_ok else "NON-CIM"
            print(f"  [{status:4s}] [{cim_tag:7s}] {src.relative_to(ROOT)}")

    print(f"\nWrote {total} hw-compliant specimens.")


if __name__ == "__main__":
    generate()
