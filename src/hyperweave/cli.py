"""HyperWeave CLI -- Typer application."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

app = typer.Typer(
    name="hyperweave",
    help="Compositor API for self-contained SVG artifacts.",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    """Eager ``--version`` — print and exit before any subcommand resolves."""
    if value:
        from hyperweave import __version__

        typer.echo(f"hyperweave v{__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Print the version and exit."),
    ] = False,
) -> None:
    """Compositor API for self-contained SVG artifacts."""


# Primer's chromatic variants. Receipts render on the primer genome; the only
# axis a user picks is which variant supplies the chromatics. Typing a bare
# variant name (``--genome noir``) resolves to genome=primer / variant=noir so
# the ergonomic short-form survives the retirement of the pre-genome skins.
_PRIMER_VARIANTS = frozenset({"noir", "carbon", "space", "anvil", "porcelain", "cream", "dusk", "petrol"})


def _hyperweave_root() -> Path:
    """Resolve the project-root anchor for the ``.hyperweave`` telemetry corpus.

    Session-receipt hooks fire with whatever working directory the session was
    left in -- often a subdirectory the agent ``cd``'d into. A bare relative
    ``Path(".hyperweave")`` would then scatter receipts into that subdirectory.
    Anchor to the project root instead: honor ``CLAUDE_PROJECT_DIR`` (set by the
    Claude Code hook runner), else walk up to the nearest ``.git`` marker, else
    fall back to the current directory.
    """
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root and Path(env_root).is_dir():
        return Path(env_root)
    here = Path.cwd()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return here


def _looks_like_path(value: str) -> bool:
    """A crude path/bundled-name split: contains a separator or a `.json` suffix."""
    return "/" in value or "\\" in value or value.endswith(".json")


def _classify_spec_shape(data: dict[str, Any]) -> str:
    """ONE shape decision for compose AND validate: ``envelope`` |
    ``envelope-missing-spec`` | ``diagram`` | ``matrix`` | ``unknown``.

    Both verbs consume this result — the two sniffers previously made the
    call independently and gave contradictory diagnoses for an envelope
    missing its ``spec`` object. A ``type`` key always means envelope-family
    (bare IR never has one — DiagramSpec/MatrixSpec forbid extras)."""
    if "type" in data:
        return "envelope" if isinstance(data.get("spec"), dict) else "envelope-missing-spec"
    if "topology" in data:
        return "diagram"
    if {"columns", "rows"} & data.keys():
        return "matrix"
    return "unknown"


def _echo_envelope_missing_spec(data: dict[str, Any]) -> None:
    """The shared (compose ≡ validate) diagnosis for a spec-less envelope."""
    typer.echo(
        f"Error: the envelope declares type {str(data.get('type', ''))!r} but has no 'spec' object; "
        "put the frame IR under spec: {...} (or drop 'type' and pass bare IR)",
        err=True,
    )


def _is_bundled_name(name: str) -> bool:
    from hyperweave.compose.bundled_specs import bundled_spec_names

    return any(name in bundled_spec_names(frame) for frame in ("diagram", "matrix"))


def _read_spec_source(spec_file: Path) -> tuple[str, Any]:
    """Resolve a spec-file argument to ``('data', parsed_dict)`` or ``('preset', name)``.

    The one file-vs-preset decision for compose AND validate:

    * a real FILE parses as JSON — with a loud stderr note when its bare name
      also matches a bundled spec (the local file wins);
    * a DIRECTORY is never spec input — a bare name falls through to the
      bundled store (with a note; preset names like ``stack``/``tree`` double
      as common directory names), a path-looking one errors cleanly;
    * a MISSING path-looking value errors cleanly (``not found``);
    * anything else is a bundled-spec name.

    Exits 2 on invalid JSON, non-object JSON, or a directory path.
    """
    name = str(spec_file)
    if spec_file.is_file():
        import json

        try:
            data = json.loads(spec_file.read_text())
        except json.JSONDecodeError as exc:
            typer.echo(f"Error: {spec_file} is not valid JSON: {exc}", err=True)
            raise typer.Exit(2) from exc
        if not isinstance(data, dict):
            typer.echo(f"Error: {spec_file} must contain a JSON object", err=True)
            raise typer.Exit(2)
        if not _looks_like_path(name) and _is_bundled_name(name):
            typer.echo(
                f"note: reading local file '{name}', which shadows the bundled spec of the same name "
                f"(pass ./{name} to silence this, or rename the file to use the bundled spec)",
                err=True,
            )
        return "data", data
    if spec_file.is_dir():
        if _looks_like_path(name):
            typer.echo(f"Error: {spec_file} is a directory, not a spec file", err=True)
            raise typer.Exit(2)
        typer.echo(f"note: '{name}' is a directory here; resolving it as a bundled spec name", err=True)
        return "preset", name
    if _looks_like_path(name):
        typer.echo(f"Error: {spec_file} not found", err=True)
        raise typer.Exit(2)
    return "preset", name


def _compose_refusals() -> tuple[type[Exception], ...]:
    """The caller-error family the compose engine raises.

    Everything here must reach the agent as a clean sentence (message + fix,
    exit 2), never a traceback — the refusal classes span the whole pipeline:
    structured errors (HwError), input/solver refusals (DiagramInputError —
    caps included — and MatrixInputError), and an unregistered genome id
    (GenomeNotFoundError)."""
    from hyperweave.compose.resolver import GenomeNotFoundError
    from hyperweave.core.diagram import DiagramInputError
    from hyperweave.core.errors import HwError
    from hyperweave.core.matrix import MatrixInputError

    return (HwError, DiagramInputError, MatrixInputError, GenomeNotFoundError)


def _echo_refusal(exc: Exception) -> None:
    """Print one compose refusal as clean stderr text: message, then fix."""
    from hyperweave.compose.resolver import GenomeNotFoundError
    from hyperweave.core.errors import HwError

    if isinstance(exc, HwError):
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


def _sniff_spec_shape(
    frame_type: str,
    data: dict[str, Any],
    *,
    genome: str,
    variant: str,
    genome_explicit: bool,
    variant_explicit: bool,
) -> tuple[Any, str, str]:
    """Shape-sniff a parsed ``--spec-file``/``--spec`` JSON object.

    Two accepted shapes, matching what ``validate`` accepts (one spec shape
    everywhere): a ``{type, spec, genome?, variant?}`` envelope, or bare frame
    IR (a literal ``DiagramSpec``/``MatrixSpec``-shaped dict). An envelope's
    ``type`` must match the ``compose <frame_type>`` argument — a mismatch is
    a clean caller error, not a downstream pydantic explosion. An envelope's
    ``genome``/``variant`` apply ONLY where the caller left the corresponding
    CLI flag at its default; an explicit ``--genome``/``--variant`` always wins.
    Returns ``(BundledSpec, resolved_genome, resolved_variant)``.
    """
    from hyperweave.compose.bundled_specs import BundledSpec

    ir_field = "diagram" if frame_type == "diagram" else "matrix"
    shape = _classify_spec_shape(data)
    if shape == "envelope":
        env_type = str(data.get("type", ""))
        if env_type != frame_type:
            typer.echo(
                f"Error: the spec envelope declares type {env_type!r}, but `compose {frame_type}` "
                f"needs a {frame_type!r} envelope (or bare {frame_type} IR)",
                err=True,
            )
            raise typer.Exit(2)
        resolved_genome = genome if genome_explicit else (str(data.get("genome", "")) or genome)
        resolved_variant = variant if variant_explicit else (str(data.get("variant", "")) or variant)
        return BundledSpec(field=ir_field, value=dict(data["spec"])), resolved_genome, resolved_variant
    if shape == "envelope-missing-spec":
        _echo_envelope_missing_spec(data)
        raise typer.Exit(2)
    # Bare IR (or an unknown shape): compose knows the frame from argv, so the
    # dict parses as that frame's IR and pydantic names every missing field.
    return BundledSpec(field=ir_field, value=data), genome, variant


def _resolve_spec_file(
    frame_type: str,
    spec_file: Path | None,
    *,
    genome: str = "",
    variant: str = "",
    genome_explicit: bool = False,
    variant_explicit: bool = False,
) -> tuple[Any, str, str]:
    """Resolve ``--spec-file`` for matrix/diagram: a JSON path OR a bundled name.

    The retired ``--preset`` flag folds into ``--spec-file``: if the value
    is an existing file it is parsed as the frame's IR OR a ``{type, spec}``
    envelope (see :func:`_sniff_spec_shape`); if it is not a path it resolves
    against the single bundled-spec store (the same store the HTTP GET
    ``/v1/{matrix,diagram}/{name}`` routes read). Returns
    ``(BundledSpec | None, resolved_genome, resolved_variant)`` — ``None`` for
    the spec when no ``--spec-file`` was given. Exits 2 on a bad file / name.
    """
    from hyperweave.compose.bundled_specs import resolve_bundled_spec

    if spec_file is None:
        return None, genome, variant
    kind, payload = _read_spec_source(spec_file)
    if kind == "data":
        return _sniff_spec_shape(
            frame_type,
            payload,
            genome=genome,
            variant=variant,
            genome_explicit=genome_explicit,
            variant_explicit=variant_explicit,
        )
    # kind == "preset": resolve the bare name against the bundled store.
    from hyperweave.core.errors import HwError

    try:
        return resolve_bundled_spec(frame_type, payload), genome, variant
    except HwError as exc:
        typer.echo(f"Error: {exc.cli_text()}", err=True)
        raise typer.Exit(2) from exc


def _resolve_inline_spec(
    frame_type: str,
    spec_inline: str,
    *,
    genome: str,
    variant: str,
    genome_explicit: bool,
    variant_explicit: bool,
) -> tuple[Any, str, str]:
    """Resolve ``--spec`` (inline JSON) the same way ``--spec-file`` resolves
    a file's contents: a bare frame IR or a ``{type, spec}`` envelope."""
    import json

    try:
        data = json.loads(spec_inline)
    except json.JSONDecodeError as exc:
        typer.echo(f"Error: --spec is not valid JSON: {exc}", err=True)
        raise typer.Exit(2) from exc
    if not isinstance(data, dict):
        typer.echo("Error: --spec must be a JSON object", err=True)
        raise typer.Exit(2)
    return _sniff_spec_shape(
        frame_type,
        data,
        genome=genome,
        variant=variant,
        genome_explicit=genome_explicit,
        variant_explicit=variant_explicit,
    )


def _deliver_projection(data: bytes, *, is_text: bool, output: Path | None, width: int, height: int) -> None:
    """Write a projection's bytes to a file, stdout, or a terminal blit.

    The one delivery model the CLI names is bytes to ``-o``/stdout. A file always
    gets raw bytes. For stdout, text projections (svg/svg-static) print as text;
    raster projections (png/webp) blit into a graphics-capable interactive
    terminal (kitty protocol, auto-detected — no flag), print a redirect hint to
    an interactive non-capable terminal (never binary at a TTY), and stream raw
    bytes when piped/redirected (``not isatty`` — the ls/git/bat convention).
    """
    if output is not None:
        output.write_bytes(data)
        typer.echo(f"Wrote {output} ({width}x{height})", err=True)
        return

    if is_text:
        sys.stdout.write(data.decode("utf-8"))
        return

    # Raster bytes to stdout: blit / hint / raw depending on the stream.
    if sys.stdout.isatty():
        from hyperweave.delivery import kitty

        if kitty.terminal_supports_graphics():
            kitty.blit(data, sys.stdout.buffer)
            typer.echo("shown in the terminal only — add -o out.png to save a file", err=True)
        else:
            typer.echo(
                "raster output is binary; this terminal can't display it inline. "
                "save to a file: hyperweave compose ... -o out.png",
                err=True,
            )
            raise typer.Exit(2)
    else:
        sys.stdout.buffer.write(data)


def _resolve_receipt_genome(slug: str) -> tuple[str, str]:
    """Resolve a receipt ``--genome`` slug to a ``(genome, variant)`` pair.

    Three cases:

    * a bare primer variant (``noir`` … ``petrol``) → ``("primer", <name>)`` so
      ``--genome cream`` renders a primer **cream** receipt (no skin collision);
    * a real receipt-capable genome slug (``primer``, ``raw``) → ``(slug, "")``;
    * empty / anything else → ``("", "")``, letting the resolver fall back to
      primer/porcelain.

    A dotted slug (``primer.cream``) splits into ``("primer", "cream")`` so every
    receipt entry point (compose, the session alias, install-hook) accepts the
    dotted ``--genome`` form. The bare primer-variant shorthand still works.

    The pre-genome ``telemetry-*`` skins (and their ``cream``/``voltage``/
    ``claude-code`` short-forms) are retired: they were never variants and no
    longer resolve here.
    """
    s = (slug or "").strip().lower()
    if not s:
        return "", ""
    if "." in s:
        base, _, dotted_variant = s.partition(".")
        return base, dotted_variant
    if s in _PRIMER_VARIANTS:
        return "primer", s
    return s, ""


def _render_receipt_from_transcript(
    transcript_path: Path | None,
    genome: str = "",
    variant: str = "",
    output: Path | None = None,
    *,
    hook_mode: bool = False,
) -> None:
    """Parse an agent ``.jsonl`` transcript and render a session receipt.

    The single receipt-from-transcript path: powers ``compose receipt x.jsonl``,
    ``compose x.jsonl`` (extension-inferred), and ``compose -`` (reads hook JSON
    from stdin). The receipt renders on the primer genome; a primer variant
    (noir…petrol) selects the chromatics. Hook mode no-ops silently when a
    SessionEnd fires with no transcript.
    """
    import json

    # Resolve the transcript path: explicit arg > stdin hook JSON (hook mode).
    if transcript_path is None and not sys.stdin.isatty():
        try:
            hook_input = json.load(sys.stdin)
            raw_path = hook_input.get("transcript_path", "")
            if raw_path:
                transcript_path = Path(raw_path)
        except (json.JSONDecodeError, AttributeError):
            pass

    if not transcript_path or not transcript_path.exists():
        if hook_mode or not sys.stdin.isatty():
            return  # graceful no-op for a hook SessionEnd with no transcript
        typer.echo("Error: no transcript found (pass a .jsonl path or pipe hook JSON on stdin)", err=True)
        raise typer.Exit(1)

    from datetime import datetime as _dt

    from hyperweave.compose.engine import compose as do_compose
    from hyperweave.core.models import ComposeSpec
    from hyperweave.telemetry.contract import build_contract, build_receipt_contract
    from hyperweave.telemetry.receipt_paths import receipt_filename, slugify_session_name

    contract = build_contract(str(transcript_path))

    # Skip empty sessions (opened, did nothing, closed) — a blank receipt is noise.
    if not contract.get("tools") and contract.get("profile", {}).get("total_cost", 0) == 0:
        if sys.stdin.isatty():
            sid = contract.get("session", {}).get("id", "unknown")
            typer.echo(f"Skipped empty session {sid}: no tool calls, no cost.", err=True)
        return

    genome_slug, inferred_variant = _resolve_receipt_genome(genome)
    variant_slug = variant or inferred_variant

    sess = contract.get("session", {})
    user_events = contract.get("user_events", []) or []
    first_prompt = user_events[0].get("preview", "") if user_events else ""
    display_name = sess.get("name", "") or slugify_session_name(first_prompt[:40])

    if not output:
        try:
            ts = _dt.fromisoformat(sess.get("start", ""))
        except (TypeError, ValueError):
            ts = _dt.now()
        hw_dir = _hyperweave_root() / ".hyperweave" / "receipts"
        hw_dir.mkdir(parents=True, exist_ok=True)
        output = hw_dir / receipt_filename(timestamp=ts, session_id=sess.get("id", "unknown"), prompt_text=first_prompt)

    receipt_payload = build_receipt_contract(str(transcript_path))
    spec = ComposeSpec(
        type="receipt",
        genome_id=genome_slug,
        variant=variant_slug,
        telemetry_data=receipt_payload,
        receipt_display_name=display_name,
    )
    try:
        result = do_compose(spec)
    except _compose_refusals() as exc:
        _echo_refusal(exc)
        raise typer.Exit(2) from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.svg)

    cost = receipt_payload.get("cost_usd", 0)
    total_tok = receipt_payload.get("tokens", {}).get("total", 0)
    dur = receipt_payload.get("active_min", 0)
    tok_label = f"{total_tok / 1_000_000:.1f}M" if total_tok >= 1_000_000 else f"{total_tok / 1000:.1f}K"
    typer.echo(f"Receipt: ${cost:.2f} · {tok_label} tokens · {int(dur)}m -> {output}", err=True)


@app.command()
def version() -> None:
    """Print the HyperWeave version."""
    from hyperweave import __version__

    typer.echo(f"hyperweave v{__version__}")


def _sniff_validate_shape(data: dict[str, Any]) -> Any:
    """Sniff a parsed JSON object into a :class:`SpecEnvelope` for ``validate``.

    Mirrors :func:`_sniff_spec_shape` (one spec shape everywhere): a
    ``{type, spec, genome?, variant?}`` envelope, or bare frame IR inferred
    from its distinctive fields — ``topology`` (diagram) or ``columns``/
    ``rows`` (matrix). Neither shape matching is a clean caller error naming
    both accepted forms, never a raw pydantic explosion.
    """
    from hyperweave.compose.surface import SpecEnvelope

    shape = _classify_spec_shape(data)
    if shape == "envelope":
        return SpecEnvelope(
            type=str(data.get("type", "")),
            genome=str(data.get("genome", "")),
            variant=str(data.get("variant", "")),
            spec=dict(data["spec"]),
        )
    if shape == "envelope-missing-spec":
        _echo_envelope_missing_spec(data)
        raise typer.Exit(code=2)
    if shape == "diagram":
        return SpecEnvelope(type="diagram", spec=data)
    if shape == "matrix":
        return SpecEnvelope(type="matrix", spec=data)
    typer.echo(
        "invalid spec: expected a {type, spec} envelope, bare diagram IR (a 'topology' key), "
        "or bare matrix IR ('columns'/'rows' keys)",
        err=True,
    )
    raise typer.Exit(code=2)


def _resolve_validate_preset(name: str) -> Any:
    """Resolve a bundled preset NAME (not a path) into a :class:`SpecEnvelope`.

    Tries the diagram store then the matrix store (the same two stores
    ``compose --spec-file`` reads); a matrix preset's payload is a
    ``connector_data`` adapter dict, so it rides ``spec.connector_data``
    (lifted to the ComposeSpec field of the same name) rather than
    ``spec.matrix``. Returns ``None`` when the name matches neither store.
    """
    from hyperweave.compose.bundled_specs import resolve_bundled_spec
    from hyperweave.compose.surface import SpecEnvelope
    from hyperweave.core.errors import HwError

    for frame_type in ("diagram", "matrix"):
        try:
            bundled = resolve_bundled_spec(frame_type, name)
        except HwError:
            continue
        spec_body = dict(bundled.value) if bundled.field == "diagram" else {bundled.field: bundled.value}
        return SpecEnvelope(type=frame_type, spec=spec_body)
    return None


@app.command()
def validate(
    spec_file: Annotated[
        Path | None,
        typer.Argument(help="Spec envelope JSON file, bare IR JSON file, bundled preset name, or '-' for stdin."),
    ] = None,
    spec_file_opt: Annotated[
        Path | None,
        typer.Option("--spec-file", help="Same as the positional spec-file argument."),
    ] = None,
    spec: Annotated[str, typer.Option("--spec", help="Inline spec envelope or bare IR JSON.")] = "",
) -> None:
    """Validate a spec envelope, bare IR, or bundled preset name without rendering.

    Accepts the same shapes ``compose --spec-file``/``--spec`` accept: a
    ``{type, spec}`` envelope, bare diagram/matrix IR, or a bundled preset
    name (resolved against the diagram then matrix store). Exits non-zero
    when invalid.
    """
    import json as _json

    from hyperweave.compose.surface import validate_surface

    if spec_file is not None and spec_file_opt is not None and str(spec_file) != str(spec_file_opt):
        typer.echo("Error: the positional spec-file and --spec-file disagree; pass only one", err=True)
        raise typer.Exit(code=2)
    spec_file = spec_file if spec_file is not None else spec_file_opt

    env: Any = None
    raw = ""
    if spec:
        raw = spec
    elif spec_file is not None and str(spec_file) == "-":
        raw = sys.stdin.read()
    elif spec_file is not None:
        # The SAME file-vs-preset decision compose makes (is_file/is_dir/
        # missing/shadow all handled there — never an IsADirectoryError).
        kind, payload = _read_spec_source(spec_file)
        if kind == "data":
            env = _sniff_validate_shape(payload)
        else:
            env = _resolve_validate_preset(payload)
            if env is None:
                from hyperweave.compose.bundled_specs import bundled_spec_names

                typer.echo(
                    f"Error: {payload!r} is not a spec file, and matches no bundled diagram or matrix preset.\n"
                    f"  known diagram specs: {', '.join(bundled_spec_names('diagram')) or '(none configured)'}\n"
                    f"  known matrix specs: {', '.join(bundled_spec_names('matrix')) or '(none configured)'}",
                    err=True,
                )
                raise typer.Exit(code=2)
    else:
        typer.echo("provide a spec file, --spec '{...}', or - for stdin", err=True)
        raise typer.Exit(code=2)

    if env is None:
        try:
            data = _json.loads(raw)
        except _json.JSONDecodeError as exc:
            typer.echo(f"invalid JSON: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        if not isinstance(data, dict):
            typer.echo("invalid spec: top-level JSON must be an object", err=True)
            raise typer.Exit(code=2)
        env = _sniff_validate_shape(data)

    report = validate_surface(env)
    if report.get("valid"):
        typer.echo(f"valid: {report['type']} ({report['genome']})")
        return
    err = report.get("error", {})
    typer.echo(f"INVALID [{err.get('code')}]: {err.get('message')}", err=True)
    if err.get("fix"):
        typer.echo(f"  fix: {err['fix']}", err=True)
    raise typer.Exit(code=1)


@app.command()
def compose(
    frame_type: Annotated[
        str,
        typer.Argument(help="Frame: badge, strip, icon, divider, marquee, card, chart, matrix, diagram"),
    ],
    title: Annotated[str, typer.Argument(help="Primary text (label, identity, username, owner/repo, ...)")] = "",
    value: Annotated[str, typer.Argument(help="Secondary text or chart subtype (e.g. 'stars')")] = "",
    genome: Annotated[
        str,
        typer.Option(
            "--genome",
            "-g",
            help="Genome id, or dotted 'genome.variant' (e.g. primer.porcelain). Default: primer.",
        ),
    ] = "",
    genome_file: Annotated[
        Path | None,
        typer.Option(
            "--genome-file",
            help="Path to a local genome JSON file (bypasses built-in registry)",
        ),
    ] = None,
    state: Annotated[str, typer.Option("--state", "-s")] = "active",
    motion: Annotated[str, typer.Option("--motion", "-m")] = "static",
    glyph: Annotated[str, typer.Option("--glyph")] = "",
    glyph_mode: Annotated[str, typer.Option("--glyph-mode")] = "auto",
    regime: Annotated[str, typer.Option("--regime")] = "normal",
    size: Annotated[str, typer.Option("--size")] = "default",
    shape: Annotated[str, typer.Option("--shape", help="Icon shape: square, circle")] = "",
    variant: Annotated[
        str,
        typer.Option(
            "--variant",
            help="Variant slug (whitelist in genome JSON)",
        ),
    ] = "",
    pair: Annotated[
        str,
        typer.Option(
            "--pair",
            help=(
                "Cellular paradigm pairing modifier (automata only). "
                "Composes any solo tone with any other solo tone. "
                "Bifamily frames (strip, divider) consume the pair; "
                "other frames silently ignore it."
            ),
        ),
    ] = "",
    state_glyph_shape: Annotated[
        str,
        typer.Option("--state-glyph-shape", help="Badge state-indicator shape: square | circle | diamond"),
    ] = "",
    # Divider options
    divider_variant: Annotated[str, typer.Option("--divider-variant")] = "zeropoint",
    # Marquee options
    direction: Annotated[str, typer.Option("--direction")] = "ltr",
    data: Annotated[
        str,
        typer.Option(
            "--data",
            help=(
                "Data tokens, comma-separated. Forms: text:STRING | kv:KEY=VALUE | "
                "gh:owner/repo.metric | pypi:pkg.metric | npm:pkg.metric | "
                "hf:org/model.metric | arxiv:id.metric | docker:owner/image.metric | "
                "crates:pkg.metric | scorecard:owner/repo.metric | dora:owner/repo.metric. "
                "Embedded commas in text/kv payloads escape as \\,."
            ),
        ),
    ] = "",
    # Matrix / diagram options
    spec_file: Annotated[
        Path | None,
        typer.Option(
            "--spec-file",
            help=(
                "MatrixSpec/DiagramSpec JSON file, a bundled-spec name (matrix: connectors; diagram: "
                "rag-pipeline, ..), or a {type, spec} envelope matching the frame. Mutually exclusive with --spec."
            ),
        ),
    ] = None,
    spec_inline: Annotated[
        str,
        typer.Option(
            "--spec",
            help=(
                "Inline MatrixSpec/DiagramSpec JSON, or a {type, spec} envelope matching the frame. "
                "Matrix/diagram frames only; mutually exclusive with --spec-file."
            ),
        ),
    ] = "",
    preset: Annotated[
        str,
        typer.Option("--preset", hidden=True, help="Removed — pass the bundled-spec name to --spec-file instead."),
    ] = "",
    markdown_out: Annotated[
        Path | None,
        typer.Option("--markdown-out", help="Also write the markdown shadow (matrix/diagram frames)"),
    ] = None,
    glyph_tint: Annotated[
        str,
        typer.Option(
            "--glyph-tint",
            help="Glyph fill selection: ink | brand | full (per-slot IR declarations outrank it)",
        ),
    ] = "",
    performance: Annotated[
        str,
        typer.Option(
            "--performance",
            help="Surface tier (diagram motion is composite-only by construction; recorded in the payload)",
        ),
    ] = "",
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output byte format: svg (live, default) | svg-static (flattened, static) | png | webp | ansi",
        ),
    ] = "svg",
    respond: Annotated[
        str,
        typer.Option(
            "--respond",
            help="Machine-readable stdout instead of SVG bytes: envelope ({envelope, url} — the "
            "actionable read, no pixels inline; same shape HTTP/MCP return) | json ({svg, markdown, "
            "width, height}).",
        ),
    ] = "",
    target: Annotated[
        str,
        typer.Option(
            "--target",
            hidden=True,
            help="Removed — use --format (svg-static for obsidian/email/pdf, png for slack).",
        ),
    ] = "",
    font_mode: Annotated[
        str,
        typer.Option(
            "--font-mode",
            help="Font embedding: embed (default, self-contained) | cdn (Google Fonts) | system (bare fallbacks)",
        ),
    ] = "embed",
    edge_motion: Annotated[
        str,
        typer.Option(
            "--edge-motion",
            help="Diagram edge-motion override: dash | particle (overrides the spec/preset's motion)",
        ),
    ] = "",
    # Surface modes (matrix + diagram): how the artifact meets the host page.
    surface: Annotated[
        str,
        typer.Option(
            "--surface",
            help="Surface preset: plate (opaque, fixed) | inlay (bare, adaptive) | twin (opaque, adaptive)",
        ),
    ] = "",
    ground: Annotated[
        str,
        typer.Option("--ground", help="Surface ground axis: opaque (own background) | bare (borrow host)"),
    ] = "",
    palette: Annotated[
        str,
        typer.Option("--palette", help="Surface palette axis: fixed (one scheme) | adaptive (light/dark via @media)"),
    ] = "",
    faces: Annotated[
        bool,
        typer.Option("--faces", help="Twin: also write <out>-light.svg / <out>-dark.svg (the <picture> pair)"),
    ] = False,
    face: Annotated[
        str,
        typer.Option(
            "--face",
            help=(
                "Render ONE fixed color scheme (light | dark | auto). With --surface inlay the image keeps "
                "a transparent background — the viewer's background shows through; use --surface plate for "
                "an image that draws its own. 'auto' detects the terminal's background (interactive "
                "terminals only); light/dark stay the explicit, scriptable path."
            ),
        ),
    ] = "",
    # Output
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Write the artifact to this file path")] = None,
    metrics: Annotated[str, typer.Option("--metrics", help="Strip metrics: 'STARS:2.9k,FORKS:278'")] = "",
) -> None:
    r"""Compose a single HyperWeave artifact.

    Examples:

    \b
      hyperweave compose card <username>                           \[fetches GitHub data; 'stats' is an alias]
      hyperweave compose chart stars <owner/repo>                  \[fetches star history]
      hyperweave compose badge STARS --data gh:anthropics/claude-code.stars
      hyperweave compose marquee --data text:NEW,gh:owner/repo.stars,text:DOWNLOAD
      hyperweave compose matrix --spec-file table.json -g primer --variant porcelain
      hyperweave compose matrix --spec-file connectors -g primer --markdown-out table.md
      hyperweave compose diagram --spec-file rag-pipeline -g primer --variant porcelain
      hyperweave compose diagram --spec-file flow.json -g primer --markdown-out flow.md
      hyperweave compose diagram --spec '\{"topology": "pipeline", "nodes": [...], "edges": [...]}'
      hyperweave compose badge STARS 1234 --format png -o badge.png  \[rasterize; needs hyperweave\[raster]]
      hyperweave compose <any-frame> --genome-file ./x.json        \[custom genome]
      hyperweave compose receipt session.jsonl                     \[render a session receipt]
      hyperweave compose -  < hook.json                            \[Claude Code SessionEnd hook]
    """
    # ── Retired-flag migration (one release) ─────────────────────────
    if target:
        typer.echo(
            "Error: --target was removed. Use --format: svg (default, github/web serve the "
            "live svg) | svg-static (obsidian/email/pdf) | png (slack).",
            err=True,
        )
        raise typer.Exit(2)
    if preset:
        typer.echo(
            "Error: --preset was removed. Pass the bundled-spec name to --spec-file (e.g. --spec-file rag-pipeline).",
            err=True,
        )
        raise typer.Exit(2)
    # ── Dotted --genome sugar (before both the receipt and compose paths) ──
    # `--genome primer.porcelain` == `--genome primer --variant porcelain`.
    # Pre-split via the SHARED grammar so a dotted-supplied variant counts as
    # explicit for envelope precedence below; resolve_presentation re-splits
    # idempotently for the other surfaces. An unset genome stays "" here —
    # the seam applies the primer default just before the spec builds.
    from hyperweave.compose.surface import split_dotted_genome
    from hyperweave.core.errors import HwError as _HwError

    try:
        genome, variant = split_dotted_genome(genome, variant)
    except _HwError as exc:
        typer.echo(exc.cli_text(), err=True)
        raise typer.Exit(2) from exc
    # Captured AFTER the dotted split, BEFORE any envelope fill — an
    # envelope-carried genome (--spec-file/--spec) only applies when the caller
    # left the CLI flag unset; this bit is how that precedence is decided.
    genome_explicit = bool(genome)
    variant_explicit = bool(variant)
    # ── Receipt-from-transcript dispatch ─────────────────────────────
    # The receipt frame reads an agent's existing .jsonl transcript, never flags:
    #   compose -                  → hook mode: read hook JSON (transcript_path) on stdin
    #   compose <x>.jsonl          → infer the receipt from the transcript path
    #   compose receipt <x>.jsonl  → receipt from the named transcript path
    # Receipts speak primer only; a non-receipt-capable genome slug falls back
    # to primer/porcelain, and a real primer variant still selects chroma.
    receipt_src: Path | None = None
    hook_mode = frame_type == "-"
    if frame_type.endswith(".jsonl"):
        receipt_src = Path(frame_type)
    elif frame_type == "receipt" and title.endswith(".jsonl"):
        receipt_src = Path(title)
    if hook_mode or receipt_src is not None:
        receipt_genome = genome if (genome in {"primer", "raw"} or genome in _PRIMER_VARIANTS) else ""
        _render_receipt_from_transcript(receipt_src, receipt_genome, variant, output, hook_mode=hook_mode)
        return

    import asyncio
    import json

    from hyperweave.compose.engine import compose as do_compose

    # ── Optional custom genome loaded from file ──────────────────────
    genome_override: dict[str, object] | None = None
    if genome_file is not None:
        from hyperweave.config.genome_validator import load_and_validate_genome_file

        try:
            genome_override, errors = load_and_validate_genome_file(genome_file)
        except FileNotFoundError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(2) from exc
        except json.JSONDecodeError as exc:
            typer.echo(f"Error: {genome_file} is not valid JSON: {exc}", err=True)
            raise typer.Exit(2) from exc
        if errors:
            typer.echo(f"Genome file validation failed for {genome_file.name}:", err=True)
            for err in errors:
                typer.echo(f"  {err}", err=True)
            raise typer.Exit(2)
        # Update the genome slug to match the loaded file (so data-hw-genome is correct).
        genome = str(genome_override.get("id", genome))
        genome_explicit = True  # a loaded genome file always wins over an envelope's genome

    # ── Frame-type-specific argument interpretation + connector fetch ──
    connector_data: dict[str, object] | None = None
    stats_username = ""
    chart_owner = ""
    chart_repo = ""
    final_value = metrics if metrics else value

    if frame_type == "stats":
        # First positional arg = username. Fetch full stats card data.
        stats_username = title
        if stats_username:
            try:
                from hyperweave.connectors.github import fetch_user_stats

                connector_data = asyncio.run(fetch_user_stats(stats_username))
            except Exception as exc:  # network or parse error → graceful degradation
                typer.echo(f"(warning) stats fetch failed for {stats_username}: {exc}", err=True)
                connector_data = None
    elif frame_type == "chart":
        # `compose chart stars <owner/repo>` is the PRD-canonical form.
        # title == chart subtype ("stars"), value == "owner/repo".
        repo_spec = value
        if "/" in repo_spec:
            chart_owner, chart_repo = repo_spec.split("/", 1)
        try:
            from hyperweave.connectors.github import fetch_stargazer_history

            connector_data = asyncio.run(fetch_stargazer_history(chart_owner, chart_repo))
        except Exception as exc:
            typer.echo(f"(warning) chart fetch failed for {chart_owner}/{chart_repo}: {exc}", err=True)
            connector_data = None

    # ── --spec / --spec-file: mutually exclusive, matrix/diagram only ──
    if spec_inline:
        if spec_file is not None:
            typer.echo("Error: --spec and --spec-file are mutually exclusive", err=True)
            raise typer.Exit(2)
        if frame_type not in {"matrix", "diagram"}:
            typer.echo(f"Error: --spec is only valid for matrix/diagram frames (got {frame_type!r})", err=True)
            raise typer.Exit(2)

    # ── Matrix input: --spec-file/--spec — a path, bundled name, inline JSON, or envelope ──
    matrix_spec: dict[str, object] | None = None
    if frame_type == "matrix":
        if spec_inline:
            resolved_spec, genome, variant = _resolve_inline_spec(
                "matrix",
                spec_inline,
                genome=genome,
                variant=variant,
                genome_explicit=genome_explicit,
                variant_explicit=variant_explicit,
            )
        else:
            resolved_spec, genome, variant = _resolve_spec_file(
                "matrix",
                spec_file,
                genome=genome,
                variant=variant,
                genome_explicit=genome_explicit,
                variant_explicit=variant_explicit,
            )
        if resolved_spec is not None:
            if resolved_spec.field == "connector_data":
                connector_data = resolved_spec.value  # bundled matrix spec = adapter payload
            else:
                matrix_spec = resolved_spec.value

    # ── Diagram input: --spec-file/--spec — a path, bundled name, inline JSON, or envelope ──
    diagram_spec: dict[str, object] | None = None
    if frame_type == "diagram":
        if spec_inline:
            resolved_spec, genome, variant = _resolve_inline_spec(
                "diagram",
                spec_inline,
                genome=genome,
                variant=variant,
                genome_explicit=genome_explicit,
                variant_explicit=variant_explicit,
            )
        else:
            resolved_spec, genome, variant = _resolve_spec_file(
                "diagram",
                spec_file,
                genome=genome,
                variant=variant,
                genome_explicit=genome_explicit,
                variant_explicit=variant_explicit,
            )
        if resolved_spec is not None:
            diagram_spec = resolved_spec.value

        # Artifact-level edge-motion override — mirrors the HTTP ?edge_motion=
        # query: replaces the spec/preset's edge_motion before compose (per-edge
        # IR declarations still outrank it). Validated against the closed pair.
        if edge_motion:
            from hyperweave.core.diagram import EdgeMotion

            if edge_motion not in {e.value for e in EdgeMotion}:
                allowed = " | ".join(e.value for e in EdgeMotion)
                typer.echo(f"Error: --edge-motion must be one of: {allowed}", err=True)
                raise typer.Exit(2)
            if diagram_spec is not None:
                diagram_spec = {**diagram_spec, "edge_motion": edge_motion}

    # ── ?data= / --data: unified data-token grammar ──
    # Marquee-horizontal consumes spec.data_tokens directly (the resolved list);
    # other frames receive the formatted "K1:V1,K2:V2" string via spec.value.
    data_tokens_resolved: list[Any] | None = None
    if data:
        try:
            from hyperweave.connectors.data_tokens import (
                format_for_value,
                parse_data_tokens,
                resolve_data_tokens,
            )
        except ModuleNotFoundError as exc:  # pragma: no cover - broken install
            typer.echo(
                f"Error: --data needs the '{exc.name}' package. Reinstall with:\n  pip install hyperweave",
                err=True,
            )
            raise typer.Exit(1) from exc

        try:
            tokens = parse_data_tokens(data)
            resolved, _ttl = asyncio.run(resolve_data_tokens(tokens))
        except ValueError as exc:
            typer.echo(f"Error: --data parse failed: {exc}", err=True)
            raise typer.Exit(2) from exc

        if frame_type in {"marquee", "stats", "matrix"}:
            data_tokens_resolved = list(resolved)
        else:
            formatted = format_for_value(resolved)
            if formatted:
                final_value = formatted

    # ── Surface modes: expand the preset/axes sugar BEFORE ComposeSpec ──
    # surface=plate|inlay|twin OR explicit --ground/--palette resolve to the two
    # axes here so the ComposeSpec carries only ground/palette (never the preset
    # name). expand_surface_preset raises on a preset/axis contradiction or the
    # trap corner (bare+fixed); surface the ValueError as a clean CLI error.
    surface_ground, surface_palette = "", ""
    if surface or ground or palette:
        from hyperweave.core.surface_spec import expand_surface_preset

        try:
            resolved_surface = expand_surface_preset(surface, ground, palette)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(2) from exc
        surface_ground = resolved_surface.ground.value
        surface_palette = resolved_surface.palette.value

    # One exception-mapping seam with HTTP/MCP: a malformed spec prints the
    # same rule text everywhere (never a traceback), exit 2 = input problem.
    from hyperweave.compose.surface import build_compose_spec, resolve_presentation
    from hyperweave.core.errors import HwError

    # The ONE presentation-resolution step (shared with validate on every
    # surface): primer default, dotted split, genome existence, frame support
    # (receipt's primer fallback included), variant whitelist.
    try:
        genome, variant = resolve_presentation(frame_type, genome, variant, genome_override=genome_override)
    except HwError as exc:
        typer.echo(exc.cli_text(), err=True)
        raise typer.Exit(2) from exc

    spec_kwargs: dict[str, Any] = {
        "type": frame_type,
        "genome_id": genome,
        "genome_override": genome_override,
        "title": title,
        "value": final_value,
        "state": state,
        "motion": motion,
        "glyph": glyph,
        "glyph_mode": glyph_mode,
        "font_mode": font_mode,
        "regime": regime,
        "size": size,
        "shape": shape,
        "variant": variant,
        "pair": pair,
        "state_glyph_shape": state_glyph_shape,
        "divider_variant": divider_variant,
        "marquee_direction": direction,
        "stats_username": stats_username,
        "chart_owner": chart_owner,
        "chart_repo": chart_repo,
        "connector_data": connector_data,
        "data_tokens": data_tokens_resolved,
        "matrix": matrix_spec,
        "diagram": diagram_spec,
        "glyph_tint": glyph_tint,
        "performance": performance,
        "ground": surface_ground,
        "palette": surface_palette,
    }
    try:
        spec = build_compose_spec(spec_kwargs, frame_type)
    except HwError as exc:
        typer.echo(exc.cli_text(), err=True)
        raise typer.Exit(2) from exc

    # ── --face: bake ONE scheme (the single twin face / the bare inlay face) ──
    # An explicit face commits the palette: palette=fixed + surface_face. On a
    # bare ground this is the TERMINAL-INLAY face — bare+fixed is legal with a
    # face (theme-committed, not theme-blind) — and --format png then composites
    # the inks over the terminal ground (alpha preserved, no plate, no box).
    if face:
        if face == "auto":
            # sec 12.3: the caller opted into detection — OSC 11 asks the
            # terminal; silence or a non-tty refuses with the explicit fix.
            from hyperweave.core.errors import HwError
            from hyperweave.delivery.face_detect import detect_terminal_face

            try:
                face = detect_terminal_face()
            except HwError as exc:
                typer.echo(exc.cli_text(), err=True)
                raise typer.Exit(2) from exc
            typer.echo(f"face auto: terminal reports {face}", err=True)
        if face not in ("light", "dark"):
            typer.echo(f"Error: --face must be 'light', 'dark', or 'auto' (got {face!r})", err=True)
            raise typer.Exit(2)
        if faces:
            typer.echo("Error: --face (one baked scheme) and --faces (the twin pair) are exclusive", err=True)
            raise typer.Exit(2)
        spec = spec.model_copy(update={"palette": "fixed", "surface_face": face})

    # ── --faces: twin → write both baked faces beside -o ──
    # A twin's light + dark faces are plain plate renders (surface_face pinned; the
    # resolver merges the flipped palette for dark). Each writes to a suffixed path
    # next to -o (<out>-light.svg / <out>-dark.svg) — the <picture> pair. Requires
    # -o (two files can't stream to stdout) and a twin surface.
    if faces:
        if respond:
            typer.echo(
                "Error: --faces (two files beside -o) and --respond (one stdout document) are exclusive", err=True
            )
            raise typer.Exit(2)
        if output is None:
            typer.echo("Error: --faces needs -o/--output (writes <out>-light.svg and <out>-dark.svg)", err=True)
            raise typer.Exit(2)
        if not (surface_palette == "adaptive" and surface_ground != "bare"):
            typer.echo("Error: --faces requires a twin surface (--surface twin)", err=True)
            raise typer.Exit(2)
        for face_name in ("light", "dark"):
            try:
                face_result = do_compose(spec.model_copy(update={"palette": "fixed", "surface_face": face_name}))
            except _compose_refusals() as exc:
                _echo_refusal(exc)
                raise typer.Exit(2) from exc
            dest = output.with_name(f"{output.stem}-{face_name}{output.suffix}")
            dest.write_text(face_result.svg)
            typer.echo(f"Wrote {dest} ({face_result.width}x{face_result.height})", err=True)
        return

    try:
        result = do_compose(spec)
    except _compose_refusals() as exc:
        _echo_refusal(exc)
        raise typer.Exit(2) from exc

    # Non-fatal normalization notes (e.g. a cyclic diagram declared as 'dag'
    # promoted to 'state-machine') go to stderr so they never corrupt bytes on
    # stdout.
    for warning in result.warnings:
        typer.echo(f"warning: {warning}", err=True)
    # sec 6 compiler diagnostics — advisory, stderr-only (stdout stays bytes).
    for diag in result.diagnostics:
        typer.echo(
            f"diagnostic: {diag['rule']} — {diag['measured']} (band: {diag['band']}) → {diag['suggestion']}",
            err=True,
        )

    # Verb advertisement (stderr, unconditional): the artifact's id + the verbs
    # that operate on it, in SELF_INSTRUCT's own vocabulary so the terminal
    # hint and the embedded self-instruction cannot drift.
    from hyperweave.core.envelope import extract_envelope

    advert_envelope = extract_envelope(result.svg) or {}
    advert_id = str(advert_envelope.get("id", "")).removeprefix("sha256:")[:12]
    if advert_id:
        typer.echo(
            f"artifact {advert_id} — verbs over the seed: extract · verify · transform · "
            "diff · query (hyperweave discover verbs)",
            err=True,
        )

    # ── --respond: machine-readable stdout (the HTTP/MCP response shapes) ──
    # envelope = the actionable read + content handle, no pixels inline; json =
    # svg + markdown shadow inline. Either way stdout is one JSON document; the
    # -o file write still happens additionally (transform's -o convention).
    if respond:
        if respond not in ("envelope", "json"):
            typer.echo(f"Error: --respond must be 'envelope' or 'json' (got {respond!r})", err=True)
            raise typer.Exit(2)
        if output_format != "svg":
            typer.echo("Error: --respond emits the live artifact; it composes with --format svg only", err=True)
            raise typer.Exit(2)
        import json as _json

        if respond == "json":
            respond_doc: dict[str, Any] = {
                "svg": result.svg,
                "markdown": result.markdown,
                "width": result.width,
                "height": result.height,
            }
        else:
            from hyperweave.compose.artifact_store import store_artifact
            from hyperweave.compose.surface import build_artifact_url
            from hyperweave.core.envelope import extract_envelope

            envelope = extract_envelope(result.svg) or {}
            digest = str(envelope.get("id", ""))
            if digest:
                store_artifact(digest, result.svg)
            respond_doc = {
                "width": result.width,
                "height": result.height,
                "genome": spec.genome_id,
                "variant": spec.variant,
                "url": build_artifact_url(digest) if digest else "",
                "envelope": envelope,
            }
            if output is None:
                # Errors-as-documentation: the url is a relative handle backed by
                # the per-process store — name the exits (transform's pattern).
                typer.echo(
                    "url resolves under `hyperweave serve`; pass -o/--output to write the SVG to a file",
                    err=True,
                )
        if output is not None:
            output.write_text(result.svg)
            typer.echo(f"Wrote {output} ({result.width}x{result.height})", err=True)
        typer.echo(_json.dumps(respond_doc, indent=2))
        return

    # Project the live SVG into the requested --format (svg passes through;
    # svg-static flattens vars + strips motion; png/webp rasterize the static
    # projection). project() enforces the adaptive x flatten guard and raster
    # availability, surfacing a structured error to stderr.
    from hyperweave.formats import is_flattening, project

    # A genome-DEFAULTED adaptive surface (primer twins by default) commits to
    # its plate for a flattening format instead of failing — the plate IS the
    # native face. An EXPLICIT adaptive request still fails loud in project().
    surface_explicit = bool(surface or ground or palette or face)
    if not surface_explicit and is_flattening(output_format) and 'data-hw-adapt="adaptive"' in result.svg:
        try:
            result = do_compose(spec.model_copy(update={"ground": "opaque", "palette": "fixed"}))
        except _compose_refusals() as exc:
            _echo_refusal(exc)
            raise typer.Exit(2) from exc

    try:
        projection = project(result.svg, output_format, is_face=spec.surface_face != "")
    except HwError as exc:
        typer.echo(f"Error: {exc.cli_text()}", err=True)
        raise typer.Exit(2) from exc

    # Projection honesty (stderr, mirrors the warnings pattern): declare what
    # the flattening dropped instead of stripping blind.
    if projection.diagnostics:
        dropped = ", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in projection.diagnostics.items())
        typer.echo(f"static projection — {dropped}", err=True)

    _deliver_projection(
        projection.data, is_text=projection.is_text, output=output, width=result.width, height=result.height
    )
    if markdown_out is not None and result.markdown:
        markdown_out.write_text(result.markdown)
        typer.echo(f"Wrote {markdown_out} (markdown shadow)", err=True)


# Session telemetry — hidden back-compat alias for the agent-runtime hook.


@app.command(hidden=True)
def session(
    action: Annotated[str, typer.Argument(help="receipt")] = "receipt",
    transcript: Annotated[Path | None, typer.Argument(help="Path to transcript JSONL")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    genome: Annotated[
        str,
        typer.Option(
            "--genome",
            help=(
                "Receipt genome or primer variant (noir, carbon, space, anvil, "
                "porcelain, cream, dusk, petrol); 'primer'/'raw' select the genome "
                "directly. Empty = primer/porcelain."
            ),
        ),
    ] = "",
    variant: Annotated[
        str,
        typer.Option(
            "--variant",
            help="Primer variant (noir … petrol). Empty = porcelain (light flagship).",
        ),
    ] = "",
) -> None:
    """Hidden back-compat alias for the Claude Code / Codex session-receipt hook.

    Equivalent to ``compose -`` (stdin hook JSON) or ``compose <transcript>.jsonl``.
    Hooks already registered as ``hyperweave session receipt`` keep working
    unchanged; new callers should use ``compose``. Only the ``receipt`` action is
    supported — ``session parse`` retired with the unified verb surface.
    """
    if action != "receipt":
        typer.echo(f"Unknown action '{action}'. Use: receipt (or run 'hyperweave compose').", err=True)
        raise typer.Exit(1)
    # No explicit transcript → behave as a hook (read transcript_path from stdin,
    # silently no-op on an empty SessionEnd). An explicit path renders directly.
    _render_receipt_from_transcript(transcript, genome, variant, output, hook_mode=transcript is None)


# Live data commands


# Admin commands


@app.command("genomes")
def genomes_cmd(
    show: Annotated[str | None, typer.Argument(help="Genome ID to show details")] = None,
    ids_only: Annotated[bool, typer.Option("--ids-only")] = False,
    explain: Annotated[
        bool,
        typer.Option("--explain", help="Role → token → value breakdown instead of the raw JSON dump."),
    ] = False,
) -> None:
    """List or inspect genomes."""
    from hyperweave.config.loader import get_loader

    loader = get_loader()

    if explain and not show:
        typer.echo("--explain needs a genome id: hyperweave genomes <id> --explain", err=True)
        raise typer.Exit(2)

    if show:
        genome = loader.genomes.get(show)
        if not genome:
            typer.echo(f"Genome '{show}' not found.", err=True)
            raise typer.Exit(1)
        if explain:
            # Recoloring as intent: the role tells you WHAT a token does; the
            # raw dump only tells you what hex it happens to be. One extraction
            # shared with `discover genome:<id>` so the two faces cannot drift.
            from hyperweave.surfaces.discover import genome_deep_dive

            info = genome_deep_dive(show)
            typer.echo(f"{show} — {info['name']} ({info['category']})")
            for role, tokens in info["roles"].items():
                typer.echo(f"  {role}:")
                for token, token_value in tokens.items():
                    typer.echo(f"    {token:<36} {token_value}")
            return
        import json

        typer.echo(json.dumps(genome, indent=2))
        return

    for gid in sorted(loader.genomes):
        if ids_only:
            typer.echo(gid)
        else:
            g = loader.genomes[gid]
            typer.echo(f"  {gid:<30} {g.get('name', gid)}")


def _install_claude_code_hook(hook_command: str, pin: str) -> None:
    """Write a SessionEnd hook to ``~/.claude/settings.json``.

    Idempotent: prior hyperweave hook entries are removed before the new
    one is appended, so re-running install-hook with a different
    ``--genome`` replaces (not stacks) the previous pin.
    """
    import json

    settings_path = Path.home() / ".claude" / "settings.json"
    settings: dict[str, object] = {}
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())

    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        settings["hooks"] = hooks

    raw_session_end = hooks.setdefault("SessionEnd", [])
    session_end: list[object] = raw_session_end if isinstance(raw_session_end, list) else []
    if not isinstance(raw_session_end, list):
        hooks["SessionEnd"] = session_end

    # Remove stale "hw" hooks (0A bug: hw binary never existed) AND any prior
    # hyperweave hook entry — pinning a new --genome should replace, not append.
    cleaned = []
    for entry in session_end:
        if not isinstance(entry, dict):
            cleaned.append(entry)
            continue
        entry_hooks = entry.get("hooks", [])
        if not isinstance(entry_hooks, list):
            cleaned.append(entry)
            continue
        cmds = [str(h.get("command", "")) for h in entry_hooks if isinstance(h, dict)]
        if any("hw session" in c and "hyperweave" not in c for c in cmds):
            continue
        if any("hyperweave session" in c for c in cmds):
            continue
        cleaned.append(entry)
    hooks["SessionEnd"] = cleaned
    session_end = cleaned

    hook_entry = {"hooks": [{"type": "command", "command": hook_command, "timeout": 10}]}
    session_end.append(hook_entry)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")

    pinned = f" (pinned to {pin})" if pin else " (primer/porcelain)"
    typer.echo(f"Installed SessionEnd hook in {settings_path}{pinned}")


# Codex hook event names (v0.129.0 GA). Used by ``_install_codex_hook`` and
# ``_doctor_runtime_status`` to detect pre-GA flat-format event keys sitting
# at the top of ``hooks.json`` and lift them under the canonical ``hooks``
# wrapper introduced when hooks went GA.
_CODEX_HOOK_EVENTS = frozenset(
    {
        "SessionStart",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "UserPromptSubmit",
        "Stop",
    }
)


def _wrap_legacy_codex_hook_entry(entry: object) -> object:
    """Lift a pre-GA bare-command hook entry into the GA matcher+hooks group.

    Codex v0.129 (hooks GA) changed each event-array entry from a bare
    ``{type, command, timeout}`` to a matcher group
    ``{matcher, hooks: [{type, command, timeout}]}``. Idempotent: an entry
    already carrying a list-valued ``hooks`` key is returned unchanged so
    repeated migrations stay stable. Bare-command entries are wrapped under
    a universal ``"*"`` matcher; the matcher is parsed-but-ignored for Stop
    today per the spec, but we use ``"*"`` for forward-compat against any
    future Codex release that begins to honor it on Stop.
    """
    if not isinstance(entry, dict):
        return entry
    if isinstance(entry.get("hooks"), list):
        return entry  # already in GA shape
    if entry.get("type") == "command":
        return {"matcher": "*", "hooks": [entry]}
    return entry  # unknown shape — preserve as-is


def _install_codex_hook(hook_command: str, pin: str) -> None:
    """Write a Stop hook to ``~/.codex/hooks.json`` + enable hooks feature.

    Per developers.openai.com/codex/hooks, Codex CLI fires Stop hooks
    PER-TURN (after every assistant response). The receipt rewrites the
    same deterministic filename each turn, so the on-disk file becomes a
    live mid-session telemetry window — opening it during a long session
    shows the current state, and the final write at session-end carries
    the complete cumulative receipt. This is intentional; future versions
    will lean into live-receipt consumers (file watchers, dashboards)
    rather than collapse it back to a single session-end event.

    Codex v0.129.0 (2026-05-07) took hooks GA with two shape changes the
    installer handles via migration-on-write:

    * ``hooks.json`` moved from flat ``{Stop: [{type, command, timeout}]}``
      to wrapped ``{hooks: {Stop: [{matcher, hooks: [{type, command,
      timeout}]}]}}``. Any pre-GA event keys at the top level are lifted
      under the new wrapper; each bare-command entry is wrapped under a
      universal ``"*"`` matcher group.
    * ``[features].codex_hooks`` was aliased as ``[features].hooks``. The
      installer strips any legacy ``codex_hooks`` entry and writes the
      canonical ``hooks = true``.

    Both migrations are idempotent — re-running install-hook over any
    combination of pre-GA, partially-migrated, or GA configs converges to
    the canonical GA shape with exactly one hyperweave entry.
    """
    import json

    codex_dir = Path.home() / ".codex"
    hooks_path = codex_dir / "hooks.json"
    config_path = codex_dir / "config.toml"
    codex_dir.mkdir(parents=True, exist_ok=True)

    # ── Update hooks.json: lift any pre-GA flat keys into the wrapper, then
    # operate on hooks.Stop as the canonical GA structure ──
    config: dict[str, object] = {}
    if hooks_path.exists():
        loaded = json.loads(hooks_path.read_text())
        if isinstance(loaded, dict):
            config = loaded

    # GA wrapper: hooks lives under config["hooks"]. Pre-GA configs may not
    # have it yet; create it (or reset if it's the wrong shape).
    wrapper_raw = config.setdefault("hooks", {})
    hooks_wrapper: dict[str, object]
    if isinstance(wrapper_raw, dict):
        hooks_wrapper = wrapper_raw
    else:
        hooks_wrapper = {}
        config["hooks"] = hooks_wrapper

    # Lift any pre-GA top-level event keys (Stop, PreToolUse, etc.) into the
    # wrapper, wrapping bare-command entries with a universal matcher group.
    # Iterate over a snapshot of keys since we mutate during traversal.
    for legacy_event in list(config.keys()):
        if legacy_event == "hooks" or legacy_event not in _CODEX_HOOK_EVENTS:
            continue
        legacy_value = config.pop(legacy_event)
        if not isinstance(legacy_value, list):
            continue
        target_raw = hooks_wrapper.setdefault(legacy_event, [])
        target: list[object]
        if isinstance(target_raw, list):
            target = target_raw
        else:
            target = []
            hooks_wrapper[legacy_event] = target
        for entry in legacy_value:
            target.append(_wrap_legacy_codex_hook_entry(entry))

    # Now drop any prior hyperweave matcher groups under hooks.Stop and
    # append the fresh one. A hyperweave group is identified by ANY inner
    # handler whose command mentions "hyperweave session".
    raw_stop = hooks_wrapper.setdefault("Stop", [])
    stop_groups: list[object]
    if isinstance(raw_stop, list):
        stop_groups = raw_stop
    else:
        stop_groups = []
        hooks_wrapper["Stop"] = stop_groups

    cleaned: list[object] = []
    for group in stop_groups:
        if not isinstance(group, dict):
            cleaned.append(group)
            continue
        inner_hooks = group.get("hooks", [])
        if isinstance(inner_hooks, list) and any(
            isinstance(h, dict) and "hyperweave session" in str(h.get("command", "")) for h in inner_hooks
        ):
            continue  # drop the whole matcher group — owned by hyperweave
        cleaned.append(group)
    cleaned.append(
        {
            "matcher": "*",
            "hooks": [{"type": "command", "command": hook_command, "timeout": 10}],
        }
    )
    hooks_wrapper["Stop"] = cleaned
    hooks_path.write_text(json.dumps(config, indent=2) + "\n")

    # ── Update config.toml: ensure [features] hooks = true (preserve other keys) ──
    # Codex v0.130.0 renamed the gate from `codex_hooks` to `hooks`; strip any
    # legacy key on the way in so re-running install-hook over an older config
    # upgrades cleanly instead of leaving a dead key. Key detection is exact-
    # match (split-on-=, strip), not prefix, so `hooks_*` lookalikes can't
    # spoof a hit.
    config_lines: list[str] = []
    if config_path.exists():
        config_lines = config_path.read_text().splitlines()
    config_lines = [line for line in config_lines if line.split("=", 1)[0].strip() != "codex_hooks"]
    has_features_section = any(line.strip() == "[features]" for line in config_lines)
    has_hooks_key = any("=" in line and line.split("=", 1)[0].strip() == "hooks" for line in config_lines)
    if not has_features_section:
        config_lines.extend(["", "[features]", "hooks = true"])
    elif not has_hooks_key:
        # Insert hooks = true right after [features] header
        for i, line in enumerate(config_lines):
            if line.strip() == "[features]":
                config_lines.insert(i + 1, "hooks = true")
                break
    config_path.write_text("\n".join(config_lines) + "\n")

    pinned = f" (pinned to {pin})" if pin else " (primer/porcelain)"
    typer.echo(f"Installed Stop hook in {hooks_path}{pinned}")
    typer.echo(f"Set [features] hooks = true in {config_path}")
    typer.echo(
        "Note: Codex Stop fires per-turn — the receipt file refreshes live as the "
        "session progresses, always reflecting current cumulative state.",
        err=True,
    )


# Runtime → install-hook handler. Dispatch by runtime is intrinsic here
# (different runtimes write to different config files at different paths
# with different event names); not the polymorphism that resolver.py /
# parser.py avoid via runtime registries.
_HOOK_INSTALLERS = {
    "claude-code": _install_claude_code_hook,
    "codex": _install_codex_hook,
}

# Runtime → (config_dirname_under_home, cli_binary_name). Drives both the
# auto-detect path (config dir OR binary on PATH) and `hyperweave doctor`
# state reporting. Config-dir presence means "agent has been run at least
# once"; binary-on-PATH covers fresh installs where the dir hasn't been
# created yet. The installers create their dirs on demand, so installing
# for a binary-only runtime is safe.
_RUNTIME_DETECTION = {
    "claude-code": (".claude", "claude"),
    "codex": (".codex", "codex"),
}


def _detect_installed_runtimes() -> list[tuple[str, str]]:
    """Detect installed agent runtimes via config-dir-OR-binary-on-PATH.

    Returns ``(runtime_key, signal)`` tuples in ``_RUNTIME_DETECTION`` order.
    Signal is ``"initialized"`` when the runtime's config dir exists (agent
    has been run at least once), ``"binary_only"`` when only the CLI is on
    PATH (fresh install, config dir not created yet). Runtimes with
    neither signal are omitted entirely.
    """
    import shutil

    detected: list[tuple[str, str]] = []
    for runtime, (dirname, binname) in _RUNTIME_DETECTION.items():
        if (Path.home() / dirname).exists():
            detected.append((runtime, "initialized"))
        elif shutil.which(binname):
            detected.append((runtime, "binary_only"))
    return detected


@app.command("install-hook")
def install_hook(
    genome: Annotated[
        str,
        typer.Option(
            "--genome",
            help=(
                "Pin a primer variant (noir, carbon, space, anvil, porcelain, "
                "cream, dusk, petrol) for every session receipt, or 'primer'/'raw' "
                "for the genome directly. Empty = primer/porcelain."
            ),
        ),
    ] = "",
    runtime: Annotated[
        str,
        typer.Option(
            "--runtime",
            help=(
                "Agent runtime to install the receipt hook for. Empty (default) "
                "auto-detects installed runtimes (~/.claude, ~/.codex, or 'claude'/"
                "'codex' on PATH) and registers for each present. 'claude-code' "
                "writes a SessionEnd hook to ~/.claude/settings.json. 'codex' writes "
                "a Stop hook to ~/.codex/hooks.json plus [features] hooks in "
                "~/.codex/config.toml. 'all' forces both regardless of detection."
            ),
        ),
    ] = "",
) -> None:
    """Install session-receipt hooks for installed agent runtimes.

    Default behavior detects which agent CLIs are installed (Claude Code,
    Codex) via config dir presence or binary on PATH, and registers receipt
    hooks for each. Pass ``--runtime <name>`` to scope to a single runtime,
    or ``--runtime all`` to force both regardless of detection.
    """
    from hyperweave.compose.resolver import _RECEIPT_DEFAULT_GENOME, genome_supports_receipts

    # Resolve targets:
    #   ""     (default) → auto-detect installed runtimes (config dir OR binary)
    #   "all"            → both runtimes regardless of detection
    #   "<name>"         → just that runtime (legacy explicit form)
    if runtime == "":
        detected = _detect_installed_runtimes()
        if not detected:
            typer.echo(
                "Error: no agent runtime detected (~/.claude, ~/.codex, or "
                "'claude'/'codex' on PATH). Install Claude Code or Codex CLI, "
                "or pass --runtime <name> to force.",
                err=True,
            )
            raise typer.Exit(1)
        targets = [rt for rt, _signal in detected]
    elif runtime == "all":
        targets = list(_HOOK_INSTALLERS)
    elif runtime in _HOOK_INSTALLERS:
        targets = [runtime]
    else:
        typer.echo(
            f"Error: unknown runtime '{runtime}'. Supported: {sorted(_HOOK_INSTALLERS)} or 'all'.",
            err=True,
        )
        raise typer.Exit(1)

    # Validate --genome BEFORE writing any hook. install-hook fails loud
    # (unlike the receipt CLI which silently falls through) because pinning
    # a bad genome would produce silent surprises every session-end until
    # someone notices. Validate once even when targeting multiple runtimes.
    # A primer variant (cream …) resolves to genome=primer, which is
    # receipt-capable; a bare genome slug must declare paradigms.receipt.
    pin = ""
    if genome:
        resolved_genome, _resolved_variant = _resolve_receipt_genome(genome)
        check_genome = resolved_genome or _RECEIPT_DEFAULT_GENOME
        if not genome_supports_receipts(check_genome):
            typer.echo(
                f"Error: genome '{genome}' (resolved to '{check_genome}') does not support receipts. "
                "Use a primer variant (noir, carbon, space, anvil, porcelain, cream, dusk, petrol) "
                "or 'primer'/'raw'.",
                err=True,
            )
            raise typer.Exit(1)
        # Re-emit the user's token verbatim: session parses primer variants and
        # genome slugs identically, so the command round-trips at session-end.
        pin = genome

    hook_command = f"hyperweave session receipt --genome {pin}" if pin else "hyperweave session receipt"

    for target in targets:
        _HOOK_INSTALLERS[target](hook_command, pin)


def _doctor_runtime_status(runtime: str, home_dir: Path) -> str:
    """Parse a runtime's hook config and return a one-line status string.

    Returns ``✓`` when the hyperweave hook is wired correctly, ``✗`` when
    the runtime is initialized but no hyperweave hook is registered, or
    ``⚠`` when the wiring is partial (malformed config; codex missing the
    [features] hooks flag — renamed from ``codex_hooks`` in Codex v0.130.0).
    The string is rendered verbatim by ``doctor``.
    """
    import json

    if runtime == "claude-code":
        settings_path = home_dir / "settings.json"
        if not settings_path.exists():
            return (
                f"✗ {runtime}: ~/.claude/ exists but no settings.json — "
                f"run 'hyperweave install-hook --runtime {runtime}'"
            )
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            return f"⚠ {runtime}: ~/.claude/settings.json is malformed"
        for entry in settings.get("hooks", {}).get("SessionEnd", []) or []:
            if not isinstance(entry, dict):
                continue
            for hook in entry.get("hooks", []) or []:
                if not isinstance(hook, dict):
                    continue
                cmd = str(hook.get("command", ""))
                if "hyperweave session" in cmd:
                    return f"✓ {runtime}: hook registered — {cmd}"
        return f"✗ {runtime}: initialized but no hyperweave hook — run 'hyperweave install-hook --runtime {runtime}'"

    if runtime == "codex":
        hooks_path = home_dir / "hooks.json"
        config_path = home_dir / "config.toml"
        registered_cmd: str | None = None
        legacy_flat_cmd: str | None = None
        if hooks_path.exists():
            try:
                hooks = json.loads(hooks_path.read_text())
            except json.JSONDecodeError:
                return f"⚠ {runtime}: ~/.codex/hooks.json is malformed"
            # GA traversal (Codex v0.129+):
            #   hooks["hooks"]["Stop"][group].hooks[handler].command
            wrapper = hooks.get("hooks") if isinstance(hooks, dict) else None
            if isinstance(wrapper, dict):
                for group in wrapper.get("Stop") or []:
                    if not isinstance(group, dict):
                        continue
                    for handler in group.get("hooks") or []:
                        if not isinstance(handler, dict):
                            continue
                        cmd = str(handler.get("command", ""))
                        if "hyperweave session" in cmd:
                            registered_cmd = cmd
                            break
                    if registered_cmd:
                        break
            # Pre-GA flat fallback (kept for one release): hooks["Stop"][entry]
            # with command directly on the entry. Detected separately so a
            # legacy install surfaces as ⚠ with an upgrade pointer instead of
            # silently misreporting the hook as missing.
            if not registered_cmd and isinstance(hooks, dict):
                for entry in hooks.get("Stop") or []:
                    if not isinstance(entry, dict):
                        continue
                    cmd = str(entry.get("command", ""))
                    if "hyperweave session" in cmd:
                        legacy_flat_cmd = cmd
                        break
        if legacy_flat_cmd and not registered_cmd:
            return (
                f"⚠ {runtime}: hook registered in legacy pre-GA flat format — "
                f"re-run 'hyperweave install-hook --runtime {runtime}' to lift "
                f"it to the GA wrapped structure (Codex v0.129+)"
            )
        if not registered_cmd:
            return (
                f"✗ {runtime}: initialized but no hyperweave hook — run 'hyperweave install-hook --runtime {runtime}'"
            )
        # [features] hooks = true must be present for the hook to fire; the
        # install command writes it, but a hand-edited config could miss it.
        # Codex v0.130.0 renamed the gate from `codex_hooks` to `hooks`; key
        # detection is exact-match within the [features] section so a stale
        # `codex_hooks = true` left over from older installs is not mistaken
        # for the live gate (and so `hooks_*` lookalikes can't spoof a hit).
        feature_ok = False
        if config_path.exists():
            in_features = False
            for line in config_path.read_text().splitlines():
                stripped = line.strip()
                if stripped == "[features]":
                    in_features = True
                    continue
                if in_features and stripped.startswith("["):
                    in_features = False
                    continue
                if in_features and "=" in stripped:
                    key, _, value = stripped.partition("=")
                    if key.strip() == "hooks" and "true" in value:
                        feature_ok = True
                        break
        if not feature_ok:
            return (
                f"⚠ {runtime}: hook registered but [features] hooks = true "
                f"is missing — re-run 'hyperweave install-hook --runtime {runtime}'"
            )
        return f"✓ {runtime}: hook registered — {registered_cmd}"

    return f"? {runtime}: unknown runtime"


@app.command()
def doctor() -> None:
    """Diagnose hyperweave telemetry wiring across agent runtimes.

    Reports per-runtime detection state (initialized / binary-only /
    absent), hook registration status, transcript dir state, and recent
    receipt activity in the current directory. Read-only — never
    modifies any config. Always exits 0.
    """
    import shutil
    from datetime import datetime, timedelta

    from hyperweave import __version__

    typer.echo(f"hyperweave doctor — v{__version__}")
    typer.echo("")
    typer.echo("Runtimes:")
    for runtime, (dirname, binname) in _RUNTIME_DETECTION.items():
        home_dir = Path.home() / dirname
        if home_dir.exists():
            typer.echo(f"  {_doctor_runtime_status(runtime, home_dir)}")
        elif bin_path := shutil.which(binname):
            typer.echo(
                f"  ⚠ {runtime}: CLI on PATH at {bin_path} but ~/{dirname}/ "
                f"not initialized — run '{binname}' once, then "
                f"'hyperweave install-hook --runtime {runtime}'"
            )
        else:
            typer.echo(f"  ✗ {runtime}: not detected")

    typer.echo("")
    typer.echo("Transcripts:")
    for runtime, subdir in (("claude-code", "projects"), ("codex", "sessions")):
        dirname = _RUNTIME_DETECTION[runtime][0]
        root = Path.home() / dirname / subdir
        display_root = f"~/{dirname}/{subdir}"
        if not root.exists():
            typer.echo(f"  {runtime}: {display_root} (not found)")
            continue
        files = list(root.rglob("*.jsonl"))
        if not files:
            typer.echo(f"  {runtime}: {display_root}/ (empty)")
            continue
        most_recent = max(files, key=lambda p: p.stat().st_mtime)
        mtime = datetime.fromtimestamp(most_recent.stat().st_mtime)
        typer.echo(f"  {runtime}: {len(files)} transcript(s), most recent {mtime:%Y-%m-%d %H:%M}")

    typer.echo("")
    receipts_dir = _hyperweave_root() / ".hyperweave" / "receipts"
    typer.echo(f"Receipts ({receipts_dir}/):")
    if not receipts_dir.exists():
        typer.echo("  (no receipts directory)")
        return
    svgs = [p for p in receipts_dir.iterdir() if p.is_file() and p.suffix == ".svg"]
    if not svgs:
        typer.echo("  (no receipts)")
        return
    cutoff = datetime.now() - timedelta(days=7)
    recent = [p for p in svgs if datetime.fromtimestamp(p.stat().st_mtime) > cutoff]
    most_recent = max(svgs, key=lambda p: p.stat().st_mtime)
    typer.echo(f"  {len(recent)} receipt(s) in last 7 days, {len(svgs)} total")
    typer.echo(f"  most recent: {most_recent.name}")


@app.command("validate-genome")
def validate_genome(
    genome_path: Annotated[Path, typer.Argument(help="Path to genome JSON file")],
    profile: Annotated[str, typer.Option("--profile", help="Profile to validate against")] = "",
) -> None:
    """Validate a genome JSON against a profile contract schema."""
    import json

    from hyperweave.core.color import contrast_ratio

    if not genome_path.exists():
        typer.echo(f"Error: {genome_path} not found", err=True)
        raise typer.Exit(1)

    genome = json.loads(genome_path.read_text())
    profile_id = profile or genome.get("profile", "flat")

    # Load contract schema
    contract_path = Path(__file__).parent / "data" / "profiles" / f"{profile_id}.contract.json"
    if not contract_path.exists():
        typer.echo(f"Error: no contract schema for profile '{profile_id}'", err=True)
        raise typer.Exit(1)

    contract = json.loads(contract_path.read_text())
    errors: list[str] = []

    # Check required DNA vars have corresponding genome keys
    for var_name, var_spec in contract.get("required_dna_vars", {}).items():
        source_key = var_spec.get("source", "")
        if source_key and not genome.get(source_key):
            errors.append(f"MISSING: {var_name} (genome key '{source_key}' not set)")

    # Check material-layer (dimensional profile) requirements
    for key, key_spec in contract.get("material_required", {}).items():
        val = genome.get(key)
        if not val:
            errors.append(f"MISSING: material required field '{key}'")
        elif key_spec.get("type") == "array" and isinstance(val, list):
            min_items = key_spec.get("min_items", 1)
            if len(val) < min_items:
                errors.append(f"INVALID: '{key}' has {len(val)} items, needs >= {min_items}")

    # WCAG contrast checks
    for pair in contract.get("contrast_pairs", []):
        fg = genome.get(pair["foreground"], "")
        bg = genome.get(pair["background"], "")
        if not fg or not bg or not fg.startswith("#") or not bg.startswith("#"):
            continue
        try:
            ratio = contrast_ratio(fg, bg)
            min_ratio = pair["min_ratio"]
            if ratio < min_ratio:
                errors.append(f"WCAG FAIL: {pair['label']} — {ratio:.1f}:1 < {min_ratio}:1 ({fg} on {bg})")
            else:
                typer.echo(f"  PASS: {pair['label']} — {ratio:.1f}:1 >= {min_ratio}:1")
        except (ValueError, TypeError):
            errors.append(f"INVALID COLOR: {pair['label']} — cannot parse {fg} or {bg}")

    if errors:
        typer.echo(f"\nValidation FAILED for {genome_path.name} against {profile_id}:")
        for e in errors:
            typer.echo(f"  {e}", err=True)
        raise typer.Exit(1)
    else:
        typer.echo(f"\nValidation PASSED: {genome_path.name} is a valid {profile_id} genome.")


@app.command()
def mcp(
    transport: Annotated[str, typer.Option("--transport")] = "stdio",
) -> None:
    """Start the HyperWeave MCP server."""
    from typing import Literal, cast

    try:
        from hyperweave.mcp.server import mcp as mcp_server
    except ModuleNotFoundError as exc:
        # fastmcp ships in the optional [mcp] extra (see pyproject.toml). A
        # core-only install reaches here — guide the user instead of dumping a
        # raw ImportError.
        typer.echo(
            "The MCP server requires the 'mcp' extra. Install it with:\n  pip install 'hyperweave[mcp]'",
            err=True,
        )
        raise typer.Exit(1) from exc

    # FastMCP's run() accepts a narrow Literal for transport. Cast after
    # validating the input instead of changing the user-facing CLI type.
    allowed: tuple[str, ...] = ("stdio", "http", "sse", "streamable-http")
    if transport not in allowed:
        typer.echo(f"Error: transport must be one of {allowed}, got {transport!r}", err=True)
        raise typer.Exit(1)
    mcp_server.run(
        transport=cast("Literal['stdio', 'http', 'sse', 'streamable-http']", transport),
    )


@app.command()
def serve(
    port: Annotated[int, typer.Option("--port")] = 8000,
    host: Annotated[str, typer.Option("--host")] = "0.0.0.0",
    reload: Annotated[bool, typer.Option("--reload")] = False,
) -> None:
    """Start the HyperWeave HTTP server."""
    try:
        import uvicorn
    except ModuleNotFoundError as exc:
        # fastapi + uvicorn ship in the optional [serve] extra (see
        # pyproject.toml). A core-only install reaches here — guide the user.
        typer.echo(
            "The HTTP server requires the 'serve' extra. Install it with:\n  pip install 'hyperweave[serve]'",
            err=True,
        )
        raise typer.Exit(1) from exc

    uvicorn.run(
        "hyperweave.serve.app:app",
        host=host,
        port=port,
        reload=reload,
    )


# Verb-capability commands (extract/verify/diff/query/transform) — attached from
# the surface layer so the registry is the single roster. Adding a verb adds a
# command in surfaces/cli.py, never here.
from hyperweave.surfaces.cli import register_capability_commands  # noqa: E402

register_capability_commands(app)
