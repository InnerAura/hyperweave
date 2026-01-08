"""
HyperWeave v7 Ontology Loader - Theme-Centric Architecture.

Loads the Living Artifact Protocol v7 ontology with self-contained themes.
Replaces primitive-based composition with theme-first approach.
"""

import json
from pathlib import Path
from typing import Any, cast


class OntologyLoader:
    """
    Ontology Loader - Theme-centric architecture.

    Loads single consolidated ontology file with self-contained themes.
    Replaces primitive-based composition with theme-first approach.

    Ontology location: svg-primitives/hw-living-artifact-ontology-v7.json

    Usage:
        >>> ontology = OntologyLoader()
        >>> theme = ontology.get_theme("chrome")
        >>> themes = ontology.get_themes_by_tier("scholarly")
    """

    def __init__(self, ontology_path: Path | None = None) -> None:
        """
        Initialize loader with v7 ontology.

        Args:
            ontology_path: Path to hw-living-artifact-ontology-v7.json
                          Defaults to svg-primitives/hw-living-artifact-ontology-v7.json
        """
        if ontology_path is None:
            ontology_path = (
                Path(__file__).parent.parent.parent.parent
                / "svg-primitives"
                / "hw-living-artifact-ontology-v7.json"
            )

        self.ontology_path = Path(ontology_path)
        self._data: dict[str, Any] = {}
        self._themes_cache: dict[str, dict[str, Any]] = {}
        self._load_ontology()

    def _load_ontology(self) -> None:
        """Load and parse v7 ontology JSON."""
        if not self.ontology_path.exists():
            raise FileNotFoundError(
                f"Ontology file not found: {self.ontology_path}\n"
                f"Expected location: svg-primitives/hw-living-artifact-ontology-v7.json"
            )

        with open(self.ontology_path) as f:
            self._data = json.load(f)

        # Validate schema version
        version = self._data.get("version")
        if version != "7.0.0":
            raise ValueError(
                f"Expected ontology v7.0.0, got {version}\n"
                f"This loader only supports Living Artifact Protocol v7.0"
            )

        # Cache themes for quick access
        themes = self._data.get("themes", {})
        for theme_id, theme_data in themes.items():
            # Add theme ID to the data for convenience
            theme_data["id"] = theme_id
            self._themes_cache[theme_id] = theme_data

    # ─── PRIMARY THEME ACCESS ───────────────────────────────────

    def get_theme(self, theme_id: str) -> dict[str, Any]:
        """
        Get theme by ID.

        Args:
            theme_id: Theme identifier (e.g., "chrome", "neon", "sakura")

        Returns:
            Theme dict with complete specification including:
            - id, tier, series, description
            - label/value configs
            - effects array
            - glyph config
            - states dict
            - compatibleMotions list

        Raises:
            KeyError: If theme_id does not exist in ontology

        Example:
            >>> theme = ontology.get_theme("codex")
            >>> print(theme["tier"])  # "scholarly"
            >>> print(theme["compatibleMotions"])  # ["static", "breathe", "sweep"]
        """
        if theme_id not in self._themes_cache:
            available = ", ".join(sorted(self.get_all_theme_ids()))
            suggestion = self._get_closest_match(theme_id, self.get_all_theme_ids())

            raise KeyError(
                f"Theme '{theme_id}' not found in ontology.\n"
                f"Available themes: {available}\n"
                f"Did you mean '{suggestion}'?"
            )

        return self._themes_cache[theme_id]

    def get_all_themes(self) -> dict[str, dict[str, Any]]:
        """
        Get all themes as dict[theme_id → theme_config].

        Returns:
            Dictionary mapping theme IDs to theme configurations

        Example:
            >>> themes = ontology.get_all_themes()
            >>> len(themes)  # 20
            >>> list(themes.keys())  # ["void", "neon", "glass", ...]
        """
        return self._themes_cache.copy()

    def get_all_theme_ids(self) -> list[str]:
        """
        Get list of all theme IDs.

        Returns:
            Sorted list of theme identifiers

        Example:
            >>> ids = ontology.get_all_theme_ids()
            >>> "codex" in ids  # True
            >>> len(ids)  # 20
        """
        return sorted(self._themes_cache.keys())

    def get_themes_by_tier(self, tier: str) -> list[dict[str, Any]]:
        """
        Get all themes in a tier.

        Args:
            tier: Tier name (minimal, flagship, premium, industrial, brutalist, cosmology, scholarly)

        Returns:
            List of theme configs in that tier

        Example:
            >>> scholarly = ontology.get_themes_by_tier("scholarly")
            >>> len(scholarly)  # 5
            >>> [t["id"] for t in scholarly]  # ["codex", "theorem", "archive", "symposium", "cipher"]
        """
        return [theme for theme in self._themes_cache.values() if theme.get("tier") == tier]

    def get_themes_by_series(self, series: str) -> list[dict[str, Any]]:
        """
        Get all themes in a series.

        Args:
            series: Series name (e.g., "core", "five-scholars")

        Returns:
            List of theme configs in that series

        Example:
            >>> core = ontology.get_themes_by_series("core")
            >>> len(core)  # 15
        """
        return [theme for theme in self._themes_cache.values() if theme.get("series") == series]

    # ─── SECONDARY ACCESS (SUPPORTING DATA) ─────────────────────

    def get_effect_definition(self, effect_id: str) -> dict[str, Any]:
        """
        Get effect definition for rendering.

        Args:
            effect_id: Effect identifier (e.g., "dropShadow", "sweepHighlight")

        Returns:
            Effect definition dict with:
            - type: "filter", "gradient", or "animation"
            - template: SVG template string
            - id: Template ID with placeholders
            - Additional type-specific parameters

        Raises:
            KeyError: If effect_id not found in effectDefinitions

        Example:
            >>> effect = ontology.get_effect_definition("dropShadow")
            >>> print(effect["type"])  # "filter"
        """
        effects = self._data.get("effectDefinitions", {})
        if effect_id not in effects:
            available = ", ".join(sorted(effects.keys()))
            raise KeyError(
                f"Effect '{effect_id}' not found in effectDefinitions.\n"
                f"Available effects: {available}"
            )
        return cast(dict[str, Any], effects[effect_id])

    def get_all_effect_definitions(self) -> dict[str, Any]:
        """
        Get all effect definitions.

        Returns:
            Dictionary of effect definitions keyed by effect ID
        """
        return cast(dict[str, Any], self._data.get("effectDefinitions", {}))

    def get_motion_definition(self, motion_id: str) -> dict[str, Any]:
        """
        Get motion definition.

        Args:
            motion_id: Motion identifier (e.g., "static", "breathe", "sweep")

        Returns:
            Motion definition with:
            - effects: List of effect IDs
            - duration: Animation duration
            - keyframes: CSS keyframes (if applicable)
            - css: CSS animation rules (if applicable)

        Raises:
            KeyError: If motion_id not found

        Example:
            >>> motion = ontology.get_motion_definition("sweep")
            >>> print(motion["duration"])  # "5s"
        """
        motions = self._data.get("motions", {})
        if motion_id not in motions:
            available = ", ".join(sorted(motions.keys()))
            raise KeyError(
                f"Motion '{motion_id}' not found in motions.\nAvailable motions: {available}"
            )
        return cast(dict[str, Any], motions[motion_id])

    def get_all_motions(self) -> dict[str, Any]:
        """Get all motion definitions."""
        return cast(dict[str, Any], self._data.get("motions", {}))

    def get_glyph_definition(self, glyph_type: str) -> dict[str, Any]:
        """
        Get glyph (indicator) SVG template.

        Args:
            glyph_type: Glyph type (none, dot, check, cross, star, arrow-up, arrow-down, warning, info, live)

        Returns:
            Glyph definition with:
            - svg: SVG template string with placeholders
            - semantic: Semantic meaning
            - animation: Optional animation reference

        Raises:
            KeyError: If glyph_type not found

        Example:
            >>> glyph = ontology.get_glyph_definition("dot")
            >>> print(glyph["semantic"])  # "active/online/live"
        """
        glyphs = self._data.get("glyphs", {})
        if glyph_type not in glyphs:
            available = ", ".join(sorted(glyphs.keys()))
            raise KeyError(
                f"Glyph '{glyph_type}' not found in glyphs.\nAvailable glyphs: {available}"
            )
        return cast(dict[str, Any], glyphs[glyph_type])

    def get_all_glyphs(self) -> dict[str, Any]:
        """Get all glyph definitions."""
        return cast(dict[str, Any], self._data.get("glyphs", {}))

    def get_icon_definition(self, icon_type: str) -> dict[str, Any]:
        """
        Get brand icon SVG template.

        Args:
            icon_type: Icon type (github, npm, discord, twitter, vercel, docker, twitch, youtube, slack, etc.)

        Returns:
            Icon definition with:
            - svg: SVG template string with placeholders
            - viewBox: Icon viewBox dimensions

        Raises:
            KeyError: If icon_type not found

        Example:
            >>> icon = ontology.get_icon_definition("github")
            >>> print(icon["viewBox"])  # "0 0 16 16"
        """
        icons = self._data.get("icons", {})
        if icon_type not in icons:
            available = ", ".join(sorted(icons.keys()))
            raise KeyError(f"Icon '{icon_type}' not found in icons.\nAvailable icons: {available}")
        return cast(dict[str, Any], icons[icon_type])

    def get_all_icons(self) -> dict[str, Any]:
        """Get all icon definitions."""
        return cast(dict[str, Any], self._data.get("icons", {}))

    def get_chromatic_system(self, chromatic_id: str) -> dict[str, Any]:
        """
        Get chromatic color system definition.

        Args:
            chromatic_id: Chromatic system identifier (neutral-mono, carbon-crimson, obsidian-gold)

        Returns:
            Chromatic system definition with:
            - name: Display name
            - description: System description
            - tier: universal, flagship, or premium
            - light: Light mode colors (primary, secondary, tertiary, accent, text, semantic)
            - dark: Dark mode colors (primary, secondary, tertiary, accent, text, semantic)
            - intent: Design reasoning
            - approach: Technical approach
            - tradeoffs: Design tradeoffs

        Raises:
            KeyError: If chromatic_id not found

        Example:
            >>> chromatic = ontology.get_chromatic_system("carbon-crimson")
            >>> print(chromatic["dark"]["accent"])  # "#b31b1b"
        """
        chromatics = self._data.get("chromaticSystems", {})
        if chromatic_id not in chromatics:
            available = ", ".join(sorted(chromatics.keys()))
            raise KeyError(
                f"Chromatic system '{chromatic_id}' not found in chromaticSystems.\n"
                f"Available chromatic systems: {available}"
            )
        return cast(dict[str, Any], chromatics[chromatic_id])

    def get_all_chromatic_systems(self) -> dict[str, Any]:
        """
        Get all chromatic color system definitions.

        Returns:
            Dictionary of chromatic systems keyed by ID
        """
        return cast(dict[str, Any], self._data.get("chromaticSystems", {}))

    def get_metadata_template(self) -> dict[str, Any]:
        """
        Get metadata template for Living Artifact Protocol.

        Returns:
            Metadata template with:
            - rdf: RDF/DC metadata configuration
            - hw:artifact: HyperWeave artifact configuration
        """
        return cast(dict[str, Any], self._data.get("metadataTemplate", {}))

    def get_svg_template(self) -> dict[str, Any]:
        """
        Get SVG structure template.

        Returns:
            SVG template with:
            - rootAttributes: Required SVG root attributes
            - structure: Ordered list of SVG sections
        """
        return cast(dict[str, Any], self._data.get("svgTemplate", {}))

    def get_layout(self) -> dict[str, Any]:
        """
        Get layout configuration.

        Returns:
            Layout config with:
            - dimensions: width, height
            - sections: label/value positioning
            - corners: border radius, paths
            - typography: font config
            - glyph: glyph positioning
        """
        return cast(dict[str, Any], self._data.get("layout", {}))

    def get_protocol_info(self) -> dict[str, Any]:
        """
        Get Living Artifact Protocol metadata.

        Returns:
            Protocol info with:
            - name: Protocol name
            - version: Protocol version
            - namespaces: XML namespace definitions
        """
        return cast(dict[str, Any], self._data.get("protocol", {}))

    def get_accessibility_config(self) -> dict[str, Any]:
        """
        Get accessibility requirements.

        Returns:
            Accessibility config with:
            - required: Required ARIA attributes
            - elements: title/desc templates
            - reducedMotion: Motion preference handling
            - contrast: WCAG contrast requirements
        """
        return cast(dict[str, Any], self._data.get("accessibility", {}))

    # ─── VALIDATION ─────────────────────────────────────────────

    def validate_theme_motion_compatibility(
        self, theme_id: str, motion_id: str
    ) -> tuple[bool, str | None]:
        """
        Validate theme-motion compatibility.

        Args:
            theme_id: Theme to validate
            motion_id: Motion to apply

        Returns:
            (is_valid, error_message) tuple
            - is_valid: True if motion compatible with theme
            - error_message: Error description if invalid, None if valid

        Example:
            >>> valid, error = ontology.validate_theme_motion_compatibility("chrome", "sweep")
            >>> print(valid)  # True
            >>> valid, error = ontology.validate_theme_motion_compatibility("brutalist", "sweep")
            >>> print(valid)  # False
            >>> print(error)  # "Motion 'sweep' not compatible with theme 'brutalist'..."
        """
        try:
            theme = self.get_theme(theme_id)
        except KeyError as e:
            return (False, str(e))

        compatible = theme.get("compatibleMotions", [])

        if motion_id not in compatible:
            return (
                False,
                f"Motion '{motion_id}' not compatible with theme '{theme_id}'. "
                f"Compatible motions: {', '.join(compatible)}",
            )

        return (True, None)

    def validate_effect_exists(self, effect_id: str) -> bool:
        """
        Check if effect definition exists.

        Args:
            effect_id: Effect identifier to check

        Returns:
            True if effect exists in effectDefinitions
        """
        return effect_id in self._data.get("effectDefinitions", {})

    # ─── UTILITY METHODS ────────────────────────────────────────

    def _get_closest_match(self, query: str, options: list[str]) -> str:
        """
        Find closest matching string using simple edit distance.

        Args:
            query: String to match
            options: List of valid options

        Returns:
            Closest matching option
        """
        if not options:
            return ""

        # Simple Levenshtein distance
        def levenshtein(s1: str, s2: str) -> int:
            if len(s1) < len(s2):
                return levenshtein(s2, s1)
            if len(s2) == 0:
                return len(s1)

            previous_row: list[int] = list(range(len(s2) + 1))
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row

            return previous_row[-1]

        return min(options, key=lambda opt: levenshtein(query.lower(), opt.lower()))

    def get_version(self) -> str:
        """
        Get ontology version.

        Returns:
            Ontology version string (e.g., "7.0.0")
        """
        return str(self._data.get("version", "unknown"))

    def get_description(self) -> str:
        """
        Get ontology description.

        Returns:
            Human-readable ontology description
        """
        return str(self._data.get("description", ""))
