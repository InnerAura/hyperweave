"""One genome gallery builder, driven entirely by genome config.

Four near-identical emitters used to live in the proofset generator — automata,
brutalist, primer and chrome each with its own ~150-line copy of "for every
variant, emit a badge row, a strip, a marquee, a divider, the five states".
They restated data the genome JSON already carries (the variant roster, the
dark/light substrate split, the per-variant phenomenology, the divider slugs),
and one of them said so out loud: *"if you add a brutalist variant, append here
too."* Adding a variant meant editing Python in three places and hoping.

Nothing factual is written here. The roster comes from ``cfg.variants``, the
substrate split from ``variant_overrides[v].substrate_kind``, the identity line
from ``cfg.variant_phenomenology``, the divider slugs from ``cfg.dividers``, the
icon shapes from the paradigm's ``icon.supported_shapes``, and every image link
from the artifact records themselves. What IS written here is document voice —
the prose introducing each gallery, which is editorial copy about the page, not
configuration the engine reads.

Adding a genome or a variant now takes zero edits to this file.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hyperweave.config.loader import load_genomes, load_paradigms
from hyperweave.core.enums import ArtifactStatus, BorderMotionId, Regime
from scripts.examples.manifest import Gallery
from scripts.examples.markdown import Doc
from scripts.examples.render import OUTPUTS, spec

if TYPE_CHECKING:
    from pathlib import Path

    from scripts.examples.manifest import Artifact

GENOMES_ROOT = OUTPUTS / "genomes"

# The state ladder every genome renders, in severity order.
STATES: tuple[ArtifactStatus, ...] = (
    ArtifactStatus.PASSING,
    ArtifactStatus.WARNING,
    ArtifactStatus.CRITICAL,
    ArtifactStatus.BUILDING,
    ArtifactStatus.OFFLINE,
)
# The three states a strip renders (a strip has no build/offline register).
STRIP_STATES: tuple[ArtifactStatus, ...] = (
    ArtifactStatus.ACTIVE,
    ArtifactStatus.WARNING,
    ArtifactStatus.CRITICAL,
)

# The repo the sample artifacts speak about. One subject across every genome so
# a reader comparing two galleries is comparing chromatics, not content.
SUBJECT = "eli64s/readme-ai"
SUBJECT_NAME = "readme-ai"
SUBJECT_METRICS = "STARS:12.4k,VERSION:v0.6.9,BUILD:passing"

# Document voice — the paragraph that opens each gallery. Editorial copy about
# the page, deliberately NOT in genome JSON: it describes what the reader is
# about to scroll through, and every factual number in the page is computed.
_PROSE: dict[str, tuple[str, str]] = {
    "brutalist": (
        "Brutalist — Substrate Matrix",
        "Concrete grammar: heavy rules, a solid ink register, and one accent per substrate. "
        "The dark monochromes are materials; the light scholars are functional roles.",
    ),
    "primer": (
        "Primer — Substrate Matrix",
        "The editorial genome: paper and ink first, chromatics second. Its badge indicator is a "
        "state-KEYED animated mark (`status-glyph` — ping / throb / shake) rather than a geometric "
        "shape, so the state register reads as behavior instead of colour alone.",
    ),
    "chrome": (
        "Chrome — Material Identity Matrix",
        "The dark-envelope flagship: midnight gradient, slate seam, sparing warm-metal accents. "
        "Each variant changes the **material identity** of the envelope while the structural chrome "
        "(envelope + well + rim + rhythm) stays put. Every envelope is hex-baked into its gradient "
        "stops and is therefore scheme-stable — light-mode CSS variables do not invert it.",
    ),
    "automata": (
        "Automata — Cellular Tone Matrix",
        "The cellular paradigm: solo tones plus a request-time pairing grammar that composes any "
        "two of them into a bifamily strip or divider. Use `?variant=primary&pair=secondary` to "
        "pair, `?variant=primary` alone for solo.",
    ),
}

# The pairings the automata gallery showcases. A sample of the combinatorial
# surface, with the reason each pair is interesting — the grammar accepts any
# two tones, so the count is illustrative rather than exhaustive.
_PAIRINGS: tuple[tuple[str, str, str], ...] = (
    ("teal", "violet", "the bifamily flagship"),
    ("bone", "steel", "neutral on neutral"),
    ("cobalt", "magenta", "warm/cool tension"),
    ("jade", "crimson", "complementary wheel opposites"),
    ("violet", "amber", "purple and gold"),
    ("solar", "abyssal", "thermal opposites"),
    ("toxic", "jade", "adjacent greens"),
    ("crimson", "steel", "warm signal on cool substrate"),
    ("magenta", "bone", "saturated on neutral"),
    ("amber", "cobalt", "warm/cool inverted"),
)


def _substrate_of(cfg: Any, variant: str) -> str:
    """A variant's substrate kind, or "" when the genome declares no axis."""
    return str((cfg.variant_overrides.get(variant) or {}).get("substrate_kind", ""))


def _icon_shapes(cfg: Any) -> list[str]:
    """Every shape the genome's icon paradigm declares.

    Data-driven so a paradigm supporting both circle and square can never
    silently document just one.
    """
    paradigm = load_paradigms().get(cfg.paradigms.get("icon", "default"))
    return list(paradigm.icon.supported_shapes) if paradigm else []


def _supports_compact(cfg: Any) -> bool:
    """Whether the genome's badge paradigm declares compact geometry.

    Compact is paradigm GEOMETRY, not genome chromatics: a paradigm without
    compact tuning renders a misshapen 20px badge, so the gallery must not ask
    for one. Declared by an explicit compact glyph size, a compact glyph ratio,
    or a compact frame height that differs from the default.
    """
    paradigm = load_paradigms().get(cfg.paradigms.get("badge", "default"))
    if paradigm is None:
        return False
    badge = paradigm.badge
    return (
        badge.glyph_size_compact > 0
        or badge.glyph_size_compact_ratio > 0
        or badge.frame_height_compact != badge.frame_height
    )


def _motions(cfg: Any) -> list[str]:
    """Border motions the genome declares itself compatible with."""
    compatible = set(cfg.compatible_motions)
    return [m.value for m in BorderMotionId if m.value in compatible]


def build_gallery(genome: str) -> Gallery:
    """Declare every static artifact of one genome's gallery.

    Declaration order is reading order in the emitted document.
    """
    cfg = load_genomes()[genome]
    title, _prose = _PROSE.get(genome, (genome.title(), ""))
    gallery = Gallery(genome, GENOMES_ROOT / genome, title=title)
    compact = _supports_compact(cfg)
    shapes = _icon_shapes(cfg)

    # ── base: the genome without a variant ──
    gallery.add("base/badge.svg", spec("badge", genome, "BUILD", "passing", "passing", "github"))
    gallery.add(
        "base/strip.svg",
        spec("strip", genome, SUBJECT_NAME, SUBJECT_METRICS, "active", "github", connector_data={"repo_slug": SUBJECT}),
    )
    if len(shapes) > 1:
        for shape in shapes:
            gallery.add(f"base/icon_{shape}.svg", spec("icon", genome, glyph="github", shape=shape))
    else:
        gallery.add("base/icon.svg", spec("icon", genome, glyph="github"))
    for slug in cfg.dividers:
        gallery.add(f"base/divider_{slug}.svg", spec("divider", genome, divider_variant=slug))
    gallery.add("base/marquee.svg", spec("marquee", genome, _marquee_text(genome)))

    # ── variants: the full suite per chromatic slug ──
    for variant in cfg.variants:
        _add_variant_suite(gallery, genome, variant, compact=compact, shapes=shapes, dividers=cfg.dividers)

    # ── pairings: the bifamily grammar (genomes with a pair axis) ──
    if genome == "automata":
        for primary, secondary in ((p, s) for p, s, _why in _PAIRINGS):
            slug = f"{primary}-{secondary}"
            gallery.add(
                f"pairings/strip_{slug}.svg",
                spec(
                    "strip",
                    genome,
                    SUBJECT_NAME,
                    SUBJECT_METRICS,
                    "passing",
                    "github",
                    variant=primary,
                    pair=secondary,
                    connector_data={"repo_slug": SUBJECT},
                ),
            )
            gallery.add(
                f"pairings/divider_dissolve_{slug}.svg",
                spec("divider", genome, divider_variant="dissolve", variant=primary, pair=secondary),
            )

    # ── states / policy lanes / border motions: the behavioral registers ──
    for status in STATES:
        gallery.add(f"states/badge_{status}.svg", spec("badge", genome, "BUILD", status.value, status.value, "github"))
    for status in STRIP_STATES:
        gallery.add(
            f"states/strip_{status}.svg",
            spec(
                "strip",
                genome,
                SUBJECT_NAME,
                "STARS:12.4k,COVERAGE:94%",
                status.value,
                "github",
                connector_data={"repo_slug": SUBJECT},
            ),
        )
    for regime in (Regime.NORMAL, Regime.UNGOVERNED):
        gallery.add(
            f"policy-lanes/badge_{regime}.svg",
            spec("badge", genome, "BUILD", "passing", "passing", "github", regime=regime.value),
        )
    # Border motions are non-CIM (SMIL stroke-dashoffset and friends), so the
    # permissive regime is what lets them render instead of downgrading to
    # static — the artifact under review is the motion, not the policy.
    for motion in _motions(cfg):
        gallery.add(
            f"border-motions/badge_{motion}.svg",
            spec(
                "badge", genome, "BUILD", "passing", "active", "github", motion=motion, regime=Regime.PERMISSIVE.value
            ),
        )
        gallery.add(
            f"border-motions/strip_{motion}.svg",
            spec(
                "strip",
                genome,
                SUBJECT_NAME,
                "STARS:12.4k,FORKS:1.2k",
                "active",
                motion=motion,
                regime=Regime.PERMISSIVE.value,
                connector_data={"repo_slug": SUBJECT},
            ),
        )
    return gallery


def _marquee_text(genome: str) -> str:
    """Marquee copy in the genome's own voice, pipe-separated into tokens."""
    voices = {
        "chrome": "HYPERWEAVE|CHROME HORIZON|LIVING SVG ARTIFACTS",
        "brutalist": "LIVING ARTIFACTS|SELF-CONTAINED SVG|AGENT INTERFACES",
        "automata": "HYPERWEAVE|CELLULAR-AUTOMATA|LIVING ARTIFACTS|AGENT-READABLE|COMPOSITIONAL",
    }
    return voices.get(genome, "HYPERWEAVE|LIVING ARTIFACTS")


def _add_variant_suite(
    gallery: Gallery,
    genome: str,
    variant: str,
    *,
    compact: bool,
    shapes: list[str],
    dividers: list[str],
) -> None:
    """The per-variant artifact suite: badges, icons, strip, marquee, dividers."""
    v = variant
    gallery.add(
        f"variants/badge_pypi_{v}_default.svg",
        spec("badge", genome, "PYPI", "v0.4.2", "active", "python", variant=v),
    )
    if compact:
        gallery.add(
            f"variants/badge_pypi_{v}_compact.svg",
            spec("badge", genome, "PYPI", "v0.4.2", "active", "python", variant=v, size="compact"),
        )
    for status in STATES:
        gallery.add(
            f"variants/badge_{status}_{v}.svg",
            spec("badge", genome, "BUILD", status.value, status.value, "github", variant=v),
        )
        if compact:
            gallery.add(
                f"variants/badge_{status}_{v}_compact.svg",
                spec("badge", genome, "BUILD", status.value, status.value, "github", variant=v, size="compact"),
            )
    if len(shapes) > 1:
        for shape in shapes:
            gallery.add(
                f"variants/icon_github_{v}_{shape}.svg",
                spec("icon", genome, glyph="github", shape=shape, variant=v),
            )
    else:
        gallery.add(f"variants/icon_github_{v}.svg", spec("icon", genome, glyph="github", variant=v))
    gallery.add(
        f"variants/strip_{v}.svg",
        spec(
            "strip",
            genome,
            SUBJECT_NAME,
            SUBJECT_METRICS,
            "passing",
            "github",
            variant=v,
            connector_data={"repo_slug": SUBJECT},
        ),
    )
    gallery.add(f"variants/marquee_{v}.svg", spec("marquee", genome, _marquee_text(genome), variant=v))
    for slug in dividers:
        gallery.add(
            f"variants/divider_{slug}_{v}.svg",
            spec("divider", genome, divider_variant=slug, variant=v),
        )


# ── The document ─────────────────────────────────────────────────────────────


def register_live_cards(gallery: Gallery, written: list[Path]) -> int:
    """Adopt the live stats/chart cards a network pass already rendered.

    They are this genome's artifacts — its `stats` and `chart` paradigms, the
    two frames the gallery otherwise never showed — but they cannot be DECLARED
    ahead of time: which ones exist depends on what the connectors returned, and
    a chart whose REST/GraphQL cross-check disagreed is deliberately absent
    rather than wrong. So the writer hands over what it wrote.

    Marked ``prerendered``: the sweep leaves their bytes alone, because
    re-rendering would re-fetch and compare two different moments.
    """
    adopted = 0
    for path in written:
        try:
            rel = path.relative_to(gallery.root)
        except ValueError:
            continue
        if path.suffix != ".svg" or rel.parts[0] not in ("data-cards", "variants", "stress"):
            continue
        if rel.parts[0] == "variants" and not path.name.startswith(("stats_", "chart_")):
            continue  # the variant suite is declared; only the live cards land here
        gallery.add(
            str(rel),
            spec("stats" if path.name.startswith("stats") else "chart", gallery.name),
            prerendered=True,
        )
        adopted += 1
    return adopted


def emit(gallery: Gallery, *, addenda: list[str] | None = None) -> Path:
    """Compose the gallery's README from its artifact records.

    Every image link is read off a record, so the page cannot cite a file the
    gallery did not render, and a renamed artifact moves the link with it.

    ``addenda`` are pre-rendered markdown blocks for live-data sections whose
    content depends on what a connector actually returned — they cannot be
    declared ahead of the fetch, so they arrive already built and land before
    the cross-reference.
    """
    genome = gallery.name
    cfg = load_genomes()[genome]
    _title, prose = _PROSE.get(genome, (genome.title(), ""))
    doc = Doc(f"HyperWeave {gallery.title}")
    doc.para(prose)

    substrates = {v: _substrate_of(cfg, v) for v in cfg.variants}
    split = sorted({s for s in substrates.values() if s})
    roster = _roster_sentence(cfg, substrates, split)
    doc.para(roster)
    doc.para(
        "Every variant below renders the full suite: badge (default"
        + (" + compact" if _supports_compact(cfg) else "")
        + f"), {_shape_phrase(_icon_shapes(cfg))}, strip, marquee, "
        + _divider_phrase(cfg.dividers)
        + ", and the five badge states."
    )
    doc.rule()

    if split:
        # A genome with a substrate axis reads as two families, not one list —
        # the dark/light difference is the largest thing about these variants.
        for kind in split:
            members = [v for v in cfg.variants if substrates[v] == kind]
            doc.h2(f"{kind.title()} substrates ({len(members)})")
            for variant in members:
                _variant_block(doc, gallery, cfg, genome, variant)
    else:
        for variant in cfg.variants:
            _variant_block(doc, gallery, cfg, genome, variant)

    if genome == "automata":
        _pairings_section(doc, gallery)

    _register_sections(doc, gallery, cfg)
    _data_card_section(doc, gallery)
    for block in addenda or []:
        doc.raw(block.rstrip())
    _cross_reference(doc, genome)

    path = gallery.root / "README.md"
    doc.write(path)
    return path


def _roster_sentence(cfg: Any, substrates: dict[str, str], split: list[str]) -> str:
    """The variant roster, counted and named from config."""
    total = len(cfg.variants)
    if split:
        parts = [f"{sum(1 for s in substrates.values() if s == kind)} {kind}" for kind in split]
        breakdown = " + ".join(parts)
        return f"**{total} variants** ({breakdown}): " + " · ".join(f"`{v}`" for v in cfg.variants) + "."
    return f"**{total} variants**: " + " · ".join(f"`{v}`" for v in cfg.variants) + "."


def _shape_phrase(shapes: list[str]) -> str:
    if len(shapes) > 1:
        return f"icons ({' + '.join(shapes)})"
    return "icon"


def _divider_phrase(dividers: list[str]) -> str:
    if not dividers:
        return "no genome divider"
    named = " + ".join(f"`{d}`" for d in dividers)
    return f"{'dividers' if len(dividers) > 1 else 'divider'} ({named})"


def _bare_url_variant(cfg: Any) -> str:
    """Which variant a bare ``{genome}.static`` URL renders, or "" if undecidable.

    Two mechanisms reach the same answer, and reading only the first is what
    made this document drop a true line:

    * ``flagship_variant`` set — the resolver applies that variant by name when
      the caller supplies none (brutalist celadon, primer porcelain).
    * ``flagship_variant`` empty — then the variant declaring NO chromatic
      override IS the base palette, so a bare URL already renders it. Chrome's
      ``horizon`` is exactly this: it has no ``variant_overrides`` entry at all,
      so `chrome.static` and `chrome.static?variant=horizon` paint the same
      envelope and differ only in whether the artifact NAMES its variant.

    Derived rather than declared, so a genome that later gives its flagship a
    real override stops claiming this on its own. Silent when it cannot tell:
    automata carries its tones in ``variant_tones``, so no single variant is
    distinguishable as the base and the document says nothing instead of
    guessing.
    """
    if cfg.flagship_variant:
        return str(cfg.flagship_variant)
    unoverridden = [v for v in cfg.variants if not cfg.variant_overrides.get(v)]
    return unoverridden[0] if len(unoverridden) == 1 else ""


def _variant_block(doc: Doc, gallery: Gallery, cfg: Any, genome: str, variant: str) -> None:
    """One variant's section: identity line, then its artifacts in rows."""
    doc.h3(f"`?variant={variant}`")
    identity = cfg.variant_phenomenology.get(variant, "")
    if variant and variant == _bare_url_variant(cfg):
        identity = f"{identity} (flagship — a bare `{genome}.static` URL renders this)".lstrip(" ")
    doc.italic(identity)

    shapes = _icon_shapes(cfg)
    icons = (
        [gallery.get(f"variants/icon_github_{variant}_{s}.svg") for s in shapes]
        if len(shapes) > 1
        else [gallery.get(f"variants/icon_github_{variant}.svg")]
    )
    badges = [gallery.get(f"variants/badge_pypi_{variant}_default.svg")]
    if _supports_compact(cfg):
        badges.append(gallery.get(f"variants/badge_pypi_{variant}_compact.svg"))
    doc.row([*badges, *icons])
    doc.image(gallery.get(f"variants/strip_{variant}.svg"))
    doc.image(gallery.get(f"variants/marquee_{variant}.svg"))
    for slug in cfg.dividers:
        doc.image(gallery.get(f"variants/divider_{slug}_{variant}.svg"))
    for rel in (f"variants/stats_{variant}.svg", f"variants/chart_stars_{variant}.svg"):
        card = _optional(gallery, rel)
        if card is not None:
            doc.image(card)
    doc.row([gallery.get(f"variants/badge_{s}_{variant}.svg") for s in STATES])
    doc.rule()


def _optional(gallery: Gallery, rel: str) -> Artifact | None:
    """A record that exists only when a live fetch produced it.

    The live stats and star-chart cards are deliberately skipped when a
    connector cross-check disagrees — shipping no card is honest, shipping a
    made-up one is not. This asks the manifest, never the filesystem: the
    document still describes exactly what was rendered.
    """
    try:
        return gallery.get(rel)
    except KeyError:
        return None


def _pairings_section(doc: Doc, gallery: Gallery) -> None:
    doc.h2("Pairings")
    doc.para(
        "The pairing grammar (`?variant=primary&pair=secondary`) composes any two solo tones into",
        "bifamily strips and dividers. Other frame types silently ignore the pair and render the",
        "primary tone solo. These sample the surface; every ordered pair works the same way.",
    )
    for primary, secondary, why in _PAIRINGS:
        slug = f"{primary}-{secondary}"
        doc.h3(f"`?variant={primary}&pair={secondary}`")
        doc.italic(why)
        doc.image(gallery.get(f"pairings/strip_{slug}.svg"))
        doc.image(gallery.get(f"pairings/divider_dissolve_{slug}.svg"))


def _register_sections(doc: Doc, gallery: Gallery, cfg: Any) -> None:
    """Base frames and the three behavioral registers, at the foot of the page.

    These are genome-level rather than per-variant, so they read once rather
    than repeating under every chromatic slug.
    """
    doc.h2("Base frames")
    doc.para("The genome with no variant named — what a bare `{genome}.static` URL renders.")
    shapes = _icon_shapes(cfg)
    base_icons = (
        [gallery.get(f"base/icon_{s}.svg") for s in shapes] if len(shapes) > 1 else [gallery.get("base/icon.svg")]
    )
    doc.row([gallery.get("base/badge.svg"), *base_icons])
    doc.image(gallery.get("base/strip.svg"))
    doc.image(gallery.get("base/marquee.svg"))
    for slug in cfg.dividers:
        doc.image(gallery.get(f"base/divider_{slug}.svg"))

    doc.h2("States")
    doc.para("The badge state ladder, then the three states a strip carries.")
    doc.row([gallery.get(f"states/badge_{s}.svg") for s in STATES])
    for status in STRIP_STATES:
        doc.image(gallery.get(f"states/strip_{status}.svg"))

    doc.h2("Policy lanes")
    doc.para(
        "`normal` governs motion and metadata to the platform's limits; `ungoverned` lifts them.",
        "The same badge under each.",
    )
    doc.row([gallery.get(f"policy-lanes/badge_{r}.svg") for r in (Regime.NORMAL, Regime.UNGOVERNED)])

    motions = _motions(cfg)
    if motions:
        doc.h2("Border motions")
        doc.para(
            f"The {len(motions)} motions this genome declares itself compatible with, rendered under the",
            "permissive regime — border motion is non-CIM, so the normal regime would downgrade it to",
            "static and there would be nothing to review.",
        )
        for motion in motions:
            doc.h3(f"`{motion}`")
            doc.image(gallery.get(f"border-motions/badge_{motion}.svg"))
            doc.image(gallery.get(f"border-motions/strip_{motion}.svg"))


def _data_card_section(doc: Doc, gallery: Gallery) -> None:
    """The live-data frames: `stats` cards and `chart` histories.

    Every genome declares both paradigms, so a gallery without them was showing
    eight of this genome's ten frame types and calling it the full suite.
    Absent when a run had no network — stated, so an empty section is never
    mistaken for a genome that cannot render them.
    """
    cards = [a for a in gallery if a.rel.startswith("data-cards/")]
    if not cards:
        doc.h2("Data cards")
        doc.para(
            "No live cards this run — the `stats` and `chart` frames bind real connector data, and",
            "this pass had no reachable network. They are skipped rather than filled with invented",
            "numbers.",
        )
        return
    doc.h2(f"Data cards ({len(cards)})")
    doc.para(
        "The two live-data frames. `stats` is a profile card, `chart` a star or download history —",
        "both bound to real connector values, so what appears here is what the providers actually",
        "returned. A chart whose REST and GraphQL readings disagreed is absent rather than wrong.",
    )
    for artifact in cards:
        doc.h3(f"`{artifact.rel.rsplit('/', 1)[-1].removesuffix('.svg')}`")
        doc.image(artifact)


def _cross_reference(doc: Doc, genome: str) -> None:
    others = [g for g in sorted(load_genomes()) if g != genome and load_genomes()[g].variants]
    doc.h2("Cross-reference")
    doc.bullets(
        [
            "[Proofset index](../../README.md) — every gallery, plus the parity summary",
            "[Matrices](../../matrices/README.md) — the matrix frame's specimens and boundary suite",
            *[f"[{g}](../{g}/README.md) — {len(load_genomes()[g].variants)} variants" for g in others],
        ]
    )


def build_all() -> dict[str, Gallery]:
    """Every genome that has a gallery, keyed by genome id.

    A genome with no variants (raw — receipts only) has no chromatic matrix to
    show, so it gets no gallery rather than an empty one.
    """
    return {gid: build_gallery(gid) for gid, cfg in sorted(load_genomes().items()) if cfg.variants}
