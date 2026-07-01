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


def _resolve_receipt_genome(slug: str) -> tuple[str, str]:
    """Resolve a receipt ``--genome`` slug to a ``(genome, variant)`` pair.

    Three cases:

    * a bare primer variant (``noir`` … ``petrol``) → ``("primer", <name>)`` so
      ``--genome cream`` renders a primer **cream** receipt (no skin collision);
    * a real receipt-capable genome slug (``primer``, ``raw``) → ``(slug, "")``;
    * empty / anything else → ``("", "")``, letting the resolver fall back to
      primer/porcelain.

    The pre-genome ``telemetry-*`` skins (and their ``cream``/``voltage``/
    ``claude-code`` short-forms) are retired: they were never variants and no
    longer resolve here.
    """
    s = (slug or "").strip().lower()
    if not s:
        return "", ""
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
    result = do_compose(spec)
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


@app.command()
def validate(
    spec_file: Annotated[Path | None, typer.Argument(help="Spec envelope JSON file, or '-' for stdin.")] = None,
    spec: Annotated[str, typer.Option("--spec", help="Inline spec envelope JSON.")] = "",
) -> None:
    """Validate a spec envelope without rendering. Exits non-zero when invalid."""
    import json as _json

    from hyperweave.compose.surface import SpecEnvelope, validate_surface

    if spec:
        raw = spec
    elif spec_file is not None and str(spec_file) == "-":
        raw = sys.stdin.read()
    elif spec_file is not None:
        raw = spec_file.read_text()
    else:
        typer.echo("provide a spec file, --spec '{...}', or - for stdin", err=True)
        raise typer.Exit(code=2)

    try:
        data = _json.loads(raw)
    except _json.JSONDecodeError as exc:
        typer.echo(f"invalid JSON: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    report = validate_surface(
        SpecEnvelope(
            type=str(data.get("type", "")),
            genome=str(data.get("genome", "primer")),
            variant=str(data.get("variant", "")),
            spec=dict(data.get("spec") or {}),
        )
    )
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
        typer.Argument(help="Frame: badge, strip, icon, divider, marquee, stats, chart, matrix, diagram"),
    ],
    title: Annotated[str, typer.Argument(help="Primary text (label, identity, username, owner/repo, ...)")] = "",
    value: Annotated[str, typer.Argument(help="Secondary text or chart subtype (e.g. 'stars')")] = "",
    genome: Annotated[str, typer.Option("--genome", "-g")] = "brutalist",
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
    # Matrix options
    spec_file: Annotated[
        Path | None,
        typer.Option("--spec-file", help="MatrixSpec/DiagramSpec JSON file (matrix/diagram frames)"),
    ] = None,
    preset: Annotated[
        str,
        typer.Option("--preset", help="Server-known preset (matrix: connectors; diagram: pipeline, flywheel, ...)"),
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
            help="Surface tier: composite-only ladders diagram beam->particle, flow->dash (recorded in the payload)",
        ),
    ] = "",
    chrome: Annotated[
        str,
        typer.Option(
            "--chrome",
            help="Diagram presentation: card (default) | bare — transparent paper, no masthead/footer",
        ),
    ] = "card",
    target: Annotated[
        str,
        typer.Option(
            "--target",
            help="Surface pack: web (default) | github | email | pdf | obsidian | slack — "
            "flattens var()->hex and strips motion for non-browser surfaces",
        ),
    ] = "web",
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
            help="Diagram edge-motion override: dash | particle | beam | flow (overrides the spec/preset's motion)",
        ),
    ] = "",
    # Output
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    metrics: Annotated[str, typer.Option("--metrics", help="Strip metrics: 'STARS:2.9k,FORKS:278'")] = "",
) -> None:
    """Compose a single HyperWeave artifact.

    Examples:

    \b
      hyperweave compose stats <username>                          [fetches GitHub data]
      hyperweave compose chart stars <owner/repo>                  [fetches star history]
      hyperweave compose badge STARS --data gh:anthropics/claude-code.stars
      hyperweave compose marquee --data text:NEW,gh:owner/repo.stars,text:DOWNLOAD
      hyperweave compose matrix --spec-file table.json -g primer --variant porcelain
      hyperweave compose matrix --preset connectors -g primer --markdown-out table.md
      hyperweave compose diagram --preset pipeline -g primer --variant porcelain
      hyperweave compose diagram --spec-file flow.json -g primer --markdown-out flow.md
      hyperweave compose <any-frame> --genome-file ./x.json        [custom genome]
      hyperweave compose receipt session.jsonl                     [render a session receipt]
      hyperweave compose -  < hook.json                            [Claude Code SessionEnd hook]
    """
    # ── Receipt-from-transcript dispatch ─────────────────────────────
    # The receipt frame reads an agent's existing .jsonl transcript, never flags:
    #   compose -                  → hook mode: read hook JSON (transcript_path) on stdin
    #   compose <x>.jsonl          → infer the receipt from the transcript path
    #   compose receipt <x>.jsonl  → receipt from the named transcript path
    # Receipts speak primer only, so the brutalist compose default (or any non-primer
    # slug) falls back to primer/porcelain; a real primer variant still selects chroma.
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
    from hyperweave.core.models import ComposeSpec

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

    # ── Matrix input: --spec-file (caller IR) or --preset (server-known) ──
    matrix_spec: dict[str, object] | None = None
    if frame_type == "matrix":
        if spec_file is not None:
            try:
                matrix_spec = json.loads(spec_file.read_text())
            except FileNotFoundError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(2) from exc
            except json.JSONDecodeError as exc:
                typer.echo(f"Error: {spec_file} is not valid JSON: {exc}", err=True)
                raise typer.Exit(2) from exc
        elif preset:
            from hyperweave.compose.matrix.input import resolve_matrix_preset
            from hyperweave.core.matrix import MatrixInputError

            try:
                connector_data = resolve_matrix_preset(preset)
            except MatrixInputError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(2) from exc

    # ── Diagram input: --spec-file (caller IR) or --preset (server-known) ──
    diagram_spec: dict[str, object] | None = None
    if frame_type == "diagram":
        if spec_file is not None:
            try:
                diagram_spec = json.loads(spec_file.read_text())
            except FileNotFoundError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(2) from exc
            except json.JSONDecodeError as exc:
                typer.echo(f"Error: {spec_file} is not valid JSON: {exc}", err=True)
                raise typer.Exit(2) from exc
        elif preset:
            from hyperweave.compose.diagram.input import resolve_diagram_preset
            from hyperweave.core.diagram import DiagramInputError

            try:
                diagram_spec = resolve_diagram_preset(preset)
            except DiagramInputError as exc:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(2) from exc

        # Artifact-level edge-motion override — mirrors the HTTP ?edge_motion=
        # query: replaces the spec/preset's edge_motion before compose (per-edge
        # IR declarations still outrank it). Validated against the closed 2x2.
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
        from hyperweave.serve.data_tokens import (
            format_for_value,
            parse_data_tokens,
            resolve_data_tokens,
        )

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

    spec = ComposeSpec(
        type=frame_type,
        genome_id=genome,
        genome_override=genome_override,
        title=title,
        value=final_value,
        state=state,
        motion=motion,
        glyph=glyph,
        glyph_mode=glyph_mode,
        font_mode=font_mode,
        regime=regime,
        size=size,
        shape=shape,
        variant=variant,
        pair=pair,
        state_glyph_shape=state_glyph_shape,
        divider_variant=divider_variant,
        marquee_direction=direction,
        stats_username=stats_username,
        chart_owner=chart_owner,
        chart_repo=chart_repo,
        connector_data=connector_data,
        data_tokens=data_tokens_resolved,
        matrix=matrix_spec,
        diagram=diagram_spec,
        glyph_tint=glyph_tint,
        performance=performance,
        chrome=chrome,
    )

    result = do_compose(spec)
    svg = result.svg
    if target and target != "web":
        from hyperweave.compose.targets import apply_target

        svg = apply_target(svg, target)

    if output:
        output.write_text(svg)
        typer.echo(f"Wrote {output} ({result.width}x{result.height})")
    else:
        sys.stdout.write(svg)
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
) -> None:
    """List or inspect genomes."""
    from hyperweave.config.loader import get_loader

    loader = get_loader()

    if show:
        genome = loader.genomes.get(show)
        if not genome:
            typer.echo(f"Genome '{show}' not found.", err=True)
            raise typer.Exit(1)
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
    from hyperweave.compose.resolver import _RECEIPT_DEFAULT_GENOME, _genome_supports_receipts

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
        if not _genome_supports_receipts(check_genome):
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
