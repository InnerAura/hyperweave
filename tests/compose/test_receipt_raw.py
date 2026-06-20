"""Raw thermal-tape receipt tests (the fixed-substrate meme receipt).

Pins the raw chassis (``v04/specimens/receipts/raw-receipt-v2.svg``):
* 300x835 fixed canvas, paper substrate, monospace register tape
* the SAME receipt/1 payload as the primer chassis (a second chassis, not a
  second data path) — payload + envelope id byte-identical to the primer twin
* the tape sections: header lockup, session/cashier, TOOL QTY/TOKENS columns
  with '% of basket' + '+N OTHERS' overflow, VOID/FAILED per-tool breakdown,
  the token ledger, TOTAL DUE, TENDERED, barcode footer
* adaptation OFF — no prefers-color-scheme swap (the paper IS the joke); the
  reduced-motion guard stays
"""
# ruff: noqa: RUF001, RUF003  ×/− are the deliberate till glyphs the specimen prints

from __future__ import annotations

import hashlib
import re
from typing import Any

from hyperweave.compose.engine import compose
from hyperweave.compose.resolvers.raw_sections import (
    RAW_H,
    RAW_W,
    _palette_from_genome,
    build_raw_receipt,
)
from hyperweave.core.models import ComposeSpec

# Reuse the canonical specimen payload the primer tests pin (the receipt/1
# contract is chassis-agnostic — both receipts read the same dict).
from .test_receipt_primer import SPECIMEN_PAYLOAD

_RAW_PALETTE: dict[str, str] = {
    "paper": "#f3f1ea",
    "ink": "#2d2a24",
    "faint": "#918c80",
    "rule": "#ded8cc",
    "accent": "#a64536",
    "sheen_dim": "#d8d2c4",
    "sheen_bright": "#fffffa",
    "sheen_shadow": "#4c4636",
    "cockle_light": "#fffefb",
}


def _compose_raw(payload: dict[str, Any]) -> str:
    return compose(ComposeSpec(type="receipt", genome_id="raw", telemetry_data=payload)).svg


# --------------------------------------------------------------------------- #
# Chassis: 300px-wide paper tape, content-derived height                        #
# --------------------------------------------------------------------------- #


class TestRawChassis:
    def test_canvas_width_fixed_height_content_derived(self) -> None:
        """The tape pins its 300px WIDTH; the height follows the content cursor
        (barcode + footer ride a thermal feed-margin below the last data line,
        so a sparse session is short and a rich one long — no fixed-835 dead
        blank). The full specimen session renders a long tape within bounds."""
        result = compose(ComposeSpec(type="receipt", genome_id="raw", telemetry_data=SPECIMEN_PAYLOAD))
        assert result.width == 300
        svg = result.svg
        assert f'width="300" height="{result.height}"' in svg
        assert f'viewBox="0 0 300 {result.height}"' in svg
        # A full session produces a long tape; a sparse one is materially shorter.
        assert 400 <= result.height <= 900

    def test_sparse_tape_is_shorter_than_rich(self) -> None:
        """The content-derived height collapses for a sparse session (the
        missing-bottom bug was dead tape on a fixed canvas)."""
        sparse = {
            **SPECIMEN_PAYLOAD,
            "models": [{"name": "opus-4.7", "role": "main thread", "cost_usd": 3.2, "cost_pct": 100}],
            "tools": [{"name": "Edit", "tok": 32000, "calls": 14, "class": "mutate"}],
            "errors": 0,
            "context": {"window": 200000, "peak_ctx": 0, "events": [], "note": ""},
        }
        rich_h = compose(ComposeSpec(type="receipt", genome_id="raw", telemetry_data=SPECIMEN_PAYLOAD)).height
        sparse_h = compose(ComposeSpec(type="receipt", genome_id="raw", telemetry_data=sparse)).height
        assert sparse_h < rich_h

    def test_paper_genome_root_attrs(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        assert 'data-hw-genome="raw"' in svg
        # category=light → data-hw-mode=light, matching the specimen (a paper
        # receipt is always cream-and-ink, never a dark thermal print).
        assert 'data-hw-mode="light"' in svg

    def test_paper_substrate_hex_baked_not_css_var(self) -> None:
        """The vellum palette is literal hex (survives static renderers)."""
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        assert "#f3f1ea" in svg  # paper
        assert "#2d2a24" in svg  # ink
        assert "#a64536" in svg  # thermal-red accent
        # The vellum-onionskin material filters flood via literals — never a var()
        # in an attribute (var() doesn't resolve in lighting-color / stop-color).
        assert "feTurbulence" in svg
        for fid in ("cockle", "translucent", "grain"):
            m = re.search(rf"<filter[^>]*-{fid}[^>]*>.*?</filter>", svg, re.S)
            assert m is not None, f"missing {fid} filter"
            assert "var(--dna" not in m.group(0)


# --------------------------------------------------------------------------- #
# Adaptation OFF (the fixed-substrate doctrine)                                #
# --------------------------------------------------------------------------- #


class TestAdaptationOff:
    def test_no_prefers_color_scheme_swap(self) -> None:
        """Raw declares no light_mode → the assembler emits no light swap RULE.

        (A CSS *comment* mentioning prefers-color-scheme ships in the shared
        base CSS on every artifact; we assert no actual ``@media
        (prefers-color-scheme: light) {`` swap rule, which is what would flip
        the paper to a dark print.)
        """
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        swap_rules = re.findall(r"@media\s*\(prefers-color-scheme:\s*light\)\s*\{", svg)
        assert swap_rules == [], "raw must not carry a light-mode swap (fixed paper substrate)"

    def test_reduced_motion_guard_present(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        assert "prefers-reduced-motion" in svg

    def test_static_no_script(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        assert "<script" not in svg.lower()


# --------------------------------------------------------------------------- #
# Tape sections present                                                        #
# --------------------------------------------------------------------------- #


class TestTapeSections:
    def test_all_tape_sections_render(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        for needle in (
            "HYPERWEAVE",
            "CASHIER: Claude Code",
            "31 TURNS",
            "157m",
            "REGISTER 200K",
            "PEAK 196K",
            "CLEARED 4×",
            "TOOL QTY",
            "TOKENS",
            "% of basket",
            "VOID / FAILED CALLS",
            "TOKENS IN",
            "SUBTOTAL",
            "TOTAL DUE",
            "$175.01",
            "TENDERED",
        ):
            assert needle in svg, f"missing tape section {needle!r}"

    def test_tool_columns_show_qty_and_tokens(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        assert "EDIT ×242" in svg
        assert "709.3K" in svg
        assert "69% of basket" in svg

    def test_token_ledger_complete(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        for needle in ("TOKENS IN", "TOKENS OUT", "CACHED", "WRITTEN", "SUBTOTAL", "VOIDED CALLS"):
            assert needle in svg

    def test_tender_lists_models(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        assert "OPUS-4.7" in svg
        assert "$128.00" in svg
        assert "3 MODELS" in svg


# --------------------------------------------------------------------------- #
# '+N OTHERS' overflow + VOID per-tool errors                                  #
# --------------------------------------------------------------------------- #


class TestOverflowAndVoid:
    def test_long_tool_list_collapses_to_plus_n_others(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        # The specimen's 10 tools collapse to 4 shown + '+6 OTHERS'.
        assert re.search(r"\+6 OTHERS ×\d+", svg)

    def test_others_tokens_are_working_remainder(self) -> None:
        tape = build_raw_receipt(SPECIMEN_PAYLOAD, palette=_RAW_PALETTE)
        others = next(r for r in tape.tool_rows if r.label.startswith("+"))
        # working 1024800 − shown(709300+116400+94600+30200)=950500 → 74300 → 74.3K
        assert others.value == "74.3K"

    def test_void_per_tool_breakdown(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        # Per-tool VOID rows, accent-coloured ×N values, sorted by error count.
        assert "VOID EDIT-RETRY" in svg
        assert "VOID ASKUSERQUESTION-FAIL" in svg
        tape = build_raw_receipt(SPECIMEN_PAYLOAD, palette=_RAW_PALETTE)
        errs = [r.value for r in tape.void_rows]
        assert errs == ["×6", "×3", "×3", "×2", "×1"]  # descending
        # The void header carries the total as a negative.
        assert tape.void_header.value == "−15"

    def test_void_values_use_accent_tone(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        # The ×N error values render in the thermal-red accent, not ink.
        assert re.search(r'fill="#a64536"[^>]*>×6<', svg)

    def test_no_failures_suppresses_void_rows(self) -> None:
        clean = {
            **SPECIMEN_PAYLOAD,
            "errors": 0,
            "tools": [
                {"name": "Edit", "tok": 1000, "calls": 2, "class": "mutate"},
                {"name": "Read", "tok": 500, "calls": 1, "class": "explore"},
            ],
        }
        tape = build_raw_receipt(clean, palette=_RAW_PALETTE)
        assert tape.show_void is False
        assert tape.void_rows == []

    def test_short_tool_list_no_overflow(self) -> None:
        short = {
            **SPECIMEN_PAYLOAD,
            "tools": [
                {"name": "Edit", "tok": 1000, "calls": 2, "err": 0, "class": "mutate"},
                {"name": "Read", "tok": 500, "calls": 1, "err": 0, "class": "explore"},
            ],
        }
        tape = build_raw_receipt(short, palette=_RAW_PALETTE)
        assert all(not r.label.startswith("+") for r in tape.tool_rows)
        assert len(tape.tool_rows) == 2


# --------------------------------------------------------------------------- #
# Solo-model + zero-case tender                                                #
# --------------------------------------------------------------------------- #


class TestTenderCases:
    def test_solo_model_singular_count_label(self) -> None:
        solo = {**SPECIMEN_PAYLOAD, "models": [SPECIMEN_PAYLOAD["models"][0]]}
        tape = build_raw_receipt(solo, palette=_RAW_PALETTE)
        assert tape.tender_count == "1 MODEL"
        assert len(tape.tender_rows) == 1
        # A solo run's only row stays ink (the faint-trailing rule needs >1).
        assert tape.tender_rows[0].tone == "ink"

    def test_trailing_model_is_faint(self) -> None:
        tape = build_raw_receipt(SPECIMEN_PAYLOAD, palette=_RAW_PALETTE)
        assert tape.tender_rows[-1].tone == "faint"
        assert all(r.tone == "ink" for r in tape.tender_rows[:-1])


# --------------------------------------------------------------------------- #
# Payload + envelope (shared with the primer twin)                            #
# --------------------------------------------------------------------------- #


class TestPayloadEnvelope:
    def test_payload_is_compact_data_only(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        m = re.search(r'schema="receipt/1"[^>]*><!\[CDATA\[(.*?)\]\]>', svg, re.S)
        assert m, "receipt/1 payload CDATA not found"
        body = m.group(1)
        assert "\n" not in body  # single-line
        assert "$" not in body  # no formatted money
        assert "% of basket" not in body  # no formatted display strings

    def test_envelope_id_hashes_the_payload(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        m = re.search(r'schema="receipt/1"[^>]*><!\[CDATA\[(.*?)\]\]>', svg, re.S)
        assert m
        digest = hashlib.sha256(m.group(1).encode("utf-8")).hexdigest()
        assert f"sha256:{digest}" in svg

    def test_raw_and_primer_carry_identical_payload(self) -> None:
        """Both chassis embed the same receipt/1 bytes for the same session."""
        raw = _compose_raw(SPECIMEN_PAYLOAD)
        primer = compose(
            ComposeSpec(type="receipt", genome_id="primer", variant="porcelain", telemetry_data=SPECIMEN_PAYLOAD)
        ).svg
        raw_body = re.search(r'schema="receipt/1"[^>]*><!\[CDATA\[(.*?)\]\]>', raw, re.S).group(1)
        primer_body = re.search(r'schema="receipt/1"[^>]*><!\[CDATA\[(.*?)\]\]>', primer, re.S).group(1)
        assert raw_body == primer_body


# --------------------------------------------------------------------------- #
# Reasoning metadata (the explainability layer)                               #
# --------------------------------------------------------------------------- #


class TestReasoning:
    def test_reasoning_block_populated(self) -> None:
        """The raw chassis ships non-empty hw:reasoning (the XAI quality bar)."""
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        for tag in ("hw:intent", "hw:approach", "hw:tradeoffs"):
            m = re.search(rf"<{tag}>(.*?)</{tag}>", svg, re.S)
            assert m and m.group(1).strip(), f"{tag} must be populated"

    def test_tradeoffs_carry_the_adaptation_decision(self) -> None:
        """The load-bearing tradeoff (adaptation removed) is documented."""
        svg = _compose_raw(SPECIMEN_PAYLOAD)
        tradeoffs = re.search(r"<hw:tradeoffs>(.*?)</hw:tradeoffs>", svg, re.S).group(1)
        assert len(tradeoffs.strip()) >= 21  # ReasoningFields min_length
        assert "light_mode" in tradeoffs or "adaptation" in tradeoffs.lower()
        # A spatial measurement + an explicit removal (the quality bar).
        assert "835" in tradeoffs
        assert any(w in tradeoffs.lower() for w in ("removed", "dropped", "fixed"))


# --------------------------------------------------------------------------- #
# Identity (cashier line — runtime/model inference, never theming)            #
# --------------------------------------------------------------------------- #


class TestCashierIdentity:
    def test_claude_model_prints_claude_cashier(self) -> None:
        svg = _compose_raw(SPECIMEN_PAYLOAD)  # model opus-4.7
        assert "CASHIER: Claude Code" in svg

    def test_codex_model_prints_codex_cashier(self) -> None:
        codex = {**SPECIMEN_PAYLOAD, "model": "gpt-5.4", "dominant": "gpt-5.4"}
        svg = _compose_raw(codex)
        assert "CASHIER: Codex" in svg


# --------------------------------------------------------------------------- #
# Module constants                                                             #
# --------------------------------------------------------------------------- #


def test_raw_dimensions_constants() -> None:
    # Width is the fixed tape identity; RAW_H is now a legacy magnitude reference
    # (the rendered height is content-derived from the tape's cursor).
    assert RAW_W == 300.0
    assert RAW_H == 835.0  # prototype-provenance reference (not a hard canvas)


def test_palette_from_genome_maps_thermal_fields() -> None:
    """The raw genome maps the vellum palette + baked material colours onto fields."""
    from hyperweave.config.registry import get_genomes

    pal = _palette_from_genome(get_genomes()["raw"])
    assert pal == {
        "paper": "#f3f1ea",
        "ink": "#2d2a24",
        "faint": "#918c80",
        "rule": "#ded8cc",
        "accent": "#a64536",
        "sheen_dim": "#d8d2c4",
        "sheen_bright": "#fffffa",
        "sheen_shadow": "#4c4636",
        "cockle_light": "#fffefb",
    }
