"""Receipt zone dataclasses + layout pass (the v3 prototype, data computed once).

One pure dataclass per visual zone, plus a ``build_*`` function that folds the
``receipt/1`` payload into it with every coordinate pinned to the specimen's
``hw:spatial-notes``. Drawing happens in the template; this module owns the
geometry and the formatted strings. Real text measurement (``core/text.py``)
drives every fit decision so the layout survives long tool lists, many models,
and high counts (the explicit quality bar).

Specimen anchors (``receipt_primer-noir-v3.svg``)::

    rails       24 left / 776 right / 752 content
    identity    glyph x24 y14 18x18; wordmark x48 y28 (Inter 14/700)
    model-mix   eyebrow y17; dominant y33; split y46 (all right-anchored x776)
    hero        cost x24 y72 (38/800); EST after cost y68; tokens y72
    metrics     y93; CALLS·STAGES·TURNS·ERRORS, errors in semantic red
    rule        y106 (ink at 0.1)
    tool-spend  header y124; rows y137 pitch 23; legend y261; rule y266
    cost-by-mdl eyebrow y281; bar y288 h20; legend y322
    context     translate(24,350); plot box (34,22,718,108)
    rule        y524 (signal at 0.85)
    footer      y542 (TL/TR); y560 (BL/BR)
"""

# ruff: noqa: RUF001, RUF002  deliberate multiplication-sign glyph in subagent-count roles
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hyperweave.compose.chart.area import (
    GLYPH_CHEVRON_H,
    GLYPH_CHEVRON_W,
    GLYPH_CIRCLE_R,
    GLYPH_DIAMOND_R,
    GLYPH_LIFT,
    LEGEND_LINE_SWATCH_W,
    PLOT_BOTTOM_INSET,
    PLOT_TOP_INSET,
    ContextLoadLayout,
    ResetEvent,
    ResetMarker,
    layout_context_load,
)
from hyperweave.core.text import format_duration, measure_text

# --------------------------------------------------------------------------- #
# Chassis constants (single source of truth — the template imports these too   #
# indirectly via the resolver's context).                                      #
# --------------------------------------------------------------------------- #

LEFT_RAIL = 24.0
RIGHT_RAIL = 776.0
CONTENT_W = RIGHT_RAIL - LEFT_RAIL  # 752.0

_INTER = "Inter"
_MONO = "JetBrains Mono"

# --------------------------------------------------------------------------- #
# Content-aware vertical rhythm (the cursor model)                            #
# --------------------------------------------------------------------------- #
# Zones flow top-to-bottom from a y-cursor: each zone's top = where the prior
# zone ended, and the footer + card height FOLLOW the content (no pinned y's).
# Every constant below is a *within-zone offset* or an *inter-zone gap* derived
# from the full-session specimen (receipt_primer-noir-v3.svg) so that the
# maximal case — all zones, 5 tool rows + overflow, full context — reproduces
# the specimen's 578px height exactly while a sparse session compacts with no
# dead band before the footer.

# Identity / model-mix header band (always present). Measured from the card top
# (cursor origin 0): the glyph tops at 14, the wordmark baseline at 28, the
# model-mix split baseline at 46; the hero cost baseline sits at 72. So the
# cursor's first stop — the hero baseline — is 72 below the top edge.
_BAND_HEADER_H = 72.0  # card top → hero cost baseline (absolute)

# Hero band: cost baseline at band-top; metrics baseline +21 below it.
_HERO_TO_METRICS = 21.0
# Metrics baseline → the hairline rule below it.
_METRICS_TO_RULE = 13.0
# Rule → tool-spend header.
_RULE_TO_TS_HEADER = 18.0

# Tool-spend internal rhythm (relative to the tool-spend header baseline):
#   row0 top   = header + 13
#   row i top  = header + 13 + i*pitch
#   legend     = last_row_top + 32  (pitch 23 + 9px row-content)
#   rule       = legend + 5
_TS_HEADER_TO_ROW0 = 13.0
_TS_ROW_PITCH = 23.0
_TS_LASTROW_TO_LEGEND = 32.0
_TS_LEGEND_TO_RULE = 5.0

# Cost-by-model internal rhythm (relative to its eyebrow baseline):
#   eyebrow      = band-top
#   bar top      = eyebrow + 7   (height 20)
#   first marker = bar-bottom + 10, rows pitch 16, marker 8px, name baseline +8
# Inter-zone: tool-spend rule → cost-by-model eyebrow = 15.
# "Rich" mode (≥3 models) adds the right-eyebrow count, segment dividers, and a
# closing rule before the chart — matching the multi-agent specimen; ≤2 models
# stay plain (the two rows are self-evidently the model list). The threshold also
# sets the gap to the context-load chart: plain flows +24, rich rule+chart at +14/+35.
_TS_RULE_TO_CBM = 15.0
_CBM_EYEBROW_TO_BAR = 7.0
_CBM_BAR_H = 20.0
_CBM_BAR_TO_ROWS = 10.0  # bar bottom → first row-marker top
_CBM_ROW_PITCH = 16.0  # marker-to-marker vertical pitch
_CBM_MARKER_SIZE = 8.0  # row marker square edge (name baseline sits on its base)
_CBM_NAME_DX = 14.0  # rail → row name, and segment-left → in-bar name
_CBM_BARNAME_DY = 13.6  # bar top → in-bar dominant-name baseline
_CBM_BARNAME_SIZE = 10.0  # in-bar dominant-name font size
_CBM_BARNAME_PAD = 8.0  # min right padding for an in-bar name to fit its segment
_CBM_DIVIDER_W = 1.5  # rich-mode segment-boundary hairline width
_CBM_PCT_COL_W = 64.0  # reserved right column → cost column right edge = 776 - 64
_CBM_RICH_MIN_MODELS = 3  # ≥ this many models → right-eyebrow + dividers + rule
_CBM_ROWS_TO_CTX = 24.0  # plain mode: last row baseline → context-load translate
_CBM_RICH_SEP_DY = 14.0  # rich mode: last row baseline → closing rule
_CBM_RICH_ROWS_TO_CTX = 35.0  # rich mode: last row baseline → context-load translate

# Context-load panel (delegated to area.py). Its group spans header(+10) →
# panel box(+22..+130) → legend(+153..+156); from the group-translate origin the
# legend caption baseline sits at +156. Inter-zone: a present cost-by-model
# legend → ctx translate = 28; when cost-by-model is absent the cursor flows
# straight from the tool-spend rule.
_CTX_GROUP_BOTTOM = 156.0  # translate origin → legend caption baseline
# When there is no cost-by-model zone, the gap from the tool-spend rule to the
# context-load translate matches the metrics→header rhythm (a single rule gap).
_RULE_TO_CTX = 18.0

# Closing rule + footer (always). The closing rule sits 18 below the last
# content zone's bottom; footer TL/TR 18 below the rule; footer BL/BR 18 below
# that; the card bottom edge 18 below the footer baseline.
_CONTENT_TO_CLOSING_RULE = 18.0
_RULE_TO_FOOTER_TOP = 18.0
_FOOTER_TOP_TO_BOTTOM = 18.0
_FOOTER_BOTTOM_TO_EDGE = 18.0


# --------------------------------------------------------------------------- #
# Numeric formatting (display strings live HERE, never in the payload)         #
# --------------------------------------------------------------------------- #


def _fmt_tok(n: float) -> str:
    """Compact token magnitude: 709300 → '709.3K', 1024800 → '1.0M'.

    Keeps the trailing '.0' (the specimen renders '1.0M working', not '1M') so
    the magnitude reads with consistent precision across the receipt.
    """
    n = float(n)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{round(n)}"


def _fmt_money(value: Any) -> str:
    """'$175.01' / '$128' — 2dp unless a whole dollar (matches the specimen)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "$0"
    if abs(v - round(v)) < 0.005:
        return f"${round(v)}"
    return f"${v:.2f}"


def _fmt_money_cents(value: Any) -> str:
    """Always 2dp money for the hero ($175.01)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "$0.00"
    return f"${v:,.2f}"


def _coerce_tools(raw: Any) -> list[dict[str, Any]]:
    """Return a clean ``receipt/1`` ``tools[]`` list-of-dicts from opaque input.

    The canonical form is a list of sparse dicts. The resolver consumes
    ``ComposeSpec.telemetry_data`` opaquely, so a caller passing the legacy
    dict-keyed-by-name shape (or anything malformed) must not crash the render —
    a dict is folded into ``[{name, **fields}]``, non-dict entries are dropped,
    and anything else yields an empty list.
    """
    if isinstance(raw, list):
        return [t for t in raw if isinstance(t, dict)]
    if isinstance(raw, dict):
        return [{"name": name, **fields} for name, fields in raw.items() if isinstance(fields, dict)]
    return []


# --------------------------------------------------------------------------- #
# identity                                                                     #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Identity:
    """Runtime glyph + wordmark (top-left). Geometry fixed; colour from palette."""

    glyph_id: str
    glyph_x: float
    glyph_y: float
    glyph_size: float
    wordmark: str
    wordmark_x: float
    wordmark_y: float


def build_identity(*, glyph_id: str, wordmark: str, palette: dict[str, str]) -> Identity:
    return Identity(
        glyph_id=glyph_id,
        glyph_x=LEFT_RAIL,
        glyph_y=14.0,
        glyph_size=18.0,
        wordmark=wordmark,
        wordmark_x=48.0,
        wordmark_y=28.0,
    )


# --------------------------------------------------------------------------- #
# model-mix                                                                    #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ModelMix:
    """Right-aligned model summary — always present. Solo runs show a single-model variant."""

    show: bool
    eyebrow: str
    eyebrow_y: float
    dominant: str
    dominant_suffix: str
    dominant_y: float
    split: str
    split_y: float
    anchor_x: float


def build_model_mix(payload: dict[str, Any], *, palette: dict[str, str]) -> ModelMix:
    """Build the model-mix corner block — always present (the prototypes carry it).

    Multi-model: 'MODEL MIX · N MODELS' / '{dominant} DOMINANT' / '{p0}% spend ·
    {m1} {p1}% · …'. Solo: 'MODEL' / '{model}' / '100% spend' — the slot still
    names the model, since the identity zone names the runtime, not the model.
    """
    models: list[dict[str, Any]] = list(payload.get("models") or [])
    n = len(models)
    if n <= 1:
        solo = models[0] if models else {}
        model = str(payload.get("dominant") or solo.get("name") or payload.get("model") or "")
        return ModelMix(
            show=bool(model),
            eyebrow="MODEL",
            eyebrow_y=17.0,
            dominant=model,
            dominant_suffix="",
            dominant_y=33.0,
            split="100% spend",
            split_y=46.0,
            anchor_x=RIGHT_RAIL,
        )

    dominant = str(payload.get("dominant") or models[0].get("name", ""))
    eyebrow = f"MODEL MIX · {n} MODELS"
    # Split line: lead model's percent as 'N% spend', then each subsequent
    # model's short name + percent. Short-name = strip the '-x.y' version tail.
    lead_pct = int(models[0].get("cost_pct", 0))
    parts = [f"{lead_pct}% spend"]
    for m in models[1:]:
        short = _short_model_name(str(m.get("name", "")))
        parts.append(f"{short} {int(m.get('cost_pct', 0))}%")
    split = " · ".join(parts)

    return ModelMix(
        show=True,
        eyebrow=eyebrow,
        eyebrow_y=17.0,
        dominant=dominant,
        dominant_suffix="DOMINANT",
        dominant_y=33.0,
        split=split,
        split_y=46.0,
        anchor_x=RIGHT_RAIL,
    )


def _short_model_name(name: str) -> str:
    """'sonnet-4.6' → 'sonnet' — drop the version tail for the split line."""
    return name.split("-", 1)[0] if "-" in name else name


# --------------------------------------------------------------------------- #
# hero                                                                         #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Hero:
    """Cost outcome + EST flag + tokens·active subline (y72)."""

    cost: str
    cost_x: float
    cost_y: float
    cost_size: float
    est_label: str
    est_x: float
    est_y: float
    show_est: bool
    subline: str
    subline_x: float
    subline_y: float


def build_hero(payload: dict[str, Any], *, palette: dict[str, str], cost_baseline_y: float = 72.0) -> Hero:
    """Lay out the hero row, measuring the cost string to place EST + subline.

    The cost number sits on ``cost_baseline_y`` (threaded by the cursor; 72 in
    the specimen). The EST flag and the 'NNN tokens · NNm active' subline sit to
    the right, x's measured off the cost glyphs so the layout holds for $9.40
    through $9,999.99 without overlap (the specimen hardcodes 176.1 / 208.8 for
    '$175.01'; we measure to generalize). EST baseline lifts 4px above the cost.
    """
    # The cost renders .s (Inter) — measure it with Inter. EST + subline render
    # the mono default in the specimen — measure EST with mono so the subline's
    # x (placed past EST) matches the rendered advance (measured == rendered).
    cost = _fmt_money_cents(payload.get("cost_usd", 0))
    cost_size = 38.0
    cost_w = measure_text(cost, font_family=_INTER, font_size=cost_size, font_weight=800, letter_spacing_em=-0.01)
    est_x = round(LEFT_RAIL + cost_w + 8.94, 1)
    est_w = measure_text("EST", font_family=_MONO, font_size=8.0, font_weight=700, letter_spacing_em=0.14)
    subline_x = round(est_x + est_w + 15.04, 1)

    tokens = payload.get("tokens", {}) or {}
    active = int(payload.get("active_min", 0) or 0)
    subline = f"{_fmt_tok(tokens.get('total', 0))} tokens   ·   {format_duration(active)} active"

    return Hero(
        cost=cost,
        cost_x=LEFT_RAIL,
        cost_y=round(cost_baseline_y, 1),
        cost_size=cost_size,
        est_label="EST",
        est_x=est_x,
        est_y=round(cost_baseline_y - 4.0, 1),
        show_est=bool(payload.get("estimate", False)),
        subline=subline,
        subline_x=subline_x,
        subline_y=round(cost_baseline_y, 1),
    )


# --------------------------------------------------------------------------- #
# metrics                                                                      #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class MetricCell:
    """One CALLS/STAGES/TURNS/ERRORS pair: bold value + tracked label."""

    value: str
    value_x: float
    label: str
    label_x: float
    is_error: bool
    sep_x: float
    show_sep: bool


@dataclass(frozen=True, slots=True)
class Metrics:
    """The metric row (y93). Cells measured so the · separators never collide."""

    y: float
    cells: list[MetricCell] = field(default_factory=list)


def build_metrics(payload: dict[str, Any], *, palette: dict[str, str], baseline_y: float = 93.0) -> Metrics:
    """Lay out CALLS·STAGES·TURNS·ERRORS, measuring each run so the row packs.

    The row sits on ``baseline_y`` (threaded by the cursor; 93 in the specimen).
    Errors render in the semantic-red palette tone (``is_error``); a zero-error
    session still shows '0 ERRORS' (positive signal — the run was clean). Each
    cell measures its value + label + the interpunct so the next cell starts
    flush, reproducing the specimen's 24 → 46.8 → 79 → 90.6 … cadence.
    """
    y = round(baseline_y, 1)
    value_size = 11.0
    label_size = 8.0
    sep = "·"
    sep_w = measure_text(sep, font_family=_MONO, font_size=value_size, font_weight=400)
    # Specimen advance gaps (derived from the noir metric row coordinates):
    # value→label 3px, label→separator 5px, separator→next value 5px.
    gap_vl = 3.0
    gap_ls = 5.0
    gap_sv = 5.0

    entries = [
        (str(payload.get("calls", 0)), "CALLS", False),
        (str(payload.get("stages", 0)), "STAGES", False),
        (str(payload.get("turns", 0)), "TURNS", False),
        (str(payload.get("errors", 0)), "ERRORS", True),
    ]

    cells: list[MetricCell] = []
    cursor = LEFT_RAIL
    last = len(entries) - 1
    for i, (value, label, is_error) in enumerate(entries):
        value_x = cursor
        value_w = measure_text(value, font_family=_MONO, font_size=value_size, font_weight=700)
        label_x = round(value_x + value_w + gap_vl, 1)
        label_w = measure_text(label, font_family=_MONO, font_size=label_size, font_weight=700, letter_spacing_em=0.1)
        if i < last:
            sep_x = round(label_x + label_w + gap_ls, 1)
            next_cursor = round(sep_x + sep_w + gap_sv, 1)
            cells.append(
                MetricCell(
                    value=value,
                    value_x=value_x,
                    label=label,
                    label_x=label_x,
                    is_error=is_error,
                    sep_x=sep_x,
                    show_sep=True,
                )
            )
            cursor = next_cursor
        else:
            cells.append(
                MetricCell(
                    value=value,
                    value_x=value_x,
                    label=label,
                    label_x=label_x,
                    is_error=is_error,
                    sep_x=0.0,
                    show_sep=False,
                )
            )
    return Metrics(y=y, cells=cells)


# --------------------------------------------------------------------------- #
# tool-spend                                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ToolRow:
    """One tool's spend bar: accent stripe + label + proportional bar + stats."""

    name: str
    name_x: float
    accent_y: float
    accent_fill: str
    label_y: float
    is_tail: bool
    bar_track_y: float
    bar_fill_w: float
    bar_fill: str
    pct: str
    pct_fill: str
    tokens: str
    calls: str
    text_y: float
    err: int
    err_y: float
    err_text_y: float


@dataclass(frozen=True, slots=True)
class ToolLegendChip:
    """One tool-class swatch in the bottom legend strip."""

    label: str
    swatch_x: float
    swatch_fill: str
    label_x: float


@dataclass(frozen=True, slots=True)
class ToolSpend:
    """The tool-spend zone: header + cache summary + N bars + class legend."""

    eyebrow: str
    eyebrow_x: float
    eyebrow_cont: str
    eyebrow_cont_x: float
    header_y: float
    cache_pct: str
    cache_pct_x: float
    cache_summary: str
    cache_summary_x: float
    cache_sep_x: float
    cache_working: str
    cache_working_x: float
    rows: list[ToolRow]
    legend_y: float
    legend_swatch_y: float
    legend_chips: list[ToolLegendChip]
    err_legend_x: float
    err_legend_label_x: float
    show_err_legend: bool
    rule_y: float


# Tool-spend horizontal columns (fixed) + the per-row vertical rhythm. The band
# is content-aware: rows flow from the header baseline (threaded by the cursor)
# and the legend + rule follow the last row, so a sparse session has no dead
# space. The 5-row cap matches the full-session specimen (rows + overflow).
_TS_BAR_X = 150.0
_TS_BAR_W = 322.0
_TS_NAME_X = 36.0
_TS_PCT_X = 484.0
_TS_TOKENS_X = 600.0
_TS_CALLS_X = 690.0
_TS_ERR_X = 769.0  # errcount badge centre
_TS_MAX_ROWS = 5  # specimen full-session maximum (4 tools + '+N others')


def build_tool_spend(payload: dict[str, Any], *, palette: dict[str, str], header_y: float = 124.0) -> ToolSpend:
    """Lay out the tool-spend bars: top-N by working-token share + '+N OTHERS'.

    The header sits on ``header_y`` (threaded by the cursor; 124 in the
    specimen). Rows flow from ``header_y + 13`` at pitch 23; the legend follows
    the last row and the rule follows the legend, so the band's HEIGHT scales
    with the row count — a 2-tool session is compact, a full session reaches the
    specimen's 5-row layout. When more tools exist than fit (``_TS_MAX_ROWS``),
    the tail collapses into a single '+N others' row whose bar/stats aggregate
    the remainder. Per-row bar widths are proportional to the leader's tokens;
    the ramp tier and a lighter pct-label tone come from the palette by index.
    """
    tools = _coerce_tools(payload.get("tools"))
    ramp = palette["ramp"] if isinstance(palette.get("ramp"), list) else []
    ramp_list: list[str] = list(ramp) if ramp else ["#FAFAFA"]

    # Per-tool percent is the tool's working tokens over the SESSION working
    # total (tokens.working) — so the displayed shares match the cache summary's
    # '… working' figure, not a re-derived sum (specimen: Edit 709.3K / 1.0M =
    # 69%). The bar WIDTH is proportional to the leader instead, so the top tool
    # fills the track and the rest read relative to it.
    token_tools = [t for t in tools if int(t.get("tok", 0) or 0) > 0]
    session_working = int((payload.get("tokens", {}) or {}).get("working", 0) or 0)
    total_working = session_working or sum(int(t.get("tok", 0) or 0) for t in tools) or 1
    leader_tok = max((int(t.get("tok", 0) or 0) for t in token_tools), default=1) or 1

    row0_y = round(header_y + _TS_HEADER_TO_ROW0, 1)
    rows: list[ToolRow] = []
    name_budget = _TS_BAR_X - _TS_NAME_X - 6.0  # label zone before the bar

    if len(tools) <= _TS_MAX_ROWS:
        head = tools
        tail: list[dict[str, Any]] = []
    else:
        head = tools[: _TS_MAX_ROWS - 1]
        tail = tools[_TS_MAX_ROWS - 1 :]

    for i, tool in enumerate(head):
        rows.append(
            _tool_row(
                tool,
                index=i,
                row0_y=row0_y,
                ramp=ramp_list,
                total_working=total_working,
                leader_tok=leader_tok,
                palette=palette,
                name_budget=name_budget,
            )
        )

    if tail:
        # Tail tools are sparse (most carry no `tok`), so the collapsed row's
        # tokens are the REMAINDER of the session working total after the shown
        # rows — not a sum of the tail's (mostly absent) tok fields. This matches
        # the specimen's '+6 others 74.3K' = working(1.0M) minus shown(950.5K).
        shown_tok = sum(int(t.get("tok", 0) or 0) for t in head)
        agg_tok = max(0, total_working - shown_tok) if session_working else sum(int(t.get("tok", 0) or 0) for t in tail)
        agg_calls = sum(int(t.get("calls", 0) or 0) for t in tail)
        agg_err = sum(int(t.get("err", 0) or 0) for t in tail)
        rows.append(
            _others_row(
                count=len(tail),
                tok=agg_tok,
                calls=agg_calls,
                err=agg_err,
                index=len(head),
                row0_y=row0_y,
                ramp=ramp_list,
                total_working=total_working,
                leader_tok=leader_tok,
                palette=palette,
            )
        )

    # Legend + rule FOLLOW the last row (content-aware). When there are zero
    # token rows the band still reserves one row slot so the header isn't flush
    # against the legend. Specimen: 5 rows → last_row_top 229, legend 261 (+32),
    # rule 266 (+5).
    n_rows = max(1, len(rows))
    last_row_top = row0_y + (n_rows - 1) * _TS_ROW_PITCH
    legend_y = round(last_row_top + _TS_LASTROW_TO_LEGEND, 1)
    rule_y = round(legend_y + _TS_LEGEND_TO_RULE, 1)

    # Cache summary (right-aligned at the header): '98%  · 257.6M cached  ·
    # 1.0M working'. cache_pct is the cache-read share of all tokens.
    tok = payload.get("tokens", {}) or {}
    total_tok = float(tok.get("total", 0) or 0)
    cache_read = float(tok.get("cache_read", 0) or 0)
    working = float(tok.get("working", 0) or 0)
    cache_pct = round(cache_read / total_tok * 100) if total_tok > 0 else 0

    cache_pct_s = f"{cache_pct}%"
    cache_summary_s = f"{_fmt_tok(cache_read)} cached"
    cache_working_s = f"{_fmt_tok(working)} working"
    # Right-to-left placement off RIGHT_RAIL so the trio packs without overlap.
    # MEASURED with JetBrains Mono because the specimen renders the cache summary
    # in the mono default (only the wordmark + cost are .s/Inter) — measured ==
    # rendered keeps the right-anchored trio aligned.
    working_w = measure_text(cache_working_s, font_family=_MONO, font_size=9.0, font_weight=400)
    cached_w = measure_text(cache_summary_s, font_family=_MONO, font_size=9.0, font_weight=400)
    sep_w = measure_text("·", font_family=_MONO, font_size=9.0, font_weight=400)
    # Right-anchored: each text's RIGHT edge sits ~12px left of the previous
    # run's LEFT edge (specimen advance between cache-summary runs).
    working_x = RIGHT_RAIL
    cached_x = round(working_x - working_w - 12.0, 1)
    sep_x = round(cached_x - cached_w - 8.0, 1)
    pct_x = round(sep_x - sep_w - 8.0, 1)

    eyebrow_w = measure_text("TOOL SPEND", font_family=_MONO, font_size=7.0, font_weight=700, letter_spacing_em=0.22)

    # Class legend (bottom strip): one swatch per distinct class present, in the
    # palette ramp order the bars used, plus the '= failed calls' marker when
    # any row carries an error.
    legend_chips, show_err = _tool_class_legend(head + ([{}] if tail else []), tools, ramp_list, palette)
    # Error marker sits ~24px past the last class chip's label, with its label
    # 13px past the swatch (specimen: coordinate-end → err-swatch@281 → @294).
    if legend_chips:
        last = legend_chips[-1]
        last_w = measure_text(last.label, font_family=_MONO, font_size=8.5, font_weight=400)
        err_legend_x = round(last.label_x + last_w + 24.0, 1)
    else:
        err_legend_x = 281.0
    err_legend_label_x = round(err_legend_x + 13.0, 1)

    return ToolSpend(
        eyebrow="TOOL SPEND",
        eyebrow_x=LEFT_RAIL,
        eyebrow_cont="· WORKING TOKENS",
        eyebrow_cont_x=round(LEFT_RAIL + eyebrow_w + 2.0, 1),
        header_y=round(header_y, 1),
        cache_pct=cache_pct_s,
        cache_pct_x=pct_x,
        cache_summary=cache_summary_s,
        cache_summary_x=cached_x,
        cache_sep_x=sep_x,
        cache_working=cache_working_s,
        cache_working_x=working_x,
        rows=rows,
        legend_y=legend_y,
        legend_swatch_y=round(legend_y - 6.0, 1),
        legend_chips=legend_chips,
        err_legend_x=err_legend_x,
        err_legend_label_x=err_legend_label_x,
        show_err_legend=show_err,
        rule_y=rule_y,
    )


def _ramp_at(ramp: list[str], index: int) -> str:
    """Ramp tier for a row, clamping past the last tier (long tails reuse it)."""
    if not ramp:
        return "#FAFAFA"
    return ramp[min(index, len(ramp) - 1)]


def _tool_row(
    tool: dict[str, Any],
    *,
    index: int,
    row0_y: float,
    ramp: list[str],
    total_working: int,
    leader_tok: int,
    palette: dict[str, str],
    name_budget: float,
) -> ToolRow:
    name = str(tool.get("name", ""))
    name = _truncate(name, budget=name_budget, font_family=_MONO, font_size=12.0, font_weight=700)
    tok = int(tool.get("tok", 0) or 0)
    calls = int(tool.get("calls", 0) or 0)
    err = int(tool.get("err", 0) or 0)
    pct = round(tok / total_working * 100) if total_working > 0 else 0
    fill_w = round(_TS_BAR_W * (tok / leader_tok), 1) if leader_tok > 0 else 0.0
    fill_w = max(0.0, min(_TS_BAR_W, fill_w))
    tier = _ramp_at(ramp, index)

    row_y = round(row0_y + index * _TS_ROW_PITCH, 1)
    return ToolRow(
        name=name,
        name_x=_TS_NAME_X,
        accent_y=row_y,
        accent_fill=tier,
        label_y=row_y + 9.0,
        is_tail=False,
        bar_track_y=row_y + 3.0,
        bar_fill_w=fill_w,
        bar_fill=tier,
        pct=f"{pct}%",
        pct_fill=_lighten_tone(tier, palette),
        tokens=_fmt_tok(tok),
        calls=f"{calls} calls",
        text_y=row_y + 9.0,
        err=err,
        err_y=round(row_y + 1.2, 1),
        err_text_y=round(row_y + 10.78, 2),
    )


def _others_row(
    *,
    count: int,
    tok: int,
    calls: int,
    err: int,
    index: int,
    row0_y: float,
    ramp: list[str],
    total_working: int,
    leader_tok: int,
    palette: dict[str, str],
) -> ToolRow:
    pct = round(tok / total_working * 100) if total_working > 0 else 0
    fill_w = round(_TS_BAR_W * (tok / leader_tok), 1) if leader_tok > 0 else 0.0
    fill_w = max(0.0, min(_TS_BAR_W, fill_w))
    tier = _ramp_at(ramp, index)
    row_y = round(row0_y + index * _TS_ROW_PITCH, 1)
    return ToolRow(
        name=f"+{count} others",
        name_x=_TS_NAME_X,
        accent_y=row_y,
        accent_fill=tier,
        label_y=row_y + 9.0,
        is_tail=True,
        bar_track_y=row_y + 3.0,
        bar_fill_w=fill_w,
        bar_fill=tier,
        pct=f"{pct}%",
        pct_fill=_lighten_tone(tier, palette),
        tokens=_fmt_tok(tok),
        calls=f"{calls} calls",
        text_y=row_y + 9.0,
        err=err,
        err_y=round(row_y + 1.2, 1),
        err_text_y=round(row_y + 10.78, 2),
    )


def _tool_class_legend(
    rows_source: list[dict[str, Any]],
    all_tools: list[dict[str, Any]],
    ramp: list[str],
    palette: dict[str, str],
) -> tuple[list[ToolLegendChip], bool]:
    """Build the bottom class-legend strip: one swatch per distinct class.

    Classes appear in first-seen order across the token-bearing tools, each
    keyed to the ramp tier its rows used. Returns the chips + whether any tool
    carried an error (gates the '= failed calls' marker).
    """
    seen: list[str] = []
    for t in all_tools:
        cls = str(t.get("class", "") or "")
        if cls and cls not in seen:
            seen.append(cls)
    has_err = any(int(t.get("err", 0) or 0) > 0 for t in all_tools)

    # Specimen advances: swatch→label 10px, label-end→next-swatch ~19.5px.
    chips: list[ToolLegendChip] = []
    cursor = LEFT_RAIL
    for i, cls in enumerate(seen):
        swatch_x = cursor
        label_x = round(swatch_x + 10.0, 1)
        # Legend labels render the mono default (specimen) — measure mono.
        label_w = measure_text(cls, font_family=_MONO, font_size=8.5, font_weight=400)
        chips.append(
            ToolLegendChip(
                label=cls,
                swatch_x=swatch_x,
                swatch_fill=_ramp_at(ramp, i),
                label_x=label_x,
            )
        )
        cursor = round(label_x + label_w + 19.5, 1)
    return chips, has_err


def _lighten_tone(hex_color: str, palette: dict[str, str]) -> str:
    """Return a lighter sibling of a ramp tier for the pct label.

    The specimen tints each row's percent text a step brighter than its bar
    (noir Edit bar #FAFAFA / pct #FAFAFA; Bash bar #D7D7D7 / pct #EDEDED). We
    lerp 50% toward white for dark substrates and 35% toward the value-ink for
    light substrates so the pct reads as the bar's bright echo. Falls back to
    the tier itself when the hex is unparseable.
    """
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    try:
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return hex_color
    # Lerp toward white — bar's bright echo. Light variants already use
    # saturated blues whose lighter tint stays legible against white paper.
    t = 0.32
    nr = round(r + (255 - r) * t)
    ng = round(g + (255 - g) * t)
    nb = round(b + (255 - b) * t)
    return f"#{nr:02X}{ng:02X}{nb:02X}"


# --------------------------------------------------------------------------- #
# cost-by-model                                                               #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class CostSegment:
    """One proportion-bar segment (a model's cost share)."""

    x: float
    w: float
    fill: str


@dataclass(frozen=True, slots=True)
class CostBarName:
    """A dominant model name stamped inside its bar segment (ink-on-accent).

    Only emitted for segments wide enough to hold the measured name + insets;
    narrow slivers carry no in-bar label and are read off their row instead.
    """

    x: float
    y: float
    text: str


@dataclass(frozen=True, slots=True)
class CostMarkerRow:
    """One model row below the bar: color marker + name·role + cost + pct.

    ``marker_fill`` is the model's bar-segment tone, so the eye maps a row to its
    slice of the bar. ``cost``/``pct`` are right-anchored at the layout's shared
    ``cost_x``/``pct_x`` columns; ``role`` is the display form
    (main thread / subagent / subagents ×N).
    """

    marker_x: float
    marker_y: float
    marker_fill: str
    text_x: float
    text_y: float
    name: str
    role: str
    cost: str
    pct: str


@dataclass(frozen=True, slots=True)
class CostByModel:
    """The cost-by-model shelf: eyebrow + proportion bar + one row per model.

    The bar partitions 752px by real cost share (segments sum exactly to the
    rail); each model also gets a row below — a ramp-colored marker matching its
    segment, the name + role, and the right-anchored cost + pct columns. Rows and
    segments both run high→low by cost. ``rich`` (≥3 models) turns on the
    right-eyebrow count, the segment dividers, and a closing rule before the
    chart; ≤2 models stay plain (two rows are self-evidently the model list).
    ``show=False`` (no models) makes the cursor skip the zone.
    """

    show: bool
    rich: bool
    eyebrow: str
    eyebrow_x: float
    eyebrow_y: float
    count_label: str
    count_label_x: float
    bar_x: float
    bar_y: float
    bar_w: float
    bar_h: float
    segments: list[CostSegment]
    dividers: list[float]
    bar_names: list[CostBarName]
    rows: list[CostMarkerRow]
    cost_x: float
    pct_x: float
    rows_bottom: float
    separator_y: float


def build_cost_by_model(payload: dict[str, Any], *, palette: dict[str, str], eyebrow_y: float = 281.0) -> CostByModel:
    """Partition one bar by cost share + lay a row per model beneath it.

    Models sort by cost descending. Segment widths come from real ``cost_usd``
    proportions (not the rounded ``cost_pct``, so a sub-1% model still shows a
    sliver); the LAST segment absorbs cumulative rounding so the bar closes
    precisely on the right rail. Each segment's tone (``ramp`` tier, clamped past
    the last) is reused for its row marker, so the reader maps slice → row. A
    dominant name is stamped inside any segment wide enough to hold the measured
    name. ≥3 models switch on the right-eyebrow count, the boundary dividers, and
    the closing rule. ``show=False`` when there are no models.
    """
    models: list[dict[str, Any]] = list(payload.get("models") or [])
    # High→low by cost: the bar reads left-heavy, the rows top-heavy.
    models.sort(key=lambda m: float(m.get("cost_usd", 0) or 0), reverse=True)
    ramp = palette["ramp"] if isinstance(palette.get("ramp"), list) else []
    ramp_list: list[str] = list(ramp) if ramp else ["#FAFAFA"]
    n = len(models)
    rich = n >= _CBM_RICH_MIN_MODELS
    bar_y = round(eyebrow_y + _CBM_EYEBROW_TO_BAR, 1)

    eyebrow = "COST BY MODEL"

    # Right-eyebrow (rich only): the model count + a folded-subagent flag. An
    # all-main-thread model switch shows the bare "N MODELS"; folded subagents add
    # the suffix. Right-anchored at the rail (text-anchor=end), so x IS the rail.
    has_subagents = any(str(m.get("role", "")) != "main thread" for m in models)
    count_label = ""
    if rich:
        count_label = f"{n} MODELS" + (" · WITH SUBAGENTS" if has_subagents else "")

    # Segment widths from real cost share, summing EXACTLY to CONTENT_W; the last
    # segment absorbs cumulative rounding so the bar closes on the right rail.
    total_cost = sum(float(m.get("cost_usd", 0) or 0) for m in models) or 1.0
    segments: list[CostSegment] = []
    x = float(LEFT_RAIL)
    consumed = 0.0
    for i, m in enumerate(models):
        if i == n - 1:
            w = round(CONTENT_W - consumed, 2)
        else:
            w = round(CONTENT_W * (float(m.get("cost_usd", 0) or 0) / total_cost), 2)
            consumed = round(consumed + w, 2)
        segments.append(CostSegment(x=round(x, 2), w=w, fill=_ramp_at(ramp_list, i)))
        x = round(x + w, 2)

    # Dividers (rich only): a hairline centred on each internal segment boundary.
    dividers: list[float] = []
    if rich:
        dividers = [round(seg.x - _CBM_DIVIDER_W / 2.0, 2) for seg in segments[1:]]

    # In-bar dominant names: stamp the full model name inside any segment wide
    # enough for the measured name + left inset + right pad. Slivers carry none.
    bar_names: list[CostBarName] = []
    barname_y = round(bar_y + _CBM_BARNAME_DY, 1)
    for seg, m in zip(segments, models, strict=True):
        name = str(m.get("name", ""))
        if not name:
            continue
        name_w = measure_text(
            name, font_family=_MONO, font_size=_CBM_BARNAME_SIZE, font_weight=700, letter_spacing_em=0.0
        )
        if seg.w >= name_w + _CBM_NAME_DX + _CBM_BARNAME_PAD:
            bar_names.append(CostBarName(x=round(seg.x + _CBM_NAME_DX, 2), y=barname_y, text=name))

    # Rows: marker (segment tone) + name·role + right-anchored cost + pct. Pitch
    # 16; the name baseline rests on the marker's lower edge. The cost column's
    # right edge reserves _CBM_PCT_COL_W for the pct beside it; the name band
    # (text_x → cost_x) clears any real model name + role (pinned in tests).
    cost_x = round(RIGHT_RAIL - _CBM_PCT_COL_W, 1)
    pct_x = float(RIGHT_RAIL)
    first_marker_y = round(bar_y + _CBM_BAR_H + _CBM_BAR_TO_ROWS, 1)
    rows: list[CostMarkerRow] = []
    for i, m in enumerate(models):
        marker_y = round(first_marker_y + i * _CBM_ROW_PITCH, 1)
        cost_usd = float(m.get("cost_usd", 0) or 0)
        pct_val = int(m.get("cost_pct", 0) or 0)
        # A non-zero cost that rounds to 0% reads "<1%", never a bare "0%".
        pct_str = "<1%" if (pct_val == 0 and cost_usd > 0) else f"{pct_val}%"
        rows.append(
            CostMarkerRow(
                marker_x=float(LEFT_RAIL),
                marker_y=marker_y,
                marker_fill=_ramp_at(ramp_list, i),
                text_x=round(LEFT_RAIL + _CBM_NAME_DX, 1),
                text_y=round(marker_y + _CBM_MARKER_SIZE, 1),
                name=str(m.get("name", "")),
                role=_role_display(str(m.get("role", ""))),
                cost=f"${cost_usd:,.2f}",
                pct=pct_str,
            )
        )

    rows_bottom = round(first_marker_y + max(n - 1, 0) * _CBM_ROW_PITCH + _CBM_MARKER_SIZE, 1) if n else bar_y

    return CostByModel(
        show=n > 0,
        rich=rich,
        eyebrow=eyebrow,
        eyebrow_x=float(LEFT_RAIL),
        eyebrow_y=round(eyebrow_y, 1),
        count_label=count_label,
        count_label_x=float(RIGHT_RAIL),
        bar_x=float(LEFT_RAIL),
        bar_y=bar_y,
        bar_w=CONTENT_W,
        bar_h=_CBM_BAR_H,
        segments=segments,
        dividers=dividers,
        bar_names=bar_names,
        rows=rows,
        cost_x=cost_x,
        pct_x=pct_x,
        rows_bottom=rows_bottom,
        separator_y=round(rows_bottom + _CBM_RICH_SEP_DY, 1),
    )


def _role_display(role: str) -> str:
    """Payload role → row label.

    'main thread' passes through verbatim; a subagent role ('N subagents' from the
    payload) becomes 'subagent' (N=1) or 'subagents ×N' (N≥2). Anything else (an
    empty or unrecognised role) passes through unchanged.
    """
    if not role or role == "main thread":
        return role
    head, _, tail = role.partition(" ")
    if tail.startswith("subagent") and head.isdigit():
        count = int(head)
        return "subagent" if count == 1 else f"subagents ×{count}"
    return role


# --------------------------------------------------------------------------- #
# context-load (delegates geometry to compose/chart/area.py)                  #
# --------------------------------------------------------------------------- #


# The context panel's group spans the translate origin to the legend caption
# baseline at +156 (header +10, panel box +22..+130, legend +153..+156).
_CTX_PANEL_BOTTOM = _CTX_GROUP_BOTTOM


@dataclass(frozen=True, slots=True)
class ContextLoad:
    """The burn-curve panel. Geometry from ``layout_context_load``; the resolver
    carries the translate offset + the computed layout + the disclosure for any
    error dots that couldn't fit. ``show=False`` (no window/occupancy data) makes
    the cursor skip the zone."""

    show: bool
    translate_x: float
    translate_y: float
    layout: ContextLoadLayout
    dropped_errors: int


def build_context_load(payload: dict[str, Any], *, palette: dict[str, str], translate_y: float = 350.0) -> ContextLoad:
    """Delegate the occupancy curve to the shared area primitive.

    Passes the payload's ``context.events`` (typed reset events), ``window``,
    ``peak_ctx``, the elapsed wall-clock ``span_min``, and the ``errors`` count.
    The whole panel is
    rendered under translate(24, ``translate_y``) — the cursor threads the y so a
    sparse receipt without the cost-by-model shelf places the chart higher.
    ``show=False`` when there is no OCCUPANCY signal — no peak AND no reset
    events. A window size alone (a session that never measurably filled it) would
    render a flat empty box, so the cursor omits the panel; a real burn needs at
    least a peak or a reset to be worth drawing.
    """
    ctx = payload.get("context", {}) or {}
    events_raw = ctx.get("events", []) or []
    events: list[ResetEvent] = [
        {"min": float(e.get("min", 0)), "cmd": str(e.get("cmd", "compact")), "to": float(e.get("to", 0))}
        for e in events_raw
    ]
    window = float(ctx.get("window", 0) or 0)
    peak_ctx = float(ctx.get("peak_ctx", 0) or 0)
    show = bool(peak_ctx > 0 or events)
    layout = layout_context_load(
        events=events,
        window=window,
        peak_ctx=peak_ctx,
        # x-axis runs on the elapsed wall-clock span (the timeline reset events
        # are timestamped on), NOT the active-work sum — else glyphs from a
        # session resumed across days crush onto the right rail. Fall back to
        # active_min for older payloads without span_min.
        span_min=float(ctx.get("span_min") or payload.get("active_min", 0) or 0),
        error_minutes=[float(m) for m in ctx.get("error_min", []) or []],
    )
    return ContextLoad(
        show=show,
        translate_x=LEFT_RAIL,
        translate_y=round(translate_y, 1),
        layout=layout,
        dropped_errors=layout.dropped_errors,
    )


# --------------------------------------------------------------------------- #
# footer                                                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Footer:
    """The 4-quadrant footer + the closing rule above it."""

    rule_y: float
    tl: str
    tl_y: float
    tr: str
    tr_y: float
    bl: str
    bl_y: float
    br: str
    br_y: float


def build_footer(
    payload: dict[str, Any],
    *,
    palette: dict[str, str],
    display_name: str,
    timestamp: str,
    rule_y: float = 524.0,
) -> Footer:
    """Build the footer quadrants, right-truncating the name if TL+TR collide.

    The closing rule sits on ``rule_y`` (threaded by the cursor; 524 in the
    specimen — it FOLLOWS the content rather than being pinned). TL/TR sit +18
    below the rule, BL/BR +18 below that. TL = 'repo · branch · name'; TR =
    'session <id> · <timestamp>'; BL = the italic cost-estimate disclaimer; BR =
    'hyperweave.app'. ``display_name`` is the live session title read at render
    time, so a mid-session rename surfaces here without repointing the on-disk
    file. When the measured TL + TR would overflow the content width the name is
    right-truncated with an ellipsis (the repo · branch prefix is preserved).
    """
    footer_top_y = round(rule_y + _RULE_TO_FOOTER_TOP, 1)
    footer_bottom_y = round(footer_top_y + _FOOTER_TOP_TO_BOTTOM, 1)
    session_id = str(payload.get("session") or "")
    repo = str(payload.get("repo") or "hyperweave")
    branch = str(payload.get("branch") or "main")

    tr_parts: list[str] = []
    if session_id:
        tr_parts.append(f"session {session_id}")
    if timestamp:
        tr_parts.append(timestamp)
    tr = " · ".join(tr_parts)

    prefix = f"{repo} · {branch}" if branch else repo
    name = display_name.strip()
    tl = f"{prefix} · {name}" if name else prefix

    # Overlap guard — measure both at the footer font (9px mono, 0.02em) and, if
    # they would collide, right-truncate the variable-length session name.
    tr_w = measure_text(tr, font_family=_MONO, font_size=9.0, font_weight=400, letter_spacing_em=0.02)
    tl_w = measure_text(tl, font_family=_MONO, font_size=9.0, font_weight=400, letter_spacing_em=0.02)
    if name and tl_w + 16.0 + tr_w > CONTENT_W:
        prefix_w = measure_text(
            f"{prefix} · ", font_family=_MONO, font_size=9.0, font_weight=400, letter_spacing_em=0.02
        )
        budget = CONTENT_W - 16.0 - tr_w - prefix_w
        name = _truncate(name, budget=budget, font_family=_MONO, font_size=9.0, font_weight=400)
        tl = f"{prefix} · {name}" if name else prefix

    return Footer(
        rule_y=round(rule_y, 1),
        tl=tl,
        tl_y=footer_top_y,
        tr=tr,
        tr_y=footer_top_y,
        bl="Cost is an estimate based on public per-token rates.",
        bl_y=footer_bottom_y,
        br="hyperweave.app",
        br_y=footer_bottom_y,
    )


# --------------------------------------------------------------------------- #
# Shared text helpers                                                          #
# --------------------------------------------------------------------------- #


def _truncate(text: str, *, budget: float, font_family: str, font_size: float, font_weight: int) -> str:
    """Right-truncate ``text`` with an ellipsis to fit ``budget`` px."""
    if budget <= 0 or not text:
        return text
    if measure_text(text, font_family=font_family, font_size=font_size, font_weight=font_weight) <= budget:
        return text
    ell = "…"
    lo, hi, best = 0, len(text), ell
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = text[:mid].rstrip() + ell
        if measure_text(cand, font_family=font_family, font_size=font_size, font_weight=font_weight) <= budget:
            best = cand
            lo = mid + 1
        else:
            hi = mid - 1
    return best


# --------------------------------------------------------------------------- #
# context-load glyph prep (markers → ready-to-stamp shape geometry)            #
# --------------------------------------------------------------------------- #
#
# area.py hands back typed ResetMarker / legend records with anchor
# coordinates + a `kind`; it deliberately exports only shape CONSTANTS, never
# shape strings (it is colour-free, renderer-agnostic). Templates can't do
# arithmetic, so the resolver folds each marker into a concrete glyph dict
# (path / cx / cy / r) here — the same division of labor bar.py uses. This keeps
# the template a pure stamp and the geometry pinned to the specimen.


@dataclass(frozen=True, slots=True)
class CtxPlot:
    """Plot-box rectangle for the context panel (group-local)."""

    box_x: float
    box_y: float
    box_w: float
    box_h: float


@dataclass(frozen=True, slots=True)
class CtxGlyph:
    """One ready-to-stamp reset glyph. ``kind`` selects the template branch."""

    kind: str
    path: str = ""
    cx: float = 0.0
    cy: float = 0.0
    r: float = 0.0


@dataclass(frozen=True, slots=True)
class CtxLegendItem:
    """One ready-to-stamp legend item (swatch geometry + measured label x)."""

    kind: str
    label: str
    label_x: float
    swatch_x: float = 0.0
    swatch_x2: float = 0.0
    cx: float = 0.0
    path: str = ""


def _chevron_path(cx: float, marker_y: float) -> str:
    """Compact-reset chevron: 3-point polyline, tip GLYPH_LIFT above the curve."""
    tip_y = marker_y - GLYPH_LIFT
    top_y = tip_y - GLYPH_CHEVRON_H
    return f"M {cx - GLYPH_CHEVRON_W:.1f},{top_y:.1f} L {cx:.1f},{tip_y:.1f} L {cx + GLYPH_CHEVRON_W:.1f},{top_y:.1f}"


def _diamond_path(cx: float, cy: float, r: float) -> str:
    """Auto-reset (or peak) diamond: 4-point closed path centred at (cx, cy)."""
    return f"M {cx - r:.1f},{cy:.1f} L {cx:.1f},{cy - r:.1f} L {cx + r:.1f},{cy:.1f} L {cx:.1f},{cy + r:.1f} Z"


def _reset_glyph(marker: ResetMarker) -> CtxGlyph:
    """Convert a typed reset marker into a stampable glyph dict."""
    cx = marker.draw_x
    anchor_y = marker.y - GLYPH_LIFT
    if marker.kind == "clear":
        return CtxGlyph(kind="clear", cx=cx, cy=anchor_y, r=GLYPH_CIRCLE_R)
    if marker.kind == "auto":
        return CtxGlyph(kind="auto", path=_diamond_path(cx, anchor_y, GLYPH_DIAMOND_R))
    return CtxGlyph(kind="compact", path=_chevron_path(cx, marker.y))


def build_context_glyphs(context_load: ContextLoad) -> dict[str, Any]:
    """Build all stampable context-load geometry from the area layout.

    Returns the plot box, the per-reset glyph list, the peak up-diamond path,
    and the legend item list (each with concrete swatch geometry + the measured
    label_x that area.py already computed). The template stamps these directly.
    """
    lay = context_load.layout
    # Plot box: invert the inset math area.py applied (plot_top = box_y + top_inset,
    # plot_bottom = box_y + box_h - bottom_inset).
    box_x = lay.plot_left
    box_y = lay.plot_top - PLOT_TOP_INSET
    box_w = lay.plot_right - lay.plot_left
    box_h = (lay.plot_bottom + PLOT_BOTTOM_INSET) - box_y
    plot = CtxPlot(box_x=box_x, box_y=box_y, box_w=box_w, box_h=box_h)

    glyphs = [_reset_glyph(mk) for mk in lay.reset_markers]

    legend: list[CtxLegendItem] = []
    for item in lay.legend:
        if item.kind == "line":
            legend.append(
                CtxLegendItem(
                    kind="line",
                    label=item.label,
                    label_x=item.label_x,
                    swatch_x=item.swatch_x,
                    swatch_x2=item.swatch_x + LEGEND_LINE_SWATCH_W,
                )
            )
        elif item.kind == "clear":
            legend.append(
                CtxLegendItem(kind="clear", label=item.label, label_x=item.label_x, cx=item.swatch_x + GLYPH_CIRCLE_R)
            )
        elif item.kind == "auto":
            legend.append(
                CtxLegendItem(
                    kind="auto",
                    label=item.label,
                    label_x=item.label_x,
                    path=_diamond_path(item.swatch_x + GLYPH_DIAMOND_R, lay.legend_y, GLYPH_DIAMOND_R),
                )
            )
        elif item.kind == "error":
            legend.append(CtxLegendItem(kind="error", label=item.label, label_x=item.label_x, cx=item.swatch_x + 2.2))
        else:  # compact
            legend.append(
                CtxLegendItem(
                    kind="compact",
                    label=item.label,
                    label_x=item.label_x,
                    path=_chevron_legend_path(item.swatch_x, lay.legend_y),
                )
            )

    return {
        "ctx_plot": plot,
        "ctx_reset_glyphs": glyphs,
        "ctx_legend": legend,
        "ctx_legend_y": lay.legend_y,
        "ctx_legend_text_y": lay.legend_y + 3.1,
    }


def _chevron_legend_path(swatch_x: float, y: float) -> str:
    """Legend chevron: same 3-point shape, centred in its swatch slot at y."""
    cx = swatch_x + GLYPH_CHEVRON_W
    tip_y = y + 2.0
    top_y = y - 2.0
    return f"M {cx - GLYPH_CHEVRON_W:.1f},{top_y:.1f} L {cx:.1f},{tip_y:.1f} L {cx + GLYPH_CHEVRON_W:.1f},{top_y:.1f}"


# --------------------------------------------------------------------------- #
# Layout orchestration — the content-aware y-cursor                           #
# --------------------------------------------------------------------------- #
#
# Zones flow from a y-cursor: each zone's top = where the prior zone ended, and
# the footer + card height FOLLOW the content. The full-session case (all zones,
# 5 tool rows + overflow, full context) reproduces the specimen's 578px exactly;
# a sparse session compacts with no dead band before the footer. This mirrors
# the stat card's compute_stats_card_height discipline (height in the resolver
# envelope → viewBox), applied to the receipt's eight zones.


@dataclass(frozen=True, slots=True)
class ReceiptLayout:
    """All zone dataclasses + the content-derived card height (the cursor pass)."""

    identity: Identity
    model_mix: ModelMix
    hero: Hero
    metrics: Metrics
    tool_spend: ToolSpend
    cost_by_model: CostByModel
    context_load: ContextLoad
    footer: Footer
    height: int


def compute_receipt_layout(
    payload: dict[str, Any],
    *,
    palette: dict[str, str],
    glyph_id: str,
    wordmark: str,
    display_name: str,
    timestamp: str,
) -> ReceiptLayout:
    """Thread the y-cursor through every zone and derive the card height.

    The header band (identity + model-mix) and hero/metrics are always present.
    Tool-spend's height scales with its row count. Cost-by-model renders iff the
    session has models; context-load iff it has occupancy data. The footer +
    closing rule follow the last present content zone, and the card height is the
    footer baseline plus the bottom-edge gap. For the full specimen session this
    yields 578; for a sparse session it yields a tight card.
    """
    # ── Header band (always; fixed at the top of the card) ─────────────────
    identity = build_identity(glyph_id=glyph_id, wordmark=wordmark, palette=palette)
    model_mix = build_model_mix(payload, palette=palette)

    # ── Hero → metrics → rule (always) ─────────────────────────────────────
    cursor = _BAND_HEADER_H  # hero cost baseline
    hero = build_hero(payload, palette=palette, cost_baseline_y=cursor)
    cursor += _HERO_TO_METRICS  # metrics baseline
    metrics = build_metrics(payload, palette=palette, baseline_y=cursor)
    cursor += _METRICS_TO_RULE  # the hairline rule below metrics (receipt_rule_ys re-derives its y)

    # ── Tool-spend (variable height) ───────────────────────────────────────
    ts_header_y = round(cursor + _RULE_TO_TS_HEADER, 1)
    tool_spend = build_tool_spend(payload, palette=palette, header_y=ts_header_y)
    cursor = tool_spend.rule_y  # the tool-spend closing rule

    # ── Cost-by-model (present iff models) ─────────────────────────────────
    cbm_eyebrow_y = round(cursor + _TS_RULE_TO_CBM, 1)
    cost_by_model = build_cost_by_model(payload, palette=palette, eyebrow_y=cbm_eyebrow_y)
    if cost_by_model.show:
        cursor = cost_by_model.rows_bottom  # last model-row baseline
        # Rich mode lays a closing rule then more air before the chart; plain mode
        # flows straight in. Both gaps are measured from the last row baseline.
        ctx_gap = _CBM_RICH_ROWS_TO_CTX if cost_by_model.rich else _CBM_ROWS_TO_CTX
    else:
        # No shelf: the chart (or footer) follows the tool-spend rule directly.
        ctx_gap = _RULE_TO_CTX

    # ── Context-load (present iff occupancy data) ──────────────────────────
    ctx_translate_y = round(cursor + ctx_gap, 1)
    context_load = build_context_load(payload, palette=palette, translate_y=ctx_translate_y)
    if context_load.show:
        cursor = round(ctx_translate_y + _CTX_PANEL_BOTTOM, 1)  # legend caption baseline

    # ── Footer (always; follows the last content zone) ─────────────────────
    closing_rule_y = round(cursor + _CONTENT_TO_CLOSING_RULE, 1)
    footer = build_footer(
        payload,
        palette=palette,
        display_name=display_name,
        timestamp=timestamp,
        rule_y=closing_rule_y,
    )
    height = round(footer.bl_y + _FOOTER_BOTTOM_TO_EDGE)

    return ReceiptLayout(
        identity=identity,
        model_mix=model_mix,
        hero=hero,
        metrics=metrics,
        tool_spend=tool_spend,
        cost_by_model=cost_by_model,
        context_load=context_load,
        footer=footer,
        height=height,
        # rule positions the template stamps (the metrics + tool-spend hairlines).
    )


def receipt_rule_ys(layout: ReceiptLayout) -> tuple[float, float]:
    """Return the two inter-zone hairline y's (metrics rule, tool-spend rule).

    The metrics rule sits ``_METRICS_TO_RULE`` below the metrics baseline; the
    tool-spend rule is the zone's own ``rule_y``. Exposed so the resolver can
    pass them to the template (which stamps the two ``<line>`` rules)."""
    metrics_rule_y = round(layout.metrics.y + _METRICS_TO_RULE, 1)
    return metrics_rule_y, layout.tool_spend.rule_y
