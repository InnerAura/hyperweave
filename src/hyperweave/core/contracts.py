"""Artifact contracts -- geometry calculations for badges and strips."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from hyperweave.core.text import measure_text

if TYPE_CHECKING:
    from hyperweave.core.models import ProfileConfig

# -- Badge geometry constants (PRD ss7) --
BADGE_PAD: int = 6
BADGE_GLYPH_SIZE: int = 14
BADGE_GLYPH_GAP: int = 3
BADGE_INDICATOR_WIDTH: int = 14
BADGE_SEP_WIDTH: int = 2
BADGE_SEAM_GAP: int = 3
BADGE_FONT_SIZE: float = 11.0

# -- Strip geometry constants --
STRIP_MIN_WIDTH: int = 530
STRIP_HEIGHT: int = 52


class ArtifactContract:
    """Geometry contract for computing artifact dimensions."""

    @staticmethod
    def badge_width(
        label: str,
        value: str,
        has_glyph: bool = False,
        has_indicator: bool = False,
        profile: ProfileConfig | None = None,
    ) -> int:
        """Compute badge total width in pixels."""
        label_w = measure_text(label, font_size=BADGE_FONT_SIZE)
        value_w = measure_text(value, font_size=BADGE_FONT_SIZE, bold=True)

        # Left segment: pad + [accent_bar] + [glyph + gap] + label + pad
        accent_w = 0.0
        if profile and profile.strip_accent_width > 0:
            accent_w = profile.strip_accent_width

        left = BADGE_PAD + accent_w
        if has_glyph:
            left += BADGE_GLYPH_SIZE + BADGE_GLYPH_GAP
        left += label_w + BADGE_PAD

        # Separator
        sep = BADGE_SEP_WIDTH + BADGE_SEAM_GAP * 2

        # Right segment: pad + value + [indicator] + pad
        right = BADGE_PAD + value_w
        if has_indicator:
            right += BADGE_GLYPH_GAP + BADGE_INDICATOR_WIDTH
        right += BADGE_PAD

        return math.ceil(left + sep + right)

    @staticmethod
    def badge_height(profile: ProfileConfig | None = None) -> int:
        """Return badge height from profile."""
        if profile:
            return profile.badge_frame_height
        return 22

    @staticmethod
    def strip_width(
        title: str,
        metrics: list[tuple[str, str]] | None = None,
        profile: ProfileConfig | None = None,
    ) -> int:
        """Compute strip total width in pixels."""
        pitch = 80
        accent_w = 0.0
        if profile:
            pitch = profile.strip_metric_pitch
            accent_w = profile.strip_accent_width

        # Identity section: accent + glyph(24) + gap(8) + title + gap(16)
        title_w = measure_text(title, font_size=14.0, bold=True)
        identity_w = accent_w + 24 + 8 + title_w + 16

        # Metric cells
        metric_w = 0.0
        if metrics:
            metric_w = len(metrics) * pitch

        # Status indicator + padding
        tail_w = BADGE_INDICATOR_WIDTH + BADGE_PAD * 2

        computed = math.ceil(identity_w + metric_w + tail_w)
        return max(computed, STRIP_MIN_WIDTH)
