"""Deterministic spec generators for the spatial property battery.

Each generator yields ``(name, compose_kwargs)`` pairs inside the engine's
declared caps, varying the axes the audits showed matter — node count, label
and description length, edge pattern, band and row counts. No randomness:
the same grid composes on every machine, and a failing name reproduces
directly through ``hw compose``.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

Case = tuple[str, dict[str, Any]]

_BANK = ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa", "lambda", "mu")
SHORT, LONG = 10, 46


def text(n_chars: int, offset: int = 0) -> str:
    """A deterministic run of at least ``n_chars`` characters from a word bank."""
    words: list[str] = []
    i = offset
    while len(" ".join(words)) < n_chars:
        words.append(_BANK[i % len(_BANK)])
        i += 1
    return " ".join(words)


def _diagram(name: str, spec: dict[str, Any]) -> Case:
    return name, {"type": "diagram", "genome_id": "primer", "diagram": spec}


def _matrix(name: str, spec: dict[str, Any]) -> Case:
    return name, {"type": "matrix", "genome_id": "primer", "matrix": spec}


def pipelines() -> Iterator[Case]:
    for n in (2, 4, 7):
        for desc_len in (0, SHORT, LONG):
            nodes = [
                {"id": f"s{i}", "label": f"Stage {i}", **({"desc": text(desc_len, i)} if desc_len else {})}
                for i in range(n)
            ]
            yield _diagram(f"pipeline-n{n}-desc{desc_len}", {"topology": "pipeline", "nodes": nodes})


def stacks() -> Iterator[Case]:
    for n in (3, 5):
        for direction in ("up", "down"):
            for bypass in (False, True):
                nodes = [{"id": "crown", "label": "Crown", "role": "hero"}] + [
                    {"id": f"l{i}", "label": f"Layer {i}"} for i in range(1, n)
                ]
                order = [f"l{i}" for i in range(n - 1, 0, -1)] + ["crown"]
                if direction == "down":
                    order = list(reversed(order))
                edges = [{"source": a, "target": b} for a, b in pairwise(order)]
                if bypass and n > 3:
                    edges.append({"source": f"l{n - 1}", "target": "crown", "relation": "bypass"})
                yield _diagram(
                    f"stack-n{n}-{direction}{'-bypass' if bypass else ''}",
                    {"topology": "pipeline", "orientation": "vertical", "nodes": nodes, "edges": edges},
                )


def lanes() -> Iterator[Case]:
    for bands in (2, 3, 5):
        for rows in (2, 3):
            categories = [text(LONG if bands == 3 else SHORT, b).title() for b in range(bands)]
            nodes = [
                {"id": f"n{b}_{r}", "label": f"Node {b}.{r}", "category": categories[b]}
                for b in range(bands)
                for r in range(rows)
            ]
            edges = [{"source": f"n{b}_0", "target": f"n{b + 1}_0", "label": text(SHORT, b)} for b in range(bands - 1)]
            if rows >= 3:
                edges.append({"source": "n0_0", "target": "n0_2", "label": "skip"})
            yield _diagram(
                f"lanes-b{bands}-r{rows}",
                {"topology": "lanes", "lanes": categories, "nodes": nodes, "edges": edges},
            )


def sequences() -> Iterator[Case]:
    for lifelines in (2, 3, 4):
        for messages in (2, 5, 8):
            for label_len in (SHORT, LONG):
                nodes = [{"id": f"p{i}", "label": f"Party {i}"} for i in range(lifelines)]
                edges = []
                for m in range(messages):
                    a, b = m % lifelines, (m + 1) % lifelines
                    edges.append(
                        {
                            "source": f"p{a}",
                            "target": f"p{b}",
                            "label": text(label_len, m),
                            "kind": "return" if m % 3 == 2 else "call",
                        }
                    )
                yield _diagram(
                    f"sequence-l{lifelines}-m{messages}-len{label_len}",
                    {"topology": "sequence", "nodes": nodes, "edges": edges},
                )
    yield _diagram(
        "sequence-selfcall",
        {
            "topology": "sequence",
            "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            "edges": [
                {"source": "a", "target": "b", "label": "call", "kind": "call"},
                {"source": "b", "target": "b", "label": "validate()", "kind": "call"},
                {"source": "b", "target": "a", "label": "ok", "kind": "return"},
            ],
        },
    )


def state_machines() -> Iterator[Case]:
    for states in (3, 5, 8):
        for back_edges in (1, 2):
            nodes = [{"id": f"s{i}", "label": text(SHORT, i).title()} for i in range(states)]
            edges = [{"source": f"s{i}", "target": f"s{i + 1}", "label": f"go{i}"} for i in range(states - 1)]
            edges.append({"source": f"s{states - 1}", "target": "s0", "label": "retry"})
            if back_edges == 2 and states >= 4:
                edges.append({"source": f"s{states - 2}", "target": "s1", "label": "revise"})
            yield _diagram(
                f"sm-n{states}-back{back_edges}", {"topology": "state-machine", "nodes": nodes, "edges": edges}
            )


def hubs() -> Iterator[Case]:
    for spokes in (3, 6, 8):
        for desc_len in (SHORT, LONG):
            nodes = [{"id": "hero", "label": "Hub", "role": "hero", "desc": text(desc_len)}] + [
                {"id": f"s{i}", "label": f"Spoke {i}", "desc": text(desc_len, i)} for i in range(spokes)
            ]
            edges = [{"source": "hero", "target": f"s{i}", "label": f"op{i}"} for i in range(spokes)]
            yield _diagram(f"hub-s{spokes}-desc{desc_len}", {"topology": "hub", "nodes": nodes, "edges": edges})


def fanouts() -> Iterator[Case]:
    caps = {"horizontal": 8, "bilateral": 6, "upward": 6, "downward": 7, "radial": 8}
    for orientation, dests in caps.items():
        for label_len in (SHORT, LONG):
            nodes = [{"id": "src", "label": "Source", "role": "hero"}] + [
                {"id": f"d{i}", "label": text(label_len, i).title()} for i in range(dests)
            ]
            edges = [{"source": "src", "target": f"d{i}"} for i in range(dests)]
            yield _diagram(
                f"fanout-{orientation}-d{dests}-len{label_len}",
                {"topology": "fanout", "orientation": orientation, "nodes": nodes, "edges": edges},
            )


def trees() -> Iterator[Case]:
    shapes = {"balanced": (2, 2), "asymmetric": (1, 4)}
    for name, (left, right) in shapes.items():
        nodes = [
            {"id": "root", "label": "Root", "role": "hero"},
            {"id": "a", "label": text(LONG).title()},
            {"id": "b", "label": "B"},
        ]
        edges = [{"source": "root", "target": "a"}, {"source": "root", "target": "b"}]
        for i in range(left):
            nodes.append({"id": f"a{i}", "label": f"Leaf a{i}"})
            edges.append({"source": "a", "target": f"a{i}"})
        for i in range(right):
            nodes.append({"id": f"b{i}", "label": f"Leaf b{i}"})
            edges.append({"source": "b", "target": f"b{i}"})
        yield _diagram(f"tree-{name}", {"topology": "tree", "nodes": nodes, "edges": edges})


def matrices() -> Iterator[Case]:
    kinds = ("check", "chip", "numeric", "text")
    for n_cols in (2, 5, 9):
        for header_len in (SHORT, LONG):
            for label_len in (SHORT, LONG):
                columns = [{"id": "l", "label": "LABEL", "role": "label"}]
                for j in range(n_cols):
                    kind = kinds[j % len(kinds)]
                    col: dict[str, Any] = {"id": f"c{j}", "label": text(header_len, j).upper(), "kind": kind}
                    if kind == "numeric":
                        col["polarity"] = "higher"
                    columns.append(col)
                rows = []
                for r in range(3):
                    cells = []
                    for j in range(n_cols):
                        kind = kinds[j % len(kinds)]
                        if kind == "check":
                            cells.append({"state": ("full", "partial", "none")[(r + j) % 3]})
                        elif kind == "chip":
                            cells.append({"chips": [text(SHORT, r + j).split()[0]]})
                        elif kind == "numeric":
                            cells.append({"value": 10 * (r + 1) + j})
                        else:
                            cells.append({"value": text(SHORT, r)})
                    rows.append({"label": text(label_len, r).title(), "cells": cells})
                yield _matrix(
                    f"matrix-c{n_cols}-head{header_len}-label{label_len}",
                    {"title": "Generated matrix", "columns": columns, "rows": rows},
                )


def all_cases() -> list[Case]:
    cases: list[Case] = []
    for gen in (pipelines, stacks, lanes, sequences, state_machines, hubs, fanouts, trees, matrices):
        cases.extend(gen())
    return cases
