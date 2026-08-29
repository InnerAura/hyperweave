default:
    @just --list


# ──────────────────────────────
# Quality Gates
# ──────────────────────────────

qa: lint typecheck test

# Both, always: a format-only failure has pushed red twice.
lint:
    uv run ruff check .
    uv run ruff format --check .

fmt:
    uv run ruff format .
    uv run ruff check --fix .

typecheck:
    uv run mypy src/hyperweave/ --strict

test *ARGS:
    uv run pytest -n auto --cov=hyperweave --cov-report=term-missing {{ARGS}}

test-debug *ARGS:
    uv run pytest -x -vvs {{ARGS}}

snapshots:
    uv run pytest tests/ -k snapshot --snapshot-update


# ──────────────────────────────
# Smoke
# ──────────────────────────────

smoke:
    uv run hyperweave compose badge "build" "passing" --genome brutalist

smoke-receipt:
    uv run hyperweave compose receipt tests/fixtures/session.jsonl -o /tmp/hw-smoke-receipt.svg

# Every frame against every genome; prints only the pairs that fail.
proof-set:
    #!/usr/bin/env bash
    for genome in $(uv run hyperweave genomes list --ids-only); do
        for frame in badge strip icon divider marquee; do
            uv run hyperweave compose $frame "test" "value" --genome $genome > /dev/null || echo "FAIL: $genome/$frame"
        done
    done


# ──────────────────────────────
# Galleries
# ──────────────────────────────

# Renders each artifact through compose, CLI, HTTP and MCP and requires
# byte-agreement. `just proofset direct` skips the three witnesses.
proofset SURFACES="all":
    uv run python -m scripts.examples --surfaces {{SURFACES}}

# Ends with the law sweep over every render - exits non-zero on a violation.
diagrams TARGET="all":
    uv run python -m scripts.examples.diagrams {{TARGET}}

# Rebuilds the tabbed page from the family documents on disk - no re-render.
topology-viewer:
    uv run python -m scripts.examples.topologies.viewer

# not committed (wip)
# `just kit check` checks the plates only; `just kit html` skips the checks.
kit TARGET="all":
    uv run python -m scripts.kit {{TARGET}}

surface-matrix:
    uv run python scripts/examples/surface_matrix.py


# ──────────────────────────────
# Glyph Registry
# ──────────────────────────────

extract-glyphs:
    uv run python scripts/glyphs/extract.py

fetch-core-glyphs:
    uv run python scripts/glyphs/fetch.py

# Run after any registry rebuild. Needs Playwright.
glyph-audit:
    uv run python scripts/glyphs/audit.py


# ──────────────────────────────
# Examples
# ──────────────────────────────

# Renders from real local transcripts, skipping loudly if none are found.
# `--mock` is dev-only synthetic data and must never be committed.
refresh-examples *ARGS:
    uv run python scripts/examples/refresh.py {{ARGS}}


# ──────────────────────────────
# App & Site
# ──────────────────────────────

serve:
    uv run hyperweave serve --port 8000 --reload

# not committed (wip)
registry OUT="apps/hw-app/public/registry":
    uv run python -m scripts.registry --out {{OUT}}

# not committed (wip)
# Indexes and glyphs only — skips the ~28MB render copy.
registry-fast OUT="apps/hw-app/public/registry":
    uv run python -m scripts.registry --out {{OUT}} --no-renders


# ──────────────────────────────
# Release
# ──────────────────────────────

build:
    uv build

version-refresh:
    uv pip install -e . --force-reinstall --no-deps --quiet
    @uv run python -c "import hyperweave; print(f'_version.py refreshed to {hyperweave.__version__}')"

# ANNOTATED, never lightweight — a lightweight tag breaks --follow-tags.
tag VERSION MESSAGE:
    #!/usr/bin/env bash
    set -euo pipefail
    VER="{{VERSION}}"
    [[ "$VER" == v* ]] || VER="v$VER"
    git tag -a "$VER" -m "{{MESSAGE}}"
    just version-refresh
    echo ""
    echo "Tagged $VER. Push with: git push --follow-tags"
