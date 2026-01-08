"""
HyperWeave CLI - Living Artifact Command Line Interface.

Generate living SVG badges from the command line.
"""

from pathlib import Path
from typing import Literal

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from hyperweave.core.generator import BadgeGenerator
from hyperweave.core.ontology import OntologyLoader
from hyperweave.models.badge import BadgeContent, BadgeRequest, BadgeState

app = typer.Typer(
    name="hyperweave",
    help="HyperWeave Living Artifact Protocol CLI - Generate living SVG badges",
    no_args_is_help=True,
)

console = Console()

# Shared instances
_ontology: OntologyLoader | None = None
_generator: BadgeGenerator | None = None


def get_ontology() -> OntologyLoader:
    """Get or initialize the ontology loader."""
    global _ontology
    if _ontology is None:
        _ontology = OntologyLoader()
    return _ontology


def get_generator() -> BadgeGenerator:
    """Get or initialize the badge generator."""
    global _generator
    if _generator is None:
        _generator = BadgeGenerator(get_ontology())
    return _generator


@app.command()
def generate(
    label: str = typer.Argument(..., help="Left segment text"),
    value: str = typer.Argument(..., help="Right segment text"),
    output: Path = typer.Option("badge.svg", "--output", "-o", help="Output file path"),
    state: BadgeState | None = typer.Option(
        None, "--state", "-s", help="Badge state (passing, warning, failing, etc.)"
    ),
    shape: Literal["standard", "pill", "square"] = typer.Option(
        "standard", "--shape", help="Badge shape"
    ),
    size: Literal["sm", "md", "lg", "xl"] = typer.Option("md", "--size", help="Badge size"),
    finish_label: str | None = typer.Option(None, "--finish-label", help="Label segment finish"),
    finish_value: str | None = typer.Option(None, "--finish-value", help="Value segment finish"),
    seam: str = typer.Option("vertical", "--seam", help="Seam type"),
    shadow: str | None = typer.Option(None, "--shadow", help="Shadow type"),
    border: str | None = typer.Option(None, "--border", help="Border style"),
    motion: str | None = typer.Option(None, "--motion", help="Animation type"),
    tier: Literal["NAKED", "BASIC", "FULL"] = typer.Option("FULL", "--tier", help="Metadata tier"),
    intent: str | None = typer.Option(
        None, "--intent", help="Design intent (required for FULL tier)"
    ),
    approach: str | None = typer.Option(
        None, "--approach", help="Design approach (required for FULL tier)"
    ),
    tradeoffs: str | None = typer.Option(
        None, "--tradeoffs", help="Design tradeoffs (required for FULL tier)"
    ),
):
    """
    Generate a living SVG badge.

    Example:
        hyperweave generate build passing -o build-badge.svg --state passing
    """
    generator = get_generator()

    # Validate reasoning for FULL tier
    if tier == "FULL":
        if not all([intent, approach, tradeoffs]):
            rprint(
                "[red]Error:[/red] --intent, --approach, and --tradeoffs are required for FULL tier"
            )
            raise typer.Exit(1)

    reasoning = None
    if intent and approach and tradeoffs:
        reasoning = {
            "intent": intent,
            "approach": approach,
            "tradeoffs": tradeoffs,
        }

    # Build request
    badge_request = BadgeRequest(
        content=BadgeContent(label=label, value=value, state=state),
        shape=shape,
        size=size,
        finish_label=finish_label,
        finish_value=finish_value,
        seam=seam,
        shadow=shadow,
        border=border,
        motion=motion,
        artifact_tier=tier,
        reasoning=reasoning,
    )

    try:
        # Generate badge
        response = generator.generate(badge_request)

        # Write output
        output.write_text(response.svg)

        rprint(f"[green]✓[/green] Generated badge: {output}")
        rprint(f"  Series: {response.theme_dna.series or 'N/A'}")
        rprint(f"  Size: {response.metadata.size}")
        rprint(f"  Tier: {tier}")

    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def specimen(
    theme: str | None = typer.Argument(None, help="Theme ID (e.g., chrome, codex, neon)"),
    label: str | None = typer.Argument(None, help="Left segment text (default: 'version')"),
    value: str | None = typer.Argument(None, help="Right segment text (default: '1.0.0')"),
    output: Path = typer.Option("badge.svg", "--output", "-o", help="Output file path"),
    state: BadgeState | None = typer.Option(
        None, "--state", "-s", help="Badge state (passing, warning, failing, neutral)"
    ),
    motion: str | None = typer.Option(
        None, "--motion", "-m", help="Override motion (must be compatible with theme)"
    ),
    list_themes: bool = typer.Option(False, "--list", "-l", help="List all available themes"),
    intent: str | None = typer.Option(None, "--intent", help="Design intent (optional)"),
    approach: str | None = typer.Option(None, "--approach", help="Design approach (optional)"),
    tradeoffs: str | None = typer.Option(None, "--tradeoffs", help="Design tradeoffs (optional)"),
):
    """
    Generate a badge from a v7 theme.

    Examples:
        hyperweave specimen chrome                         # Simple chrome badge
        hyperweave specimen codex status passing          # Codex theme with custom text
        hyperweave specimen neon --motion sweep           # Neon with sweep animation
        hyperweave specimen --list                        # Show all available themes

    Available themes: Use --list to see all 20 themes across 6 tiers
    """
    ontology = get_ontology()
    generator = get_generator()

    try:
        # List themes mode
        if list_themes:
            themes = ontology.get_all_themes()
            rprint("[bold]Available Themes:[/bold]\n")

            # Group by tier
            tiers = {}
            for theme_id, theme_data in themes.items():
                tier = theme_data.get("tier", "unknown")
                if tier not in tiers:
                    tiers[tier] = []
                tiers[tier].append(theme_id)

            for tier_name, theme_ids in sorted(tiers.items()):
                rprint(f"[cyan]{tier_name}[/cyan]: {', '.join(theme_ids)}")

            return

        # Require theme if not in list mode
        if not theme:
            rprint("[red]Error:[/red] Theme argument required (or use --list to see all themes)")
            raise typer.Exit(1)

        # Get theme
        try:
            theme_config = ontology.get_theme(theme)
        except KeyError:
            available = ", ".join(list(ontology.get_all_themes().keys())[:10]) + "..."
            rprint(f"[red]Error:[/red] Theme '{theme}' not found")
            rprint(f"Available themes: {available}")
            rprint("Use --list to see all themes")
            raise typer.Exit(1)

        # Build badge request
        label_text = label or "version"
        value_text = value or "1.0.0"

        # Use provided motion or default from theme
        if motion:
            compatible = theme_config.get("compatibleMotions", ["static"])
            if motion not in compatible:
                rprint(f"[red]Error:[/red] Motion '{motion}' not compatible with theme '{theme}'")
                rprint(f"Compatible motions: {', '.join(compatible)}")
                raise typer.Exit(1)
            motion_to_use = motion
        else:
            motion_to_use = theme_config.get("compatibleMotions", ["static"])[0]

        # Build reasoning if provided
        reasoning = None
        if intent or approach or tradeoffs:
            reasoning = {
                "intent": intent or f"Demonstrate {theme} theme",
                "approach": approach or f"Using {theme} theme from v7 ontology",
                "tradeoffs": tradeoffs or f"Selected {theme} for its visual characteristics",
            }

        badge_request = BadgeRequest(
            theme=theme,
            content=BadgeContent(label=label_text, value=value_text, state=state),
            motion=motion_to_use,
            size="md",
            artifact_tier="FULL" if reasoning else "BASIC",
            reasoning=reasoning,
        )

        # Generate badge
        response = generator.generate(badge_request)

        # Write output
        output.write_text(response.svg)

        rprint(f"[green]✓[/green] Generated badge with theme: {theme}")
        rprint(f"  Output: {output}")
        rprint(f"  Tier: {theme_config.get('tier')}")
        rprint(f"  Series: {theme_config.get('series')}")
        rprint(f"  Motion: {motion_to_use}")
        rprint("  Performance: composite-only")
        rprint("  Accessibility: WCAG-AA")

    except Exception as e:
        rprint(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def ontology(
    category: Literal["themes", "motions", "effects", "glyphs"] | None = typer.Argument(
        None, help="Category to query (omit for summary)"
    ),
    tier: str | None = typer.Option(
        None, "--tier", "-t", help="Filter themes by tier (industrial, flagship, premium, etc.)"
    ),
    series: str | None = typer.Option(None, "--series", "-s", help="Filter themes by series"),
    full: bool = typer.Option(False, "--full", help="Show full details"),
):
    """
    Query the HyperWeave v7 Ontology (theme-centric).

    Examples:
        hyperweave ontology                    # Summary
        hyperweave ontology themes --tier industrial
        hyperweave ontology motions
        hyperweave ontology effects
    """
    ont = get_ontology()

    if category is None:
        # Show summary
        themes = ont.get_all_themes()
        motions = ont.get_all_motions()
        glyphs = ont.get_all_glyphs()
        effects = ont.get_all_effect_definitions()

        rprint("[bold]HyperWeave Living Artifact Protocol v7.0[/bold]\n")
        rprint("Formula: BADGE = Theme(state) × Content × Motion_Override?")
        rprint(f"Themes: {len(themes)} across 6 tiers, 20 variants total\n")

        table = Table(title="v7 Ontology Summary", show_header=True)
        table.add_column("Category", style="cyan")
        table.add_column("Count", style="magenta")
        table.add_column("Examples", style="green")

        theme_examples = ", ".join(list(themes.keys())[:5]) + "..."
        motion_examples = ", ".join(list(motions.keys())[:5])
        glyph_examples = ", ".join(list(glyphs.keys())[:5])
        effect_examples = ", ".join(list(effects.keys())[:5]) + "..."

        table.add_row("Themes", str(len(themes)), theme_examples)
        table.add_row("Motions", str(len(motions)), motion_examples)
        table.add_row("Glyphs", str(len(glyphs)), glyph_examples)
        table.add_row("Effects", str(len(effects)), effect_examples)

        console.print(table)

        # Group themes by tier
        rprint("\n[bold]Themes by Tier:[/bold]")
        tiers = {}
        for theme_id, theme in themes.items():
            tier_name = theme.get("tier", "unknown")
            if tier_name not in tiers:
                tiers[tier_name] = []
            tiers[tier_name].append(theme_id)

        for tier_name, theme_ids in sorted(tiers.items()):
            rprint(f"  • {tier_name}: {', '.join(theme_ids)}")

    elif category == "themes":
        # Query themes
        themes = ont.get_all_themes()

        # Apply filters
        if tier:
            themes = {k: v for k, v in themes.items() if v.get("tier") == tier}
        if series:
            themes = {k: v for k, v in themes.items() if v.get("series") == series}

        rprint(f"[bold]Themes[/bold] ({len(themes)} items)\n")

        if full:
            # Show detailed theme info
            for theme_id, theme in themes.items():
                rprint(f"[bold cyan]{theme_id}[/bold cyan]")
                rprint(f"  Tier: {theme.get('tier')}")
                rprint(f"  Series: {theme.get('series')}")
                rprint(f"  Compatible Motions: {', '.join(theme.get('compatibleMotions', []))}")
                rprint(f"  Effects: {', '.join(theme.get('effects', []))}")
                rprint()
        else:
            # Show compact table
            table = Table(show_header=True)
            table.add_column("Theme ID", style="cyan")
            table.add_column("Tier", style="green")
            table.add_column("Series", style="yellow")
            table.add_column("Motions", style="blue")

            for theme_id, theme in themes.items():
                table.add_row(
                    theme_id,
                    theme.get("tier", ""),
                    theme.get("series", ""),
                    str(len(theme.get("compatibleMotions", []))),
                )

            console.print(table)

    elif category == "motions":
        # Query motions
        motions = ont.get_all_motions()
        rprint(f"[bold]Motions[/bold] ({len(motions)} items)\n")

        if full:
            import json

            for motion_id, motion_data in motions.items():
                rprint(f"[cyan]{motion_id}:[/cyan]")
                rprint(json.dumps(motion_data, indent=2))
                rprint()
        else:
            for motion_id, motion_data in motions.items():
                desc = motion_data.get("description", "No description")
                rprint(f"  • [cyan]{motion_id}[/cyan]: {desc}")

    elif category == "effects":
        # Query effects
        effects = ont.get_all_effect_definitions()
        rprint(f"[bold]Effects[/bold] ({len(effects)} items)\n")

        if full:
            import json

            for effect_id, effect_data in effects.items():
                rprint(f"[cyan]{effect_id}:[/cyan]")
                rprint(json.dumps(effect_data, indent=2))
                rprint()
        else:
            for effect_id, effect_data in effects.items():
                effect_type = effect_data.get("type", "unknown")
                rprint(f"  • [cyan]{effect_id}[/cyan] ({effect_type})")

    elif category == "glyphs":
        # Query glyphs
        glyphs = ont.get_all_glyphs()
        rprint(f"[bold]Glyphs[/bold] ({len(glyphs)} items)\n")

        if full:
            import json

            for glyph_type, glyph_data in glyphs.items():
                rprint(f"[cyan]{glyph_type}:[/cyan]")
                rprint(json.dumps(glyph_data, indent=2))
                rprint()
        else:
            for glyph_type in glyphs.keys():
                rprint(f"  • {glyph_type}")


@app.command()
def validate(
    file: Path = typer.Argument(..., help="SVG file to validate", exists=True),
    require_tradeoffs: bool = typer.Option(
        True, "--require-tradeoffs/--no-require-tradeoffs", help="Require tradeoffs field"
    ),
):
    """
    Validate an SVG against HyperWeave Living Artifact Protocol.

    Example:
        hyperweave validate badge.svg
    """
    import re

    svg_content = file.read_text()

    issues = []

    # Living Artifact validation
    has_hw_namespace = 'xmlns:hw="https://hyperweave.dev/hw/v1.0"' in svg_content
    has_metadata_block = "<metadata>" in svg_content
    has_provenance = "<hw:provenance>" in svg_content
    has_reasoning = "<hw:reasoning>" in svg_content
    has_spec = "<hw:spec" in svg_content

    # Extract tradeoffs
    tradeoffs_match = re.search(r"<hw:tradeoffs>(.*?)</hw:tradeoffs>", svg_content, re.DOTALL)
    has_tradeoffs = bool(tradeoffs_match)

    if not has_hw_namespace:
        issues.append(("error", "Missing xmlns:hw namespace declaration"))
    if not has_metadata_block:
        issues.append(("error", "Missing <metadata> block"))
    if not has_provenance:
        issues.append(("error", "Missing <hw:provenance> block"))
    if not has_reasoning:
        issues.append(("error", "Missing <hw:reasoning> block"))
    if not has_spec:
        issues.append(("error", "Missing <hw:spec> element"))
    if not has_tradeoffs and require_tradeoffs:
        issues.append(("error", "Missing <hw:tradeoffs> field"))

    # Accessibility validation
    has_role = 'role="img"' in svg_content
    has_title = "<title" in svg_content
    has_reduced_motion = "@media (prefers-reduced-motion" in svg_content

    if not has_role:
        issues.append(("error", "Missing role='img' attribute"))
    if not has_title:
        issues.append(("error", "Missing <title> element"))
    if not has_reduced_motion:
        issues.append(("warning", "Missing @media (prefers-reduced-motion) support"))

    # Ontology validation
    theme_dna_match = re.search(r"<hw:theme-dna[^>]*>", svg_content)
    has_theme_dna = bool(theme_dna_match)

    if not has_theme_dna:
        issues.append(("warning", "Missing <hw:theme-dna> block"))

    # Display results
    rprint(f"\n[bold]Validating:[/bold] {file}\n")

    if not issues:
        rprint("[green]✓ Valid HyperWeave Living Artifact[/green]\n")
        rprint("  Living Artifact: ✓")
        rprint("  Accessibility: ✓")
        rprint("  Ontology: ✓")
    else:
        errors = [i for i in issues if i[0] == "error"]
        warnings = [i for i in issues if i[0] == "warning"]

        if errors:
            rprint(f"[red]✗ {len(errors)} error(s) found[/red]\n")
            for _, msg in errors:
                rprint(f"  [red]✗[/red] {msg}")
        if warnings:
            rprint(f"\n[yellow]⚠ {len(warnings)} warning(s)[/yellow]\n")
            for _, msg in warnings:
                rprint(f"  [yellow]⚠[/yellow] {msg}")

        if errors:
            raise typer.Exit(1)


@app.command()
def version():
    """Show version information."""
    rprint("[bold]HyperWeave CLI v3.3.0[/bold]")
    rprint("Ontology: v2.0.0")
    rprint("Protocol: Living Artifact Protocol v1.0")


if __name__ == "__main__":
    app()
