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


def _normalize_genome_slug(slug: str) -> str:
    """Expand short-form telemetry skin slugs (e.g. ``cream`` → ``telemetry-cream``).

    Lets users type ``--genome cream`` instead of ``--genome telemetry-cream`` for
    the three v0.2.21 telemetry skins. Pass-through for slugs that already carry
    the ``telemetry-`` prefix or any non-telemetry genome (brutalist, chrome, etc.).
    """
    if not slug or slug.startswith("telemetry-"):
        return slug
    candidate = f"telemetry-{slug}"
    # Only auto-prefix when the prefixed form actually exists; otherwise pass
    # the original through so non-telemetry genomes (brutalist, chrome) still work.
    from hyperweave.compose.resolver import _genome_supports_receipts

    if _genome_supports_receipts(candidate):
        return candidate
    return slug


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
        size=size,
        shape=shape,
        variant=variant,
        pair=pair,
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
    genome: Annotated[str, typer.Option("--genome", "-g")] = "brutalist",
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
    genome: Annotated[
        str,
        typer.Option(
            "--genome",
            help=(
                "Pin telemetry skin (cream, voltage, claude-code, or full slug like "
                "telemetry-cream). Empty = auto-detect from JSONL runtime field, "
                "fall back to telemetry-voltage."
            ),
        ),
    ] = "",
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
    genome_slug = _normalize_genome_slug(genome) if genome else ""

    # Pre-compute the receipt's on-disk filename (when applicable) so the
    # footer can render the same path as the file the user sees. The compose
    # pipeline reads receipt_filename_hint when set; an empty hint falls back
    # to the legacy UUID-path footer (HTTP / MCP). Pass the FULL relative
    # path (not just the basename) so the footer is self-documenting — a
    # reader sees ".hyperweave/receipts/{slug}.svg" and knows where to find
    # the file without prior context. Long footers trigger left-truncation
    # of the constant prefix at resolver.py:_truncate_path_left.
    filename_hint = ""
    if action == "receipt" and not output:
        from datetime import datetime as _dt

        from hyperweave.telemetry.receipt_paths import receipt_filename

        sess = contract.get("session", {})
        sid = sess.get("id", "unknown")
        session_name = sess.get("name", "")
        start_iso = sess.get("start", "")
        try:
            ts = _dt.fromisoformat(start_iso)
        except (TypeError, ValueError):
            ts = _dt.now()
        user_events = contract.get("user_events", []) or []
        first_prompt = user_events[0].get("preview", "") if user_events else ""
        hw_dir = Path(".hyperweave") / "receipts"
        hw_dir.mkdir(parents=True, exist_ok=True)
        output = hw_dir / receipt_filename(
            timestamp=ts,
            session_name=session_name,
            session_id=sid,
            prompt_text=first_prompt,
        )
        filename_hint = str(output)
    elif action == "receipt" and output:
        # Explicit --output: surface whatever path shape the user provided.
        filename_hint = str(output)

    spec = ComposeSpec(
        type=frame_type,
        genome_id=genome_slug,
        telemetry_data=contract,
        receipt_filename_hint=filename_hint,
    )
    result = do_compose(spec)

    if action == "receipt":
        # output is guaranteed non-None here: the receipt branch above either
        # received an explicit --output or computed a default path.
        assert output is not None
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
    genome: Annotated[str, typer.Option("--genome", "-g")] = "brutalist",
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


def _install_claude_code_hook(hook_command: str, full_slug: str) -> None:
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

    pinned = f" (pinned to {full_slug})" if full_slug else " (auto-detect skin)"
    typer.echo(f"Installed SessionEnd hook in {settings_path}{pinned}")


def _install_codex_hook(hook_command: str, full_slug: str) -> None:
    """Write a Stop hook to ``~/.codex/hooks.json`` + enable codex_hooks feature.

    Per developers.openai.com/codex/hooks, Codex CLI fires Stop hooks
    PER-TURN (after every assistant response). The receipt rewrites the
    same deterministic filename each turn, so the on-disk file becomes a
    live mid-session telemetry window — opening it during a long session
    shows the current state, and the final write at session-end carries
    the complete cumulative receipt. This is intentional; future versions
    will lean into live-receipt consumers (file watchers, dashboards)
    rather than collapse it back to a single session-end event.

    Also writes ``[features] codex_hooks = true`` to ``~/.codex/config.toml``
    (preserving any other keys); the feature flag is required for the
    hook system to fire.
    """
    import json

    codex_dir = Path.home() / ".codex"
    hooks_path = codex_dir / "hooks.json"
    config_path = codex_dir / "config.toml"
    codex_dir.mkdir(parents=True, exist_ok=True)

    # ── Update hooks.json: remove prior hyperweave Stop entries, append new one ──
    config: dict[str, object] = {}
    if hooks_path.exists():
        config = json.loads(hooks_path.read_text())

    raw_stop = config.setdefault("Stop", [])
    stop_hooks: list[object] = raw_stop if isinstance(raw_stop, list) else []
    if not isinstance(raw_stop, list):
        config["Stop"] = stop_hooks

    cleaned = []
    for entry in stop_hooks:
        if not isinstance(entry, dict):
            cleaned.append(entry)
            continue
        cmd = str(entry.get("command", ""))
        if "hyperweave session" in cmd:
            continue  # drop prior hyperweave hook
        cleaned.append(entry)
    cleaned.append({"type": "command", "command": hook_command, "timeout": 10})
    config["Stop"] = cleaned
    hooks_path.write_text(json.dumps(config, indent=2) + "\n")

    # ── Update config.toml: ensure [features] codex_hooks = true (preserve other keys) ──
    config_lines: list[str] = []
    if config_path.exists():
        config_lines = config_path.read_text().splitlines()
    has_features_section = any(line.strip() == "[features]" for line in config_lines)
    has_codex_hooks_key = any(line.strip().startswith("codex_hooks") for line in config_lines)
    if not has_features_section:
        config_lines.extend(["", "[features]", "codex_hooks = true"])
    elif not has_codex_hooks_key:
        # Insert codex_hooks = true right after [features] header
        for i, line in enumerate(config_lines):
            if line.strip() == "[features]":
                config_lines.insert(i + 1, "codex_hooks = true")
                break
    config_path.write_text("\n".join(config_lines) + "\n")

    pinned = f" (pinned to {full_slug})" if full_slug else " (auto-detect skin)"
    typer.echo(f"Installed Stop hook in {hooks_path}{pinned}")
    typer.echo(f"Set [features] codex_hooks = true in {config_path}")
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
                "Pin telemetry skin for every session receipt (cream, voltage, "
                "claude-code, codex, or full slug like telemetry-cream). Empty = "
                "auto-detect from JSONL runtime field at session-end time."
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
                "a Stop hook to ~/.codex/hooks.json plus [features] codex_hooks in "
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
    from hyperweave.compose.resolver import _genome_supports_receipts

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
    full_slug = ""
    if genome:
        full_slug = _normalize_genome_slug(genome)
        if not _genome_supports_receipts(full_slug):
            typer.echo(
                f"Error: genome '{genome}' (resolved to '{full_slug}') does not support receipts. "
                "Telemetry skins must declare paradigms.receipt — try 'cream', 'voltage', "
                "'claude-code', or 'codex'.",
                err=True,
            )
            raise typer.Exit(1)

    hook_command = f"hyperweave session receipt --genome {full_slug}" if full_slug else "hyperweave session receipt"

    for target in targets:
        _HOOK_INSTALLERS[target](hook_command, full_slug)


def _doctor_runtime_status(runtime: str, home_dir: Path) -> str:
    """Parse a runtime's hook config and return a one-line status string.

    Returns ``✓`` when the hyperweave hook is wired correctly, ``✗`` when
    the runtime is initialized but no hyperweave hook is registered, or
    ``⚠`` when the wiring is partial (malformed config; codex missing the
    [features] codex_hooks flag). The string is rendered verbatim by
    ``doctor``.
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
        if hooks_path.exists():
            try:
                hooks = json.loads(hooks_path.read_text())
            except json.JSONDecodeError:
                return f"⚠ {runtime}: ~/.codex/hooks.json is malformed"
            for entry in hooks.get("Stop", []) or []:
                if not isinstance(entry, dict):
                    continue
                cmd = str(entry.get("command", ""))
                if "hyperweave session" in cmd:
                    registered_cmd = cmd
                    break
        if not registered_cmd:
            return (
                f"✗ {runtime}: initialized but no hyperweave hook — run 'hyperweave install-hook --runtime {runtime}'"
            )
        # [features] codex_hooks = true must be present for the hook to fire;
        # the install command writes it, but a hand-edited config could miss it.
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
                if in_features and stripped.startswith("codex_hooks") and "true" in stripped:
                    feature_ok = True
                    break
        if not feature_ok:
            return (
                f"⚠ {runtime}: hook registered but [features] codex_hooks = true "
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
    typer.echo("Receipts (./.hyperweave/receipts/):")
    receipts_dir = Path(".hyperweave") / "receipts"
    if not receipts_dir.exists():
        typer.echo("  (no receipts directory in cwd)")
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
