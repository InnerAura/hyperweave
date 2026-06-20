"""Raw thermal-tape receipt — layout pass (the meme-receipt chassis).

The ``raw`` genome renders the SAME ``receipt/1`` payload as the primer receipt,
but on a fixed 300x835 monospace register-tape substrate (``raw-receipt-v2.svg``)
rather than the 800x578 editorial card. This module owns the TAPE geometry: a
vertical y-cursor walks line by line, each line a left label + a right-aligned
value at one baseline. The template only stamps pre-computed coordinates — zero
arithmetic in Jinja (project invariant).

The data is read straight off the canonical ``receipt/1`` payload (top-level
``calls`` / ``errors`` / ``turns`` / ``active_min``; nested ``tokens`` /
``context`` / ``tools[]`` / ``models[]``), so there is no separate parser path —
this is a second chassis over Workstream C's section DATA. Numeric formatters and
the sparse-tools coercion are reused from :mod:`receipt_sections`; JetBrains Mono
is monospace so ``measure_text`` is exact (no shrink-to-fit guessing).

Specimen anchors (``raw-receipt-v2.svg``)::

    canvas        300 x 835, fixed paper substrate, adaptation OFF
    rails         left x18 / right x282 / centre x150
    perforation   top y10 / bottom y827 (dashed rule, 0.7 opacity)
    grain         feTurbulence fractalNoise baseFrequency 0.9, 3.5% ink wash
    header        HW diamond + HYPERWEAVE wordmark + store lines (centred)
    session       SESSION id · ts; CASHIER line; REGISTER/PEAK/CLEARED line
    tool columns  TOOL QTY (left) / TOKENS (right) + '% of basket' sublines
    overflow      '+N OTHERS xM' collapse row with the rolled-up names
    void          VOID / FAILED CALLS header + per-tool 'VOID NAME-SUFFIX xE'
    ledger        TOKENS IN / OUT / CACHED / WRITTEN / SUBTOTAL / VOIDED CALLS
    total         TOTAL DUE + grand cost; est. disclaimer line
    tender        TENDERED + per-model 'NAME · role · pct' / '$cost'
    barcode       machine-readable furniture at the optical base (session hash)
    footer        HW · id · MADE BY AGENTS · hyperweave.app + curl shadow
"""
# ruff: noqa: RUF001, RUF003  ×/−/· are the deliberate till glyphs (quantity,
# void, separator) the receipt specimen prints — never plain x / - / dot.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hyperweave.core.text import measure_text

from .receipt_sections import (
    _coerce_tools,
    _fmt_money,
    _fmt_money_cents,
    _fmt_tok,
)

# --------------------------------------------------------------------------- #
# Chassis constants (single source of truth — pinned to the 300x835 specimen)  #
# --------------------------------------------------------------------------- #

RAW_W = 300.0
# Legacy reference: the original prototype was a fixed 300x835 tape. The height
# is now content-derived (the barcode + footer ride a feed-margin below the last
# data line), so 835 is just the rough magnitude of a long full session — never
# a hard canvas. Kept for the prototype-provenance reference + a sanity bound.
RAW_H = 835.0

# Paper card inset (the dashed perforation sits just inside it).
CARD_INSET = 6.0
CARD_X = CARD_INSET
CARD_Y = CARD_INSET
CARD_W = RAW_W - 2 * CARD_INSET  # 288

# Itemisation rails (the ~12% thermal-paper margins).
LEFT_RAIL = 18.0
RIGHT_RAIL = 282.0
CENTER_X = 150.0
SUB_INDENT = 24.0  # '% of basket' sublines sit one tab in

# Inner-rule rails (the dashed dividers between sections).
RULE_LEFT = 16.0
RULE_RIGHT = 284.0
SUB_FONT = 7.5  # '% of basket' subline + disclaimer + footer caption size

# Barcode/footer feed-margin deltas (content-derived — the furniture FOLLOWS the
# content cursor instead of riding a fixed 835 base). The feed margin is the
# blank thermal tape between the last data line and the barcode rule; the rest
# preserve the specimen's vertical spacing (rule 765 → bars 773 → footer 807 →
# perf 827). A sparse session stays short; a rich one runs long.
_FEED_MARGIN = 28.0  # last data line + 10 → barcode rule (thermal feed gap)
_BARCODE_RULE_TO_BARS = 8.0  # specimen: rule 765 → barcode group 773
_BARS_TO_FOOTER = 34.0  # specimen: barcode 773 → footer 807
_FOOTER_TO_PERF = 20.0  # specimen: footer 807 → bottom perforation 827

# Fixed shape geometry the template stamps — card rect, rails, barcode bar
# height, curl rect width. Kept HERE (not as template literals) so the template
# carries zero geometry numbers (stencil invariant: compose owns geometry). The
# values reproduce the specimen exactly. Per-row/section y's that DEPEND on the
# data live on the dataclass instead.
RAW_GEOM: dict[str, float] = {
    "card_x": CARD_X,
    "card_y": CARD_Y,
    "card_w": CARD_W,
    "card_rx": 1.5,
    "left_rail": LEFT_RAIL,
    "right_rail": RIGHT_RAIL,
    "sub_indent": SUB_INDENT,
    "sub_font": SUB_FONT,
    "barcode_h": 22.0,
    "barcode_y0": 0.0,
}

# The HW diamond sigil drawn in the header lockup. The path is the shared brand
# silhouette (glyph-local 0..64 space, placed under a translate+scale); the two
# centre dots are the recessed core. Coordinates are glyph-local constants the
# template stamps inside the scaled group — pinned to the specimen.
RAW_DIAMOND_PATH = (
    "M32 3 C39.25 10.25 53.75 24.75 61 32 C53.75 39.25 39.25 53.75 32 61 "
    "C24.75 53.75 10.25 39.25 3 32 C10.25 24.75 24.75 10.25 32 3 Z "
    "M26.56 10.25 15.69 21.12 C10.25 26.56 10.25 37.44 15.69 42.88 "
    "L26.56 53.75 37.44 53.75 48.31 42.88 C53.75 37.44 53.75 26.56 48.31 21.12 "
    "L37.44 10.25 Z"
)
RAW_DIAMOND_DOTS: tuple[dict[str, float], ...] = (
    {"cx": 32.0, "cy": 32.0, "r": 3.2, "opacity": 0.15},
    {"cx": 32.0, "cy": 32.0, "r": 2.0, "opacity": 1.0},
)

_MONO = "JetBrains Mono"

# Monospace font sizes mirroring the specimen's .xl/.lg/.md/.sm classes.
_FS_XL = 16.0
_FS_LG = 11.0
_FS_MD = 9.0
_FS_SM = 7.5

# A short suffix per tool-class so a VOID row reads as a register return line
# ('VOID EDIT-RETRY x6'). Maps the receipt/1 tool ``class`` to the failure verb;
# unknown classes fall back to FAIL.
_VOID_SUFFIX: dict[str, str] = {
    "mutate": "RETRY",
    "execute": "FAIL",
    "explore": "FAIL",
    "coordinate": "ABORT",
    "reflect": "FAIL",
}
_VOID_SUFFIX_DEFAULT = "FAIL"


# --------------------------------------------------------------------------- #
# Row primitives (the y-cursor stamps these)                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TapeRule:
    """A horizontal divider between tape sections.

    ``kind`` selects the stroke weight + dash pattern in the template:
    ``perf`` (torn-from-roll perforation), ``dash`` (light dotted divider),
    ``solid`` (the heavy ink totals rule).
    """

    y: float
    kind: str  # perf | dash | solid


@dataclass(frozen=True, slots=True)
class TapeLine:
    """One centred header/sub line (store lockup, session, cashier, savings).

    ``tone`` picks the fill (``ink`` / ``faint`` / ``accent``); ``size`` the
    font size; ``weight`` the font weight; ``bold_to`` (when > 0) renders the
    leading ``bold_to`` chars bold (the TENDER model name) before the faint
    remainder — but raw keeps lines simple, so this is for the model tender rows.
    """

    text: str
    x: float
    y: float
    size: float
    weight: int
    tone: str
    anchor: str  # start | middle | end


@dataclass(frozen=True, slots=True)
class TapeRow:
    """A left-label / right-value itemisation row at one baseline.

    The bread-and-butter tape primitive: the label is start-anchored at the
    left rail, the value end-anchored at the right rail, both on ``y``. ``sub``
    (optional) is the '% of basket' style note rendered one line below at the
    sub indent. Tones select fills; ``value_tone`` defaults to the label tone.
    """

    label: str
    value: str
    y: float
    label_size: float
    value_size: float
    label_weight: int
    value_weight: int
    label_tone: str
    value_tone: str
    sub: str = ""
    sub_y: float = 0.0


@dataclass(frozen=True, slots=True)
class TenderRow:
    """One TENDERED model line: bold NAME + faint ' · role · pct' / '$cost'."""

    name: str
    detail: str
    cost: str
    y: float
    tone: str  # ink (lead models) | faint (trailing model)


@dataclass(frozen=True, slots=True)
class BarcodeBar:
    """One barcode stripe (x offset within the barcode group + width)."""

    x: float
    w: float


@dataclass(frozen=True, slots=True)
class RawReceipt:
    """The fully-laid-out thermal tape. Every coordinate is pre-computed."""

    # Palette (literal hex — baked, never CSS vars; matches the specimen so the
    # paper survives static renderers and the grain filter floods correctly).
    paper: str
    ink: str
    faint: str
    rule: str
    accent: str
    # Baked vellum-onionskin material colours (sheen highlights + cockle light).
    sheen_dim: str
    sheen_bright: str
    sheen_shadow: str
    cockle_light: str

    # Paper card body height (content-derived: total_height − 2*inset; the rect
    # the grain filter floods).
    card_h: float

    # Header lockup.
    glyph_translate_x: float
    glyph_translate_y: float
    glyph_scale: float
    header_lines: list[TapeLine]

    # Session + cashier block.
    session_lines: list[TapeLine]

    # Tool itemisation (TOOL QTY / TOKENS columns + sublines + overflow).
    tool_header: TapeRow
    tool_rows: list[TapeRow]

    # VOID / FAILED CALLS breakdown.
    void_header: TapeRow
    void_rows: list[TapeRow]
    show_void: bool

    # Token ledger (IN / OUT / CACHED / WRITTEN / SUBTOTAL / VOIDED CALLS).
    ledger_rows: list[TapeRow]

    # Grand total.
    total_label: str
    total_value: str
    total_y: float
    total_label_size: float
    total_value_size: float
    disclaimer: str
    disclaimer_y: float

    # Tendered models.
    tender_header: TapeLine
    tender_count: str
    tender_count_y: float
    tender_rows: list[TenderRow]
    tender_summary: str
    tender_summary_y: float
    show_tender: bool

    # Barcode + footer.
    barcode_translate_x: float
    barcode_translate_y: float
    barcode_bars: list[BarcodeBar]
    footer_line: TapeLine

    # Content-derived canvas height (the cursor walks content, then the barcode +
    # footer + perforation follow with a thermal feed-margin, so a sparse session
    # produces a short receipt and a rich one a long tape — no fixed-835 dead
    # blank). Feeds the resolver envelope → viewBox.
    total_height: float

    # Section rules (drawn in document order between the blocks above).
    rules: list[TapeRule] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Build                                                                        #
# --------------------------------------------------------------------------- #


def _short_id(session_id: str) -> str:
    """First 8 chars of the session id, upper-cased (the till SESSION number)."""
    return session_id[:8].upper() if session_id else "00000000"


def _fmt_ts(payload: dict[str, Any]) -> str:
    """'YYYY-MM-DD HH:MM' from the payload's start time (best-effort)."""
    from datetime import datetime

    iso = str(payload.get("started") or payload.get("ts") or "")
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return ""


def _void_label(tool_name: str, tool_class: str) -> str:
    """'Edit'/'mutate' → 'VOID EDIT-RETRY' (the register return line)."""
    suffix = _VOID_SUFFIX.get(tool_class, _VOID_SUFFIX_DEFAULT)
    return f"VOID {tool_name.upper()}-{suffix}"


def build_raw_receipt(payload: dict[str, Any], *, palette: dict[str, str]) -> RawReceipt:
    """Fold the ``receipt/1`` payload into the thermal-tape layout.

    A single y-cursor walks the tape top to bottom, advancing per line; section
    dividers are emitted as ``TapeRule`` records as the cursor crosses them. The
    tool list is collapsed top-N + '+N OTHERS' (the remainder-token accounting
    C established), and the per-tool VOID breakdown is sorted by error count.
    """
    paper = palette["paper"]
    ink = palette["ink"]
    faint = palette["faint"]
    rule = palette["rule"]
    accent = palette["accent"]
    sheen_dim = palette["sheen_dim"]
    sheen_bright = palette["sheen_bright"]
    sheen_shadow = palette["sheen_shadow"]
    cockle_light = palette["cockle_light"]

    rules: list[TapeRule] = []

    # ── Header lockup (HW diamond + wordmark + store lines), all centred ────
    # The diamond is the shared HW sigil at 0.33 scale; the wordmark + three
    # store lines sit beneath it. Coordinates pinned to the specimen.
    session_id = str(payload.get("session") or "")
    short = _short_id(session_id)
    ts = _fmt_ts(payload)
    branch = str(payload.get("branch") or "main")
    register_path = f"/receipts/{short.lower()}" + (f" · {branch}" if branch else "")

    rules.append(TapeRule(y=10.0, kind="perf"))
    header_lines = [
        TapeLine("HYPERWEAVE", CENTER_X, 52.0, _FS_XL, 700, "ink", "middle"),
        TapeLine("SELF-CONTAINED VISUAL ARTIFACTS", CENTER_X, 65.0, _FS_SM, 500, "faint", "middle"),
        TapeLine("hyperweave.app · STORE #0001", CENTER_X, 76.0, _FS_SM, 500, "faint", "middle"),
        TapeLine(f"REGISTER {register_path}", CENTER_X, 87.0, _FS_SM, 500, "faint", "middle"),
    ]

    # ── Session + cashier block ─────────────────────────────────────────────
    rules.append(TapeRule(y=99.0, kind="dash"))
    agent = _resolve_agent_name(payload)
    turns = int(payload.get("turns", 0) or 0)
    active = int(payload.get("active_min", 0) or 0)
    ctx = payload.get("context", {}) or {}
    window = int(ctx.get("window", 0) or 0)
    peak = int(ctx.get("peak_ctx", 0) or 0)
    resets = len(ctx.get("events", []) or [])

    session_title = f"SESSION {short}" + (f" · {ts}" if ts else "")
    session_lines = [
        TapeLine(session_title, CENTER_X, 115.0, _FS_MD, 500, "ink", "middle"),
        TapeLine(f"CASHIER: {agent} · {turns} TURNS · {active}m", CENTER_X, 127.0, _FS_SM, 500, "faint", "middle"),
        TapeLine(
            f"REGISTER {_fmt_ctx(window)} · PEAK {_fmt_ctx(peak)} · CLEARED {resets}×",
            CENTER_X,
            138.0,
            _FS_SM,
            500,
            "faint",
            "middle",
        ),
    ]

    # ── Tool itemisation (TOOL QTY / TOKENS columns) ────────────────────────
    rules.append(TapeRule(y=148.0, kind="dash"))
    tool_header = TapeRow(
        label="TOOL QTY",
        value="TOKENS",
        y=164.0,
        label_size=_FS_MD,
        value_size=_FS_MD,
        label_weight=500,
        value_weight=500,
        label_tone="ink",
        value_tone="ink",
    )

    tools = _coerce_tools(payload.get("tools"))
    working = int((payload.get("tokens", {}) or {}).get("working", 0) or 0)
    total_working = working or sum(int(t.get("tok", 0) or 0) for t in tools) or 1

    # Top-N token-bearing tools fit the band; the sparse tail collapses into a
    # '+N OTHERS' row whose tokens are the remainder of the working total (the
    # tail mostly carries no `tok`), matching the specimen's '+6 OTHERS 74.3K'.
    token_tools = [t for t in tools if int(t.get("tok", 0) or 0) > 0]
    _MAX_TOOL_ROWS = 5
    if len(token_tools) <= _MAX_TOOL_ROWS and len(tools) <= _MAX_TOOL_ROWS:
        head = tools
        tail: list[dict[str, Any]] = []
    else:
        head = token_tools[: _MAX_TOOL_ROWS - 1]
        head_names = {str(t.get("name", "")) for t in head}
        tail = [t for t in tools if str(t.get("name", "")) not in head_names]

    tool_rows: list[TapeRow] = []
    y = 180.0
    row_pitch = 27.0  # value line + subline + breathing room (specimen cadence)
    for tool in head:
        name = str(tool.get("name", ""))
        tok = int(tool.get("tok", 0) or 0)
        calls = int(tool.get("calls", 0) or 0)
        pct = round(tok / total_working * 100) if total_working > 0 else 0
        tool_rows.append(
            TapeRow(
                label=f"{name.upper()} ×{calls}",
                value=_fmt_tok(tok),
                y=y,
                label_size=_FS_LG,
                value_size=_FS_LG,
                label_weight=700,
                value_weight=700,
                label_tone="ink",
                value_tone="ink",
                sub=f"{pct}% of basket",
                sub_y=y + 11.0,
            )
        )
        y += row_pitch

    if tail:
        shown_tok = sum(int(t.get("tok", 0) or 0) for t in head)
        agg_tok = max(0, total_working - shown_tok) if working else sum(int(t.get("tok", 0) or 0) for t in tail)
        agg_calls = sum(int(t.get("calls", 0) or 0) for t in tail)
        agg_pct = round(agg_tok / total_working * 100) if total_working > 0 else 0
        # The collapsed names list (lower-cased short tokens), truncated to the
        # subline budget so a long tail never overruns the rail.
        names = " ".join(str(t.get("name", "")).split("-")[0].lower() for t in tail)
        sub = _fit(f"{agg_pct}% · {names}", budget=RIGHT_RAIL - SUB_INDENT, size=_FS_SM)
        tool_rows.append(
            TapeRow(
                label=f"+{len(tail)} OTHERS ×{agg_calls}",
                value=_fmt_tok(agg_tok),
                y=y,
                label_size=_FS_MD,
                value_size=_FS_MD,
                label_weight=500,
                value_weight=500,
                label_tone="faint",
                value_tone="faint",
                sub=sub,
                sub_y=y + 11.0,
            )
        )
        y += row_pitch

    # ── VOID / FAILED CALLS breakdown ───────────────────────────────────────
    void_rule_y = y - 4.0
    rules.append(TapeRule(y=void_rule_y, kind="dash"))
    total_errors = int(payload.get("errors", 0) or 0)
    y = void_rule_y + 15.0

    void_header = TapeRow(
        label="VOID / FAILED CALLS",
        value=f"−{total_errors}",
        y=y,
        label_size=_FS_SM,
        value_size=_FS_SM,
        label_weight=500,
        value_weight=500,
        label_tone="faint",
        value_tone="accent",
    )
    y += 14.0

    # Per-tool error rows, sorted by error count descending (the heaviest void
    # leads). Sparse tools without `err` are skipped — only failing tools list.
    failing = sorted(
        ((str(t.get("name", "")), str(t.get("class", "")), int(t.get("err", 0) or 0)) for t in tools),
        key=lambda r: r[2],
        reverse=True,
    )
    void_rows: list[TapeRow] = []
    for name, cls, err in failing:
        if err <= 0:
            continue
        void_rows.append(
            TapeRow(
                label=_void_label(name, cls),
                value=f"×{err}",
                y=y,
                label_size=_FS_MD,
                value_size=_FS_MD,
                label_weight=500,
                value_weight=500,
                label_tone="ink",
                value_tone="accent",
            )
        )
        y += 14.0
    show_void = bool(void_rows)
    if not show_void:
        # No failures: pull the cursor back so the ledger doesn't leave a gap.
        y = void_header.y + 14.0

    # ── Token ledger ────────────────────────────────────────────────────────
    ledger_rule_y = y - 4.0
    rules.append(TapeRule(y=ledger_rule_y, kind="dash"))
    y = ledger_rule_y + 15.0

    tokens: dict[str, Any] = payload.get("tokens", {}) or {}
    ledger_specs = [
        ("TOKENS IN", _fmt_tok(int(tokens.get("in", 0) or 0)), "ink"),
        ("TOKENS OUT", _fmt_tok(int(tokens.get("out", 0) or 0)), "ink"),
        ("CACHED", _fmt_tok(int(tokens.get("cache_read", 0) or 0)), "ink"),
        ("WRITTEN", _fmt_tok(int(tokens.get("cache_write", 0) or 0)), "ink"),
        ("SUBTOTAL", f"{_fmt_tok(int(tokens.get('total', 0) or 0))} tok", "ink"),
        ("VOIDED CALLS", str(total_errors), "accent"),
    ]
    ledger_rows: list[TapeRow] = []
    for label, value, value_tone in ledger_specs:
        ledger_rows.append(
            TapeRow(
                label=label,
                value=value,
                y=y,
                label_size=_FS_MD,
                value_size=_FS_MD,
                label_weight=500,
                value_weight=500,
                label_tone="ink",
                value_tone=value_tone,
            )
        )
        y += 15.0

    # ── Grand total ─────────────────────────────────────────────────────────
    total_rule_y = y - 4.0
    rules.append(TapeRule(y=total_rule_y, kind="solid"))
    y = total_rule_y + 18.0
    cost = payload.get("cost_usd", 0)
    total_value = _fmt_money_cents(cost)
    total_y = y
    calls = int(payload.get("calls", 0) or 0)
    stages = int(payload.get("stages", 0) or 0)
    disclaimer = f"est. at public per-token rates · {calls} calls · {stages} stages"
    disclaimer_y = y + 12.0

    # ── Tendered models ─────────────────────────────────────────────────────
    tender_rule_y = disclaimer_y + 8.0
    rules.append(TapeRule(y=tender_rule_y, kind="solid"))
    y = tender_rule_y + 16.0
    models: list[dict[str, Any]] = list(payload.get("models") or [])
    tender_header = TapeLine("TENDERED", LEFT_RAIL, y, _FS_LG, 700, "ink", "start")
    tender_count = f"{len(models)} MODEL" + ("S" if len(models) != 1 else "")
    tender_count_y = y
    y += 15.0

    tender_rows: list[TenderRow] = []
    last_idx = len(models) - 1
    for i, m in enumerate(models):
        name = str(m.get("name", "")).upper()
        role = str(m.get("role", ""))
        pct = int(m.get("cost_pct", 0) or 0)
        detail_bits = [role] if role else []
        detail_bits.append(f"{pct}%")
        detail = " · " + " · ".join(detail_bits)
        tender_rows.append(
            TenderRow(
                name=name,
                detail=detail,
                cost=_fmt_money_cents(m.get("cost_usd", 0)),
                y=y,
                tone="faint" if i == last_idx and len(models) > 1 else "ink",
            )
        )
        y += 15.0

    dominant = str(payload.get("dominant") or (models[0].get("name") if models else ""))
    dom_pct = int(models[0].get("cost_pct", 0) or 0) if models else 0
    tender_summary = f"{dominant} dominant · {dom_pct}% of charge" if models else ""
    tender_summary_y = y
    show_tender = bool(models)

    # ── Barcode + footer (FOLLOW the content cursor — content-derived tape) ──
    # The machine-readable furniture rides a thermal feed-margin below the last
    # data line, NOT a fixed optical base: a sparse session yields a short
    # receipt and a rich one a long tape, with no dead blank (the fixed-835 gag
    # opened a void on short sessions — the visual-review bug). The feed-edge
    # curl still fills the margin between the last line and the barcode rule, so
    # the tape keeps its thermal character; it's just bounded by content now.
    content_end_y = round((tender_summary_y if show_tender else tender_count_y) + 10.0, 1)
    barcode_rule_y = round(content_end_y + _FEED_MARGIN, 1)
    rules.append(TapeRule(y=barcode_rule_y, kind="dash"))
    barcode_bars, barcode_w = _barcode_bars(short)
    barcode_translate_x = round((RAW_W - barcode_w) / 2.0, 1)
    barcode_translate_y = round(barcode_rule_y + _BARCODE_RULE_TO_BARS, 1)

    footer_y = round(barcode_translate_y + _BARS_TO_FOOTER, 1)
    footer_line = TapeLine(
        f"HW · {short} · MADE BY AGENTS · hyperweave.app",
        CENTER_X,
        footer_y,
        _FS_SM,
        500,
        "faint",
        "middle",
    )
    bottom_perf_y = round(footer_y + _FOOTER_TO_PERF, 1)
    rules.append(TapeRule(y=bottom_perf_y, kind="perf"))

    # Content-derived canvas: the perforation sits CARD_INSET above the bottom
    # edge, so the total height is the perf + inset. The paper card body runs
    # from CARD_Y to that bottom (card_h = total - 2*inset).
    total_height = round(bottom_perf_y + CARD_INSET, 1)
    card_h = round(total_height - 2 * CARD_INSET, 1)

    return RawReceipt(
        paper=paper,
        ink=ink,
        faint=faint,
        rule=rule,
        accent=accent,
        sheen_dim=sheen_dim,
        sheen_bright=sheen_bright,
        sheen_shadow=sheen_shadow,
        cockle_light=cockle_light,
        card_h=card_h,
        glyph_translate_x=139.4,
        glyph_translate_y=13.0,
        glyph_scale=0.33,
        header_lines=header_lines,
        session_lines=session_lines,
        tool_header=tool_header,
        tool_rows=tool_rows,
        void_header=void_header,
        void_rows=void_rows,
        show_void=show_void,
        ledger_rows=ledger_rows,
        total_label="TOTAL DUE",
        total_value=total_value,
        total_y=total_y,
        total_label_size=_FS_LG,
        total_value_size=_FS_XL,
        disclaimer=disclaimer,
        disclaimer_y=disclaimer_y,
        tender_header=tender_header,
        tender_count=tender_count,
        tender_count_y=tender_count_y,
        tender_rows=tender_rows,
        tender_summary=tender_summary,
        tender_summary_y=tender_summary_y,
        show_tender=show_tender,
        barcode_translate_x=barcode_translate_x,
        barcode_translate_y=barcode_translate_y,
        barcode_bars=barcode_bars,
        footer_line=footer_line,
        total_height=total_height,
        rules=rules,
    )


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


# Model-family prefixes that resolve a payload model to the Codex runtime name.
# Mirrors receipt.py's identity inference: gpt/codex/o1.. → Codex, else Claude.
_CODEX_PREFIXES = ("gpt", "codex", "o1", "o3", "o4")


def _resolve_agent_name(payload: dict[str, Any]) -> str:
    """CASHIER name from the payload runtime/model family (identity only)."""
    rt = str(payload.get("runtime") or "").strip().lower()
    if rt in ("codex", "openai-codex"):
        return "Codex"
    if rt in ("claude-code", "claude"):
        return "Claude Code"
    mdl = str(payload.get("model") or "").strip().lower()
    if any(mdl.startswith(p) for p in _CODEX_PREFIXES):
        return "Codex"
    return "Claude Code"


def _fmt_ctx(n: int) -> str:
    """Context-window magnitude in K (200000 → '200K'); 0 → '—'."""
    if n <= 0:
        return "—"
    if n >= 1000:
        return f"{round(n / 1000)}K"
    return str(n)


def _fit(text: str, *, budget: float, size: float) -> str:
    """Right-truncate (ellipsis) ``text`` to ``budget`` px at the mono ``size``."""
    if not text:
        return text
    if measure_text(text, font_family=_MONO, font_size=size, font_weight=500) <= budget:
        return text
    ell = "…"
    lo, hi, best = 0, len(text), ell
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = text[:mid].rstrip() + ell
        if measure_text(cand, font_family=_MONO, font_size=size, font_weight=500) <= budget:
            best = cand
            lo = mid + 1
        else:
            hi = mid - 1
    return best


# Barcode stripe pattern (deterministic from the session hash so the same
# session always prints the same code). Widths cycle through a Code-128-ish
# {1,2,3} px set; the gap between stripes is a constant 2px. The specimen drew
# 31 stripes; we derive the count + widths from the hash digits so every
# session's "machine-readable identity" differs while staying tape-furniture.
_BARCODE_WIDTHS = (2, 1, 3, 1, 2, 3, 1, 2, 3, 1)
_BARCODE_GAP = 2.0
_BARCODE_COUNT = 31


def _barcode_bars(session_short: str) -> tuple[list[BarcodeBar], float]:
    """Deterministic barcode stripes seeded by the session id (+ overall width)."""
    import hashlib

    digest = hashlib.sha256(session_short.encode("utf-8")).digest()
    bars: list[BarcodeBar] = []
    x = 0.0
    for i in range(_BARCODE_COUNT):
        seed = digest[i % len(digest)]
        w = float(_BARCODE_WIDTHS[seed % len(_BARCODE_WIDTHS)])
        bars.append(BarcodeBar(x=round(x, 1), w=w))
        x += w + _BARCODE_GAP
    total_w = round(x - _BARCODE_GAP, 1) if bars else 0.0
    return bars, total_w


def _palette_from_genome(genome: dict[str, Any]) -> dict[str, str]:
    """Pull the literal thermal palette off the (merged) raw genome.

    The raw genome maps the thermal-paper colours onto the standard genome
    fields (surface_0=paper, ink=ink, ink_secondary=faint, stroke=rule,
    accent=accent). The template stamps these as literal hex — never CSS vars —
    so the paper survives static renderers and the grain filter floods right
    (the var-in-attribute bug). All five are guaranteed present by GenomeSpec.
    """
    mat = genome.get("material", {}) or {}
    return {
        "paper": str(genome.get("surface_0", "#f3f1ea")),
        "ink": str(genome.get("ink", "#2d2a24")),
        "faint": str(genome.get("ink_secondary", "#918c80")),
        "rule": str(genome.get("stroke", "#ded8cc")),
        "accent": str(genome.get("accent", "#a64536")),
        # Baked vellum-onionskin material colours (the sheen highlights + the
        # cockle lighting) — literals, because var() never resolves in stop-color
        # / lighting-color attributes (static-renderer safety, same as the palette).
        "sheen_dim": str(mat.get("sheen_dim", "#d8d2c4")),
        "sheen_bright": str(mat.get("sheen_bright", "#fffffa")),
        "sheen_shadow": str(mat.get("sheen_shadow", "#4c4636")),
        "cockle_light": str(mat.get("cockle_light", "#fffefb")),
    }


# Re-export the standard money formatter for the envelope title (whole/2dp).
__all__ = [
    "RAW_H",
    "RAW_W",
    "BarcodeBar",
    "RawReceipt",
    "TapeLine",
    "TapeRow",
    "TapeRule",
    "TenderRow",
    "_fmt_money",
    "_palette_from_genome",
    "build_raw_receipt",
]
