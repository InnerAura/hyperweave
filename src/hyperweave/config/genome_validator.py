"""Reusable genome file validation.

Shared between the ``hyperweave validate-genome`` CLI command and the
``--genome-file`` flag on ``hyperweave compose``. Validates a genome JSON
file against its profile contract schema (required fields + WCAG contrast
pairs) and returns the loaded dict alongside any error messages.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hyperweave.core.color import contrast_ratio


def load_and_validate_genome_file(
    genome_path: Path,
    profile_override: str = "",
) -> tuple[dict[str, Any], list[str]]:
    """Load a genome JSON file and validate it against its profile contract.

    Returns:
        ``(genome_dict, errors)``. When ``errors`` is empty the genome is
        safe to pass into ``ComposeSpec.genome_override``. When non-empty,
        callers should surface the errors and refuse to compose.

    Raises:
        FileNotFoundError: if ``genome_path`` does not exist.
        json.JSONDecodeError: if the file is not valid JSON.
    """
    if not genome_path.exists():
        raise FileNotFoundError(f"Genome file not found: {genome_path}")

    genome_raw = json.loads(genome_path.read_text())
    profile_id = profile_override or genome_raw.get("profile", "brutalist")

    contract_path = Path(__file__).resolve().parent.parent / "data" / "profiles" / f"{profile_id}.contract.json"
    if not contract_path.exists():
        return genome_raw, [f"no contract schema for profile '{profile_id}'"]

    contract = json.loads(contract_path.read_text())
    errors: list[str] = []

    # Check required DNA vars have corresponding genome keys
    for var_name, var_spec in contract.get("required_dna_vars", {}).items():
        source_key = var_spec.get("source", "")
        if source_key and not genome_raw.get(source_key):
            errors.append(f"MISSING: {var_name} (genome key '{source_key}' not set)")

    # Chrome-specific required fields
    for key, key_spec in contract.get("chrome_required", {}).items():
        val = genome_raw.get(key)
        if not val:
            errors.append(f"MISSING: chrome required field '{key}'")
        elif key_spec.get("type") == "array" and isinstance(val, list):
            min_items = key_spec.get("min_items", 1)
            if len(val) < min_items:
                errors.append(f"INVALID: '{key}' has {len(val)} items, needs >= {min_items}")

    # WCAG contrast checks
    for pair in contract.get("contrast_pairs", []):
        fg = genome_raw.get(pair["foreground"], "")
        bg = genome_raw.get(pair["background"], "")
        if not fg or not bg or not fg.startswith("#") or not bg.startswith("#"):
            continue
        try:
            ratio = contrast_ratio(fg, bg)
            min_ratio = pair["min_ratio"]
            if ratio < min_ratio:
                errors.append(f"WCAG FAIL: {pair['label']} — {ratio:.1f}:1 < {min_ratio}:1 ({fg} on {bg})")
        except (ValueError, TypeError):
            errors.append(f"INVALID COLOR: {pair['label']} — cannot parse {fg} or {bg}")

    return genome_raw, errors
