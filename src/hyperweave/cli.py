"""HyperWeave CLI -- Typer application."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

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
    frame_type: Annotated[str, typer.Argument(help="Frame: badge, strip, banner, icon, divider, marquee-*")],
    title: Annotated[str, typer.Argument(help="Primary text (label for badge, identity for strip)")] = "",
    value: Annotated[str, typer.Argument(help="Secondary text (value for badge, metrics for strip)")] = "",
    genome: Annotated[str, typer.Option("--genome", "-g")] = "brutalist-emerald",
    state: Annotated[str, typer.Option("--state", "-s")] = "active",
    motion: Annotated[str, typer.Option("--motion", "-m")] = "static",
    glyph: Annotated[str, typer.Option("--glyph")] = "",
    glyph_mode: Annotated[str, typer.Option("--glyph-mode")] = "auto",
    regime: Annotated[str, typer.Option("--regime")] = "normal",
    variant: Annotated[str, typer.Option("--variant")] = "default",
    # Divider options
    divider_variant: Annotated[str, typer.Option("--divider-variant")] = "zeropoint",
    # Marquee options
    direction: Annotated[str, typer.Option("--direction")] = "ltr",
    rows: Annotated[int, typer.Option("--rows")] = 3,
    # Output
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    metrics: Annotated[str, typer.Option("--metrics", help="Strip metrics: 'STARS:2.9k,FORKS:278'")] = "",
) -> None:
    """Compose a single HyperWeave artifact."""
    from hyperweave.compose.engine import compose as do_compose
    from hyperweave.core.models import ComposeSpec

    final_value = metrics if metrics else value

    spec = ComposeSpec(
        type=frame_type,
        genome_id=genome,
        title=title,
        value=final_value,
        state=state,
        motion=motion,
        glyph=glyph,
        glyph_mode=glyph_mode,
        regime=regime,
        variant=variant,
        divider_variant=divider_variant,
        marquee_direction=direction,
        marquee_rows=rows,
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
        total_tok = profile.get("total_input_tokens", 0) + profile.get("total_output_tokens", 0)
        dur = contract.get("session", {}).get("duration_minutes", 0)
        tok_label = f"{total_tok / 1000:.1f}K" if total_tok >= 1000 else str(total_tok)
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

    # Check if already installed
    for entry in session_end:
        if not isinstance(entry, dict):
            continue
        entry_hooks = entry.get("hooks", [])
        if not isinstance(entry_hooks, list):
            continue
        for h in entry_hooks:
            if isinstance(h, dict) and "hw session" in str(h.get("command", "")):
                typer.echo("Hook already installed.")
                return

    hook_entry = {"hooks": [{"type": "command", "command": "hw session receipt", "timeout": 10}]}
    session_end.append(hook_entry)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    typer.echo(f"Installed SessionEnd hook in {settings_path}")


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
