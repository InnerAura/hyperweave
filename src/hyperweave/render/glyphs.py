"""Glyph registry -- loading, auto-inference, and mode rendering."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path


# Constants

GEOMETRIC_GLYPHS: frozenset[str] = frozenset(
    {
        "circle",
        "diamond",
        "triangle",
        "hexagon",
        "shield",
        "star",
    }
)


# Auto-inference keyword map (PRD SS10)

_INFERENCE_MAP: dict[str, str] = {
    # Social / platform
    "github": "github",
    "gh": "github",
    "git": "git",
    "x": "x",
    "twitter": "x",
    "discord": "discord",
    "youtube": "youtube",
    "spotify": "spotify",
    "instagram": "instagram",
    "tiktok": "tiktok",
    "reddit": "reddit",
    "mastodon": "mastodon",
    "bluesky": "bluesky",
    "linkedin": "linkedin",
    "email": "email",
    "gmail": "email",
    "mail": "email",
    # Dev ecosystems
    "python": "python",
    "pypi": "pypi",
    "pip": "pypi",
    "npm": "npm",
    "node": "nodejs",
    "nodejs": "nodejs",
    "deno": "deno",
    "bun": "bun",
    "docker": "docker",
    "container": "docker",
    "rust": "rust",
    "go": "go",
    "golang": "go",
    "typescript": "typescript",
    "javascript": "javascript",
    "react": "react",
    "vue": "vue",
    "svelte": "svelte",
    "nextjs": "nextjs",
    "next": "nextjs",
    "tailwind": "tailwindcss",
    "vite": "vite",
    "astro": "astro",
    "flutter": "flutter",
    "dart": "dart",
    "swift": "swift",
    "kotlin": "kotlin",
    "ruby": "ruby",
    "php": "php",
    "elixir": "elixir",
    "zig": "zig",
    # Platforms
    "huggingface": "huggingface",
    "hf": "huggingface",
    "arxiv": "arxiv",
    "kaggle": "kaggle",
    "vercel": "vercel",
    "netlify": "netlify",
    "cloudflare": "cloudflare",
    "googlecloud": "googlecloud",
    "gcp": "googlecloud",
    "supabase": "supabase",
    "firebase": "firebase",
    "gitlab": "gitlab",
    "bitbucket": "bitbucket",
    "digitalocean": "digitalocean",
    "stripe": "stripe",
    "shopify": "shopify",
    # Tools
    "figma": "figma",
    "neovim": "neovim",
    "notion": "notion",
    "obsidian": "obsidian",
    "linear": "linear",
    "postman": "postman",
    "grafana": "grafana",
    "storybook": "storybook",
    # AI / ML
    "anthropic": "anthropic",
    "tensorflow": "tensorflow",
    "pytorch": "pytorch",
    "jupyter": "jupyter",
    "copilot": "githubcopilot",
    # Infrastructure
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
    "terraform": "terraform",
    "nginx": "nginx",
    "redis": "redis",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "mongodb": "mongodb",
    "mongo": "mongodb",
    "kafka": "kafka",
    "elasticsearch": "elasticsearch",
    "bash": "bash",
    # Semantic -- note: "stars" maps to "github" per project convention
    "stars": "github",
    "star": "star",
    "coverage": "github",
    "ci": "githubactions",
    "build": "githubactions",
    "license": "shield",
    "mit": "shield",
    "downloads": "diamond",
    "download": "diamond",
    "version": "",  # Suppressed -- no glyph for plain version badges
    "forks": "github",
    # OS / mobile
    "android": "android",
    "ios": "apple",
    "apple": "apple",
    "linux": "linux",
}


# Loading


def load_glyphs(glyphs_path: Path) -> dict[str, dict[str, Any]]:
    """Load glyph registry from JSON file."""
    if not glyphs_path.exists():
        return {}
    with glyphs_path.open("r", encoding="utf-8") as f:
        result: dict[str, dict[str, Any]] = json.load(f)
        return result


# Auto-inference


def infer_glyph(text: str) -> str:
    """Auto-infer a glyph ID from text content."""
    text_lower = text.lower().strip()

    # Exact match first (highest priority)
    if text_lower in _INFERENCE_MAP:
        return _INFERENCE_MAP[text_lower]

    # Substring match (first hit wins, map is insertion-ordered)
    for keyword, glyph_id in _INFERENCE_MAP.items():
        if keyword in text_lower:
            return glyph_id

    return ""


# Render context builder


def render_glyph_context(
    glyph_id: str,
    glyphs: dict[str, dict[str, Any]],
    *,
    mode: str = "auto",
    size: float = 14.0,
) -> dict[str, Any]:
    """Build a template context dict for rendering a glyph."""
    glyph = glyphs.get(glyph_id, {})
    path = glyph.get("path", "")
    viewbox = glyph.get("viewBox", "0 0 640 640")
    category = glyph.get("category", "brand")

    resolved_mode = _resolve_auto_mode(mode, category)

    return {
        "glyph_id": glyph_id,
        "glyph_path": path,
        "glyph_viewbox": viewbox,
        "glyph_category": category,
        "glyph_mode": resolved_mode,
        "glyph_size": size,
        "has_glyph": bool(path),
    }


# Alias matching the original task spec signature.
render_glyph_svg = render_glyph_context


# Badge predicate


def can_render_glyph(
    glyph_id: str,
    glyphs: dict[str, dict[str, Any]],
) -> bool:
    """Return True if *glyph_id* resolves to a renderable path."""
    if not glyph_id:
        return False
    # Geometric glyphs are always available
    if glyph_id in GEOMETRIC_GLYPHS:
        entry = glyphs.get(glyph_id, {})
        return bool(entry.get("path"))
    # Brand / platform glyphs
    entry = glyphs.get(glyph_id, {})
    return bool(entry.get("path"))


def is_geometric(glyph_id: str) -> bool:
    """Return True if *glyph_id* is a geometric mark (not a brand icon)."""
    return glyph_id in GEOMETRIC_GLYPHS


# Internals


def _resolve_auto_mode(mode: str, category: str = "brand") -> str:
    if mode in ("fill", "wire", "none"):
        return mode
    # auto resolution: genome defines surface, always fill
    return "fill"
