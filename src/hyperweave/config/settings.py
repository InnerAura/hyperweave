"""Application settings -- Pydantic Settings with HW_ env prefix."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class HyperWeaveSettings(BaseSettings):
    """Global configuration for HyperWeave.

    All fields can be overridden via environment variables with the HW_ prefix.
    For example, HW_PORT=9000 overrides the port field.
    """

    model_config = {"env_prefix": "HW_", "env_file": ".env", "extra": "ignore"}

    # -- Paths (resolved relative to package if not absolute) --
    templates_dir: Path = Field(
        default=Path(__file__).resolve().parent.parent / "templates",
        description="Jinja2 template directory",
    )
    data_dir: Path = Field(
        default=Path(__file__).resolve().parent.parent / "data",
        description="Data files directory",
    )

    # -- Server --
    host: str = Field(default="0.0.0.0", description="Bind address")
    port: int = Field(default=8000, description="Server port")

    # -- Caching --
    # Cache TTLs split by route role so static-compose artifacts (no upstream
    # data) get a long Camo cache while data-bound artifacts get short cache
    # plus stale-while-revalidate. Mismatched TTLs were the #1 cause of the
    # README scatter-loading symptom: max-age=300 on a static badge forces
    # Camo to refetch every 5 minutes against an origin with a cold cache,
    # turning visible static content into a cold-start lottery.
    static_cache_ttl: int = Field(default=31536000, description="Editorial specimen max-age (1 year — immutable)")
    genome_cache_ttl: int = Field(default=86400, description="Genome registry max-age (24 hours)")
    compose_cache_ttl: int = Field(
        default=86400,
        description=(
            "Pure-compose artifact max-age (24 hours). Used for routes with no "
            "upstream data: static-state badges, icons, dividers, strips without "
            "?data=. Long because the artifact only changes when HyperWeave version "
            "ships — Camo refetches once daily."
        ),
    )
    data_cache_ttl: int = Field(
        default=300,
        description="Data-bound artifact max-age (5 min — paired with stale-while-revalidate=3600)",
    )
    error_cache_ttl: int = Field(
        default=5,
        description=(
            "Error-fallback (SMPTE NO SIGNAL) max-age (5 sec — paired with "
            "stale-while-revalidate=60). Aggressive so a recovered origin "
            "re-populates Camo in seconds, not the previous minute."
        ),
    )

    # -- Connectors --
    # NOTE: GitHub token rotation lives in ``connectors.base._get_github_token``,
    # which reads ``HW_GITHUB_TOKENS`` as a plain comma-separated string directly
    # from ``os.environ``. Do NOT add a ``github_tokens`` Pydantic field here —
    # Pydantic Settings would auto-map the same env var and try to JSON-parse
    # the CSV value, crashing app startup.
    connect_timeout: float = Field(default=10.0, description="HTTP connect timeout in seconds")
    total_timeout: float = Field(default=15.0, description="HTTP total timeout in seconds")

    # -- Defaults --
    default_genome: str = Field(default="brutalist", description="Default genome slug")
    default_metadata_tier: int = Field(default=3, description="Default metadata tier (3 = Resonant)")
    default_regime: str = Field(default="normal", description="Default policy lane")
    default_glyph_mode: str = Field(default="auto", description="Default glyph rendering mode")

    # -- Telemetry --
    telemetry_capture: bool = Field(default=True, description="Emit generation events")


_settings: HyperWeaveSettings | None = None


def get_settings() -> HyperWeaveSettings:
    """Return cached settings singleton.

    Returns
    -------
    HyperWeaveSettings
        Application settings loaded from environment.
    """
    global _settings
    if _settings is None:
        _settings = HyperWeaveSettings()
    return _settings
