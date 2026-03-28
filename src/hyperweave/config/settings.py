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
    static_cache_ttl: int = Field(default=31536000, description="Static asset max-age (1 year)")
    genome_cache_ttl: int = Field(default=86400, description="Genome registry max-age (24 hours)")
    data_cache_ttl: int = Field(default=300, description="Data-bound artifact max-age (5 min)")

    # -- Connectors --
    github_tokens: list[str] = Field(default_factory=list, description="GitHub API tokens for rotation")
    connect_timeout: float = Field(default=10.0, description="HTTP connect timeout in seconds")
    total_timeout: float = Field(default=15.0, description="HTTP total timeout in seconds")

    # -- Defaults --
    default_genome: str = Field(default="brutalist-emerald", description="Default genome slug")
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
