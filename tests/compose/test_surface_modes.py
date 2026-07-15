"""Surface Modes projection — calibration, classifier, invariants, addressing.

Locks the WC-1 foundation against the two authored prototypes on disk
(v04/alpha/v04a6/surface-modes/{cream,porcelain}-twin.svg). The math model is
CONTRAST PARITY (not a naive L-mirror); these tests pin that the shipped code
reproduces the prototype palettes within tolerance, splits the eight primer
variants into the spec §3 classifier table exactly, holds AA in both flip
directions, never flips status, and gives plate/inlay/twin distinct content
addresses.
"""

from __future__ import annotations

import pytest

from hyperweave.compose.engine import compose
from hyperweave.compose.surface_modes import (
    adaptive_css,
    classify_palette,
    flip_palette,
    flip_token,
    is_chromatic,
    native_palette,
    overlay_face_palette,
    reground,
    resolve_surface,
    stamp_surface,
    surface_from_props,
)
from hyperweave.config.loader import get_loader, load_surface_modes
from hyperweave.core.color import contrast_ratio, hex_to_rgb, rgb_to_oklch
from hyperweave.core.envelope import extract_envelope
from hyperweave.core.errors import HwError, HwErrorCode
from hyperweave.core.matrix import MatrixCell, MatrixColumn, MatrixRow, MatrixSpec
from hyperweave.core.models import ComposeSpec
from hyperweave.core.surface_spec import Ground, PaletteMode, SurfaceSpec

# ── helpers ──────────────────────────────────────────────────────────────


def _cfg():  # type: ignore[no-untyped-def]
    return load_surface_modes()


def _oklch(hex_color: str) -> tuple[float, float, float]:
    return rgb_to_oklch(*hex_to_rgb(hex_color))


def _hue_delta(a: str, b: str) -> float:
    ha, hb = _oklch(a)[2], _oklch(b)[2]
    d = abs(ha - hb) % 360.0
    return min(d, 360.0 - d)


def _variant_palette(variant: str) -> dict[str, object]:
    """The merged genome+variant mapping the resolver hands to flip_palette."""
    genome = get_loader().genomes["primer"]
    override = genome["variant_overrides"][variant]
    return {**genome, **override, "_variant": variant}


# The spec §3 classifier table — the single source of truth for is_chromatic.
_CLASSIFIER_TABLE = [
    ("porcelain", "#1D4ED8", "accent-carrying"),
    ("carbon", "#F97316", "accent-carrying"),
    ("space", "#38BDF8", "accent-carrying"),
    ("dusk", "#8A4A5E", "accent-carrying"),
    ("petrol", "#3A7070", "accent-carrying"),
    ("cream", "#2C2014", "monochrome"),
    ("anvil", "#B8B8C0", "monochrome"),
    ("noir", "#A8A8A8", "monochrome"),
]

# Text roles that must clear AA in both directions (border is a hairline, not text).
_TEXT_FIELDS = ("ink", "ink_secondary", "accent", "label_text", "badge_value_text")


# ── classifier (spec §3 8-row table) ──────────────────────────────────────


@pytest.mark.parametrize(("variant", "accent", "expected"), _CLASSIFIER_TABLE)
def test_classifier_pins_spec_table(variant: str, accent: str, expected: str) -> None:
    """classify_palette splits the 8 primer variants exactly as spec §3."""
    assert classify_palette({"accent": accent}, _cfg()) == expected


def test_is_chromatic_threshold_boundary() -> None:
    """petrol (C≈0.057) is accent-carrying; cream (C≈0.028) is not."""
    cfg = _cfg()
    assert is_chromatic("#3A7070", cfg.chroma_threshold) is True
    assert is_chromatic("#2C2014", cfg.chroma_threshold) is False


def test_is_chromatic_malformed_is_monochrome() -> None:
    """A malformed hex never raises — treated as monochrome (no carryable hue)."""
    assert is_chromatic("not-a-hex", _cfg().chroma_threshold) is False


def test_classify_is_metadata_only_not_a_flip_gate() -> None:
    """Monochrome and accent-carrying palettes both produce a full far dict.

    The classification is metadata; the emit math never branches on it. A
    monochrome variant still flips every figure/ground/border field — it simply
    arrives without a carryable identity hue.
    """
    cfg = _cfg()
    cream_far = flip_palette(_variant_palette("cream"), cfg)
    porc_far = flip_palette(_variant_palette("porcelain"), cfg)
    # both flip the ground + ink, regardless of classification
    for far in (cream_far, porc_far):
        assert "surface_0" in far
        assert "ink" in far


# ── prototype calibration (contrast parity reproduces the authored faces) ──


def test_reground_within_prototype_bounds() -> None:
    """reground lands each prototype's far ground lightness within ΔL ≤ 0.03.

    Lightness is the load-bearing dimension (the ground must land at the
    calibrated dark pole). Hue is held from the NEAR ground; the authored
    prototypes hand-shift cream's ground hue warmer, so a computed-vs-authored
    hue check is not meaningful for a near-black ground where chroma ≈ 0.02 and
    the hue angle is numerically noisy. Porcelain (higher chroma) holds hue.
    """
    cfg = _cfg()
    porc = reground("#F5F8FF", "dark", cfg)
    cream = reground("#F8F3EB", "dark", cfg)
    assert abs(_oklch(porc)[0] - _oklch("#0B1220")[0]) <= 0.03
    assert abs(_oklch(cream)[0] - _oklch("#1E140D")[0]) <= 0.03
    # Porcelain's ground carries enough chroma for hue to be meaningful; it holds
    # the near hue (deep navy, not neutral black).
    assert _hue_delta(porc, "#F5F8FF") <= 2.0
    # cream reground holds the NEAR ground hue (the computed contract), even
    # though the authored prototype hand-shifted it a few degrees warmer.
    assert _hue_delta(cream, "#F8F3EB") <= 4.0


@pytest.mark.parametrize(
    ("near_ground", "far_ground", "token", "role", "authored"),
    [
        # porcelain accent — the flip HOLDS the source hue (authored unused, see below)
        ("#F5F8FF", "#0B1220", "#1D4ED8", "accent", ""),
        ("#F5F8FF", "#0B1220", "#C7D5EA", "border", "#33425C"),
        # cream (monochrome)
        ("#F8F3EB", "#1E140D", "#2C2014", "figure", "#EADBCD"),
        ("#F8F3EB", "#1E140D", "#E0D4BE", "border", "#3A2A1C"),
    ],
)
def test_flip_token_reproduces_prototype(
    near_ground: str, far_ground: str, token: str, role: str, authored: str
) -> None:
    """Non-accent roles: flip_token lands near each authored token (hue ≤ 22°,
    L ≤ 0.10) — the contrast-parity projection reproduces the hand-authored
    prototype grounds/inks/borders within a hair.

    Accent: P5 (chroma contract) retargets the accent flip to its role FLOOR
    (drop the ``max(near_contrast, floor)`` term) so a dark-native ember no
    longer over-darkens (carbon #F97316 → #A62200). flip_token is now the
    LEGIBILITY FALLBACK — primer diagrams consume the hand-authored twin accent
    from ``diagram_faces`` directly, so the flip need not reproduce it; its
    contract is (a) HOLD THE SOURCE HUE and (b) clear AA on the far ground. The
    ``authored`` column is unused for the accent row (its hand-tuned twin value
    is a few degrees off the held source hue, by design).
    """
    cfg = _cfg()
    got = flip_token(token, near_ground, far_ground, role=role, cfg=cfg)
    if role == "accent":
        assert _hue_delta(got, token) <= 3.0, f"accent hue not held from source: {got} vs {token}"
        assert contrast_ratio(got, far_ground) >= cfg.aa_floor, f"accent {got} fails AA on far ground {far_ground}"
        return
    # border hue can drift because a near-neutral border carries little hue to hold.
    assert _hue_delta(got, authored) <= 22.0, f"{role}: {got} vs {authored} hue {_hue_delta(got, authored):.1f}"
    assert abs(_oklch(got)[0] - _oklch(authored)[0]) <= 0.10, f"{role}: L {got} vs {authored}"


def test_accent_hue_held_light_variants_flip_to_dark() -> None:
    """Light accent-carrying variants hold accent hue flipping to a dark ground.

    ``flip_token`` holds the hue in OKLCH and only moves lightness; the small
    residual drift is the sRGB gamut round-trip when a saturated hue is lightened
    (the authored porcelain prototype itself drifts ~4.9° near→far by hand). This
    is the calibrated, prototype-backed direction (light substrate → dark ground)
    where the whole model was solved — hue holds within a tight bound.
    """
    cfg = _cfg()
    for variant, _, cls in _CLASSIFIER_TABLE:
        mapping = _variant_palette(variant)
        if cls != "accent-carrying" or mapping["substrate_kind"] != "light":
            continue
        near_ground = str(mapping["surface_0"])
        far_ground = reground(near_ground, "dark", cfg)
        accent = str(mapping["accent"])
        flipped = flip_token(accent, near_ground, far_ground, role="accent", cfg=cfg)
        assert _hue_delta(accent, flipped) <= 6.0, f"{variant}: accent hue swung {_hue_delta(accent, flipped):.1f}°"


def test_dark_warm_accent_flip_to_light_stays_in_gamut() -> None:
    """A bright warm accent flipping to a LIGHT ground darkens (sRGB gamut).

    carbon's orange (#F97316) cannot hold both its hue AND high contrast on a
    near-white ground — sRGB has no dark saturated orange, so darkening compresses
    the hue toward red. This is inherent to the gamut, not a projection bug: the
    accent stays as close to its hue as sRGB permits while meeting the contrast
    contract. The invariant here is that the flip still produces a valid,
    AA-clean, in-family (warm) accent — not that the hue is pinned.
    """
    cfg = _cfg()
    mapping = _variant_palette("carbon")
    near_ground = str(mapping["surface_0"])
    far_ground = reground(near_ground, "light", cfg)
    flipped = flip_token(str(mapping["accent"]), near_ground, far_ground, role="accent", cfg=cfg)
    # AA-clean on the far light ground, and still a warm hue (< 90°, red-orange).
    assert contrast_ratio(flipped, far_ground) >= cfg.aa_floor - 0.01
    assert _oklch(flipped)[2] < 90.0


# ── AA in both directions for every text role of every variant ─────────────


@pytest.mark.parametrize("variant", [v for v, _, _ in _CLASSIFIER_TABLE])
def test_far_face_text_roles_meet_aa(variant: str) -> None:
    """Every text-role token clears AA (4.5) against the far ground it lands on."""
    cfg = _cfg()
    mapping = _variant_palette(variant)
    far = flip_palette(mapping, cfg)
    far_ground = far["surface_0"]
    for field in _TEXT_FIELDS:
        if field in far:
            ratio = contrast_ratio(far[field], far_ground)
            assert ratio >= cfg.aa_floor - 0.01, f"{variant}.{field}: {ratio:.2f} < AA on far ground"


@pytest.mark.parametrize("variant", [v for v, _, _ in _CLASSIFIER_TABLE])
def test_near_face_text_roles_meet_aa(variant: str) -> None:
    """The authored near face already clears AA (the plates ship AA-clean)."""
    cfg = _cfg()
    mapping = _variant_palette(variant)
    near_ground = str(mapping["surface_0"])
    for field in ("ink", "accent"):
        ratio = contrast_ratio(str(mapping[field]), near_ground)
        assert ratio >= cfg.aa_floor - 0.01, f"{variant}.{field}: {ratio:.2f} < AA on near ground"


# ── status never flips (structurally absent from the far dict) ─────────────


@pytest.mark.parametrize("variant", [v for v, _, _ in _CLASSIFIER_TABLE])
def test_status_structurally_absent_from_far_dict(variant: str) -> None:
    """No status/held field appears in a far dict — the never-flips invariant
    holds by construction, not by an equality check."""
    cfg = _cfg()
    far = flip_palette(_variant_palette(variant), cfg)
    for field, role in cfg.field_roles.items():
        if role in ("status", "held"):
            assert field not in far, f"{variant}: {field} (role={role}) leaked into far dict"


def test_status_hexes_identical_across_faces() -> None:
    """The semantic trio is byte-equal on near and far (green means pass on both).

    Because status fields are absent from the far dict, the near value holds —
    this test reads the near mapping and confirms the far dict does not redefine
    the status vars.
    """
    cfg = _cfg()
    for variant, _, _ in _CLASSIFIER_TABLE:
        far = flip_palette(_variant_palette(variant), cfg)
        assert "accent_signal" not in far
        assert "accent_warning" not in far
        assert "accent_error" not in far


def test_held_communication_palette_absent_from_far() -> None:
    """diagram_flow / receipt_ramp are genome-invariant — never in the far dict."""
    cfg = _cfg()
    far = flip_palette(_variant_palette("porcelain"), cfg)
    assert "diagram_flow" not in far
    assert "receipt_ramp" not in far


def test_twin_overrides_hook_ships_empty_but_honored() -> None:
    """The authored-override hook is checked first and honored when present.

    Ships empty on the genome (no entries), so the computed far dict is used
    verbatim; a synthetic override on a non-status field is applied last.
    """
    cfg = _cfg()
    mapping = _variant_palette("porcelain")
    baseline = flip_palette(mapping, cfg)
    mapping_with_override = {**mapping, "twin_overrides": {"porcelain": {"ink": "#ABCDEF"}}}
    overridden = flip_palette(mapping_with_override, cfg)
    assert baseline["ink"] != "#ABCDEF"
    assert overridden["ink"] == "#ABCDEF"


def test_twin_override_cannot_resurrect_status() -> None:
    """An override on a status field is ignored — status never flips, period."""
    cfg = _cfg()
    mapping = {**_variant_palette("porcelain"), "twin_overrides": {"porcelain": {"accent_signal": "#FF0000"}}}
    far = flip_palette(mapping, cfg)
    assert "accent_signal" not in far


# ── identity-hue fields flip together (the prototype's label==signal rule) ──


@pytest.mark.parametrize("variant", [v for v, _, _ in _CLASSIFIER_TABLE])
def test_identity_hue_fields_flip_identically_to_accent(variant: str) -> None:
    """label_text / glyph_inner carry the accent hue, so they flip to the same
    far value as `accent` — the twin prototypes prove --dna-label-text ==
    --dna-signal on the far face. A field carrying the identity hue that flipped
    to a different value would split the variant's identity across one artifact.
    """
    cfg = _cfg()
    mapping = _variant_palette(variant)
    far = flip_palette(mapping, cfg)
    # only assert for fields that actually equal the accent on the near face
    for field in ("label_text", "glyph_inner"):
        if str(mapping.get(field)) == str(mapping["accent"]):
            assert far[field] == far["accent"], f"{variant}.{field} split from accent"


# ── on-accent solves vs the far accent, shadow stays dark ──────────────────


def test_on_accent_solves_against_far_accent_not_ground() -> None:
    """ink_on_accent must be legible ON the far accent chip, not the far page."""
    cfg = _cfg()
    mapping = _variant_palette("porcelain")
    far = flip_palette(mapping, cfg)
    assert "ink_on_accent" in far
    assert contrast_ratio(far["ink_on_accent"], far["accent"]) >= cfg.aa_floor - 0.5


def test_shadow_stays_dark_on_far_face() -> None:
    """The drop-shadow tint never brightens — a shadow is dark on both faces."""
    cfg = _cfg()
    far = flip_palette(_variant_palette("porcelain"), cfg)
    if "shadow_color" in far:
        assert _oklch(far["shadow_color"])[0] <= 0.35


def test_border_rgba_alpha_held() -> None:
    """An rgba() border re-derives from the far ink but keeps the authored alpha."""
    cfg = _cfg()
    far = flip_palette(_variant_palette("porcelain"), cfg)
    # primer border_tint is rgba(...,0.12) on porcelain
    assert "border_tint" in far
    assert far["border_tint"].startswith("rgba(")
    assert far["border_tint"].rstrip(") ").endswith("0.12")


# ── resolve_surface: allowlist + completeness + precedence ─────────────────


def test_resolve_surface_plate_short_circuits() -> None:
    """Plate on any frame is fine — no allowlist or completeness check."""
    cfg = _cfg()
    out = resolve_surface(SurfaceSpec(), {}, "badge", cfg)
    assert out.ground is Ground.OPAQUE and out.palette is PaletteMode.FIXED


def test_resolve_surface_rejects_unsupported_frame() -> None:
    """inlay/twin on a non-allowlisted frame raises SPEC_INVALID."""
    cfg = _cfg()
    inlay = SurfaceSpec(ground=Ground.BARE, palette=PaletteMode.ADAPTIVE)
    with pytest.raises(HwError) as exc:
        resolve_surface(inlay, _variant_palette("porcelain"), "chart", cfg)
    assert exc.value.code is HwErrorCode.SPEC_INVALID


def test_resolve_surface_rejects_incomplete_palette() -> None:
    """A palette missing a required role field fails loud (supply-side gate)."""
    cfg = _cfg()
    twin = SurfaceSpec(ground=Ground.OPAQUE, palette=PaletteMode.ADAPTIVE)
    with pytest.raises(HwError) as exc:
        resolve_surface(twin, {"surface_0": "#fff"}, "matrix", cfg)  # no ink/accent
    assert exc.value.code is HwErrorCode.SPEC_INVALID


def test_resolve_surface_precedence_explicit_over_embedded() -> None:
    """An explicit request wins over an IR-embedded surface."""
    cfg = _cfg()
    explicit = SurfaceSpec(ground=Ground.BARE, palette=PaletteMode.ADAPTIVE)
    embedded = SurfaceSpec(ground=Ground.OPAQUE, palette=PaletteMode.ADAPTIVE)
    out = resolve_surface(explicit, _variant_palette("porcelain"), "matrix", cfg, embedded=embedded)
    assert out.ground is Ground.BARE


def test_resolve_surface_falls_back_to_embedded() -> None:
    """With no explicit request, the IR-embedded surface is used."""
    cfg = _cfg()
    embedded = SurfaceSpec(ground=Ground.OPAQUE, palette=PaletteMode.ADAPTIVE)
    out = resolve_surface(None, _variant_palette("porcelain"), "matrix", cfg, embedded=embedded)
    assert out.palette is PaletteMode.ADAPTIVE


# ── surface_from_props bridge ──────────────────────────────────────────────


def test_surface_from_props_plate_is_none() -> None:
    """The plate default maps to None so the payload stays byte-identical."""
    assert surface_from_props("", "", "") is None
    assert surface_from_props("opaque", "fixed", "") is None


def test_surface_from_props_inlay_twin() -> None:
    inlay = surface_from_props("bare", "adaptive", "")
    assert inlay is not None and inlay.ground is Ground.BARE
    twin = surface_from_props("opaque", "adaptive", "")
    assert twin is not None and twin.palette is PaletteMode.ADAPTIVE


def test_surface_from_props_face() -> None:
    face = surface_from_props("opaque", "adaptive", "light")
    assert face is not None and face.face == "light"


def test_surface_from_props_trap_raises() -> None:
    """bare + fixed is the trap — rejected by the SurfaceSpec validator."""
    with pytest.raises(ValueError, match="trap corner"):
        surface_from_props("bare", "fixed", "")


# ── native_palette (the un-flipped counterpart used for the normalized swap) ─


@pytest.mark.parametrize("variant", [v for v, _, _ in _CLASSIFIER_TABLE])
def test_native_palette_is_pure_passthrough(variant: str) -> None:
    """native_palette reads raw genome values, no math — same fields flip_palette
    would touch, held/status excluded, but every value is byte-identical to the
    source mapping (unlike flip_palette, which recomputes each one)."""
    cfg = _cfg()
    mapping = _variant_palette(variant)
    native = native_palette(mapping, cfg)
    assert native  # every primer variant carries ground/figure/accent fields
    for field, value in native.items():
        assert value == mapping[field], f"{variant}.{field}: native_palette mutated a raw value"


@pytest.mark.parametrize("variant", [v for v, _, _ in _CLASSIFIER_TABLE])
def test_native_palette_and_flip_palette_share_field_shape(variant: str) -> None:
    """native_palette and flip_palette touch the exact same field set — the
    normalized swap (compose/context.py) trades one for the other wholesale."""
    cfg = _cfg()
    mapping = _variant_palette(variant)
    assert set(native_palette(mapping, cfg)) == set(flip_palette(mapping, cfg))


def test_native_palette_excludes_status_and_held() -> None:
    """Same never-flips invariant as flip_palette: status/held never appear."""
    cfg = _cfg()
    native = native_palette(_variant_palette("porcelain"), cfg)
    assert "accent_signal" not in native
    assert "diagram_flow" not in native


# ── overlay_face_palette (two-sink patch: top level + variant_overrides) ────


def test_overlay_face_palette_patches_top_level() -> None:
    genome = {"ink": "#111111", "surface_0": "#FFFFFF", "variant_overrides": {}}
    patched = overlay_face_palette(genome, {"ink": "#ABCDEF"}, "")
    assert patched["ink"] == "#ABCDEF"
    assert patched["surface_0"] == "#FFFFFF"  # untouched field survives


def test_overlay_face_palette_patches_variant_overrides_sub_dict() -> None:
    """A field the variant override ALSO carries must win at both sinks — the
    inline style= attribute (sourced from variant_overrides) wins the cascade
    over the stylesheet (sourced from the top level), so a patch that misses
    this sink would silently leak the untouched value on a plate render."""
    genome = {
        "label_text": "#1D4ED8",
        "variant_overrides": {"porcelain": {"label_text": "#1D4ED8", "surface_0": "#F5F8FF"}},
    }
    patched = overlay_face_palette(genome, {"label_text": "#FF00FF"}, "porcelain")
    assert patched["label_text"] == "#FF00FF"
    assert patched["variant_overrides"]["porcelain"]["label_text"] == "#FF00FF"
    # a field the face palette doesn't carry stays as authored
    assert patched["variant_overrides"]["porcelain"]["surface_0"] == "#F5F8FF"


def test_overlay_face_palette_never_mutates_input() -> None:
    """variant_overrides is a shared config object — patching must copy, never
    mutate, or the flip would leak into later same-variant plate renders."""
    shared_overrides = {"noir": {"ink": "#E5E5E5"}}
    genome = {"ink": "#E5E5E5", "variant_overrides": shared_overrides}
    overlay_face_palette(genome, {"ink": "#000000"}, "noir")
    assert shared_overrides["noir"]["ink"] == "#E5E5E5", "overlay_face_palette mutated the shared config"
    assert genome["ink"] == "#E5E5E5", "overlay_face_palette mutated the input genome"


def test_overlay_face_palette_empty_variant_is_a_no_op_on_overrides() -> None:
    genome = {"ink": "#111111", "variant_overrides": {"x": {"ink": "#111111"}}}
    patched = overlay_face_palette(genome, {"ink": "#ABCDEF"}, "")
    assert patched["ink"] == "#ABCDEF"
    assert patched["variant_overrides"] == {"x": {"ink": "#111111"}}


# ── adaptive_css shape (matches the authored prototype) ────────────────────


def test_adaptive_css_shape() -> None:
    """The stylesheet is scoped to #id with color-scheme + a dark @media block.

    ``direction`` is gone from the signature (the signature normalization) —
    the far scope is ALWAYS ``prefers-color-scheme: dark``; the caller decides
    which face's declarations to pass as ``near_decls``/``far`` (see
    ``compose/context.py:_apply_adaptive_css``).
    """
    cfg = _cfg()
    mapping = _variant_palette("porcelain")
    far = flip_palette(mapping, cfg)
    css = adaptive_css(mapping, far, "art1", near_decls="--dna-surface:#F5F8FF;")
    assert "#art1 { color-scheme: light dark;" in css
    assert "@media (prefers-color-scheme: dark) { #art1 {" in css
    # near declarations present, far block re-declares the flipped surface var
    assert "--dna-surface:#F5F8FF;" in css
    assert "--dna-surface:" in css.split("@media", 1)[1]


def test_adaptive_css_far_block_omits_status_and_color_scheme() -> None:
    """The far @media block flips only figure/ground/accent — no color-scheme decl."""
    cfg = _cfg()
    mapping = _variant_palette("porcelain")
    far = flip_palette(mapping, cfg)
    css = adaptive_css(mapping, far, "art1", near_decls="")
    # Isolate the declaration body inside the far block's `#art1 { ... }`.
    far_block = css.split("@media", 1)[1]
    far_body = far_block.split("#art1 {", 1)[1].rsplit("}", 2)[0]
    assert "--dna-signal:" in far_body  # accent flips in the far block
    # color-scheme is a near-block-only declaration (never re-declared far).
    assert "color-scheme:" not in far_body


def test_adaptive_css_two_artifacts_disjoint_selectors() -> None:
    """Two adaptive artifacts scope to distinct ids — no clobber on one page."""
    cfg = _cfg()
    mapping = _variant_palette("porcelain")
    far = flip_palette(mapping, cfg)
    css_a = adaptive_css(mapping, far, "aaa", near_decls="")
    css_b = adaptive_css(mapping, far, "bbb", near_decls="")
    assert "#aaa {" in css_a and "#bbb {" not in css_a
    assert "#bbb {" in css_b and "#aaa {" not in css_b


# ── content-address distinctness (payload stamping) ────────────────────────


def _matrix_spec_dict() -> dict[str, object]:
    spec = MatrixSpec(
        title="T",
        columns=[MatrixColumn(id="a", label="A", role="label"), MatrixColumn(id="b", label="B", role="data")],
        rows=[MatrixRow(label="r", cells=[MatrixCell(value="x")])],
    )
    return spec.model_dump()


def _compose_id(**surface_kw: str) -> str:
    cs = ComposeSpec(type="matrix", genome_id="primer", variant="porcelain", matrix=_matrix_spec_dict(), **surface_kw)
    env = extract_envelope(compose(cs).svg)
    return str(env.get("id"))


def test_surface_absent_from_payload_by_default() -> None:
    """A surface-less MatrixSpec omits `surface` under exclude_defaults."""
    dumped = MatrixSpec(**_matrix_spec_dict()).model_dump(mode="json", exclude_defaults=True)
    assert "surface" not in dumped


def test_plate_inlay_twin_faces_distinct_addresses() -> None:
    """plate ≠ inlay ≠ twin ≠ face-light ≠ face-dark — all five distinct."""
    ids = {
        "plate": _compose_id(),
        "inlay": _compose_id(ground="bare", palette="adaptive"),
        "twin": _compose_id(ground="opaque", palette="adaptive"),
        "face_light": _compose_id(ground="opaque", palette="adaptive", surface_face="light"),
        "face_dark": _compose_id(ground="opaque", palette="adaptive", surface_face="dark"),
    }
    assert len(set(ids.values())) == 5, ids


def test_stamp_surface_plate_leaves_ir_untouched() -> None:
    """stamp_surface returns the same IR (surface=None) for plate."""
    cfg = _cfg()
    spec = MatrixSpec(**_matrix_spec_dict())
    out = stamp_surface(spec, None, _variant_palette("porcelain"), "matrix", cfg)
    assert out.surface is None


def test_stamp_surface_non_plate_sets_surface() -> None:
    """stamp_surface copies the IR with the resolved surface for inlay/twin."""
    cfg = _cfg()
    spec = MatrixSpec(**_matrix_spec_dict())
    inlay = SurfaceSpec(ground=Ground.BARE, palette=PaletteMode.ADAPTIVE)
    out = stamp_surface(spec, inlay, _variant_palette("porcelain"), "matrix", cfg)
    assert out.surface is not None and out.surface.ground is Ground.BARE


# ── frame allowlist at the resolver boundary (universal enforcement) ───────


def test_badge_rejects_surface_props() -> None:
    """A surface prop on a non-allowlisted frame (badge) fails loud at resolve."""
    cs = ComposeSpec(type="badge", genome_id="primer", title="BUILD", value="passing", palette="adaptive")
    with pytest.raises(HwError) as exc:
        compose(cs)
    assert exc.value.code is HwErrorCode.SPEC_INVALID


def test_badge_plate_still_composes() -> None:
    """Plate (no surface props) is unaffected on every frame."""
    cs = ComposeSpec(type="badge", genome_id="primer", title="BUILD", value="passing")
    assert compose(cs).width > 0


# ── adaptive x flattening guard (relocated to formats.project by WB) ────────
# The guard's home is the format-projection path; it detects an adaptive artifact
# by the data-hw-adapt="adaptive" root attribute THIS workstream's template emits.
# These tests pin the WC-side contract: an adaptive render carries the marker and
# is rejected by every flattening format, while plate/face renders are not.


def test_adaptive_render_carries_marker() -> None:
    """An inlay/twin compose emits data-hw-adapt='adaptive' — the guard's signal."""
    inlay = compose(
        ComposeSpec(
            type="matrix",
            genome_id="primer",
            variant="porcelain",
            ground="bare",
            palette="adaptive",
            matrix=_matrix_spec_dict(),
        )
    )
    assert 'data-hw-adapt="adaptive"' in inlay.svg


@pytest.mark.parametrize("fmt", ["svg-static", "png", "webp"])
def test_adaptive_flatten_rejected_by_project(fmt: str) -> None:
    """Every flattening format rejects an adaptive artifact with a fix pointing at faces."""
    from hyperweave.formats import project

    adaptive_svg = compose(
        ComposeSpec(
            type="matrix",
            genome_id="primer",
            variant="porcelain",
            ground="opaque",
            palette="adaptive",
            matrix=_matrix_spec_dict(),
        )
    ).svg
    with pytest.raises(HwError) as exc:
        project(adaptive_svg, fmt)
    assert exc.value.code is HwErrorCode.SPEC_INVALID
    assert "face" in exc.value.fix.lower()


def test_adaptive_svg_format_not_rejected() -> None:
    """The live svg format keeps the adaptive artifact (no flattening)."""
    from hyperweave.formats import project

    adaptive_svg = compose(
        ComposeSpec(
            type="matrix",
            genome_id="primer",
            variant="porcelain",
            ground="opaque",
            palette="adaptive",
            matrix=_matrix_spec_dict(),
        )
    ).svg
    out = project(adaptive_svg, "svg")
    assert b"data-hw-adapt" in out.data


def test_face_render_flattens_fine() -> None:
    """A twin face carries data-hw-face (not data-hw-adapt) and rasterizes as a plain plate."""
    from hyperweave.formats import project

    face_svg = compose(
        ComposeSpec(
            type="matrix",
            genome_id="primer",
            variant="porcelain",
            ground="opaque",
            palette="adaptive",
            surface_face="dark",
            matrix=_matrix_spec_dict(),
        )
    ).svg
    assert 'data-hw-adapt="adaptive"' not in face_svg
    assert 'data-hw-face="dark"' in face_svg
    # svg-static flatten must succeed (no adaptive marker to trip the guard).
    out = project(face_svg, "svg-static")
    assert out.data


def test_plate_matrix_flattens_via_compose_surface() -> None:
    """End-to-end: a plate matrix projects to svg-static fine (no adaptive → no guard)."""
    from hyperweave.compose.surface import SpecEnvelope, compose_surface

    # primer now defaults to the adaptive "twin" surface when no surface
    # props are supplied — request an explicit plate (the subject here).
    env = SpecEnvelope(
        type="matrix",
        genome="primer",
        variant="porcelain",
        spec={**_matrix_spec_dict(), "ground": "opaque", "palette": "fixed"},
        format="svg-static",
    )
    out = compose_surface(env)
    assert out.svg and "var(--" not in out.svg
