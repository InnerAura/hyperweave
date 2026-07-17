"""CLI adapters for the verb capabilities — thin over :func:`dispatch`.

Each command acquires input (a source resolved by :func:`_read_source`), calls
``dispatch`` on the corresponding capability, prints the JSON result to stdout,
and maps errors + negative outcomes to exit codes matching the house convention
(``validate``): **2** = input problem (missing/unreadable source, bad JSON),
**1** = the operation ran but the answer is negative (``verify`` invalid,
``diff --exit-code`` differs) or a runtime ``HwError``.

Typer is a core dependency, so this module may import it; ``registry`` and
``capabilities`` stay transport-agnostic. ``register_capability_commands(app)``
attaches the commands; ``cli.py`` gains only the import + that one call.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from hyperweave.core.errors import HwError
from hyperweave.surfaces.registry import CallContext, dispatch

# CLI-surface context: no base_url, so transform/compose emit relative handles.
_CTX = CallContext(surface="cli")


def _read_source(value: str) -> str:
    """Resolve a verb source argument to an artifact SVG / handle string.

    Order: ``-`` → stdin; an existing file path → its text; ``http(s)://`` → a
    synchronous fetch; a raw ``<svg`` string → passthrough; otherwise a
    digest/id handle (a bare hex, ``sha256:...``, or ``/v1/a/{digest}``) passed
    through for the verbs' loader to resolve against the LRU + disk tier. A
    trailing format suffix on a digest handle (``.svg`` / ``.png`` / ``.webp`` /
    ``.static.svg``) is stripped before the handle is returned so the loader
    resolves the source digest.
    """
    if value == "-":
        return sys.stdin.read()
    if value.startswith(("http://", "https://")):
        import httpx

        try:
            resp = httpx.get(value, follow_redirects=True, timeout=15.0)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            typer.echo(f"could not fetch {value}: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        return resp.text
    if "<svg" in value[:1024]:
        return value
    path = Path(value)
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    # A digest/id handle — strip a format suffix so the source digest resolves.
    return _strip_format_suffix(value)


def _strip_format_suffix(handle: str) -> str:
    """Drop a derived-format suffix from a digest handle (keep the digest)."""
    tail = handle.rsplit("/", 1)[-1]
    for suffix in (".static.svg", ".svg", ".png", ".webp", ".gif"):
        if tail.endswith(suffix):
            base = handle[: len(handle) - len(suffix)]
            return base
    return handle


def _run(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a capability, rendering an ``HwError`` to stderr + exit 1."""
    try:
        return _run_async(dispatch(name, payload, _CTX))
    except HwError as exc:
        typer.echo(exc.cli_text(), err=True)
        raise typer.Exit(code=1) from exc


def _run_async(coro: Any) -> dict[str, Any]:
    """Run an async handler to completion, safe under an already-running loop.

    The CLI is a sync surface, but a caller may invoke the Typer app from inside
    an event loop (e.g. a test harness in asyncio-auto mode, or an async host
    embedding the CLI). ``asyncio.run`` raises there, so fall back to a fresh
    loop on a worker thread when a loop is already running.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()  # type: ignore[no-any-return]


def _emit(result: dict[str, Any]) -> None:
    """Print a result dict as indented JSON to stdout."""
    typer.echo(json.dumps(result, indent=2))


def extract_cmd(
    source: Annotated[str, typer.Argument(help="Artifact SVG, a /v1/a/{digest} url/handle, a file path, or '-'.")],
    respond: Annotated[
        str,
        typer.Option("--respond", help="Depth: envelope | payload | markdown."),
    ] = "envelope",
) -> None:
    """Extract the embedded seed at a chosen depth (envelope | payload | markdown)."""
    _emit(_run("extract", {"source": _read_source(source), "respond": respond}))


def verify_cmd(
    source: Annotated[str, typer.Argument(help="Artifact SVG, a /v1/a/{digest} url/handle, a file path, or '-'.")],
) -> None:
    """Recompute the hash; prove id == sha256(payload). Exits 1 when invalid."""
    result = _run("verify", {"source": _read_source(source)})
    _emit(result)
    if not result.get("valid"):
        raise typer.Exit(code=1)


def diff_cmd(
    a: Annotated[str, typer.Argument(help="First artifact (SVG / url / handle / path / '-').")],
    b: Annotated[str, typer.Argument(help="Second artifact (SVG / url / handle / path / '-').")],
    exit_code: Annotated[
        bool,
        typer.Option("--exit-code", help="Exit 1 when the artifacts differ (git-diff convention)."),
    ] = False,
) -> None:
    """Payload-bound structured delta between two artifacts."""
    result = _run("diff", {"a": _read_source(a), "b": _read_source(b)})
    _emit(result)
    if exit_code and not result.get("same"):
        raise typer.Exit(code=1)


def query_cmd(
    source: Annotated[str, typer.Argument(help="Artifact SVG, a /v1/a/{digest} url/handle, a file path, or '-'.")],
    question: Annotated[str, typer.Argument(help="Question resolved against the artifact's envelope.")],
) -> None:
    """Answer a question about an artifact from its compact envelope."""
    _emit(_run("query", {"source": _read_source(source), "question": question}))


def transform_cmd(
    source: Annotated[str, typer.Argument(help="Artifact SVG, a /v1/a/{digest} url/handle, a file path, or '-'.")],
    patch: Annotated[
        Path | None,
        typer.Option("--patch", help="RFC-6902 patch JSON file (a list of ops), or '-' for stdin."),
    ] = None,
    patch_json: Annotated[
        str,
        typer.Option("--patch-json", help="Inline RFC-6902 patch JSON (a list of ops)."),
    ] = "",
    out: Annotated[
        Path | None,
        typer.Option("--output", "--out", "-o", help="Also write the transformed SVG to this file path."),
    ] = None,
) -> None:
    """Mutate an artifact via an RFC-6902 JSON patch → a new artifact.

    Supply the patch inline (``--patch-json '[...]'``), from a file
    (``--patch file.json``), or from stdin (``--patch -``). When the patch comes
    from stdin, the artifact source cannot also be ``-``. ``-o/--out`` writes the
    new artifact's SVG to disk in addition to (never instead of) the envelope
    JSON on stdout.
    """
    if patch_json:
        raw = patch_json
    elif patch is not None and str(patch) == "-":
        if source == "-":
            typer.echo("cannot read both the artifact and the patch from stdin", err=True)
            raise typer.Exit(code=2)
        raw = sys.stdin.read()
    elif patch is not None:
        raw = patch.read_text(encoding="utf-8")
    else:
        typer.echo("provide a patch: --patch <file>, --patch-json '[...]', or --patch -", err=True)
        raise typer.Exit(code=2)

    try:
        ops = json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.echo(f"invalid patch JSON: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if not isinstance(ops, list):
        typer.echo("patch must be a JSON list of RFC-6902 ops", err=True)
        raise typer.Exit(code=2)

    result = _run("transform", {"source": _read_source(source), "mutations": ops})
    _emit(result)

    if out is None:
        # Errors-as-documentation: the emitted url is a relative handle backed
        # by the per-process store — from a bare CLI process it resolves
        # nowhere once this call exits. Name the exits on stderr; the stdout
        # envelope JSON stays byte-identical for pipeline consumers.
        typer.echo("url resolves under `hyperweave serve`; pass -o/--out to write the SVG to a file", err=True)
    else:
        from hyperweave.compose.artifact_store import get_artifact

        new_id = str(result.get("new_id", ""))
        svg = get_artifact(new_id) if new_id else None
        if svg is None:
            typer.echo("transform produced no resolvable artifact to write", err=True)
            raise typer.Exit(code=1)
        out.write_text(svg)
        typer.echo(f"Wrote {out}", err=True)


def register_capability_commands(app: typer.Typer) -> None:
    """Attach the verb-capability CLI commands to ``app``.

    Called once from ``cli.py``; adding a verb capability adds a command here,
    never in ``cli.py``. Command names are the verbs (``extract``/``verify``/
    ``diff``/``query``/``transform``); function names carry a ``_cmd`` suffix to
    avoid shadowing the module-level verb imports.
    """
    app.command("extract")(extract_cmd)
    app.command("verify")(verify_cmd)
    app.command("diff")(diff_cmd)
    app.command("query")(query_cmd)
    app.command("transform")(transform_cmd)
