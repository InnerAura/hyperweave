"""The cascade decision, pinned as behavior (session-A audit, 2026-08-30).

The cascade-partition audit measured every cross-layer same-property collision
across five artifacts (badge + four topologies): the face overrides win by
SOURCE ORDER at equal-or-greater specificity, and every accessibility override
wins by IMPORTANCE — three mechanisms, all deterministic, none depending on
`@layer`. The selected branch is FLAT CSS: no `@layer` is emitted, the order
is structural, and this file pins the mechanisms so the cascade cannot drift
silently. Adopting `@layer` later requires a true cascade-aware lowering in
svg-static first (the CSS lowering law) — the audit found its only risky cell
is importance-inversion inside an a11y layer, so unwrapping is not free.
"""

from __future__ import annotations

import re

from hyperweave.compose.engine import compose
from hyperweave.config.loader import load_diagram_presets
from hyperweave.core.models import ComposeSpec

_UID = re.compile(r"hw-[0-9a-f]{8}")


def _styles(svg: str) -> str:
    return re.sub(
        r"/\*.*?\*/", "", "\n".join(re.findall(r"<style\b[^>]*>(.*?)</style>", svg, re.DOTALL)), flags=re.DOTALL
    )


def _spec_of(selector: str) -> tuple[int, int, int]:
    return (
        selector.count("#"),
        selector.count(".") + selector.count("["),
        len(re.findall(r"(?:^|[\s>+~])[a-zA-Z]", selector)),
    )


def _artifacts() -> list[str]:
    presets = load_diagram_presets()
    out = [compose(ComposeSpec(type="badge", title="BUILD", value="passing")).svg]
    for preset in ("loop-retry-budget", "dag-gate"):
        out.append(
            compose(
                ComposeSpec(
                    type="diagram", genome_id="primer", ground="opaque", palette="fixed", diagram=dict(presets[preset])
                )
            ).svg
        )
    return out


class TestFlatCascadeMechanisms:
    def test_accessibility_overrides_win_by_importance(self) -> None:
        # Reduced-motion and forced-colors rules override whatever came before
        # regardless of order or specificity — every declaration they carry is
        # !important, the one mechanism @layer would invert.
        for svg in _artifacts():
            css = _styles(svg)
            for media_body in re.findall(
                r"@media[^{]*(?:reduced-motion|forced-colors)[^{]*\{((?:[^{}]|\{[^{}]*\})*)\}", css
            ):
                for decls in re.findall(r"\{([^{}]*)\}", media_body):
                    for decl in filter(None, (d.strip() for d in decls.split(";"))):
                        assert "!important" in decl, f"a11y override without !important: {decl!r}"

    def test_face_overrides_follow_their_base_rules(self) -> None:
        # Every dark-face rule re-declaring a property some base rule set on
        # the same target must sit LATER in the stylesheet at >= specificity —
        # the two facts flat order needs to pick the face winner.
        for svg in _artifacts():
            css = _styles(svg)
            dark_spans = [
                (m.start(), m.group(1))
                for m in re.finditer(r"@media[^{]*prefers-color-scheme[^{]*\{((?:[^{}]|\{[^{}]*\})*)\}", css)
            ]
            base = {}
            for m in re.finditer(r"(?:^|\})\s*([^{}@%]+)\{([^{}]*)\}", css):
                if any(s <= m.start() < s + len(b) + 64 for s, b in dark_spans):
                    continue
                sel = m.group(1).strip()
                for prop in re.findall(r"([-\w]+)\s*:", m.group(2)):
                    base.setdefault((sel.split()[-1] if sel.split() else sel, prop), (m.start(), _spec_of(sel)))
            for start, body in dark_spans:
                for m in re.finditer(r"([^{}@%]+)\{([^{}]*)\}", body):
                    sel = m.group(1).strip()
                    tgt = sel.split()[-1] if sel.split() else sel
                    for prop in re.findall(r"([-\w]+)\s*:", m.group(2)):
                        hit = base.get((tgt, prop))
                        if hit is None:
                            continue
                        base_pos, base_spec = hit
                        assert start > base_pos, f"dark rule for {tgt}/{prop} precedes its base rule"
                        assert _spec_of(sel) >= base_spec, f"dark rule for {tgt}/{prop} under-specified vs base"

    def test_emission_order_is_deterministic(self) -> None:
        spec = dict(load_diagram_presets()["loop-retry-budget"])
        a, b = (
            compose(
                ComposeSpec(type="diagram", genome_id="primer", ground="opaque", palette="fixed", diagram=dict(spec))
            ).svg
            for _ in range(2)
        )
        sels_a = [s.strip() for s in re.findall(r"(?:^|\})\s*([^{}@%]+)\{", _UID.sub("hw-UID", _styles(a)))]
        sels_b = [s.strip() for s in re.findall(r"(?:^|\})\s*([^{}@%]+)\{", _UID.sub("hw-UID", _styles(b)))]
        assert sels_a == sels_b, "rule order moved between two composes of one spec"

    def test_no_layer_at_rule_ships(self) -> None:
        # The selected branch: flat CSS. @layer arrives only with its lowering
        # pass (the CSS lowering law) — never as a stray emission.
        for svg in _artifacts():
            assert "@layer" not in svg
