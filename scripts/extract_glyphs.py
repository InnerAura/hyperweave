#!/usr/bin/env python3
"""Extract curated glyphs from Simple Icons and output data/glyphs.json.

Build-time only. Requires: npm install simple-icons (temp dev dependency).

Usage:
    npm install simple-icons  # one-time
    python scripts/extract_glyphs.py

Output:
    src/hyperweave/data/glyphs.json
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Curated icon set per PRD SS10
# Keys = Simple Icons export names (camelCase with 'si' prefix)
# Values = (our slug, category)
CURATED_ICONS: dict[str, tuple[str, str]] = {
    # Social (LinkedIn/Slack removed from SI v16 — trademark)
    "siGithub": ("github", "social"),
    "siX": ("x", "social"),
    "siDiscord": ("discord", "social"),
    "siYoutube": ("youtube", "social"),
    "siSpotify": ("spotify", "social"),
    "siInstagram": ("instagram", "social"),
    "siTiktok": ("tiktok", "social"),
    "siReddit": ("reddit", "social"),
    "siMastodon": ("mastodon", "social"),
    "siBluesky": ("bluesky", "social"),
    # Dev
    "siPython": ("python", "dev"),
    "siNpm": ("npm", "dev"),
    "siDocker": ("docker", "dev"),
    "siRust": ("rust", "dev"),
    "siGo": ("go", "dev"),
    "siTypescript": ("typescript", "dev"),
    "siJavascript": ("javascript", "dev"),
    "siReact": ("react", "dev"),
    "siVuedotjs": ("vue", "dev"),
    "siSvelte": ("svelte", "dev"),
    "siNextdotjs": ("nextjs", "dev"),
    "siNodedotjs": ("nodejs", "dev"),
    "siDeno": ("deno", "dev"),
    "siSwift": ("swift", "dev"),
    "siKotlin": ("kotlin", "dev"),
    "siCplusplus": ("cplusplus", "dev"),
    "siRuby": ("ruby", "dev"),
    "siPhp": ("php", "dev"),
    "siElixir": ("elixir", "dev"),
    "siZig": ("zig", "dev"),
    # Platforms (AWS/Azure/Heroku removed from SI v16 — trademark)
    "siPypi": ("pypi", "platforms"),
    "siHuggingface": ("huggingface", "platforms"),
    "siArxiv": ("arxiv", "platforms"),
    "siKaggle": ("kaggle", "platforms"),
    "siVercel": ("vercel", "platforms"),
    "siNetlify": ("netlify", "platforms"),
    "siCloudflare": ("cloudflare", "platforms"),
    "siGooglecloud": ("googlecloud", "platforms"),
    "siDigitalocean": ("digitalocean", "platforms"),
    "siSupabase": ("supabase", "platforms"),
    "siFirebase": ("firebase", "platforms"),
    "siGithubactions": ("githubactions", "platforms"),
    "siGitlab": ("gitlab", "platforms"),
    "siBitbucket": ("bitbucket", "platforms"),
    # Tools (VS Code removed from SI v16 — trademark)
    "siNeovim": ("neovim", "tools"),
    "siFigma": ("figma", "tools"),
    "siNotion": ("notion", "tools"),
    "siObsidian": ("obsidian", "tools"),
    "siLinear": ("linear", "tools"),
    "siPostman": ("postman", "tools"),
    "siGrafana": ("grafana", "tools"),
    "siPrometheus": ("prometheus", "tools"),
    "siJetbrains": ("jetbrains", "tools"),
    "siSublimetext": ("sublimetext", "tools"),
    "siStorybook": ("storybook", "tools"),
    "siEslint": ("eslint", "tools"),
    "siPrettier": ("prettier", "tools"),
    # AI / ML (OpenAI removed from SI v16 — trademark)
    "siAnthropic": ("anthropic", "ai"),
    "siTensorflow": ("tensorflow", "ai"),
    "siPytorch": ("pytorch", "ai"),
    "siJupyter": ("jupyter", "ai"),
    "siApachespark": ("spark", "ai"),
    "siGithubcopilot": ("githubcopilot", "ai"),
    # Infrastructure (AWS/Azure/Heroku removed from SI v16 — trademark)
    "siKubernetes": ("kubernetes", "infra"),
    "siTerraform": ("terraform", "infra"),
    "siNginx": ("nginx", "infra"),
    "siRedis": ("redis", "infra"),
    "siPostgresql": ("postgresql", "infra"),
    "siMongodb": ("mongodb", "infra"),
    "siElasticsearch": ("elasticsearch", "infra"),
    "siApachekafka": ("kafka", "infra"),
    "siRabbitmq": ("rabbitmq", "infra"),
    "siGnubash": ("bash", "infra"),
    "siGit": ("git", "infra"),
    # Web / Frameworks
    "siTailwindcss": ("tailwindcss", "dev"),
    "siVite": ("vite", "dev"),
    "siBun": ("bun", "dev"),
    "siPnpm": ("pnpm", "dev"),
    "siAstro": ("astro", "dev"),
    "siRemix": ("remix", "dev"),
    "siFlutter": ("flutter", "dev"),
    "siDart": ("dart", "dev"),
    "siHtml5": ("html5", "dev"),
    "siSass": ("sass", "dev"),
    "siMarkdown": ("markdown", "dev"),
    # Mobile / OS
    "siAndroid": ("android", "platforms"),
    "siApple": ("apple", "platforms"),
    "siLinux": ("linux", "platforms"),
    # Commerce / Services
    "siStripe": ("stripe", "platforms"),
    "siShopify": ("shopify", "platforms"),
    "siAuth0": ("auth0", "platforms"),
}

# Geometric shapes (hand-authored, not from Simple Icons)
# Defined in 640x640 viewBox per PRD SS10
GEOMETRIC_SHAPES: dict[str, dict[str, str | None]] = {
    "triangle": {
        "path": "M320 53.3 586.6 533.3H53.4Z",
        "viewBox": "0 0 640 640",
        "brand_color": None,
        "category": "geometric",
    },
    "diamond": {
        "path": "M320 53.3 506.7 320 320 586.7 133.3 320Z",
        "viewBox": "0 0 640 640",
        "brand_color": None,
        "category": "geometric",
    },
    "hexagon": {
        "path": "M320 53.3 566.4 186.7V453.3L320 586.7 73.6 453.3V186.7Z",
        "viewBox": "0 0 640 640",
        "brand_color": None,
        "category": "geometric",
    },
    "shield": {
        "path": "M320 53.3 533.3 186.7V373.3C533.3 480 320 586.7 320 586.7S106.7 480 106.7 373.3V186.7Z",
        "viewBox": "0 0 640 640",
        "brand_color": None,
        "category": "geometric",
    },
    "circle": {
        "path": "M320 106.7A213.3 213.3 0 11106.7 320 213.3 213.3 0 01320 106.7Z",
        "viewBox": "0 0 640 640",
        "brand_color": None,
        "category": "geometric",
    },
    "star": {
        "path": (
            "M320 53.3 396.4 237.8 586.7 253.3 440 381.5 483.3 566.7"
            " 320 471.1 156.7 566.7 200 381.5 53.3 253.3 243.6 237.8Z"
        ),
        "viewBox": "0 0 640 640",
        "brand_color": None,
        "category": "geometric",
    },
}


def extract_from_npm() -> dict[str, dict[str, object]]:
    """Extract icons from the simple-icons npm package via Node.js subprocess.

    Uses `node -e` to require simple-icons, extract all curated paths,
    and return JSON to stdout. This avoids parsing JS manually.
    """
    # Build the Node.js extraction script
    icon_keys = list(CURATED_ICONS.keys())
    icon_keys_json = json.dumps(icon_keys)
    slugs_json = json.dumps({k: v[0] for k, v in CURATED_ICONS.items()})
    cats_json = json.dumps({k: v[1] for k, v in CURATED_ICONS.items()})

    node_script = f"""
    const si = require('simple-icons');
    const keys = {icon_keys_json};
    const slugs = {slugs_json};
    const cats = {cats_json};
    const result = {{}};
    for (const key of keys) {{
        const icon = si[key];
        if (!icon) {{
            process.stderr.write('WARN: ' + key + ' not found in simple-icons\\n');
            continue;
        }}
        result[slugs[key]] = {{
            path: icon.path,
            viewBox: '0 0 24 24',
            brand_color: '#' + icon.hex,
            category: cats[key],
        }};
    }}
    process.stdout.write(JSON.stringify(result));
    """

    try:
        proc = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            print(f"Node.js extraction failed: {proc.stderr}", file=sys.stderr)
            return {}
        if proc.stderr:
            # Print warnings (missing icons)
            for line in proc.stderr.strip().splitlines():
                print(line, file=sys.stderr)

        return json.loads(proc.stdout)

    except FileNotFoundError:
        print("Node.js not found. Install Node.js to extract Simple Icons.", file=sys.stderr)
        return {}
    except subprocess.TimeoutExpired:
        print("Node.js extraction timed out.", file=sys.stderr)
        return {}
    except json.JSONDecodeError as e:
        print(f"Invalid JSON from Node.js: {e}", file=sys.stderr)
        return {}


def main() -> None:
    """Run glyph extraction and write data/glyphs.json."""
    output_path = Path(__file__).resolve().parent.parent / "src" / "hyperweave" / "data" / "glyphs.json"

    # Extract from npm (via Node subprocess)
    glyphs = extract_from_npm()

    if not glyphs:
        print("No SI icons extracted. Check that simple-icons is installed.", file=sys.stderr)
        print("Run: npm install simple-icons", file=sys.stderr)
        sys.exit(1)

    # Add geometric shapes (always)
    for glyph_id, definition in GEOMETRIC_SHAPES.items():
        glyphs[glyph_id] = definition  # type: ignore[assignment]

    # Sort by category then name for readability
    sorted_glyphs = dict(
        sorted(
            glyphs.items(),
            key=lambda x: (x[1].get("category", "zzz"), x[0]),
        )
    )

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(sorted_glyphs, f, indent=2)
        f.write("\n")

    # Summary
    by_cat: dict[str, int] = {}
    for v in sorted_glyphs.values():
        cat = v.get("category", "unknown")
        by_cat[cat] = by_cat.get(cat, 0) + 1

    print(f"Wrote {len(sorted_glyphs)} glyphs to {output_path}")
    for cat, count in sorted(by_cat.items()):
        print(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
