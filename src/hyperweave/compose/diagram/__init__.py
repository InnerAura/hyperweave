"""Diagram frame engine: IR coercion, topology solvers, motion grammar, projections.

Importing this package registers every layout solver (the slug -> solver
dispatch dict in ``solver.py``) — the matrix kind -> builder precedent.
"""

from hyperweave.compose.diagram import fan, graph, linear, radial, sequence  # noqa: F401  (solver registration)
from hyperweave.compose.diagram.solver import compute_diagram_layout, registered_slugs

__all__ = ["compute_diagram_layout", "registered_slugs"]
