"""The positions-only solver seam guard.

Every topology module dispatches per-node sizing/placement through
``compose/diagram/sizing.py:solve_node_box`` and ``compose/diagram/
chrome.py:place_node`` — never the low-level functions directly. Calling
``solve_card_box``/``solve_card_w``/``place_card``/
``place_circle``/``place_head`` straight from a topology
module reintroduces the class of bug the seam was built to close: a solver
under-feeding one of these with a mismatched chassis, hero flag, or mark
advance (three truncation bugs shared this exact shape before the seam
existed). ``solve_node_box``/``place_node`` themselves call the low-level
functions internally — that is their job — so this guard scans the EIGHT
topology modules only, never ``sizing.py``/``chrome.py``.

AST-based, not a substring grep: a topology module's own wrapper helpers
(``_place_card`` in lanes.py, ``_place_dag_node``/``_place_sm`` in graph.py,
``_place_hub``/``_place_member`` in hub.py) legitimately contain the banned
names as a substring but are calls to a DIFFERENT (locally-defined)
identifier — a text-based check would false-positive on every one of them.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DIAGRAM_DIR = REPO_ROOT / "src" / "hyperweave" / "compose" / "diagram"

TOPOLOGY_MODULES = (
    "linear.py",
    "fan.py",
    "radial.py",
    "graph.py",
    "hub.py",
    "axial.py",
    "lanes.py",
    "sequence.py",
)

BANNED_NAMES = frozenset(
    {
        "solve_card_box",
        "solve_card_w",
        "place_card",
        "place_circle",
        "place_head",
    }
)


def _called_names(tree: ast.AST) -> set[str]:
    """Every exact identifier a ``Call`` node invokes — ``bare_name(...)`` or
    ``module.attr(...)`` — so ``_place_card(...)`` (a different identifier)
    never matches ``place_card`` and a hypothetical ``chrome.place_card(...)``
    still would."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


@pytest.mark.parametrize("filename", TOPOLOGY_MODULES)
def test_topology_module_never_calls_low_level_placement_directly(filename: str) -> None:
    path = DIAGRAM_DIR / filename
    tree = ast.parse(path.read_text(), filename=str(path))
    called = _called_names(tree)
    violations = called & BANNED_NAMES
    assert not violations, (
        f"{filename} calls {sorted(violations)} directly — route through "
        "solve_node_box (sizing.py) / place_node (chrome.py) instead, the "
        "positions-only solver seam every topology module shares."
    )


def test_seam_functions_still_exist() -> None:
    """A guard on the guard: if these get renamed, the test above would
    silently stop catching anything (BANNED_NAMES would never match)."""
    from hyperweave.compose.diagram.chrome import place_node
    from hyperweave.compose.diagram.sizing import solve_node_box

    assert callable(solve_node_box)
    assert callable(place_node)
