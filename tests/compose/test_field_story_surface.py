"""Face bakes, ground paints — the gallery's dark-face stories must be
self-contained (round-2 layer pin: `surface_face` + `ground=bare` had zero
coverage anywhere in the suite, which is why the ghosting shipped)."""

from __future__ import annotations

import re

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeSpec


def _overrides() -> dict[str, dict]:
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "generate_diagram_galleries.py"
    spec = importlib.util.spec_from_file_location("gal", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("gal", mod)
    spec.loader.exec_module(mod)
    return mod._FIELD_STORY_OVERRIDES, mod.SECTIONS


def test_field_story_face_overrides_pin_opaque_ground() -> None:
    """A bare ground assumes the host already matches the face — false for a
    dark-face override on a light-hosted gallery page."""
    overrides, _ = _overrides()
    for slug, ov in overrides.items():
        if ov.get("surface_face") and ov["surface_face"] != "light":
            assert ov.get("ground") == "opaque", f"{slug}: dark face without ground=opaque will ghost on a light host"


def test_dark_face_story_bakes_own_backdrop() -> None:
    """The baked dark face paints its own opaque dark rect and carries no
    media fallback a light host could activate."""
    overrides, sections = _overrides()
    slug = "incident-relay"
    spec = next(sd for _, stories in sections for s, _src, sd in stories if s == slug)
    kwargs: dict = dict(
        type="diagram",
        genome_id="primer",
        variant="porcelain",
        ground="bare",
        palette="fixed",
        surface_face="light",
        diagram=spec,
    )
    kwargs.update(overrides[slug])
    svg = compose(ComposeSpec(**kwargs)).svg
    m = re.search(r'<rect width="([\d.]+)" height="([\d.]+)" fill="var\(--dna-surface\)"/>', svg)
    assert m, "no backdrop rect — a dark face with no canvas paint ghosts on a light host"
    surf = re.search(r"--dna-surface: (#[0-9A-Fa-f]{6})", svg)
    assert surf is not None
    r, g, b = (int(surf.group(1)[i : i + 2], 16) for i in (1, 3, 5))
    assert (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 < 0.2, f"baked surface {surf.group(1)} is not dark"
    # An ACTIVE rule has a brace; the accessibility CSS carries a static
    # explanatory comment mentioning the query, which is inert.
    assert not re.search(r"@media\s*\(prefers-color-scheme\s*:\s*\w+\)\s*\{", svg), "baked faces never twin"
