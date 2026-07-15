"""Surface Modes projection — plate / inlay / twin off one genome palette.

NAME COLLISION, read this first: ``compose/surface.py`` is the TRANSPORT
surface — one ``SpecEnvelope`` in, one ``ResponseEnvelope`` out, the CLI/HTTP/MCP
unification seam (Architectural Invariant 9). THIS module is the VISUAL surface
mode — how an artifact's palette meets the host page's theme (opaque vs bare
ground, fixed vs adaptive scheme). They share a word and nothing else; keep them
apart.

The math is CONTRAST PARITY, not a naive OKLCH lightness mirror (a mirror does
not reproduce the authored prototypes). For each flipping token we choose a far
lightness — hue held, chroma held and gamut-reduced only as needed — so that the
token's contrast against the FAR ground matches its contrast against the NEAR
ground, then clamp up to a per-role floor. The far ground is a calibrated
lightness pole with the near hue held and its chroma boosted toward a cap.

Three invariants, all load-bearing:

  1. Status hues NEVER flip. ``accent_signal/warning/error`` (and the status-
     mark fields) are semantic — green means pass on paper and on slate. The
     never-flips property holds BY CONSTRUCTION: :func:`flip_palette` emits a
     sparse far dict from which every ``status``/``held`` field is structurally
     absent, so a far ``@media`` block simply never redeclares them and the near
     value holds across the scheme flip.
  2. Vars scope to ``#<artifact-id>``, never ``svg, :root``. Two adaptive
     artifacts on one page would otherwise clobber each other's variables.
  3. The universal (no-``prefers-color-scheme``-support) fallback face is
     ALWAYS light — every hand-authored twin prototype proves this, including
     the dark-native ones (``primer.noir``/``.carbon``/``.space``/``.anvil``):
     each puts light tokens in the base scope and its OWN native dark tokens
     inside ``@media (prefers-color-scheme: dark)``, never the reverse. A
     light-native variant's base scope is already its native palette, so
     nothing swaps; a dark-native variant's base scope must carry the
     COMPUTED light face (this module's flip, run in the light direction) and
     its native tokens move into the dark media block. :func:`flip_palette`
     itself stays direction-relative (near vs far, keyed off ``substrate_kind``)
     — the near/far-to-scope assignment is the caller's job
     (``compose/context.py:_apply_adaptive_css``, ``compose/resolver.py``'s
     face branch), using :func:`native_palette` / :func:`overlay_face_palette`
     below to source whichever face a given scope needs.

All thresholds, floors, and the field→role map live in
``data/config/surface-modes.yaml`` — this module is math over that data. Adding
a genome or a frame is a config edit; no code here changes.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator

from hyperweave.core.base import FrozenModel
from hyperweave.core.color import (
    contrast_ratio,
    hex_to_rgb,
    hex_to_rgb_triplet,
    oklch_to_rgb,
    relative_luminance,
    rgb_to_hex,
    rgb_to_oklch,
)
from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.core.surface_spec import Ground, PaletteMode, SurfaceSpec

# Projection roles that flip through contrast parity (field_roles vocabulary).
_FLIP_ROLES = {"figure", "accent", "border", "on_accent"}
# Roles never emitted in a far dict — the never-flips / genome-invariant set.
_HELD_ROLES = {"status", "held"}
# Floor-role (role_floors vocabulary) keys whose tokens are TEXT — they clamp
# additionally to the AA floor. ``border`` is a hairline, not text.
_TEXT_FLOOR_ROLES = {"ink", "ink_muted", "accent"}

# The projection role (field_roles vocabulary) names WHAT a field does; the
# contrast floor (role_floors vocabulary) names its legibility tier. A figure
# field has two tiers — primary ink vs muted ink — so the floor key can't be
# read off the projection role alone. This maps a (projection role, field) to a
# role_floors key. on_accent text sits on the accent chip, so it borrows the
# accent floor. Ground/shadow/status/held don't use a contrast floor.
_MUTED_FIGURE_FIELDS = {
    "ink_secondary",
    "ink_sub",
    "receipt_eyebrow",
    "receipt_dim_ink",
}


def _floor_role(projection_role: str, field: str) -> str:
    """Map a field to its role_floors key (the contrast tier)."""
    if projection_role == "figure":
        return "ink_muted" if field in _MUTED_FIGURE_FIELDS else "ink"
    if projection_role == "on_accent":
        return "accent"
    return projection_role  # accent, border


# Direction of a variant's flip: a light substrate flips toward dark, and vice
# versa. Keyed by the variant's ``substrate_kind``.
_FLIP_DIRECTION = {"light": "dark", "dark": "light"}


class SurfaceModesConfig(FrozenModel):
    """Calibration constants for the projection, loaded from surface-modes.yaml."""

    chroma_threshold: float = Field(description="OKLCH accent chroma above which a variant is accent-carrying")
    ground_l_dark: float = Field(description="Calibrated far-ground lightness pole in the dark direction")
    ground_l_light: float = Field(description="Calibrated far-ground lightness pole in the light direction")
    ground_tier_offsets: dict[str, float] = Field(description="surface_1/surface_2 lightness offsets from base ground")
    ground_chroma_boost: float = Field(description="Multiplier carrying the near ground's tint into the far ground")
    ground_chroma_cap: float = Field(description="Chroma ceiling so the far ground never saturates")
    role_floors: dict[str, float] = Field(description="Minimum WCAG contrast per flip role vs the far ground")
    aa_floor: float = Field(description="WCAG AA text contrast floor")
    field_roles: dict[str, str] = Field(description="Palette field → projection role")
    frames: list[str] = Field(description="Frame types that accept a non-plate surface")

    @field_validator("field_roles")
    @classmethod
    def _known_roles(cls, v: dict[str, str]) -> dict[str, str]:
        known = _FLIP_ROLES | _HELD_ROLES | {"ground", "shadow"}
        bad = sorted({role for role in v.values() if role not in known})
        if bad:
            raise ValueError(f"field_roles references unknown role(s) {bad}; known = {sorted(known)}")
        return v


def _oklch(hex_color: str) -> tuple[float, float, float]:
    r, g, b = hex_to_rgb(hex_color)
    return rgb_to_oklch(r, g, b)


def _from_oklch(lightness: float, chroma: float, hue_deg: float) -> str:
    return rgb_to_hex(*oklch_to_rgb(lightness, chroma, hue_deg))


def is_chromatic(accent_hex: str, threshold: float) -> bool:
    """True when the accent carries a hue strong enough to survive a ground flip.

    Pure OKLCH-chroma test. Accent-carrying variants keep their identity through
    ``inlay``; monochrome ones (accent == ink, or a neutral) keep only their
    skeleton. Never raises on a malformed hex — treats it as monochrome.
    """
    try:
        _, chroma, _ = _oklch(accent_hex)
    except ValueError:
        return False
    return chroma >= threshold


def classify_palette(palette: dict[str, Any], cfg: SurfaceModesConfig) -> str:
    """Classify a palette as ``"accent-carrying"`` or ``"monochrome"``.

    METADATA ONLY. The emit math (:func:`flip_palette`) never branches on this —
    a monochrome palette flips through the identical contrast-parity path, it
    simply arrives without a carryable hue. Exposed so callers/tests can pin the
    classification and so the projection can annotate what it produced.
    """
    accent = str(palette.get("accent") or "")
    return "accent-carrying" if is_chromatic(accent, cfg.chroma_threshold) else "monochrome"


def reground(ground_hex: str, direction: str, cfg: SurfaceModesConfig, *, tier: str = "surface_0") -> str:
    """Re-ground a background to the opposite scheme's calibrated pole.

    Holds the near ground's hue, drives lightness to the calibrated dark/light
    pole (plus the tier offset for surface_1/surface_2), and boosts chroma
    toward the cap so a deep ground reads as (e.g.) navy rather than flat black.
    """
    _, chroma, hue = _oklch(ground_hex)
    offset = cfg.ground_tier_offsets.get(tier, 0.0)
    # surface_1/surface_2 ALWAYS lift off surface_0 (a raised card reads lighter
    # than its page on BOTH faces): add the tier offset toward light regardless
    # of flip direction. The prior `light ? -offset` sank the cards on a light
    # far face (a dark-native genome's day scope), inverting elevation.
    base_l = cfg.ground_l_dark if direction == "dark" else cfg.ground_l_light
    target_l = base_l + offset
    boosted_c = min(chroma * cfg.ground_chroma_boost, cfg.ground_chroma_cap)
    return _from_oklch(max(0.0, min(1.0, target_l)), boosted_c, hue)


def flip_token(
    token_hex: str,
    near_ground: str,
    far_ground: str,
    *,
    role: str,
    cfg: SurfaceModesConfig,
) -> str:
    """Flip one token to the far scheme by contrast parity.

    ``role`` is a role_floors key (``ink`` / ``ink_muted`` / ``accent`` /
    ``border``) naming the token's contrast tier — :func:`flip_palette` maps a
    field's projection role to it. Holds the hue. Targets contrast(token,
    far_ground) = max(near_contrast, role_floor[, aa_floor for text]) and bisects
    lightness to reach it. If the token's chroma cannot be held at the required
    lightness (out of gamut) the bisection still lands the closest in-gamut
    lightness — monotone contrast vs a fixed ground guarantees convergence.
    On-accent text passes the far ACCENT as ``far_ground`` (text sits on the
    chip, not the page) with ``role="accent"``.
    """
    _, chroma, hue = _oklch(token_hex)
    floor = cfg.role_floors.get(role, 0.0)
    # Accent flips to MEET its role floor on the far ground — NOT to preserve the
    # near contrast. A dark-native bright accent (carbon #F97316 on near-black)
    # carries a huge near contrast, and targeting max(near, floor) drove it far
    # too dark on the light far ground (#F97316 → #A62200, identity lost). Every
    # other role holds the stronger of (near contrast, floor) so body ink stays
    # as crisp on the far face as it was on the near.
    target = floor if role == "accent" else max(contrast_ratio(token_hex, near_ground), floor)
    if role in _TEXT_FLOOR_ROLES:
        target = max(target, cfg.aa_floor)

    far_ground_l, _, _ = _oklch(far_ground)
    # Contrast vs a fixed ground is V-shaped in token lightness: it bottoms out
    # (ratio ~1.0) at the ground's OWN lightness and rises monotonically moving
    # away on either side. Anchor the search AT the ground and drive toward the
    # far pole (dark ground → up toward white; light ground → down toward black).
    # That interval is strictly monotone, so bisection converges for any target,
    # landing a low-target border just off the ground (dark-on-dark hairline) and
    # a high-target ink near the pole. Anchoring at the token's own lightness
    # (which a light border already near white shares with the near ground) would
    # exclude the dark far solution entirely.
    toward_light = far_ground_l < 0.5

    def _graded(lightness: float) -> str:
        # Chroma-preserving night grade: saturation tracks lightness (cap OKLCH
        # chroma at 0.66·L, hue held), so a DEEP flip — an accent driven dark on
        # a light far ground (a dark-native identity hue's day face) — never
        # over-saturates into a muddy neon brick (carbon's ember). Folded into
        # the search so the SOLVED lightness already accounts for the capped
        # chroma; a bright solution (accent lifted for a dark ground) sits above
        # the cap untouched, and non-accent roles never carry enough chroma to
        # trip it.
        return _from_oklch(lightness, min(chroma, 0.66 * lightness), hue)

    lo, hi = (far_ground_l, 1.0) if toward_light else (0.0, far_ground_l)
    # Anchor `best` at the far pole (max |L - ground_L| ⇒ max contrast, always
    # clears) and only ever replace it with a candidate that STILL clears the
    # target — the returned value is the tightest solution that holds the floor,
    # never one a hair under it (the accent role floor sits AT the AA floor, so a
    # sub-target landing would fail AA on the far face).
    best = _graded(hi if toward_light else lo)
    for _ in range(40):
        mid = (lo + hi) / 2.0
        cand = _graded(mid)
        cand_contrast = contrast_ratio(cand, far_ground)
        if cand_contrast >= target:
            best = cand
        # Contrast increases with |mid - far_ground_l|. Toward light: larger mid
        # ⇒ larger contrast. Toward dark: smaller mid ⇒ larger contrast.
        if toward_light:
            if cand_contrast < target:
                lo = mid
            else:
                hi = mid
        elif cand_contrast < target:
            hi = mid
        else:
            lo = mid
    return best


def _flip_rgba(token_rgba: str, far_ink_hex: str) -> str:
    """Re-derive an ``rgba(r,g,b,a)`` border tint from the far ink, alpha held.

    ``border_tint``-style fields are a translucent wash of the ink over the
    ground; on the far face they must wash the FAR ink instead, keeping the
    authored opacity so the separator stays a hairline.
    """
    triplet = hex_to_rgb_triplet(far_ink_hex)
    alpha = token_rgba.rsplit(",", 1)[-1].rstrip(") ") if "," in token_rgba else "1"
    return f"rgba({triplet},{alpha})"


def flip_palette(genome_mapping: dict[str, Any], cfg: SurfaceModesConfig) -> dict[str, str]:
    """Compute the SPARSE far-face palette for a resolved variant mapping.

    Input is the merged genome+variant palette (the fields as they render on the
    near face). Output holds ONLY the fields that change on the far face — every
    ``status`` and ``held`` field is structurally absent, so the never-flips
    invariant needs no equality check: the far ``@media`` block can only ever
    re-declare flipping fields. Grounds re-ground; figure/accent/border/on_accent
    flip by contrast parity; shadow stays dark; ``ink_on_accent`` solves against
    the FAR accent.

    Checks an authored-override hook FIRST — ``twin_overrides[variant]`` in the
    genome — which ships EMPTY (no entries); an entry hand-tunes specific fields
    a few percent past the computed result. Requires ``substrate_kind`` to pick
    the flip direction; defaults to ``light`` (flip toward dark) if absent.
    """
    substrate = str(genome_mapping.get("substrate_kind") or "light")
    direction = _FLIP_DIRECTION.get(substrate, "dark")

    near_ground = str(genome_mapping.get("surface_0") or "")
    far_ground = reground(near_ground, direction, cfg, tier="surface_0")

    # The far ink underlies both figure defaults and the border-tint wash; the
    # far accent is the target for on-accent text. Compute them once.
    near_ink = str(genome_mapping.get("ink") or "")
    far_ink = flip_token(near_ink, near_ground, far_ground, role="ink", cfg=cfg) if near_ink else far_ground
    near_accent = str(genome_mapping.get("accent") or "")
    far_accent = flip_token(near_accent, near_ground, far_ground, role="accent", cfg=cfg) if near_accent else far_ink
    far_ground_l = relative_luminance(far_ground)

    out: dict[str, str] = {}
    for field, role in cfg.field_roles.items():
        if role in _HELD_ROLES:
            continue  # status + held: structurally absent from the far dict
        value = genome_mapping.get(field)
        if not isinstance(value, str) or not value:
            continue

        if role == "ground":
            tier = field if field in cfg.ground_tier_offsets else "surface_0"
            out[field] = reground(value, direction, cfg, tier=tier)
        elif role == "shadow":
            # Shadow tint stays dark on both faces (a drop shadow is never light).
            try:
                s_l, s_c, s_h = _oklch(value)
                dark_l = min(s_l, max(0.0, far_ground_l - 0.08))
                out[field] = _from_oklch(dark_l, s_c, s_h)
            except ValueError:
                out[field] = value
        elif role == "on_accent":
            # on-accent text sits on the far accent chip; the accent floor applies.
            out[field] = flip_token(value, near_ground, far_accent, role="accent", cfg=cfg)
        elif role == "border" and value.lower().startswith("rgba"):
            out[field] = _flip_rgba(value, far_ink)
        elif role in _FLIP_ROLES:
            out[field] = flip_token(value, near_ground, far_ground, role=_floor_role(role, field), cfg=cfg)

    # Authored override wins last (hand-tuning). Ships empty.
    overrides = (genome_mapping.get("twin_overrides") or {}).get(str(genome_mapping.get("_variant") or ""))
    if isinstance(overrides, dict):
        for field, value in overrides.items():
            if isinstance(value, str) and value and cfg.field_roles.get(field) not in _HELD_ROLES:
                out[field] = value
    return out


def native_palette(genome_mapping: dict[str, Any], cfg: SurfaceModesConfig) -> dict[str, str]:
    """Sparse NATIVE-face counterpart of :func:`flip_palette`, same field shape.

    Reads each flip-through field's OWN (untouched, as-authored) genome value
    instead of computing its far-face flip — no math, a pure filter. Needed
    when a scope's face is NOT the genome's native one: a dark-native twin's
    BASE scope carries the computed light face (:func:`flip_palette` run in
    the light direction), so the native dark values have to land somewhere —
    the ``@media (prefers-color-scheme: dark)`` block. This produces exactly
    that sparse dict, mirroring ``flip_palette``'s field selection (ground/
    figure/accent/border/on_accent/shadow; status and held fields excluded —
    the never-flips invariant holds on this side too, by the same omission).
    """
    out: dict[str, str] = {}
    for field, role in cfg.field_roles.items():
        if role in _HELD_ROLES:
            continue
        value = genome_mapping.get(field)
        if isinstance(value, str) and value:
            out[field] = value
    return out


def authored_diagram_faces(genome_mapping: dict[str, Any], frame_type: str) -> dict[str, dict[str, str]] | None:
    """The resolved variant's hand-authored diagram twin faces, or None.

    A primer variant carries ``diagram_faces: {light: {...}, dark: {...}}`` —
    the twin prototype's tokens verbatim from ``verb-algebra-primer-*.svg``. The
    surface pipeline PREFERS these over the computed ``flip_palette`` far face
    (P5 chroma contract): the adaptive twin reads them for its near/@media
    scopes, and the baked ``--face light|dark`` plate overlays them so the
    <picture> pair byte-agrees with the twin. DIAGRAM-SCOPED — the matrix frame
    is also on the surface allowlist but has no authored faces, so it keeps the
    flip fallback. Returns None unless the frame is a diagram and both faces are
    present (``validate_genome_variants`` guarantees the full token set then).
    """
    if frame_type != "diagram":
        return None
    faces = genome_mapping.get("diagram_faces")
    if isinstance(faces, dict) and isinstance(faces.get("light"), dict) and isinstance(faces.get("dark"), dict):
        return {"light": dict(faces["light"]), "dark": dict(faces["dark"])}
    return None


def overlay_face_palette(
    genome_mapping: dict[str, Any],
    face_palette: dict[str, str],
    resolved_variant: str,
) -> dict[str, Any]:
    """Patch a face palette onto BOTH sinks a resolved genome exposes to CSS.

    A resolved genome dict carries chromatic fields at two places: the top
    level (read by ``css_declarations``/``genome_to_css``) and the active
    variant's ``variant_overrides[resolved_variant]`` sub-dict (read by
    ``variant_override_declarations``/``compute_variant_inline_style`` — the
    ONLY sink some fields, e.g. ``label_text``, reach on a plate render, since
    the inline ``style=`` attribute wins the cascade over the stylesheet). A
    face palette — a baked ``--face`` render, or a dark-native twin's
    light-face base patch — must win at both sinks or the second one keeps
    leaking the untouched native value. Returns a NEW dict; never mutates the
    input (``variant_overrides`` is a shared config object across renders of
    the same variant).
    """
    patched: dict[str, Any] = {**genome_mapping, **face_palette}
    if resolved_variant:
        overrides = dict((patched.get("variant_overrides") or {}).get(resolved_variant) or {})
        if overrides:
            overrides.update({k: v for k, v in face_palette.items() if k in overrides})
            patched["variant_overrides"] = {**patched["variant_overrides"], resolved_variant: overrides}
    return patched


def resolve_surface(
    surface: SurfaceSpec | None,
    genome_mapping: dict[str, Any],
    frame_type: str,
    cfg: SurfaceModesConfig,
    *,
    embedded: SurfaceSpec | None = None,
) -> SurfaceSpec:
    """Resolve the effective surface for a compose, precedence explicit > IR > plate.

    ``surface`` is the explicit request (CLI/HTTP/MCP fields); ``embedded`` is a
    SurfaceSpec already carried on the frame IR (payload round-trip). An explicit
    non-default request wins; otherwise the embedded one; otherwise plate. When
    the resolved surface is non-plate, the frame type must be in the allowlist
    and the palette must supply every field its roles need — both fail loud as
    ``SPEC_INVALID`` so a misconfigured genome can't render a half surface.
    """
    resolved = surface if surface is not None else (embedded if embedded is not None else SurfaceSpec())
    is_plate = resolved.ground is Ground.OPAQUE and resolved.palette is PaletteMode.FIXED and not resolved.face
    if is_plate:
        return resolved

    if frame_type not in cfg.frames:
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            f"surface modes (inlay/twin) are not available on the {frame_type!r} frame",
            fix=f"supported frames: {sorted(cfg.frames)}; use surface=plate elsewhere",
        )

    missing = _missing_role_fields(genome_mapping, cfg)
    if missing:
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            f"genome palette is missing surface-role fields required for adaptive rendering: {missing}",
            fix="every ground/figure/accent/border role field must carry a value",
        )
    return resolved


# The minimum palette a surface projection must find to produce a coherent far
# face: a ground, an ink, and an accent (the three roles the near scheme is
# built around). Border/on-accent degrade gracefully if absent.
_REQUIRED_SURFACE_FIELDS = ("surface_0", "ink", "accent")


def _missing_role_fields(genome_mapping: dict[str, Any], cfg: SurfaceModesConfig) -> list[str]:
    missing = [f for f in _REQUIRED_SURFACE_FIELDS if not str(genome_mapping.get(f) or "")]
    return missing


def adaptive_css(
    genome_mapping: dict[str, Any],
    far: dict[str, str],
    root_id: str,
    *,
    near_decls: str,
    override_decls: str = "",
) -> str:
    """Build the scoped adaptive stylesheet: the LIGHT face + a dark @media block.

    Shape matches every authored prototype (cream-twin.svg / porcelain-twin.svg
    and the dark-native primer.noir/.carbon/.space/.anvil twins alike):

        #<root_id> { color-scheme: light dark; <near decls> }
        @media (prefers-color-scheme: dark) { #<root_id> { <far decls> } }

    The far scope is ALWAYS ``prefers-color-scheme: dark`` — invariant 3 above
    (the universal fallback is always light). ``near_decls`` must already be
    the artifact's LIGHT-face declarations (the caller sources them from the
    genome CSS layer plus the variant inline fan-out for a light-native
    variant, or from a light-patched genome — see
    ``compose/context.py:_apply_adaptive_css`` — for a dark-native one); ``far``
    must already be the DARK-face sparse dict. The far block re-declares ONLY
    the fields ``far`` carries — status/held vars are absent from it and so
    never appear, holding across the flip. Scoped to ``#root_id`` so multiple
    adaptive artifacts coexist on one page.
    """
    far_decls = _css_var_block(far)
    near_body = near_decls.strip()
    if override_decls.strip():
        near_body = f"{near_body} {override_decls.strip()}".strip()
    lines = [
        f"#{root_id} {{ color-scheme: light dark; {near_body} }}",
    ]
    if far_decls:
        lines.append(f"@media (prefers-color-scheme: dark) {{ #{root_id} {{ {far_decls} }} }}")
    return "\n".join(lines)


# Palette field → the CSS custom property the templates read. Only fields that
# surface as ``--dna-*`` vars in the primer templates need mapping; the rest are
# consumed as ``_genome_raw`` literals and don't participate in the @media flip.
_VAR_NAMES: dict[str, str] = {
    "surface_0": "--dna-surface",
    "surface_1": "--dna-surface-alt",
    "surface_2": "--dna-surface-deep",
    "ink": "--dna-ink-primary",
    "ink_secondary": "--dna-ink-muted",
    "ink_bright": "--dna-ink-bright",
    "ink_on_accent": "--dna-ink-on-accent",
    "accent": "--dna-signal",
    "accent_text": "--dna-signal-text",
    "accent_complement": "--dna-signal-dim",
    "stroke": "--dna-border",
    "label_text": "--dna-label-text",
    "shadow_color": "--dna-shadow-color",
    "diagram_shadow_color": "--dna-diagram-shadow-color",
    "region_fill": "--dna-region",
    "region_stroke": "--dna-region-border",
}


def _css_var_block(fields: dict[str, str]) -> str:
    """Render the flipped fields as ``--dna-*: #hex;`` declarations (var-mapped)."""
    decls: list[str] = []
    for field, value in fields.items():
        var = _VAR_NAMES.get(field)
        if var is not None:
            decls.append(f"{var}:{value};")
    return " ".join(decls)


def surface_from_props(ground: str, palette: str, face: str) -> SurfaceSpec | None:
    """Build a SurfaceSpec from the ComposeSpec string props, or None for plate.

    Returns None when the props describe the plate default (opaque/fixed/no
    face) so the caller can leave the IR ``surface`` field at its default and
    keep the payload byte-identical. The trap corner (bare+fixed) is rejected by
    the SurfaceSpec validator, surfacing as a ValueError the caller maps to a
    SPEC_INVALID error.
    """
    g = (ground or "").strip().lower()
    p = (palette or "").strip().lower()
    f = (face or "").strip().lower()
    if (not g or g == "opaque") and (not p or p == "fixed") and not f:
        return None
    resolved_ground = Ground(g) if g else Ground.OPAQUE
    resolved_palette = PaletteMode(p) if p else PaletteMode.FIXED
    return SurfaceSpec(ground=resolved_ground, palette=resolved_palette, face=f)


def stamp_surface(
    ir_spec: Any,
    request_surface: SurfaceSpec | None,
    genome_mapping: dict[str, Any],
    frame_type: str,
    cfg: SurfaceModesConfig,
) -> Any:
    """Resolve the surface and stamp it onto the frame IR for content-addressing.

    ``ir_spec`` is a MatrixSpec/DiagramSpec that may already carry an embedded
    ``surface`` (payload round-trip). Precedence: explicit request > embedded >
    plate. Returns ``ir_spec`` unchanged when the resolved surface is plate (so
    ``exclude_defaults`` keeps the payload byte-identical); otherwise a
    ``model_copy`` with the resolved SurfaceSpec, so the surface serializes into
    the hashed payload and plate/inlay/twin (and each twin face) get DISTINCT
    content addresses. Validation (frame allowlist + palette completeness) runs
    inside :func:`resolve_surface` and fails loud.
    """
    embedded = getattr(ir_spec, "surface", None)
    resolved = resolve_surface(request_surface, genome_mapping, frame_type, cfg, embedded=embedded)
    is_plate = resolved.ground is Ground.OPAQUE and resolved.palette is PaletteMode.FIXED and not resolved.face
    if is_plate:
        return ir_spec
    return ir_spec.model_copy(update={"surface": resolved})
