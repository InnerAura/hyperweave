"""Solver-taxonomy gates: the ratified word/expression collapse (convergence
into the fan-linear family in fan.py, ring/flywheel into the cyclic family
in radial.py) must never regrow a duplicate twin, a hardcoded beam
reference, or a hole in the registry. These are structural pins, not
behavioral ones — parity is covered by test_specimen_parity.py; this module
guards the SHAPE of the solver layer, matching the pill-anatomy-deletion
regression guard in test_diagram_shape_orthogonality.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from hyperweave.compose.diagram.solver import registered_slugs
from hyperweave.config.loader import load_diagram_config
from hyperweave.core.diagram import Orientation, Topology, layout_slug

_DIAGRAM_DIR = Path(__file__).resolve().parents[2] / "src" / "hyperweave" / "compose" / "diagram"

# Solver modules only — chrome.py/sizing.py/annotate.py/collide.py/wiring.py
# etc. are shared placement/measurement/motion, not per-topology solvers,
# and are exempt from the solver-scoped gates below.
_SOLVER_FILES = ("fan.py", "linear.py", "radial.py", "hub.py", "axial.py", "lanes.py", "sequence.py", "graph.py")

# graph.py is deliberately excluded from the beam gate: DAG stamps its own
# ``stage_key`` per RANK TRANSITION (a structural fact wiring.py's beam-relay
# staging groups by), which is a legitimate cross-reference to the beam
# CONCEPT, not a solver hardcoding beam as a motion choice — the distinction
# the other seven solver files must never blur.
_BEAM_GATE_FILES = tuple(f for f in _SOLVER_FILES if f != "graph.py")


def test_no_second_fan_solve_twin() -> None:
    """MERGE 1 collapsed solve_convergence into the shared fan-linear
    machinery (``_solve_fan_linear``, direction=in); the duplicate ~80-line
    twin body is gone, but the module still names five ``solve_*`` entry
    points (bilateral/upward/downward keep their own geometry; horizontal
    and convergence are now one-line direction wrappers). Pinned so a future
    convergence-radial/bilateral variant lands as a direction-style wrapper
    around shared machinery, never a new hand-rolled twin."""
    text = (_DIAGRAM_DIR / "fan.py").read_text()
    count = len(re.findall(r"^def solve_", text, re.MULTILINE))
    assert count == 5, f"fan.py declares {count} top-level solve_* functions, expected 5 (pin this test if intentional)"


def test_no_second_cyclic_solve_twin() -> None:
    """MERGE 2 collapsed solve_flywheel/solve_ring into the shared cyclic
    machinery (``_solve_cyclic``, hero-presence discriminated); pinned the
    same way as the fan-linear family."""
    text = (_DIAGRAM_DIR / "radial.py").read_text()
    count = len(re.findall(r"^def solve_", text, re.MULTILINE))
    assert count == 4, (
        f"radial.py declares {count} top-level solve_* functions, expected 4 (pin this test if intentional)"
    )


@pytest.mark.parametrize("filename", _BEAM_GATE_FILES)
def test_beam_stays_dressing(filename: str) -> None:
    """Beam is a per-edge MOTION dress (relation/edge_motion data, resolved
    in wiring.py's ``wire_motion``), never a topology fact a solver
    hardcodes. Zero ``beam`` hits — including comments, case-insensitive —
    in any solver file."""
    text = (_DIAGRAM_DIR / filename).read_text()
    assert "beam" not in text.lower(), f"{filename} references 'beam' — motion dress belongs in wiring.py, not a solver"


def test_node_style_text_read_only_in_hub() -> None:
    """``NodeStyle.TEXT`` (the containerless typographic block) is
    hub-panel-orchestrator's own anatomy choice; no other solver branches
    on it — chrome.py's shared placement dispatch is exempt (it isn't a
    per-topology solver)."""
    hits = {f for f in _SOLVER_FILES if "NodeStyle.TEXT" in (_DIAGRAM_DIR / f).read_text()}
    assert hits == {"hub.py"}, f"NodeStyle.TEXT read in {sorted(hits - {'hub.py'})}, expected only hub.py among solvers"


def test_registry_completeness() -> None:
    """Every Topology value, under every orientation its own
    ``orientation_legality`` entry allows (default ``[horizontal]`` for a
    topology absent from that table), resolves through ``layout_slug`` to a
    solver actually registered — the word -> (solver, expression) registry
    has no gaps. ``layout_slug`` reads only ``topology``/``orientation``, so
    a lightweight duck-typed stub exercises it without constructing a fully
    validated DiagramSpec for every topology's own structural rules."""
    engine = load_diagram_config()
    legality: dict[str, list[str]] = engine.get("orientation_legality") or {}
    registered = set(registered_slugs())
    for topology in Topology:
        legal_orientations = legality.get(topology.value, ["horizontal"])
        for orientation_value in legal_orientations:
            orientation = Orientation(orientation_value)
            spec_stub = SimpleNamespace(topology=topology, orientation=orientation)
            slug = layout_slug(spec_stub)  # type: ignore[arg-type]
            assert slug in registered, (
                f"{topology.value}:{orientation.value} resolves to slug {slug!r}, "
                f"which has no registered solver (registered: {sorted(registered)})"
            )
