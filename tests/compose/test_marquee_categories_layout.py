"""v0.3.12 marquee upgrade — category grouping, per-cell state, role-based hero,
module-vs-ribbon layout dispatch, content-aware geometry, uniform reading rate.

Every test here drives the REAL compose + measurement pipeline end-to-end (no
pre-baked position fixtures) so a hardcoded coordinate or a measurement
regression would fail rather than hide. Marquee state/category/hero are inferred
from the existing ?data= tokens — zero new request params.
"""

from __future__ import annotations

import re

from hyperweave.compose.engine import compose
from hyperweave.connectors.data_tokens import ResolvedToken
from hyperweave.core.models import ComposeSpec


def _live(label: str, value: str, metric: str) -> ResolvedToken:
    return ResolvedToken(kind="live", label=label, value=value, ttl=0, metric=metric)


def _kv(label: str, value: str) -> ResolvedToken:
    return ResolvedToken(kind="kv", label=label, value=value, ttl=0)


def _marquee(genome: str, tokens: list[ResolvedToken], variant: str = "") -> str:
    spec = ComposeSpec(type="marquee", genome_id=genome, variant=variant, data_tokens=tokens)
    return compose(spec).svg


def _module_value_positions(svg: str) -> dict[str, int]:
    """Map each module VALUE string → its x (module values render at y=35)."""
    out: dict[str, int] = {}
    for x, value in re.findall(r'<text x="(\d+)" y="35"[^>]*>([^<]+)</text>', svg):
        out.setdefault(value, int(x))
    return out


# ── Category auto-grouping (ORDER only) ──────────────────────────────────────


def test_category_grouping_orders_volume_activity_identity() -> None:
    """Cells stable-sort volume → activity → identity regardless of input order.
    Input is deliberately scrambled (identity, activity, volume); the rendered
    x-order must be volume(STARS) < activity(BUILD) < identity(VERSION)."""
    svg = _marquee(
        "brutalist",
        [_kv("VERSION", "1.0"), _kv("BUILD", "passing"), _live("STARS", "2907", "stars")],
        variant="celadon",
    )
    pos = _module_value_positions(svg)
    assert pos["2907"] < pos["passing"] < pos["1.0"], f"group order wrong: {pos}"


# ── Role-based hero (NOT keyed on "stars") ───────────────────────────────────


def test_hero_is_first_volume_cell_role_based() -> None:
    """The hero is the FIRST volume cell by role — not the literal STARS metric.
    With FORKS first and no STARS, FORKS becomes the hero and renders at the
    larger hero font size (brutalist module: 22 vs 20 body)."""
    svg = _marquee(
        "brutalist",
        [_live("FORKS", "312", "forks"), _live("WATCHERS", "41", "watchers"), _kv("VERSION", "1.0")],
        variant="celadon",
    )
    # FORKS value (312) renders at hero font-size 22; body cells at 20.
    assert re.search(r'<text x="\d+" y="35" font-family="[^"]*" font-size="22"[^>]*>312</text>', svg), (
        "first volume cell (FORKS) is not the hero at font-size 22"
    )
    assert re.search(r'font-size="20"[^>]*>1.0</text>', svg), "identity cell should render at body size 20"


# ── Per-cell state via the cascade bridge (single-channel) ───────────────────


def test_stateful_activity_cell_binds_state_value_via_cascade() -> None:
    """An allowlisted activity cell (BUILD=passing) emits data-hw-status and
    fills its value with var(--hw-state-value) — asserting the cascade WIRING,
    not a literal hex (the genome's state_* hexes resolve it at render)."""
    svg = _marquee("brutalist", [_kv("BUILD", "passing"), _live("STARS", "10", "stars")], variant="celadon")
    assert re.search(r'data-hw-status="passing"[^>]*fill="var\(--hw-state-value\)"[^>]*>passing</text>', svg), (
        "stateful cell missing data-hw-status + var(--hw-state-value) binding"
    )
    # The cascade partial is present so the var resolves.
    assert "--hw-state-value:" in svg, "state-signal-cascade not included in marquee"


def test_volume_and_identity_cells_carry_no_data_hw_status() -> None:
    """Single-channel encoding: only activity cells carry data-hw-status. Volume
    (STARS) and identity (VERSION) cells get role color only."""
    svg = _marquee(
        "brutalist",
        [_live("STARS", "2907", "stars"), _kv("VERSION", "1.0")],
        variant="celadon",
    )
    # The STARS and VERSION value texts must not carry data-hw-status.
    assert re.search(r'<text x="\d+" y="35"(?:(?!data-hw-status)[^>])*>2907</text>', svg), (
        "volume cell wrongly carries data-hw-status"
    )
    assert re.search(r'<text x="\d+" y="35"(?:(?!data-hw-status)[^>])*>1.0</text>', svg), (
        "identity cell wrongly carries data-hw-status"
    )


def test_state_palette_is_genome_harmonized_not_tailwind() -> None:
    """The cascade resolves data-hw-status to the genome's own state_* hexes,
    not literal Tailwind-500 colors injected per-cell."""
    svg = _marquee("brutalist", [_kv("BUILD", "passing")], variant="celadon")
    # The value tspan references the var; the concrete hex lives once in the
    # cascade CSS (sourced from the genome), never inlined on the cell.
    assert svg.count('fill="var(--hw-state-value)"') >= 1


# ── Layout dispatch: module (brutalist) vs ribbon (chrome/automata) ──────────


def test_brutalist_renders_stacked_modules_with_dividers() -> None:
    """Brutalist uses item_layout=module: each metric is a label STACKED OVER a
    value (label at y=14, value at y=35) bounded by a full-height divider rect."""
    svg = _marquee(
        "brutalist",
        [_live("STARS", "2907", "stars"), _kv("BUILD", "passing"), _kv("VERSION", "1.0")],
        variant="celadon",
    )
    # Label-over-value stack: labels at y=14, values at y=35.
    assert re.search(r'<text x="\d+" y="14"[^>]*>STARS</text>', svg), "module label not at y=14"
    assert re.search(r'<text x="\d+" y="35"[^>]*>2907</text>', svg), "module value not at y=35"
    # Full-height divider per module (y=6, height=32).
    dividers = re.findall(r'<rect x="(\d+)" y="6" width="2" height="32"', svg)
    assert len(dividers) >= 3, f"expected a divider per module; got {len(dividers)}"


def test_automata_renders_ribbon_not_module() -> None:
    """Automata uses item_layout=ribbon: inline label+value tspans on ONE
    baseline (dominant-baseline=central), NO stacked label-over-value, NO
    full-height module dividers. (Reconciled to automata-bone-marquee-v4.svg.)"""
    svg = _marquee("automata", [_live("STARS", "2907", "stars"), _kv("BUILD", "passing")], variant="bone")
    assert 'dominant-baseline="central"' in svg, "automata ribbon should center on one baseline"
    assert not re.search(r'<rect x="\d+" y="6" width="2" height="32"', svg), (
        "automata ribbon must not emit module dividers"
    )
    # Ribbon ≠ stacked: there is no y=15 label / y=31 value split.
    assert not re.search(r'<text x="\d+" y="31"', svg), "automata ribbon must not stack value at y=31"


def test_chrome_renders_stacked_module() -> None:
    """v0.3.12-fix: chrome's marquee was reconciled to marquee-dense-chrome.svg,
    which STACKS a small label (y=15) over a bold value (y=31) — the same
    ``item_layout=module`` grammar brutalist uses, NOT the inline ribbon chrome
    previously fell through to. Chrome declares module_divider_w=0 (the prototype
    spaces cells; the only rule is the LIVE-panel separator), so the stacked
    text — not a divider rect — is the module signature here."""
    svg = _marquee("chrome", [_live("STARS", "2907", "stars"), _kv("BUILD", "passing")], variant="horizon")
    assert re.search(r'<text x="\d+" y="15"[^>]*>STARS</text>', svg), "chrome module label not at y=15"
    assert re.search(r'<text x="\d+" y="31"[^>]*>2907</text>', svg), "chrome module value not at y=31"
    # divider_w=0 → no full-height inter-cell rule (only the LIVE-panel separator).
    assert not re.search(r'<rect x="\d+" y="6" width="2" height="32"', svg), (
        "chrome modules space cells; no width=2 inter-cell divider"
    )


def test_brutalist_module_value_is_barlow_label_is_mono() -> None:
    """v0.3.12-fix: the brutalist DATA module value renders in Barlow Condensed —
    the SAME condensed display face as the stat-card hero and the module
    prototype (brutalist-marquee-celadon.svg). The earlier var(--dna-font-display)
    resolved to JetBrains Mono (brutalist's mono == display), which read as the
    wrong font. The small label stays JetBrains Mono via var(--dna-font-mono).
    Barlow is embedded (font-embedding.yaml marquee row)."""
    svg = _marquee("brutalist", [_live("STARS", "2907", "stars")], variant="celadon")
    assert re.search(r'font-family="Barlow Condensed[^"]*"[^>]*>2907</text>', svg), (
        "module value should be Barlow Condensed (matching the stat-card hero)"
    )
    assert re.search(r"font-family=\"var\(--dna-font-mono[^\"]*\"[^>]*>STARS</text>", svg), (
        "module label should stay JetBrains Mono via var(--dna-font-mono)"
    )
    # Barlow is embedded so it renders rather than falling back to a system serif.
    assert "@font-face" in svg and "Barlow" in svg, "Barlow Condensed must be embedded for the brutalist marquee"


# ── Download-window subtitle (v0.3.12-fix) ───────────────────────────────────


def _dl(label: str, value: str, window: str) -> ResolvedToken:
    """A windowed download cell (kv-shaped, explicit window)."""
    return ResolvedToken(kind="kv", label=label, value=value, ttl=0, window=window)


def test_download_window_derived_from_provider_metric() -> None:
    """The period qualifier is a fixed property of (provider, metric): pypi /
    crates downloads are all-time, crates recent is 90-day, npm is last-week.
    Non-download metrics carry no window."""
    from hyperweave.connectors.data_tokens import _download_window

    assert _download_window("pypi", "downloads") == "ALL-TIME"
    assert _download_window("crates", "downloads") == "ALL-TIME"
    assert _download_window("crates", "recent_downloads") == "90D"
    assert _download_window("npm", "downloads") == "7D"
    assert _download_window("github", "stars") == ""  # not a download metric


def test_kv_window_suffix_parses() -> None:
    """``kv:DOWNLOADS=847K~ALL-TIME`` splits the value from a trailing ~WINDOW so
    the proofset can bake a deterministic window across all three transports."""
    from hyperweave.connectors.data_tokens import parse_data_tokens

    tok = parse_data_tokens("kv:DOWNLOADS=847K~ALL-TIME")[0]
    assert tok.literal_value == "847K"
    assert tok.window == "ALL-TIME"
    # No ~ → no window (a bare kv value is unaffected).
    assert parse_data_tokens("kv:VERSION=2.1.0")[0].window == ""


def test_window_subtitle_renders_in_ribbon_and_module() -> None:
    """The window renders as a dim trailing tspan after the value — in BOTH the
    ribbon (automata) and module (chrome) layouts. var(--dna-ink-muted) keeps it
    recessive against the bright value."""
    for genome, variant in (("automata", "bone"), ("chrome", "horizon")):
        svg = _marquee(genome, [_dl("DOWNLOADS", "847K", "ALL-TIME"), _kv("VERSION", "2.1.0")], variant=variant)
        # Trailing tspan, dim ink-muted, 4px gap. Module also carries the label
        # font-family; ribbon inherits it — so match dx + the muted fill loosely.
        assert re.search(
            r'<tspan dx="4"[^>]*font-size="[^"]+"[^>]*fill="var\(--dna-ink-muted\)">ALL-TIME</tspan>', svg
        ), f"{genome} window subtitle not rendered as a dim trailing tspan"
        # VERSION (no window) gets no subtitle — windows are download-only.
        assert svg.count("ALL-TIME") >= 2, f"{genome} window should render in set-a + set-b"


def test_window_subtitle_does_not_cram_next_cell() -> None:
    """The window's measured width is reserved by the layout engine, so adding it
    does NOT overlap the following cell. Compare the windowed render's value
    positions to the unwindowed one: the cell AFTER downloads must shift right by
    at least the window's footprint, never overlap."""
    base = _marquee("automata", [_dl("DOWNLOADS", "847K", ""), _live("STARS", "2907", "stars")], variant="bone")
    wind = _marquee("automata", [_dl("DOWNLOADS", "847K", "ALL-TIME"), _live("STARS", "2907", "stars")], variant="bone")

    def _set_a_text_xs(svg: str) -> list[int]:
        set_a = svg.split('data-hw-zone="set-a"')[1].split('data-hw-zone="set-b"')[0]
        return [int(m) for m in re.findall(r'<text x="(\d+)"', set_a)]

    # DOWNLOADS (the hero) anchors first at the same start x in both renders; the
    # element AFTER it (the ▪ separator) must shift right when the window widens
    # the download cell. Comparing within Set-A avoids the repetition-count
    # confound that makes total scroll_distance an unreliable proxy.
    base_xs, wind_xs = _set_a_text_xs(base), _set_a_text_xs(wind)
    assert wind_xs[1] > base_xs[1], (
        f"window must push the following element right (reserved width, no cram); "
        f"base after-downloads x={base_xs[1]}, windowed x={wind_xs[1]}"
    )


# ── Set-A / Set-B parity ─────────────────────────────────────────────────────


def test_set_a_set_b_parity() -> None:
    """Set-B mirrors Set-A item-for-item (state is content-derived, not
    position-cycled), preserving the seamless loop."""
    svg = _marquee("brutalist", [_live("STARS", "2907", "stars"), _kv("BUILD", "passing")], variant="celadon")
    set_a = svg.split('data-hw-zone="set-a"')[1].split('data-hw-zone="set-b"')[0]
    set_b = svg.split('data-hw-zone="set-b"')[1]
    for value in ("2907", "passing", "STARS", "BUILD"):
        assert value in set_a and value in set_b, f"{value} missing from a set (parity broken)"


# ── Uniform reading rate (CHROME_PX_PER_SEC) ─────────────────────────────────


def _scroll_distance_and_dur(svg: str) -> tuple[int, float]:
    # Match the scroll-track animateTransform specifically (to= and dur= are
    # adjacent on it) — NOT a defs animation like chrome's envelope drift.
    m = re.search(r'to="-(\d+) 0"\s+dur="([\d.]+)s"', svg)
    assert m is not None, "scroll-track animateTransform not found"
    return int(m.group(1)), float(m.group(2))


def test_scroll_dur_uniform_reading_rate_across_genomes() -> None:
    """scroll_dur = scroll_distance ÷ CHROME_PX_PER_SEC (29.7), the SAME reading
    rate for every genome — NOT each prototype's hardcoded dur."""
    from hyperweave.compose.resolver import CHROME_PX_PER_SEC

    tokens = [_live("STARS", "2907", "stars"), _kv("BUILD", "passing"), _kv("VERSION", "1.0")]
    for genome, variant in (("brutalist", "celadon"), ("chrome", "moth"), ("automata", "bone")):
        sd, dur = _scroll_distance_and_dur(_marquee(genome, tokens, variant=variant))
        rate = sd / dur
        assert abs(rate - CHROME_PX_PER_SEC) < 1.0, f"{genome} px/s={rate:.1f} != {CHROME_PX_PER_SEC}"


# ── Content-aware geometry (no hardcoded coordinates) ────────────────────────


def test_divider_positions_track_measured_content() -> None:
    """Module pitch (and therefore every downstream divider x) derives from
    MEASURED content. Widening one value widens the uniform pitch and shifts the
    dividers — proving no hardcoded coordinate. Drives the real measurement
    engine, not a fixture."""

    def first_pitch(tokens: list[ResolvedToken]) -> int:
        svg = _marquee("brutalist", tokens, variant="celadon")
        xs = [int(x) for x in re.findall(r'<rect x="(\d+)" y="6" width="2" height="32"', svg)]
        return xs[1] - xs[0]

    short = first_pitch([_kv("A", "1"), _kv("B", "2"), _kv("C", "3")])
    wide = first_pitch([_kv("A", "1"), _kv("B", "AVERYWIDEVALUE0000"), _kv("C", "3")])
    assert wide > short, f"divider pitch did not grow with content: short={short} wide={wide}"


def test_ribbon_positions_track_measured_content() -> None:
    """Ribbon item x positions are content-packed from measured widths — a wider
    earlier value pushes later items to larger x."""

    def stars_x(forks_value: str) -> int:
        svg = _marquee("chrome", [_live("FORKS", forks_value, "forks"), _live("STARS", "10", "stars")])
        # STARS label x in the ribbon (first occurrence).
        return int(re.search(r'<text x="(\d+)"[^>]*>(?:<tspan[^>]*>)?STARS', svg).group(1))  # type: ignore[union-attr]

    assert stars_x("MUCHWIDERFORKSVALUE") > stars_x("9"), "downstream ribbon item did not shift with content"
