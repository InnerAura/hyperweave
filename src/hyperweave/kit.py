"""Kit composer -- generates composed artifact sets for any surface."""

from __future__ import annotations

from hyperweave.compose.engine import compose
from hyperweave.core.models import ComposeResult, ComposeSpec


def compose_kit(
    kit_type: str,
    genome: str = "brutalist-emerald",
    project: str = "",
    badges: str = "",
    social: str = "",
) -> dict[str, ComposeResult]:
    """Compose a full artifact kit."""
    if kit_type == "readme":
        return _readme_kit(genome, project, badges, social)
    return {}


def _readme_kit(
    genome: str,
    project: str,
    badges: str,
    social: str,
) -> dict[str, ComposeResult]:
    results: dict[str, ComposeResult] = {}
    project_name = project or "PROJECT"

    # Parse badges: "build:passing,version:v0.6.3,coverage:92%"
    badge_pairs = _parse_badge_string(badges)

    # Generate badges
    for label, value in badge_pairs:
        spec = ComposeSpec(
            type="badge",
            genome_id=genome,
            title=label,
            value=value,
            state=_infer_state(label, value),
        )
        results[f"badge-{label.lower()}"] = compose(spec)

    # Generate banner
    results["banner"] = compose(
        ComposeSpec(
            type="banner",
            genome_id=genome,
            title=project_name.upper(),
        )
    )

    # Generate strip
    if badge_pairs:
        metrics_str = ",".join(f"{k}:{v}" for k, v in badge_pairs[:4])
        results["strip"] = compose(
            ComposeSpec(
                type="strip",
                genome_id=genome,
                title=project_name,
                value=metrics_str,
            )
        )

    # Generate divider
    results["divider"] = compose(
        ComposeSpec(
            type="divider",
            genome_id=genome,
        )
    )

    # Generate social icons
    if social:
        for platform in social.split(","):
            platform = platform.strip()
            if platform:
                results[f"icon-{platform}"] = compose(
                    ComposeSpec(
                        type="icon",
                        genome_id=genome,
                        glyph=platform,
                    )
                )

    return results


def _parse_badge_string(badges: str) -> list[tuple[str, str]]:
    if not badges:
        return []
    pairs: list[tuple[str, str]] = []
    for pair in badges.split(","):
        pair = pair.strip()
        if ":" in pair:
            k, v = pair.split(":", 1)
            pairs.append((k.strip(), v.strip()))
    return pairs


def _infer_state(label: str, value: str) -> str:
    label_lower = label.lower()
    value_lower = value.lower()

    if "pass" in value_lower or "success" in value_lower:
        return "passing"
    if "fail" in value_lower or "error" in value_lower:
        return "failing"
    if "warn" in value_lower:
        return "warning"
    if "build" in label_lower and "run" in value_lower:
        return "building"

    # Percentage-based threshold
    if value.rstrip("%").replace(".", "").isdigit():
        try:
            num = float(value.rstrip("%"))
            if num >= 90:
                return "passing"
            if num >= 70:
                return "warning"
            return "critical"
        except ValueError:
            pass

    return "active"
