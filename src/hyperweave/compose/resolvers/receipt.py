"""Receipt frame resolver — economics + context-window proof (the receipt specimen).

Consumes the canonical ``receipt/1`` payload (``spec.telemetry_data``, produced
by :func:`hyperweave.telemetry.receipt_payload.build_receipt_payload`) and the
**primer** genome, and computes one pure dataclass per visual zone. A separate
layout pass pins every coordinate from the specimen's ``hw:spatial-notes``
(``v04/specimens/receipts/receipts-v3/receipt_primer-*-v3.svg``); the template
only stamps pre-computed values — zero arithmetic in Jinja (project invariant).

The eight zones, in ``data-hw-zone`` order::

    identity      runtime glyph + wordmark           (y28)
    model-mix     right-aligned 3-line summary        (y17/33/46)
    hero          cost + EST + tokens·active          (y72)
    metrics       CALLS·STAGES·TURNS·ERRORS           (y93)
    tool-spend    header + per-tool proportional bars (rows y137 pitch 23)
    cost-by-model one proportion bar + keyed legend   (eyebrow y281, bar y288)
    context-load  burn-curve area (compose/chart/area) (translate 24,350)
    footer        TL/TR/BL/BR provenance + disclaimer  (y542/560)

**Genome / variant.** Geometry is byte-identical across all 8 primer variants;
only chromatics differ. The tool-spend ramp, cost-by-model segment ramp, and
the context-load area-fill + signal line draw from genome-declared per-variant
palette fields (``receipt_ramp[]``, ``receipt_area_fill``, ``receipt_signal``,
``receipt_track``, ``receipt_track_stroke``, ``receipt_grid_ink``,
``receipt_eyebrow``, ``receipt_label_ink``, ``receipt_value_ink``,
``receipt_dim_ink``). Semantic hues (error red) stay genome-invariant —
``accent_error`` is the only tone that shifts (``#EF4444`` dark / ``#DC2626``
light), exactly as the specimens do.

**Runtime → identity only.** The agent runtime selects the glyph + display
name (claude-code → ``claude-glyph`` / "Claude Code"; codex → ``codex-glyph`` /
"Codex"). It does NOT theme the receipt — that is the variant's job.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from .raw_sections import (
    RAW_DIAMOND_DOTS,
    RAW_DIAMOND_PATH,
    RAW_GEOM,
    RAW_W,
    RawReceipt,
    _palette_from_genome,
    build_raw_receipt,
)
from .receipt_sections import (
    CONTENT_W,
    LEFT_RAIL,
    RIGHT_RAIL,
    ReceiptLayout,
    build_context_glyphs,
    compute_receipt_layout,
    receipt_rule_ys,
)

if TYPE_CHECKING:
    from hyperweave.core.models import ComposeSpec

# Receipt chassis WIDTHS — pinned by the specimen viewBox (800px primer card /
# 300px raw thermal tape). The genome's ``paradigms.receipt`` slug selects the
# chassis: ``primer`` (editorial card) or ``raw`` (register tape). Both HEIGHTS
# are content-aware (the layout cursor stacks present zones), so only the width
# is a fixed chassis identity. ``RECEIPT_H`` is the full-session UPPER anchor —
# the maximal card (all zones, 5 tool rows + overflow, full context) lands here.
RECEIPT_W = 800
RECEIPT_H = 578  # full-session upper anchor (not a fixed canvas)

# Receipt paradigm slugs with a real ``frames/receipt/<slug>-content.j2`` partial.
# Adding another chassis means another entry here + the partial — config-driven
# dispatch, not a paradigm string-compare branch.
_RECEIPT_CHASSIS: frozenset[str] = frozenset({"primer", "raw"})

# Fixed shape geometry the template stamps — fixed columns, bar/swatch sizes,
# corner radii. Kept here (not as template literals) so the template carries
# zero geometry numbers (project stencil invariant: compose owns geometry). The
# values reproduce the specimen exactly. Per-row/section positions that DEPEND
# on data live on the zone dataclasses instead.
_GEOM: dict[str, float] = {
    "card_rx": 14.0,
    "card_border_x": 0.6,
    "card_border_y": 0.6,
    "card_border_rx": 14.0,
    "card_border_sw": 1.2,
    "rule_sw": 1.0,
    "rule_opacity": 0.1,
    "footer_rule_sw": 1.2,
    "footer_rule_opacity": 0.85,
    # tool-spend fixed columns
    "ts_bar_x": 150.0,
    "ts_bar_w": 322.0,
    "ts_bar_h": 9.0,
    "ts_bar_rx": 1.0,
    "ts_track_sw": 0.5,
    "ts_accent_w": 4.0,
    "ts_accent_h": 14.0,
    "ts_accent_rx": 0.5,
    "ts_pct_x": 484.0,
    "ts_tokens_x": 600.0,
    "ts_calls_x": 690.0,
    "ts_err_x": 762.0,
    "ts_err_w": 14.0,
    "ts_err_h": 12.5,
    "ts_err_rx": 2.0,
    "ts_err_sw": 0.6,
    "ts_err_text_x": 769.0,
    "ts_swatch_w": 6.0,
    "ts_swatch_h": 6.0,
    "ts_swatch_rx": 0.5,
    "ts_errswatch_w": 9.0,
    "ts_errswatch_h": 7.0,
    "ts_errswatch_rx": 1.5,
    # cost-by-model bar + per-model rows
    "cbm_bar_rx": 4.0,
    "cbm_border_sw": 0.6,
    "cbm_divider_w": 1.5,  # rich-mode segment-boundary hairline
    "cbm_marker_w": 8.0,  # row marker square edge
    "cbm_marker_rx": 1.5,
    # context-load plot + glyph radii (group-local)
    "ctx_box_rx": 6.0,
    "ctx_box_sw": 0.75,
    "ctx_baseline_sw": 0.8,
    "ctx_grid_sw": 0.6,
    "ctx_ceiling_sw": 0.75,
    "ctx_tick_sw": 0.9,
    "ctx_gridv_sw": 0.5,
    "ctx_line_sw": 2.0,
    "ctx_glyph_sw": 1.6,
    "ctx_circle_sw": 1.4,
    "ctx_legend_clear_r": 2.6,
}

# Agent identity → (glyph symbol id, display wordmark). Identity ONLY — never a
# theme. Keyed by runtime when one is supplied out-of-band; otherwise inferred
# from the payload's authoritative ``model`` family so the identity is fully
# self-contained in the receipt/1 payload (no extra wiring through ComposeSpec).
_RUNTIME_IDENTITY: dict[str, tuple[str, str]] = {
    "claude-code": ("claude-glyph", "Claude Code"),
    "claude": ("claude-glyph", "Claude Code"),
    "codex": ("codex-glyph", "Codex"),
    "openai-codex": ("codex-glyph", "Codex"),
}
_CLAUDE_IDENTITY: tuple[str, str] = ("claude-glyph", "Claude Code")
_CODEX_IDENTITY: tuple[str, str] = ("codex-glyph", "Codex")

# Model-family prefixes that map a payload ``model`` to its agent identity. The
# Claude family is the receipt's home runtime and the default when a model is
# unrecognized, so a receipt always carries an author mark.
_CODEX_MODEL_PREFIXES = ("gpt", "codex", "o1", "o3", "o4")


def _resolve_identity(runtime: str, model: str) -> tuple[str, str]:
    """Map runtime (if known) or the model family to a (glyph_id, wordmark) pair.

    Runtime wins when supplied (CLI/HTTP may pass it); otherwise the payload's
    ``model`` decides — ``gpt-*`` / ``codex-*`` / ``o1-*`` → Codex, everything
    else (the Claude family) → Claude Code.
    """
    rt = (runtime or "").strip().lower()
    if rt in _RUNTIME_IDENTITY:
        return _RUNTIME_IDENTITY[rt]
    mdl = (model or "").strip().lower()
    if any(mdl.startswith(p) for p in _CODEX_MODEL_PREFIXES):
        return _CODEX_IDENTITY
    return _CLAUDE_IDENTITY


def _palette(genome: dict[str, Any]) -> dict[str, str]:
    """Pull the per-variant receipt palette off the (already variant-merged) genome.

    The dispatcher merges ``variant_overrides[variant]`` into ``genome`` before
    the resolver runs (``resolver.py``), so every field below is already the
    resolved variant's value. ``validate_genome_variants`` guarantees presence
    at config load, so a missing key here is a programming error, not a runtime
    condition — we read with ``str(...)`` and let a KeyError surface loudly if
    the validation contract was bypassed (e.g. a hand-built test genome).
    """
    ramp_raw = genome.get("receipt_ramp") or []
    ramp = [str(c) for c in ramp_raw]
    return {
        "ramp": ramp,  # type: ignore[dict-item]  # ordered tier list (5 stops)
        "area_fill": str(genome.get("receipt_area_fill", "")),
        "signal": str(genome.get("receipt_signal", "")),
        "track": str(genome.get("receipt_track", "")),
        "track_stroke": str(genome.get("receipt_track_stroke", "")),
        "grid_ink": str(genome.get("receipt_grid_ink", "")),
        "eyebrow": str(genome.get("receipt_eyebrow", "")),
        "label_ink": str(genome.get("receipt_label_ink", "")),
        "value_ink": str(genome.get("receipt_value_ink", "")),
        "dim_ink": str(genome.get("receipt_dim_ink", "")),
        # Semantic red — genome-invariant indicator hue (#EF4444 dark / #DC2626
        # light). Sourced from accent_error so the one allowed tone shift tracks
        # the variant without leaking into the genome-identity ramp.
        "error": str(genome.get("accent_error", "#DC2626")),
        # Structural inks borrowed from the base genome chromatic set.
        "ink": str(genome.get("ink", "")),
        "ink_secondary": str(genome.get("ink_secondary", "")),
        "stroke": str(genome.get("stroke", "")),
        "surface_1": str(genome.get("surface_1", "")),
        "surface_2": str(genome.get("surface_2", "")),
        # Pure ink-on-accent (white in every primer variant) — the dominant model
        # name stamped inside a dark cost-by-model bar segment.
        "on_accent": str(genome.get("ink_on_accent", "")),
    }


def _fmt_footer_timestamp(start_iso: str) -> str:
    """Format an ISO start time to the footer's 'YYYY-MM-DD HH:MM' shape."""
    if not start_iso:
        return ""
    try:
        return datetime.fromisoformat(start_iso.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return ""


def _receipt_paradigm(genome: dict[str, Any]) -> str:
    """The receipt chassis slug from the genome's paradigms map (default primer).

    Config-driven dispatch (Principle 26): the slug selects the
    ``frames/receipt/<slug>-content.j2`` partial via the ``_RECEIPT_CHASSIS``
    membership check. Reading the paradigms config value (the same way matrix.py
    / diagram.py do) is the intended polymorphism — not a forbidden
    paradigm-string-equality branch.
    """
    paradigms = genome.get("paradigms") or {}
    slug = str(paradigms.get("receipt", "primer")) if isinstance(paradigms, dict) else "primer"
    return slug if slug in _RECEIPT_CHASSIS else "primer"


def _payload_projection(payload: dict[str, Any], *, wordmark: str) -> tuple[str, str, str, dict[str, Any]]:
    """Compact data-only ``hw:payload`` + the envelope's human fields.

    The embedded payload is the EXACT canonical bytes (payload discipline):
    emitted once, hashed into the hwz/1 envelope id by the context builder,
    never re-serialized. Returns ``(payload_json, title, intent, data)``. Shared
    by both chassis so a primer receipt and its raw twin carry an identical
    payload + envelope id for the same session (the round-trip contract).
    """
    import json as _json

    # A receipt cost is always a public-rate estimate (computed from
    # model-pricing.yaml, never billed truth), so the self-disclosure is a
    # schema invariant of the frame — guaranteed here even when a caller's
    # payload omits it. setdefault is a no-op on the canonical assembler path.
    embedded = dict(payload)
    embedded.setdefault("cost_basis", "public per-token rates")
    embedded.setdefault("estimate", True)
    payload_json = _json.dumps(embedded, separators=(",", ":"), ensure_ascii=False)
    cost_usd = payload.get("cost_usd", 0)
    session_id = str(payload.get("session") or "")
    title = f"{wordmark} session {session_id} — ${_fmt_money(cost_usd)}"
    intent = f"Single-glance economics and context-window history for one {wordmark} session."
    data = {
        "cost_usd": cost_usd,
        "tokens": payload.get("tokens", {}).get("total", 0),
        "cache_pct": _cache_pct(payload),
        "calls": payload.get("calls", 0),
        "errors": payload.get("errors", 0),
        "peak_ctx": payload.get("context", {}).get("peak_ctx", 0),
        "window": payload.get("context", {}).get("window", 0),
        "resets": len(payload.get("context", {}).get("events", []) or []),
        "top_tool": (payload.get("tools") or [{}])[0].get("name", ""),
    }
    return payload_json, title, intent, data


def resolve_receipt(
    spec: ComposeSpec,
    genome: dict[str, Any],
    profile: dict[str, Any],
    **_kw: Any,
) -> dict[str, Any]:
    """Resolve the ``receipt/1`` payload into the receipt's frame context.

    Dispatches on the genome's ``paradigms.receipt`` slug to one of two fixed
    chassis over the SAME data: ``primer`` (the 800x578 editorial card, eight
    chromatic variants) or ``raw`` (the 300x835 thermal register tape, fixed
    paper substrate). Both compute pure dataclasses with every coordinate
    pinned to their specimen and carry the identical ``hw:payload`` + envelope.
    Returns the standard ``{width, height, template, context}`` resolver
    envelope; the template dispatcher routes the chassis partial by paradigm.
    """
    payload: dict[str, Any] = dict(spec.telemetry_data or {})
    chassis = _receipt_paradigm(genome)
    if chassis == "raw":
        return _resolve_raw(spec, genome, payload)
    return _resolve_primer(spec, genome, payload)


def _resolve_primer(spec: ComposeSpec, genome: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Build the primer editorial-card chassis (8 chromatic variants).

    The layout is content-aware: a single ``compute_receipt_layout`` cursor pass
    stacks the present zones top-to-bottom and derives the card HEIGHT, which
    feeds the resolver envelope → viewBox. The full specimen session reproduces
    578; a sparse session compacts with the footer right behind the content.
    """
    palette = _palette(genome)
    substrate_kind = str(genome.get("substrate_kind") or genome.get("category", "light"))

    # ── Identity (runtime/model → glyph + wordmark; no theming) ────────────
    # The payload carries no runtime (its keys are the locked receipt/1 set), so
    # identity is inferred from the authoritative ``model`` family unless a
    # caller threaded a runtime out-of-band on telemetry_data.
    runtime = str(payload.get("runtime") or "")
    glyph_id, wordmark = _resolve_identity(runtime, str(payload.get("model") or ""))

    # ── Content-aware layout: one cursor pass over the present zones ───────
    layout: ReceiptLayout = compute_receipt_layout(
        payload,
        palette=palette,
        glyph_id=glyph_id,
        wordmark=wordmark,
        display_name=_footer_display_name(spec),
        timestamp=_fmt_footer_timestamp(str(payload.get("started") or "")),
    )

    payload_json, envelope_title, envelope_intent, envelope_data = _payload_projection(payload, wordmark=wordmark)

    context = _assemble_context(
        layout=layout,
        palette=palette,
        substrate_kind=substrate_kind,
        glyph_id=glyph_id,
        wordmark=wordmark,
        payload_json=payload_json,
        envelope_title=envelope_title,
        envelope_intent=envelope_intent,
        envelope_data=envelope_data,
        headline=str(payload.get("cost_usd", "")),
    )

    return {
        "width": RECEIPT_W,
        "height": layout.height,
        "template": "frames/receipt.svg.j2",
        "context": context,
    }


def _resolve_raw(spec: ComposeSpec, genome: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Build the raw thermal-tape chassis (300x835, fixed paper substrate).

    Consumes the SAME ``receipt/1`` section data as the primer chassis but
    computes vertical-flow tape geometry (the meme receipt). The palette is the
    literal thermal-paper hex off the merged raw genome; the carried payload +
    envelope are byte-identical to the primer twin for the same session.
    """
    raw_palette = _palette_from_genome(genome)
    tape: RawReceipt = build_raw_receipt(payload, palette=raw_palette)

    # Identity wordmark (for the envelope title only — the tape itself prints
    # the CASHIER line from the same inference, no glyph theming).
    runtime = str(payload.get("runtime") or "")
    _glyph_id, wordmark = _resolve_identity(runtime, str(payload.get("model") or ""))

    payload_json, envelope_title, envelope_intent, envelope_data = _payload_projection(payload, wordmark=wordmark)

    # Content-derived canvas: the tape's height follows its content cursor (no
    # fixed-835 dead blank on a sparse session).
    width = int(RAW_W)
    height = round(tape.total_height)
    context: dict[str, Any] = {
        "receipt_w": width,
        "receipt_h": height,
        # The raw genome maps its palette onto base genome fields; the metadata
        # template + assembler read those. The tape draws literal hex directly.
        "receipt_tape": tape,
        # Fixed shape geometry (rails, card rect, barcode dims) — the template
        # stamps these so it carries zero geometry numbers (stencil invariant).
        "rg": RAW_GEOM,
        "diamond_path": RAW_DIAMOND_PATH,
        "diamond_dots": list(RAW_DIAMOND_DOTS),
        # data-hw-headline projection (document-level): the grand total.
        "receipt_headline_kind": "cost",
        "headline": str(payload.get("cost_usd", "")),
        # Payload + envelope projection (context builder hashes the envelope).
        "payload_json": payload_json,
        "payload_schema": "receipt/1",
        "receipt_envelope_title": envelope_title,
        "receipt_envelope_intent": envelope_intent,
        "receipt_envelope_data": envelope_data,
        # Flat list of every rendered string — the font subsetter walks this to
        # build the embedded-font glyph set (the tape dataclass is opaque to the
        # recursive char collector).
        "receipt_text_surface": _raw_text_surface(tape),
        # StrictUndefined-safe stubs for the primer-only context keys the shared
        # _ctx_receipt builder + metadata template never read on the raw path.
        "receipt_palette": {},
    }

    return {
        "width": width,
        "height": height,
        "template": "frames/receipt.svg.j2",
        "context": context,
    }


def _raw_text_surface(tape: RawReceipt) -> list[str]:
    """Collect every rendered string on the raw tape (for font subsetting)."""
    out: list[str] = []
    for line in (*tape.header_lines, *tape.session_lines):
        out.append(line.text)
    out.append(tape.footer_line.text)
    out.append(tape.tender_header.text)
    out += [tape.tender_count, tape.tender_summary]
    for row in (tape.tool_header, *tape.tool_rows, tape.void_header, *tape.void_rows, *tape.ledger_rows):
        out += [row.label, row.value, row.sub]
    out += [tape.total_label, tape.total_value, tape.disclaimer]
    for tr in tape.tender_rows:
        out += [tr.name, tr.detail, tr.cost]
    return [s for s in out if s]


def _footer_display_name(spec: ComposeSpec) -> str:
    """Footer identity name: the live session title, read at render time.

    Sourced from ``ComposeSpec.receipt_display_name`` (set by the CLI from the
    session's latest title, so a mid-session rename is reflected). HTTP / MCP
    callers that don't set it render the footer identity as 'repo · branch' with
    no name segment.
    """
    return getattr(spec, "receipt_display_name", "") or ""


def _fmt_money(value: Any) -> str:
    """Whole-dollar / 2-decimal money for the envelope title (not the payload)."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "0"
    return f"{v:.2f}"


def _cache_pct(payload: dict[str, Any]) -> int:
    """Cache-read share of all tokens, as an integer percent (for the envelope)."""
    tok = payload.get("tokens", {}) or {}
    total = float(tok.get("total", 0) or 0)
    cached = float(tok.get("cache_read", 0) or 0)
    return round(cached / total * 100) if total > 0 else 0


def _assemble_context(
    *,
    layout: ReceiptLayout,
    palette: dict[str, str],
    substrate_kind: str,
    glyph_id: str,
    wordmark: str,
    payload_json: str,
    envelope_title: str,
    envelope_intent: str,
    envelope_data: dict[str, Any],
    headline: str,
) -> dict[str, Any]:
    """Flatten the content-aware layout into the template's frame_context dict.

    Every value is pre-computed (positions, widths, formatted strings, colours,
    the content-derived card height). The template performs no arithmetic — it
    stamps these into ``<text>`` / ``<rect>`` / ``<path>`` elements and gates the
    cost-by-model + context-load zones on their ``show`` flags. The two inter-
    zone hairline y's follow the cursor (no longer pinned at 106/266).
    """
    rule_metrics_y, rule_tools_y = receipt_rule_ys(layout)
    height = layout.height
    return {
        # Chassis geometry (single source of truth, mirrors the specimen).
        "receipt_w": RECEIPT_W,
        "receipt_h": height,
        "left_rail": LEFT_RAIL,
        "right_rail": RIGHT_RAIL,
        "content_w": CONTENT_W,
        "substrate_kind": substrate_kind,
        "glyph_id": glyph_id,
        "has_glyph": bool(glyph_id),
        "wordmark": wordmark,
        # Fixed shape geometry (columns, sizes, radii) — template stamps these so
        # it carries zero geometry numbers (stencil invariant).
        "rg": _GEOM,
        # The two inter-zone hairlines — content-aware y's from the cursor pass.
        "rule_metrics_y": rule_metrics_y,
        "rule_tools_y": rule_tools_y,
        # Palette (per-variant; semantic red genome-invariant).
        "receipt_palette": palette,
        # Headline projection for the document-level data-hw-headline attr.
        "receipt_headline_kind": "cost",
        # Per-zone dataclasses (the template reaches into their fields).
        "zone_identity": layout.identity,
        "zone_model_mix": layout.model_mix,
        "zone_hero": layout.hero,
        "zone_metrics": layout.metrics,
        "zone_tool_spend": layout.tool_spend,
        "zone_cost_by_model": layout.cost_by_model,
        "zone_context_load": layout.context_load,
        "zone_footer": layout.footer,
        # Card border rect dims (pre-computed — the template stamps, never math).
        "card_border_w": RECEIPT_W - 1.2,
        "card_border_h": round(height - 1.2, 1),
        # Payload + envelope projection (context builder hashes the envelope).
        "payload_json": payload_json,
        "payload_schema": "receipt/1",
        "receipt_envelope_title": envelope_title,
        "receipt_envelope_intent": envelope_intent,
        "receipt_envelope_data": envelope_data,
        "headline": headline,
        # Flat list of every rendered string — the font subsetter walks this to
        # build the embedded-font glyph set (the zone dataclasses are opaque to
        # the recursive char collector).
        "receipt_text_surface": _text_surface(layout),
        # Context-load stampable glyph geometry (markers → paths/circles).
        **build_context_glyphs(layout.context_load),
    }


def _text_surface(layout: ReceiptLayout) -> list[str]:
    """Collect every rendered string for font subsetting (a flat list).

    Includes the cost-by-model + context-load strings unconditionally: subsetting
    the superset is harmless when a zone is hidden, and keeps the glyph set stable
    across sparse/full sessions (so a sparse receipt's font payload still covers
    every codepoint a full one would render)."""
    out: list[str] = [layout.identity.wordmark]
    mm = layout.model_mix
    out += [mm.eyebrow, mm.dominant, mm.dominant_suffix, mm.split]
    out += [layout.hero.cost, layout.hero.est_label, layout.hero.subline]
    for c in layout.metrics.cells:
        out += [c.value, c.label, "·"]
    ts = layout.tool_spend
    out += [ts.eyebrow, ts.eyebrow_cont, ts.cache_pct, ts.cache_summary, ts.cache_working, "= errors"]
    for r in ts.rows:
        out += [r.name, r.pct, r.tokens, r.calls, str(r.err)]
    for chip in ts.legend_chips:
        out.append(chip.label)
    cbm = layout.cost_by_model
    out += [cbm.eyebrow, cbm.count_label]
    for bn in cbm.bar_names:
        out.append(bn.text)
    for row in cbm.rows:
        out += [row.name, row.role, row.cost, row.pct]
    lay = layout.context_load.layout
    out += [lay.header.eyebrow, lay.header.detail, lay.header.peak_label, lay.header.resets_label]
    out += [lay.ceiling_line.label, lay.baseline.label]
    for g in lay.gridlines:
        out.append(g.label)
    for t in lay.time_ticks:
        out.append(t.label)
    for item in lay.legend:
        out.append(item.label)
    ft = layout.footer
    out += [ft.tl, ft.tr, ft.bl, ft.br]
    return [s for s in out if s]
