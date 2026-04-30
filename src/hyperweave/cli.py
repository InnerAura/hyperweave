"""HyperWeave CLI -- Typer application."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any

import typer

app = typer.Typer(
    name="hyperweave",
    help="Compositor API for self-contained SVG artifacts.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Print the HyperWeave version."""
    from hyperweave import __version__

    typer.echo(f"hyperweave {__version__}")


@app.command()
def compose(
    frame_type: Annotated[
        str,
        typer.Argument(help="Frame: badge, strip, icon, divider, marquee-horizontal, stats, chart"),
    ],
    title: Annotated[str, typer.Argument(help="Primary text (label, identity, username, owner/repo, ...)")] = "",
    value: Annotated[str, typer.Argument(help="Secondary text or chart subtype (e.g. 'stars')")] = "",
    genome: Annotated[str, typer.Option("--genome", "-g")] = "brutalist-emerald",
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
    variant: Annotated[str, typer.Option("--variant")] = "default",
    shape: Annotated[str, typer.Option("--shape", help="Icon shape: square, circle")] = "",
    family: Annotated[
        str,
        typer.Option(
            "--family",
            help="Chromatic family (automata): blue, purple, bifamily. Empty = frame default.",
        ),
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
                "hf:org/model.metric | arxiv:id.metric | docker:owner/image.metric. "
                "Embedded commas in text/kv payloads escape as \\,."
            ),
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
      hyperweave compose marquee-horizontal --data text:NEW,gh:owner/repo.stars,text:DOWNLOAD
      hyperweave compose <any-frame> --genome-file ./x.json        [custom genome]
    """
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

        if frame_type == "marquee-horizontal":
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
        regime=regime,
        variant=variant,
        shape=shape,
        family=family,
        divider_variant=divider_variant,
        marquee_direction=direction,
        stats_username=stats_username,
        chart_owner=chart_owner,
        chart_repo=chart_repo,
        connector_data=connector_data,
        data_tokens=data_tokens_resolved,
    )

    result = do_compose(spec)

    if output:
        output.write_text(result.svg)
        typer.echo(f"Wrote {output} ({result.width}x{result.height})")
    else:
        sys.stdout.write(result.svg)


@app.command()
def kit(
    kit_type: Annotated[str, typer.Argument(help="Kit type: readme")] = "readme",
    genome: Annotated[str, typer.Option("--genome", "-g")] = "brutalist-emerald",
    project: Annotated[str, typer.Option("--project")] = "",
    badges: Annotated[str, typer.Option("--badges", help="'build:passing,version:v0.6.3'")] = "",
    social: Annotated[str, typer.Option("--social", help="'github,discord,x'")] = "",
    output_dir: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Compose a full artifact kit."""
    from hyperweave.kit import compose_kit

    results = compose_kit(kit_type, genome, project, badges, social)

    out = output_dir or Path(".")
    out.mkdir(parents=True, exist_ok=True)

    for name, result in results.items():
        path = out / f"{name}.svg"
        path.write_text(result.svg)
        typer.echo(f"  {name}.svg ({result.width}x{result.height})")

    typer.echo(f"Kit '{kit_type}': {len(results)} artifacts -> {out}")


@app.command()
def render(
    template: Annotated[str, typer.Option("--template", help="Template name: receipt, rhythm-strip, master-card")],
    data: Annotated[Path, typer.Option("--data", help="Data contract JSON file")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Render a telemetry artifact from a data contract.

    Telemetry frames use their own built-in palette (no genome selection).
    """
    import json

    from hyperweave.compose.engine import compose as do_compose
    from hyperweave.core.models import ComposeSpec

    telemetry_data = json.loads(data.read_text())

    spec = ComposeSpec(
        type=template,
        telemetry_data=telemetry_data,
    )

    result = do_compose(spec)

    if output:
        output.write_text(result.svg)
        typer.echo(f"Wrote {output}")
    else:
        sys.stdout.write(result.svg)


# Session telemetry commands


@app.command()
def session(
    action: Annotated[str, typer.Argument(help="Action: receipt, strip, parse")],
    transcript: Annotated[Path | None, typer.Argument(help="Path to transcript JSONL")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Session telemetry: parse transcripts, render receipts and rhythm strips.

    When invoked as a Claude Code hook, reads transcript_path from stdin JSON.
    """
    import json

    # Resolve transcript path: arg > stdin JSON (hook mode)
    transcript_path = transcript
    if not transcript_path and not sys.stdin.isatty():
        try:
            hook_input = json.load(sys.stdin)
            raw_path = hook_input.get("transcript_path", "")
            if raw_path:
                transcript_path = Path(raw_path)
        except (json.JSONDecodeError, KeyError):
            pass

    if not transcript_path or not transcript_path.exists():
        # Graceful no-op for non-conversational sessions (e.g., `claude update`)
        # that fire SessionEnd without producing a transcript.
        if not sys.stdin.isatty():
            return
        typer.echo("Error: no transcript found (pass path or pipe hook JSON on stdin)", err=True)
        raise typer.Exit(1)

    from hyperweave.telemetry.contract import build_contract

    contract = build_contract(str(transcript_path))

    if action == "parse":
        # Parse-only: print JSON to stdout
        typer.echo(json.dumps(contract, indent=2, default=str))
        return

    if action not in ("receipt", "strip"):
        typer.echo(f"Unknown action '{action}'. Use: receipt, strip, parse", err=True)
        raise typer.Exit(1)

    # Skip empty sessions — no tool calls and no cost produces a blank receipt
    # (e.g. user opened Claude Code, did nothing, closed it; or a no-op SessionEnd).
    # Hook mode silently no-ops; interactive mode reports why.
    if not contract.get("tools") and contract.get("profile", {}).get("total_cost", 0) == 0:
        if sys.stdin.isatty():
            sid = contract.get("session", {}).get("id", "unknown")
            typer.echo(f"Skipped empty session {sid}: no tool calls, no cost.", err=True)
        return

    # Compose the telemetry artifact
    from hyperweave.compose.engine import compose as do_compose
    from hyperweave.core.models import ComposeSpec

    frame_type = "receipt" if action == "receipt" else "rhythm-strip"
    spec = ComposeSpec(type=frame_type, telemetry_data=contract)
    result = do_compose(spec)

    if action == "receipt":
        # Default output: .hyperweave/receipts/{session_id}.svg
        if not output:
            sid = contract.get("session", {}).get("id", "unknown")
            hw_dir = Path(".hyperweave") / "receipts"
            hw_dir.mkdir(parents=True, exist_ok=True)
            output = hw_dir / f"{sid}.svg"

        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.svg)

        # One-line summary to stderr
        profile = contract.get("profile", {})
        cost = profile.get("total_cost", 0)
        total_tok = (
            profile.get("total_input_tokens", 0)
            + profile.get("total_output_tokens", 0)
            + profile.get("total_cache_read_tokens", 0)
            + profile.get("total_cache_creation_tokens", 0)
        )
        dur = contract.get("session", {}).get("duration_minutes", 0)
        from hyperweave.compose.resolver import _fmt_tok

        tok_label = _fmt_tok(total_tok)
        typer.echo(f"Receipt: ${cost:.2f} · {tok_label} tokens · {int(dur)}m -> {output}", err=True)
    else:
        # Strip: stdout by default
        if output:
            output.write_text(result.svg)
            typer.echo(f"Wrote {output}", err=True)
        else:
            sys.stdout.write(result.svg)


# Live data commands


@app.command()
def live(
    provider: Annotated[str, typer.Argument(help="Provider: github, pypi, npm, arxiv, huggingface, docker")],
    identifier: Annotated[str, typer.Argument(help="Resource ID: owner/repo, package-name, paper-id")],
    metric: Annotated[str, typer.Argument(help="Metric: stars, forks, version, downloads, likes")],
    genome: Annotated[str, typer.Option("--genome", "-g")] = "brutalist-emerald",
    glyph: Annotated[str, typer.Option("--glyph")] = "",
    state: Annotated[str, typer.Option("--state", "-s")] = "active",
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Compose a badge with live data from a provider."""
    import asyncio

    from hyperweave.connectors import fetch_metric

    label = metric
    value = "n/a"
    try:
        data = asyncio.run(fetch_metric(provider, identifier, metric))
        value = str(data.get("value", "n/a"))
    except Exception as exc:
        value = f"error: {exc!s}"[:30]

    from hyperweave.compose.engine import compose as do_compose
    from hyperweave.core.models import ComposeSpec

    spec = ComposeSpec(
        type="badge",
        genome_id=genome,
        title=label,
        value=value,
        state=state,
        glyph=glyph,
    )
    result = do_compose(spec)

    if output:
        output.write_text(result.svg)
        typer.echo(f"Wrote {output} ({result.width}x{result.height})")
    else:
        sys.stdout.write(result.svg)


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


@app.command("install-hook")
def install_hook() -> None:
    """Install the SessionEnd hook into Claude Code settings."""
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

    # Remove stale "hw" hooks (0A bug: hw binary never existed)
    cleaned = []
    already_installed = False
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
            continue  # drop stale hw hook
        if any("hyperweave session" in c for c in cmds):
            already_installed = True
        cleaned.append(entry)
    hooks["SessionEnd"] = cleaned
    session_end = cleaned

    if already_installed:
        typer.echo("Hook already installed.")
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
        return

    hook_entry = {"hooks": [{"type": "command", "command": "hyperweave session receipt", "timeout": 10}]}
    session_end.append(hook_entry)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    typer.echo(f"Installed SessionEnd hook in {settings_path}")


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
    profile_id = profile or genome.get("profile", "brutalist")

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

    # Check chrome-specific requirements
    for key, key_spec in contract.get("chrome_required", {}).items():
        val = genome.get(key)
        if not val:
            errors.append(f"MISSING: chrome required field '{key}'")
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

    from hyperweave.mcp.server import mcp as mcp_server

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
    import uvicorn

    uvicorn.run(
        "hyperweave.serve.app:app",
        host=host,
        port=port,
        reload=reload,
    )
