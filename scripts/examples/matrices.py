"""The matrix gallery — canonical specimens plus the boundary suite.

Two halves, both required. The specimens prove *does it look right* against the
porcelain-final references; the boundary suite proves *does it break* at the
edges of the input space (dimension, content, structural, type isolation). A
gallery with only the first is a brochure.

The fixture specs are the same JSON the test suite loads, so a specimen can
never drift from what the tests assert about it, and the connectors matrix is
generated from `data/connector_registry.yaml` rather than transcribed.

Lifted out of the proofset generator, where ~1300 lines of matrix content sat
inside a 7200-line module alongside every other frame's emitter. The renders
and the document now come off one `Gallery`, so the page cannot cite a
boundary case that was never built.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scripts.examples.manifest import Gallery
from scripts.examples.markdown import Doc
from scripts.examples.render import OUTPUTS, REPO, gallery_spec, render, spec

if TYPE_CHECKING:
    from pathlib import Path

MATRICES_ROOT = OUTPUTS / "matrices"

# The genome the matrix frame speaks. Its eight variants are the substrate
# derivation the gallery checks the chassis against.
GENOME = "primer"
FLAGSHIP = "porcelain"

# The six canonical specimens, in the order the page walks them, each with the
# one thing it is the proof of.
SPECIMENS: tuple[tuple[str, str], ...] = (
    ("check", "Scored comparison — tri-valence marks, hero lane, score band, masthead legend."),
    (
        "connectors",
        "Registry — row glyphs, packed metric chips with `+N` overflow, status pills, "
        "content-height rows. Generated from `data/connector_registry.yaml`.",
    ),
    (
        "tiers",
        "Progressive inclusion — chained sets auto-select the tier-span projection: reach bars with "
        "terminal dots (3 spans for 27 marks), hero tier through the USE-FOR row, a one-entry "
        "tier-reach key. Non-nested dot data keeps the tier-dot grid.",
    ),
    ("readcost", "Bar scale — shared axis with nice ticks, value column, load-bearing headline chip."),
    ("plans", "Pill tags — emerald Yes capsules, neutral value capsules, recommended-column hero lane."),
    (
        "benchmark",
        "Numeric heat — diverging teal-rose tiles, gauged underlines, brand-tinted row glyphs "
        "(Gemini's gradient spark).",
    ),
)

# The boundary groups, in review order: (filename prefix, heading, why it matters).
BOUNDARY_GROUPS: tuple[tuple[str, str, str], ...] = (
    (
        "dim-",
        "Dimension boundaries",
        "The smallest and largest shapes the solver accepts. These are structural proofs, not design "
        "targets — a one-row table is legal and must still be laid out correctly.",
    ),
    (
        "content-",
        "Content boundaries",
        "Hostile text: overlong labels, empty cells, unicode, numbers at every magnitude. Raw user "
        "text must never break entity or tag syntax (Invariant 14).",
    ),
    (
        "struct-",
        "Structural boundaries",
        "Shapes that stress the layout algebra rather than the text: every column one kind, "
        "sections without members, ragged arity.",
    ),
    (
        "iso-",
        "Cell-kind isolation",
        "One kind per table, so a kind's markup can be read without any other kind's nearby. This is "
        "where a kind that silently borrows another's geometry shows up.",
    ),
)

# plate / inlay / twin — the three ways one artifact can meet a host page.
SURFACE_MODES: tuple[tuple[str, str, str, str], ...] = (
    ("plate", "opaque", "fixed", "opaque · fixed — carries its own ground, ignores the reader's theme."),
    ("inlay", "bare", "adaptive", "bare · adaptive — no ground, borrows the host page, re-inks to the reader's theme."),
    ("twin", "opaque", "adaptive", "opaque · adaptive — a light face and a dark face; contained, follows the theme."),
)


def _matrix_fixture_specs() -> dict[str, dict[str, Any]]:
    """The six canonical sub-variant specs: five JSON fixtures shared with the
    test suite + the connectors matrix generated from the registry."""
    import json as _json

    from hyperweave.compose.matrix.input import build_connector_registry_matrix
    from hyperweave.config.loader import load_connector_registry

    fixtures_dir = REPO / "tests" / "fixtures" / "matrix"
    specs = {p.stem: _json.loads(p.read_text()) for p in sorted(fixtures_dir.glob("*.json"))}
    specs["connectors"] = build_connector_registry_matrix(load_connector_registry()).model_dump(mode="json")
    return specs


def _matrix_edge_specs() -> dict[str, dict[str, Any]]:
    """The boundary suite: the specimens prove "does it look right"; these
    prove "does it break". Dimension, content, structural, and
    type-isolation boundaries — every render is eyeballed in
    README_MATRIX.md. Boundaries carry REAL-SHAPED data (actual metric
    names, plausible values) so the geometry stays judgeable even when the
    structure is deliberately degenerate.
    """
    edge: dict[str, dict[str, Any]] = {}
    # ── Dimension boundaries (structural proof, not design targets) ──
    edge["dim-single-row"] = {
        "title": "Single row",
        "subtitle": "one model across five gauged benchmarks — heat needs no neighbors",
        "row_glyph_tint": "brand",
        "columns": [
            {"id": "model", "label": "MODEL", "role": "label"},
            {"id": "mmlu", "label": "MMLU", "sublabel": "↑ higher", "kind": "numeric", "polarity": "higher"},
            {"id": "gsm", "label": "GSM8K", "sublabel": "↑ higher", "kind": "numeric", "polarity": "higher"},
            {"id": "human", "label": "HumanEval", "sublabel": "↑ higher", "kind": "numeric", "polarity": "higher"},
            {"id": "math", "label": "MATH", "sublabel": "↑ higher", "kind": "numeric", "polarity": "higher"},
            {
                "id": "price",
                "label": "$/Mtok",
                "sublabel": "↓ lower",
                "kind": "numeric",
                "polarity": "lower",
                "unit": "$",
            },
        ],
        "rows": [
            {
                "label": "Claude 3.5 Sonnet",
                "glyph": "anthropic",
                "cells": [{"value": 88.7}, {"value": 96.4}, {"value": 92.0}, {"value": 71.1}, {"value": 3.0}],
            }
        ],
    }
    edge["dim-single-col"] = {
        "title": "Single column",
        "subtitle": "one artifact, tri-state support per surface — dual-coded marks down a column",
        "columns": [
            {"id": "surface", "label": "SURFACE", "role": "label"},
            {"id": "svg", "label": "SVG support", "kind": "check"},
        ],
        "rows": [
            {"label": "GitHub README", "cells": [{"state": "full"}]},
            {"label": "GitHub PR / issue body", "cells": [{"state": "full"}]},
            {"label": "Notion embed", "cells": [{"state": "partial"}]},
            {"label": "Slack link preview", "cells": [{"state": "partial"}]},
            {"label": "Gmail body", "cells": [{"state": "none"}]},
            {"label": "VS Code markdown preview", "cells": [{"state": "full"}]},
        ],
    }
    edge["dim-1x1"] = {
        "title": "True minimum",
        "subtitle": "one cell still carries a semantic mark",
        "columns": [{"id": "svg", "label": "Renders in README", "kind": "check"}],
        "rows": [{"label": "hyperweave SVG", "cells": [{"state": "full"}]}],
    }
    _ENDPOINTS = [
        "badge",
        "strip",
        "icon",
        "divider",
        "marquee",
        "stats",
        "chart",
        "matrix",
        "compose",
        "frames",
        "health",
        "kit",
        "live",
        "discover",
        "genomes",
        "motions",
    ]
    edge["dim-soft-cap-16"] = {
        "title": "Soft cap",
        "subtitle": "16 rows of gauged latency — type and pitch tighten one step",
        "unit": "ms",
        "columns": [
            {"id": "route", "label": "ROUTE", "role": "label"},
            {"id": "p50", "label": "p50", "kind": "numeric", "polarity": "lower"},
            {"id": "p95", "label": "p95", "kind": "numeric", "polarity": "lower"},
        ],
        "rows": [
            {"label": f"GET /v1/{name}", "cells": [{"value": 8 + i * 3}, {"value": 21 + i * 7}]}
            for i, name in enumerate(_ENDPOINTS)
        ],
    }
    _SURFACES = [
        ("GitHub README", "full", "full"),
        ("GitHub PR / issue body", "full", "full"),
        ("GitHub wiki", "full", "partial"),
        ("GitHub gist", "full", "partial"),
        ("GitHub Pages", "full", "full"),
        ("GitLab README", "full", "partial"),
        ("Bitbucket README", "partial", "none"),
        ("npm package page", "full", "none"),
        ("PyPI project page", "full", "none"),
        ("crates.io readme", "partial", "none"),
        ("Notion embed", "partial", "none"),
        ("Obsidian vault", "full", "partial"),
        ("Slack link preview", "partial", "none"),
        ("Discord embed", "partial", "none"),
        ("VS Code markdown preview", "full", "partial"),
        ("JetBrains markdown", "full", "none"),
        ("Linear issue", "partial", "none"),
        ("Jira description", "none", "none"),
        ("Confluence page", "partial", "none"),
        ("Reddit post", "none", "none"),
        ("X / Twitter card", "none", "none"),
        ("Bluesky embed", "none", "none"),
        ("Mastodon preview", "partial", "none"),
        ("Apple Mail", "partial", "none"),
        ("Gmail body", "none", "none"),
        ("Outlook body", "none", "none"),
        ("Docusaurus site", "full", "full"),
        ("MkDocs site", "full", "full"),
        ("Sphinx docs", "full", "partial"),
        ("Hugo site", "full", "full"),
    ]
    edge["dim-hard-cap-30"] = {
        "title": "Hard cap",
        "subtitle": "a 30-surface support matrix — the ceiling still renders; 31 raises",
        "columns": [
            {"id": "surface", "label": "SURFACE", "role": "label"},
            {"id": "renders", "label": "Renders", "kind": "check"},
            {"id": "animates", "label": "Animates", "kind": "check"},
        ],
        "rows": [
            {"label": name, "cells": [{"state": renders}, {"state": animates}]} for name, renders, animates in _SURFACES
        ],
    }
    _EVALS = [
        ("mmlu", "MMLU", "higher"),
        ("gsm", "GSM8K", "higher"),
        ("human", "HumanEval", "higher"),
        ("math", "MATH", "higher"),
        ("gpqa", "GPQA", "higher"),
        ("mgsm", "MGSM", "higher"),
        ("drop", "DROP", "higher"),
        ("price", "$/Mtok", "lower"),
    ]
    _MODELS = [
        ("Claude 3.5 Sonnet", "anthropic", [88.7, 96.4, 92.0, 71.1, 59.4, 91.6, 87.1, 3.0]),
        ("GPT-4o", "openai", [88.7, 95.8, 90.2, 76.6, 53.6, 90.5, 83.4, 2.5]),
        ("Gemini 1.5 Pro", "gemini", [85.9, 91.7, 84.1, 67.7, 46.2, 88.7, 78.9, 1.25]),
        ("Qwen2.5-72B", "qwen", [86.1, 91.5, 86.6, 83.1, 49.0, 89.3, 76.7, 0.4]),
    ]
    edge["dim-max-cols-8"] = {
        "title": "Max columns",
        "subtitle": "a wall of gauged tiles — eight heat columns compress toward equal widths",
        "row_glyph_tint": "brand",
        "columns": [{"id": "model", "label": "MODEL", "role": "label"}]
        + [
            {
                "id": cid,
                "label": label,
                "sublabel": "↑ higher" if pol == "higher" else "↓ lower",
                "kind": "numeric",
                "polarity": pol,
            }
            for cid, label, pol in _EVALS
        ],
        "rows": [
            {"label": name, "glyph": glyph, "cells": [{"value": v} for v in values]} for name, glyph, values in _MODELS
        ],
    }
    edge["dim-label-floor"] = {
        "title": "Label column squeezed to its floor",
        "columns": [{"id": "l", "label": "CAPABILITY", "role": "label"}]
        + [{"id": f"c{j}", "label": f"TARGET {j + 1}", "kind": "check"} for j in range(6)],
        "rows": [
            {
                "label": "An extremely long capability label that must truncate with a measured ellipsis",
                "cells": [{"state": s} for s in ("full", "partial", "none", "full", "partial", "none")],
            }
            for _ in range(4)
        ],
    }
    # ── Cell content boundaries ──
    edge["content-chip-overflow-cap"] = {
        "title": "Chip overflow past the four-row cap",
        "subtitle": "chips always wrap; +N appears only when even four rows cannot hold them",
        "columns": [
            {"id": "pkg", "label": "PACKAGE", "role": "label"},
            {"id": "deps", "label": "DEPENDENCIES", "kind": "chip"},
            {"id": "lock", "label": "LOCKED", "kind": "pill"},
        ],
        "rows": [
            {
                "label": "hyperweave",
                "sublabel": "pyproject",
                "cells": [
                    {
                        "chips": [
                            "fastapi",
                            "pydantic",
                            "jinja2",
                            "typer",
                            "uvicorn",
                            "httpx",
                            "pyyaml",
                            "fastmcp",
                            "rich",
                            "anyio",
                            "starlette",
                            "click",
                            "fonttools",
                            "pillow",
                            "certifi",
                            "idna",
                            "sniffio",
                            "h11",
                            "httpcore",
                            "annotated-types",
                            "typing-extensions",
                            "markupsafe",
                            "shellingham",
                            "pygments",
                            "mdurl",
                            "markdown-it-py",
                            "python-multipart",
                            "websockets",
                            "watchfiles",
                            "httptools",
                            "uvloop",
                            "orjson",
                            "ujson",
                            "email-validator",
                            "dnspython",
                            "itsdangerous",
                            "pyperclip",
                            "docutils",
                            "packaging",
                            "six",
                        ]
                    },
                    {"state": "on"},
                ],
            }
        ],
    }
    edge["content-text-wrap-cap"] = {
        "title": "Long values wrap",
        "subtitle": "full commit subjects against narrow columns — wrap first, ellipsis last",
        "columns": [
            {"id": "sha", "label": "COMMIT", "role": "label"},
            {"id": "subject", "label": "SUBJECT", "kind": "text", "width": 150},
            {"id": "body", "label": "BODY", "kind": "text", "width": 150},
        ],
        "rows": [
            {
                "label": "1e15d4f",
                "cells": [
                    {"value": "docs: update README assets after the proofset regeneration pass"},
                    {
                        "value": "Regenerates every embedded artifact, refreshes the parity manifest, "
                        "re-runs the raster verification harness across all eight primer variants, "
                        "and pins the new solved widths in the acceptance README"
                    },
                ],
            },
            {
                "label": "4867b34",
                "cells": [
                    {"value": "feat: primer genome across all seven existing frame types"},
                    {"value": "Badge, strip, chart, stats, icon, marquee and divider all dispatch primer"},
                ],
            },
            {
                "label": "0059902",
                "cells": [
                    {"value": "fix: strip layout engine cell padding on chrome variants"},
                    {"value": "Cell padding now solves from the paradigm config"},
                ],
            },
        ],
    }
    edge["content-bar-identical"] = {
        "title": "Bars with identical values",
        "subtitle": "no differentiation to gauge — every bar fills alike",
        "unit": "ms",
        "columns": [
            {"id": "region", "label": "REGION", "role": "label"},
            {"id": "p50", "label": "p50 latency", "kind": "bar", "polarity": "lower"},
        ],
        "rows": [
            {"label": region, "cells": [{"value": 250}]} for region in ("us-east", "eu-west", "ap-south", "sa-east")
        ],
    }
    edge["content-bar-zero"] = {
        "title": "Bar containing a zero",
        "unit": "tok",
        "columns": [
            {"id": "path", "label": "CACHE PATH", "role": "label"},
            {"id": "tok", "label": "Tokens fetched", "kind": "bar"},
        ],
        "rows": [
            {"label": "warm cache hit", "cells": [{"value": 0}]},
            {"label": "cold fetch", "cells": [{"value": 1800}]},
        ],
    }
    edge["content-scattered-empty"] = {
        "title": "Scattered empty cells",
        "subtitle": "missing connector values stay blank, never fabricated",
        "columns": [
            {"id": "pkg", "label": "PACKAGE", "role": "label"},
            {"id": "pypi", "label": "PyPI DLs"},
            {"id": "npm", "label": "npm DLs"},
            {"id": "crates", "label": "Crates DLs"},
        ],
        "rows": [
            {"label": "hyperweave", "cells": [{"value": 4100}, {}, {}]},
            {"label": "readme-ai", "cells": [{"value": 9100}, {"value": 1200}, {}]},
            {"label": "svg-forge", "cells": [{}, {}, {"value": 880}]},
        ],
    }
    edge["content-empty-row"] = {
        "title": "One fully-empty row",
        "subtitle": "a package no connector resolves",
        "columns": [
            {"id": "pkg", "label": "PACKAGE", "role": "label"},
            {"id": "ver", "label": "Version"},
            {"id": "dls", "label": "Downloads"},
        ],
        "rows": [
            {"label": "hyperweave", "cells": [{"value": "0.4.0a2"}, {"value": 4100}]},
            {"label": "ghost-package", "cells": [{}, {}]},
            {"label": "readme-ai", "cells": [{"value": "3.2.1"}, {"value": 9100}]},
        ],
    }
    # ── Structural boundaries (each rhetoric block independently omitted) ──
    edge["struct-no-title"] = {
        "title": "",
        "columns": [
            {"id": "fmt", "label": "FORMAT", "role": "label"},
            {"id": "size", "label": "Size KB"},
            {"id": "tokens", "label": "Tokens"},
        ],
        "rows": [
            {"label": "raw SVG", "cells": [{"value": 44}, {"value": 3420}]},
            {"label": "hw:payload", "cells": [{"value": 2}, {"value": 480}]},
            {"label": "hwz/1 envelope", "cells": [{"value": 1}, {"value": 210}]},
        ],
    }
    edge["struct-no-sections"] = {
        "title": "Flat rows (no sections)",
        "columns": [
            {"id": "field", "label": "FIELD", "role": "label"},
            {"id": "naked", "label": "Naked", "kind": "dot"},
            {"id": "resonant", "label": "Resonant", "kind": "dot"},
        ],
        "rows": [
            {"label": "title", "cells": [{"state": "on"}, {"state": "on"}]},
            {"label": "created", "cells": [{"state": "on"}, {"state": "on"}]},
            {"label": "aesthetic", "cells": [{"state": "on"}, {"state": "off"}]},
            {"label": "reasoning", "cells": [{"state": "off"}, {"state": "on"}]},
        ],
    }
    edge["struct-no-headline"] = {
        "title": "Bar scale without a headline chip",
        "unit": "tok",
        "columns": [
            {"id": "form", "label": "REPRESENTATION", "role": "label"},
            {"id": "tok", "label": "Tokens", "kind": "bar", "polarity": "lower"},
        ],
        "rows": [
            {"label": "raw SVG source", "cells": [{"value": 3420}]},
            {"label": "hw:payload", "cells": [{"value": 480}]},
            {"label": "hwz/1 envelope", "cells": [{"value": 210}]},
        ],
    }
    edge["struct-no-summary"] = {
        "title": "Checks without a score band",
        "columns": [{"id": "cap", "label": "CAPABILITY", "role": "label"}]
        + [{"id": c, "label": c.upper(), "kind": "check"} for c in ("svg", "png")],
        "rows": [
            {"label": "Animation", "cells": [{"state": "full"}, {"state": "none"}]},
            {"label": "Crisp at any scale", "cells": [{"state": "full"}, {"state": "none"}]},
        ],
    }
    edge["struct-no-hero"] = {
        "title": "Pills without a recommended column",
        "columns": [{"id": "f", "label": "FEATURE", "role": "label"}]
        + [{"id": p, "label": p.title(), "kind": "pill"} for p in ("free", "pro")],
        "rows": [
            {"label": "API access", "cells": [{"value": False}, {"value": True}]},
            {"label": "SSO / SAML", "cells": [{"value": False}, {"value": True}]},
        ],
    }
    edge["struct-everything"] = {
        "title": "Everything at once",
        "subtitle": "headline + sections + hero + summary + axis + emphasis, composed",
        "unit": "pts",
        "hero_column": "b",
        "headline": {"value": "3x", "label": "hero over baseline"},
        "sections": ["First", "Second"],
        "summary_label": "TOTAL",
        "columns": [
            {"id": "l", "label": "ITEM", "role": "label"},
            {"id": "a", "label": "Baseline", "kind": "bar"},
            {"id": "b", "label": "Hero", "kind": "bar"},
        ],
        "rows": [
            {"label": "alpha", "section": "First", "cells": [{"value": 10}, {"value": 30}]},
            {"label": "beta", "section": "First", "emphasis": True, "cells": [{"value": 12}, {"value": 36}]},
            {"label": "gamma", "section": "Second", "cells": [{"value": 8}, {"value": 24}]},
        ],
        "summary_row": [{"value": "30"}, {"value": "90"}],
    }
    # ── Type isolation: one matrix per cell kind as the sole data column ──
    iso_rows = [("alpha", 0), ("beta", 1), ("gamma", 2)]
    edge["iso-text"] = {
        "title": "Isolation: text",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "NOTE", "kind": "text"}],
        "rows": [{"label": n, "cells": [{"value": f"note {i}"}]} for n, i in iso_rows],
    }
    edge["iso-check"] = {
        "title": "Isolation: check",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "STATE", "kind": "check"}],
        "rows": [
            {"label": n, "cells": [{"state": s}]}
            for (n, _), s in zip(iso_rows, ("full", "partial", "none"), strict=True)
        ],
    }
    edge["iso-dot"] = {
        "title": "Isolation: dot",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "TIER", "kind": "dot"}],
        "rows": [{"label": n, "cells": [{"state": "on" if i % 2 == 0 else "off"}]} for n, i in iso_rows],
    }
    edge["iso-bar"] = {
        "title": "Isolation: bar",
        "unit": "tok",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "Tokens", "kind": "bar"}],
        "rows": [{"label": n, "cells": [{"value": (i + 1) * 700}]} for n, i in iso_rows],
    }
    edge["iso-pill"] = {
        "title": "Isolation: pill",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "READY", "kind": "pill"}],
        "rows": [{"label": n, "cells": [{"value": i % 2 == 0}]} for n, i in iso_rows],
    }
    edge["iso-numeric"] = {
        "title": "Isolation: numeric heat",
        "columns": [
            {"id": "l", "label": "ROW", "role": "label"},
            {"id": "v", "label": "Score", "kind": "numeric", "polarity": "higher"},
        ],
        "rows": [{"label": n, "cells": [{"value": 60 + i * 18}]} for n, i in iso_rows],
    }
    edge["iso-chip"] = {
        "title": "Isolation: chip",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "TAGS", "kind": "chip"}],
        "rows": [{"label": n, "cells": [{"chips": [f"tag_{i}_{k}" for k in range(i + 2)]}]} for n, i in iso_rows],
    }
    edge["iso-glyph"] = {
        "title": "Isolation: glyph",
        "columns": [{"id": "l", "label": "ROW", "role": "label"}, {"id": "v", "label": "MARK", "kind": "glyph"}],
        "rows": [
            {"label": n, "cells": [{"glyph": g}]}
            for (n, _), g in zip(iso_rows, ("github", "pypi", "huggingface"), strict=True)
        ],
    }
    return edge


_MATRIX_EDGE_NOTES: dict[str, str] = {
    "dim-single-row": "Tests: one model row across five gauged heat columns — column normalization "
    "with no neighbors. Correct: every tile reads the neutral mid hue (a range of one has no poles) "
    "and the frame solves to its natural width.",
    "dim-single-col": "Tests: one data column — the solver with nothing to balance against. Correct: "
    "the check column floors, the legend stays inline beside the subtitle, marks stay centered.",
    "dim-1x1": "Tests: the true minimum input (one row, one column). Correct: a complete card — "
    "masthead, headers, one mark, footer — at the width floor.",
    "dim-soft-cap-16": "Tests: 16 rows, the soft cap — the shrink step. Correct: the type drops one "
    "step and the pitch tightens; nothing clips.",
    "dim-hard-cap-30": "Tests: 30 rows, the hard cap — the engine's last legal input. Correct: every "
    "row still renders at compact pitch; row 31 raises instead.",
    "dim-max-cols-8": "Tests: 8 data columns, the column cap — maximum horizontal compression. "
    "Correct: columns compress toward their floors with no negative widths and no header collisions.",
    "dim-label-floor": "Tests: six data columns squeezing the label column to its floor. Correct: row "
    "labels truncate with a measured ellipsis; the key takes its own row under the wide title.",
    "content-text-wrap-cap": "Tests: prose against narrow text columns. Correct: values wrap up to "
    "three lines (rows grow to fit), and the ellipsis appears only on the final line of content that "
    "exceeds the cap — never as the first behavior.",
    "content-chip-overflow-cap": "Tests: a 40-dependency chip list against the four-row cap. Correct: "
    "chips pack and wrap; past the cap one `+N` chip absorbs the remainder (the full list stays in "
    "hw:payload).",
    "content-bar-identical": "Tests: every bar the same value — a range with no spread. Correct: all "
    "bars fill alike to the axis max; no fake differentiation.",
    "content-bar-zero": "Tests: a zero value on a bar scale. Correct: the zero keeps a minimum visible "
    "ink sliver against its track, and the axis still spans 0 to max.",
    "content-scattered-empty": "Tests: null/empty cells scattered through a populated table. Correct: "
    "empty cells render honest em-dashes — no invented zeros, no collapsed columns.",
    "content-empty-row": "Tests: one row with every cell empty. Correct: the row keeps its pitch and "
    "label; the cells stay quiet dashes.",
    "struct-no-title": "Tests: no title, subtitle, or headline at all. Correct: the masthead collapses "
    "entirely — the table starts near the top with no rail, scan, or legend.",
    "struct-no-sections": "Tests: flat rows with no section grouping, with NON-nested dot columns "
    "(inclusion sets that are not subsets of each other — the tier-dot fallback). Correct: the per-cell "
    "dot grid with extent bars and the included/omitted key, never spans; no bands, no indent, the "
    "primary row-title voice.",
    "struct-no-headline": "Tests: a bar matrix without the headline chip (top-right score badge). "
    "Correct: the masthead carries title and rail only; the axis still closes the scale.",
    "struct-no-hero": "Tests: a pill table without a recommended column. Correct: no hero lane, no cap "
    "tab — all columns carry equal visual weight.",
    "struct-no-summary": "Tests: omitting the summary row. Correct: the table closes at its last row; "
    "no empty score band reserves space.",
    "struct-everything": "Tests: every rhetoric block at once — headline chip, sections, hero lane, "
    "summary row, row emphasis — composed in one artifact. Correct: each block keeps its own zone "
    "(chip on the title line, bands behind rows, lane behind the hero column, score band before the "
    "footer) with zero collisions.",
    "iso-text": "Tests: text as the sole data column — the rendered CellPlacement leak test. Correct: "
    "text runs only; zero mark/dot/bar/pill/tile/chip/glyph markup.",
    "iso-check": "Tests: check marks as the sole kind. Correct: tri-valence vector marks and their "
    "masthead key only; no other kind's markup anywhere.",
    "iso-dot": "Tests: dots as the sole kind. Correct: filled/hollow dots and their key only; no other kind's markup.",
    "iso-bar": "Tests: bars as the sole kind. Correct: tracks, fills, and the shared axis only; no "
    "other kind's markup.",
    "iso-pill": "Tests: pills as the sole kind. Correct: capsule geometry only (gradient Yes, neutral "
    "values); no other kind's markup.",
    "iso-numeric": "Tests: numeric heat as the sole kind. Correct: column washes, tinted values, and "
    "gauged underlines only; no other kind's markup.",
    "iso-chip": "Tests: chips as the sole kind. Correct: packed chip capsules only; no other kind's markup.",
    "iso-glyph": "Tests: registry glyphs as the sole kind. Correct: brand marks only — and unknown "
    "registry ids fail loud at compose time, never silently.",
}


# ── The gallery ──────────────────────────────────────────────────────────────


def build_gallery() -> Gallery:
    """Declare every matrix artifact: specimens, substrate derivation,
    boundaries, surface modes.

    The over-cap entry is deliberately absent here — it is the one case whose
    artifact comes from a REFUSAL rather than a render, so it is built in the
    emitter where its exception can be caught and shown.
    """
    gallery = Gallery("matrices", MATRICES_ROOT, title="Matrix — Specimens + Boundary Suite")
    fixtures = _matrix_fixture_specs()

    for name, caption in SPECIMENS:
        gallery.add(
            f"specimens/{name}_{FLAGSHIP}.svg",
            spec("matrix", GENOME, variant=FLAGSHIP, matrix=fixtures[name]),
            caption=caption,
        )

    # ONE fixture across the whole presentation surface: every variant, in
    # every surface mode. Substrate and surface are two axes of the same
    # question — how does this chassis meet a page — so they are declared and
    # documented together rather than as two half-sweeps.
    from hyperweave.config.loader import load_genomes

    for variant in load_genomes()[GENOME].variants:
        for slug, ground, palette, _what in SURFACE_MODES:
            gallery.add(
                f"presentation/check-{slug}_{variant}.svg",
                spec("matrix", GENOME, variant=variant, matrix=fixtures["check"], ground=ground, palette=palette),
            )

    edges = _matrix_edge_specs()
    for prefix, _heading, _why in BOUNDARY_GROUPS:
        for name, payload in edges.items():
            if name.startswith(prefix):
                gallery.add(
                    f"boundaries/{name}_{FLAGSHIP}.svg",
                    spec("matrix", GENOME, variant=FLAGSHIP, matrix=payload),
                    caption=_MATRIX_EDGE_NOTES[name],
                )

    return gallery


def _over_cap_artifact(gallery: Gallery) -> tuple[str, str]:
    """Build the over-hard-cap refusal and the artifact an embedder would see.

    31 rows is one past the cap. `compose()` raises; the image surfaces answer
    with the SMPTE error artifact at HTTP 200 / X-HW-Error-Code: 422, because a
    broken image in a README teaches nothing and a silent truncation lies.
    Returns (relative path, the refusal text).
    """
    from hyperweave.core.matrix import MatrixCapacityError
    from hyperweave.serve.app import _error_badge
    from scripts.examples.render import write

    payload = {
        "title": "Over cap",
        "columns": [{"id": "v", "label": "V"}],
        "rows": [{"label": f"r{i}", "cells": [{"value": i}]} for i in range(31)],
    }
    rel = f"boundaries/dim-over-cap-31_{FLAGSHIP}.svg"
    try:
        render(gallery_spec(type="matrix", genome_id=GENOME, variant=FLAGSHIP, matrix=payload))
    except MatrixCapacityError as exc:
        write(gallery.root / rel, _error_badge(str(exc), status_code=422))
        return rel, str(exc)
    raise AssertionError("a 31-row matrix must raise MatrixCapacityError — the cap is not being enforced")


def emit(gallery: Gallery) -> Path:
    """Compose the matrix gallery's README from its artifact records."""
    from hyperweave.compose.engine import compose

    doc = Doc(f"HyperWeave {gallery.title}")
    doc.para(
        "One generative frame renders every structured table: columns declare a cell kind",
        "(`text · check · dot · bar · pill · numeric · chip · glyph`), a measured solver places every",
        "coordinate, and each artifact embeds its lossless `hw:payload` (matrix/1), an `hwz/1`",
        "envelope, and a GFM markdown shadow.",
    )
    doc.para(
        "The specimens prove *does it look right*; the boundary suite proves *does it break*.",
        "Both are required — this file is the acceptance surface.",
    )
    doc.rule()

    doc.h2(f"Specimens ({FLAGSHIP})")
    for name, caption in SPECIMENS:
        art = gallery.get(f"specimens/{name}_{FLAGSHIP}.svg")
        doc.h3(f"`{name}`")
        doc.para(caption)
        doc.image(art)

    doc.rule()
    doc.rule()
    doc.h2("Boundary suite")
    doc.para(
        "Every boundary carries REAL-SHAPED data — actual metric names, plausible values — so the",
        "geometry stays judgeable even where the structure is deliberately degenerate.",
    )
    for prefix, heading, why in BOUNDARY_GROUPS:
        doc.h3(heading)
        doc.para(why)
        for art in gallery:
            if not art.rel.startswith(f"boundaries/{prefix}"):
                continue
            doc.raw(f"**`{art.rel.rsplit('/', 1)[-1].removesuffix(f'_{FLAGSHIP}.svg')}`**")
            doc.para(art.caption)
            doc.image(art)
        if prefix == "dim-":
            rel, refusal = _over_cap_artifact(gallery)
            doc.raw("**`dim-over-cap-31`**")
            doc.para(
                "Tests: 31 rows, one past the hard cap. Correct: `compose()` raises",
                "`MatrixCapacityError`; the image surfaces serve this artifact at HTTP 200 /",
                "`X-HW-Error-Code: 422`:",
            )
            doc.raw(f"> `{refusal}`")
            doc.raw(f"![dim-over-cap-31]({rel})")

    doc.rule()
    doc.h2("The markdown shadow")
    doc.para(
        'Every matrix also projects to a GFM table (`--markdown-out` on the CLI, `respond: "json"`',
        'on POST /v1/compose, `render_target="markdown"` on MCP). This is the `check` fixture\'s',
        "actual shadow:",
    )
    shadow = compose(
        gallery_spec(
            type="matrix",
            genome_id=GENOME,
            variant=FLAGSHIP,
            matrix=_matrix_fixture_specs()["check"],
        )
    ).markdown
    doc.details("check.md", shadow)

    doc.h2("Cross-reference")
    doc.bullets(
        [
            "[Proofset index](../README.md) — every gallery",
            "[Presentation sweep](README_PRESENTATION.md) — the check fixture on every variant x surface mode",
            f"[{GENOME} genome](../genomes/{GENOME}/README.md) — the substrate matrix these variants come from",
        ]
    )
    path = gallery.root / "README.md"
    doc.write(path)
    _emit_presentation(gallery)
    return path


def _emit_presentation(gallery: Gallery) -> Path:
    """One chassis across every variant AND every surface mode.

    Split out of the main README because it answers a different question. The
    specimens ask *does each cell kind look right* and the boundary suite asks
    *does it break*; this asks *how does one table meet a page* — which is a
    presentation axis, not a content one, and reads as a sweep rather than a
    tour.

    Substrate and surface are two halves of that same axis, so they belong in
    one document: splitting only the variants out and leaving the surface modes
    behind would leave both halves incomplete.
    """
    from hyperweave.config.loader import load_genomes

    variants = list(load_genomes()[GENOME].variants)
    modes = [(slug, what) for slug, _g, _p, what in SURFACE_MODES]
    doc = Doc("HyperWeave Matrix — Presentation Sweep")
    doc.para(
        f"The `check` fixture on every {GENOME} variant, in every surface mode:",
        f"**{len(variants)} variants x {len(modes)} modes**. One geometry, one payload — what",
        "changes is the paper and how the artifact meets the page under it.",
    )
    doc.bullets([f"**{slug}** — {what}" for slug, what in modes])
    doc.para(
        "The chassis is entirely `--dna-*` and the semantic indicator hues are genome-invariant —",
        "one hue per state, bright enough for both poles — so no variant needs a per-substrate",
        "correction. The mode serializes into the payload, so plate/inlay/twin of one spec are three",
        "distinct content addresses by construction.",
    )
    doc.para(
        "`inlay` and `twin` stay adaptive on purpose: they re-ink live via `prefers-color-scheme`,",
        "so they follow whichever scheme the *viewer* resolves for this page — which a markdown",
        "preview pane can resolve differently from its editor. `plate` bakes one fixed face.",
    )
    doc.rule()

    header = " | ".join(slug for slug, _ in modes)
    divider = " | ".join("---" for _ in modes)
    for variant in variants:
        doc.h2(f"`{variant}`")
        cells = " | ".join(
            f"![check · {variant} · {slug}]({gallery.get(f'presentation/check-{slug}_{variant}.svg').rel})"
            for slug, _ in modes
        )
        doc.raw(f"| {header} |\n| {divider} |\n| {cells} |")

    doc.h2("Cross-reference")
    doc.bullets(
        [
            "[Matrix gallery](README.md) — the specimens and the boundary suite",
            f"[{GENOME} genome](../genomes/{GENOME}/README.md) — the full substrate matrix",
        ]
    )
    path = gallery.root / "README_PRESENTATION.md"
    doc.write(path)
    return path
