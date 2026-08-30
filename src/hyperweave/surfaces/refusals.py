"""The caller-error contract every CLI surface answers to.

A refusal is not a crash. When a caller asks for something the engine will not
draw — an illegal orientation, a graph past its cap, an unregistered genome —
the answer has to be one sentence they can act on, not a stack of frames from
inside the solver.

This lived in ``cli.py`` and was applied at five compose/validate call sites,
while the verb surface (``surfaces/cli.py``) caught only ``HwError``. Everything
else in the family subclasses ``ValueError``, so a legality refusal reached a
``transform`` caller as 171 lines of traceback where the identical refusal
reached a ``compose`` caller as one line. The contract could not hold in a
module the verb surface is unable to import: ``cli.py`` imports
``surfaces/cli.py`` to register the verb commands, so the dependency only runs
one way. It lives here, where both sides can reach it.
"""

from __future__ import annotations

import typer


def caller_refusals() -> tuple[type[Exception], ...]:
    """The typed-error family the compose engine raises.

    Everything here must reach the agent as a clean sentence (message + fix),
    never a traceback. The refusal classes span the whole pipeline: structured
    errors (HwError), input/solver refusals (DiagramInputError — caps included
    — and MatrixInputError), and an unregistered genome id
    (GenomeNotFoundError). An HwError that is an ENGINE FAULT rides the same
    catchable tuple but is rendered and exit-coded distinctly — see
    :func:`refusal_exit` — so widening the catch never widens the blame."""
    from hyperweave.compose.resolver import GenomeNotFoundError
    from hyperweave.core.diagram import DiagramInputError
    from hyperweave.core.errors import HwError
    from hyperweave.core.matrix import MatrixInputError

    return (HwError, DiagramInputError, MatrixInputError, GenomeNotFoundError)


def refusal_exit(exc: Exception, *, default: int = 1) -> int:
    """The CLI exit code for one caught typed error.

    A caller refusal keeps the surface's own refusal code (``default``); an
    engine fault exits 70 (EX_SOFTWARE — internal software error) on every
    surface, so scripts and agents can tell "fix your spec" from "report this"
    without parsing prose."""
    from hyperweave.core.errors import HwError

    if isinstance(exc, HwError) and exc.is_engine_fault:
        return 70
    return default


def echo_refusal(exc: Exception) -> None:
    """Print one refusal as clean stderr text: message, then fix.

    An engine fault prints with an ``engine fault:`` prefix — the one visible
    marker that the spec is not the problem."""
    from hyperweave.compose.resolver import GenomeNotFoundError
    from hyperweave.core.errors import HwError

    if isinstance(exc, HwError) and exc.is_engine_fault:
        typer.echo(f"engine fault: {exc.cli_text()}", err=True)
    elif isinstance(exc, HwError):
        typer.echo(exc.cli_text(), err=True)
    elif isinstance(exc, GenomeNotFoundError):
        from hyperweave.config.loader import get_loader

        # GenomeNotFoundError is a KeyError carrying just the id — wording
        # matches validate's GENOME_UNKNOWN so both surfaces teach identically.
        genome_id = exc.args[0] if exc.args else "?"
        typer.echo(f"Error: unknown genome {genome_id!r}", err=True)
        typer.echo(f"  fix: known genomes: {', '.join(sorted(get_loader().genomes))}", err=True)
    else:
        typer.echo(f"Error: {exc}", err=True)
