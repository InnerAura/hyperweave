"""The one custom-genome validation boundary.

An inline genome (``--genome-file``, ``genome_override`` over HTTP/MCP/direct
dispatch) is validated exactly as hard as a registry genome before ANY code
reads it: ``GenomeSpec`` construction (typed leaf grammars, injection sweep),
profile existence, the shared cross-validation battery
(``compose.validate_paradigms.run_genome_battery``), then the profile
contract's required-DNA / material / WCAG checks. Shared by the CLI, HTTP,
MCP, direct dispatch (``compose/surface.py``), and raw ``ComposeSpec``
construction — never rely on the transport to validate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

from pydantic import ValidationError

from hyperweave.core.color import contrast_ratio, flatten_to_hex
from hyperweave.core.errors import HwError, HwErrorCode


def _contract_errors(genome: Mapping[str, Any], profile_id: str) -> list[str]:
    """Profile-contract violations: required DNA vars, material fields, WCAG."""
    contract_path = Path(__file__).resolve().parent.parent / "data" / "profiles" / f"{profile_id}.contract.json"
    if not contract_path.exists():
        return [f"no contract schema for profile '{profile_id}'"]

    contract = json.loads(contract_path.read_text())
    errors: list[str] = []

    for var_name, var_spec in contract.get("required_dna_vars", {}).items():
        source_key = var_spec.get("source", "")
        if source_key and not genome.get(source_key):
            errors.append(f"MISSING: {var_name} (genome key '{source_key}' not set)")

    for key, key_spec in contract.get("material_required", {}).items():
        val = genome.get(key)
        if not val:
            errors.append(f"MISSING: material required field '{key}'")
        elif key_spec.get("type") == "array" and isinstance(val, list):
            min_items = key_spec.get("min_items", 1)
            if len(val) < min_items:
                errors.append(f"INVALID: '{key}' has {len(val)} items, needs >= {min_items}")

    # Every required pair is EVALUATED or REJECTED — never skipped. A
    # translucent surface used to slip past the whole WCAG gate because the
    # check demanded two '#' strings, so a genome could ship rgba surfaces
    # with no contrast floor enforced at all.
    backdrop = _substrate_backdrop(genome)
    for pair in contract.get("contrast_pairs", []):
        label, min_ratio = pair["label"], pair["min_ratio"]
        fg_raw = str(genome.get(pair["foreground"], "") or "")
        bg_raw = str(genome.get(pair["background"], "") or "")
        if not fg_raw or not bg_raw:
            errors.append(
                f"MISSING: {label} — contrast pair needs both '{pair['foreground']}' and '{pair['background']}' set"
            )
            continue
        fg, bg = flatten_to_hex(fg_raw, backdrop), flatten_to_hex(bg_raw, backdrop)
        if fg is None or bg is None:
            unresolved = fg_raw if fg is None else bg_raw
            errors.append(f"INVALID COLOR: {label} — cannot establish contrast for {unresolved!r}")
            continue
        ratio = contrast_ratio(fg, bg)
        if ratio < min_ratio:
            composited = (fg, bg) != (fg_raw.upper(), bg_raw.upper())
            detail = f"({fg} on {bg} composited)" if composited else f"({fg_raw} on {bg_raw})"
            errors.append(f"WCAG FAIL: {label} — {ratio:.1f}:1 < {min_ratio}:1 {detail}")

    return errors


def _substrate_backdrop(genome: Mapping[str, Any]) -> str:
    """The deterministic opaque backdrop a translucent color composites over.

    Contrast on an alpha color depends on what is behind it. The genome's own
    ``surface_0`` is that backdrop when it is opaque; when the surface itself
    is translucent the substrate reference for its category is (a dark genome
    layers over black, a light one over white). Deterministic by construction,
    so the same genome always grades the same way.
    """
    surface = str(genome.get("surface_0", "") or "")
    if surface.startswith("#"):
        return surface
    return "#FFFFFF" if str(genome.get("category", "dark")) == "light" else "#000000"


def effective_variant_errors(spec: Any, profile_id: str) -> list[str]:
    """Violations of each EFFECTIVE variant — the genome a variant renders as.

    ``variant_overrides`` bodies were typed ``dict[str, Any]`` and merged into
    the genome AFTER validation, so a variant could carry a non-string
    (``{"surface_0": 123}`` → late AttributeError), an invalid color that
    emitted broken CSS, a nested gradient stop whose offset broke the composed
    SVG, or an ink/surface pair that collapsed to black on black — the profile
    contrast gate only ever graded the base genome.

    Every override key is now accounted for by exactly one of three rules:
    control-plane keys are refused outright (a variant restyles, it never
    re-identifies), keys the model owns re-validate through ``GenomeSpec``, and
    the remaining nested structures validate against their declared kind in
    ``VARIANT_EXTRA_KINDS``. An unlisted key is refused rather than trusted.
    The merged result then faces the full profile contract, contrast included.
    """
    from hyperweave.core.schema import (
        VARIANT_CONTROL_PLANE_KEYS,
        VARIANT_EXTRA_KINDS,
        GenomeSpec,
        check_override_value,
    )

    known = set(GenomeSpec.model_fields)
    base = spec.model_dump()
    errors: list[str] = []
    for variant, override in (spec.variant_overrides or {}).items():
        where = f"variant '{variant}'"
        if not isinstance(override, dict):
            errors.append(f"{where}: override must be a dict of genome fields")
            continue

        forbidden = sorted(set(override) & VARIANT_CONTROL_PLANE_KEYS)
        if forbidden:
            errors.append(f"{where}: may not override control-plane keys {forbidden}")
        for key, value in override.items():
            if key in known or key in VARIANT_CONTROL_PLANE_KEYS:
                continue
            kind = VARIANT_EXTRA_KINDS.get(key)
            if kind is None:
                errors.append(f"{where}: unknown override key '{key}'")
                continue
            errors.extend(check_override_value(key, kind, value, where))

        merged = {**base, **{key: value for key, value in override.items() if key not in VARIANT_CONTROL_PLANE_KEYS}}
        try:
            GenomeSpec(**{key: value for key, value in merged.items() if key in known})
        except ValidationError as exc:
            errors.extend(
                f"{where}: {'.'.join(str(part) for part in err.get('loc') or ())} — {err.get('msg', '')}"
                for err in exc.errors(include_url=False)
            )
            continue
        errors.extend(f"{where}: {line}" for line in _contract_errors(merged, profile_id))
    errors.extend(_variant_tone_errors(spec))
    return errors


def _variant_tone_errors(spec: Any) -> list[str]:
    """Tone primitives are chromatic values too — typed, not free-form.

    ``variant_tones.<tone>`` declares per-tone colors and color ramps that the
    cellular palette resolves into rendered paint, so an entity-bearing value
    (``canvas_top = "x&y"``) reached the composed SVG and broke it.
    """
    from hyperweave.core.schema import check_override_value

    errors: list[str] = []
    for tone, body in (spec.variant_tones or {}).items():
        if not isinstance(body, dict):
            errors.append(f"variant_tones '{tone}': must be a map of chromatic values")
            continue
        for key, value in body.items():
            # A tone ramp is either gradient stops (rim_stops) or a plain
            # color ladder (cellular_cells, area_tiers, …); the element shape
            # says which, and both are typed.
            if isinstance(value, list):
                kind = "stops" if any(isinstance(item, dict) for item in value) else "color_list"
            else:
                kind = "color"
            errors.extend(check_override_value(key, kind, value, f"variant_tones '{tone}'"))
    return errors


def validate_genome_override(raw: Mapping[str, Any], *, profile_override: str = "") -> dict[str, Any]:
    """Validate an inline genome dict exactly as hard as a registry genome.

    Sequence: ``GenomeSpec`` construction → profile existence → the shared
    ``run_genome_battery`` (paradigms / variants / surface contract / roles /
    chromatic coverage — the identical loop ``ConfigLoader.load`` runs on
    built-ins) → the profile contract (required DNA vars, material fields,
    WCAG contrast pairs). Idempotent: the returned ``GenomeSpec.model_dump()``
    is the registry shape and revalidates clean.

    :raises HwError: ``SPEC_INVALID`` aggregating every violation;
        ``detail["errors"]`` carries pydantic-shaped field errors with
        ``genome_override``-prefixed locs so surfaces render exact paths.
    """
    from hyperweave.compose.validate_paradigms import run_genome_battery
    from hyperweave.config.loader import get_loader, load_surface_modes
    from hyperweave.core.schema import GenomeSpec

    data = dict(raw)
    if profile_override:
        data["profile"] = profile_override

    field_errors: list[dict[str, Any]] = []
    try:
        spec = GenomeSpec(**data)
    except ValidationError as exc:
        # Keep only the JSON-serializable core of each pydantic error (ctx can
        # carry raw exception objects); prefix locs with the field the caller
        # actually supplied.
        field_errors = [
            {
                "type": err.get("type", "value_error"),
                "loc": ("genome_override", *tuple(err.get("loc") or ())),
                "msg": err.get("msg", ""),
            }
            for err in exc.errors(include_url=False)
        ]
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            "custom genome is invalid",
            fix="repair the named genome fields; a custom genome must satisfy the full GenomeSpec grammar",
            detail={"errors": field_errors},
        ) from exc

    loader = get_loader()
    messages: list[str] = []
    if spec.profile not in loader.profiles:
        messages.append(f"unknown profile '{spec.profile}' (known: {', '.join(sorted(loader.profiles))})")
    else:
        try:
            run_genome_battery(spec, loader.paradigms, frozenset(load_surface_modes().frames))
        except ValueError as exc:
            messages.append(str(exc))
        messages.extend(_contract_errors(spec.model_dump(), spec.profile))
        messages.extend(effective_variant_errors(spec, spec.profile))

    if messages:
        raise HwError(
            HwErrorCode.SPEC_INVALID,
            "custom genome is invalid",
            fix="; ".join(messages)[:800],
            detail={"errors": [{"loc": ("genome_override",), "msg": m, "type": "value_error"} for m in messages]},
        )
    return spec.model_dump()


def load_and_validate_genome_file(genome_path: Path, profile_override: str = "") -> dict[str, Any]:
    """Read a genome JSON file and validate it through :func:`validate_genome_override`.

    :raises FileNotFoundError: if ``genome_path`` does not exist.
    :raises json.JSONDecodeError: if the file is not valid JSON.
    :raises HwError: ``SPEC_INVALID`` when the genome fails the boundary.
    """
    if not genome_path.exists():
        raise FileNotFoundError(f"Genome file not found: {genome_path}")
    raw = json.loads(genome_path.read_text())
    if not isinstance(raw, dict):
        raise HwError(HwErrorCode.SPEC_INVALID, "genome file must contain a JSON object")
    return validate_genome_override(raw, profile_override=profile_override)
