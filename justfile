default:
    @just --list


# -------------
# Quality Gates
# -------------

qa: lint typecheck test

# Exactly what CI installs — the lockfile, nothing resolved fresh.
install:
    uv sync --locked --group dev

lint:
    uv run ruff check .
    uv run ruff format --check .

fmt:
    uv run ruff format .
    uv run ruff check --fix .

typecheck:
    uv run ty check

test *ARGS:
    PYTHONDONTWRITEBYTECODE=1 uv run pytest -n auto --cov=hyperweave --cov-report=term-missing {{ARGS}}

# log_cli is opt-in HERE only: Click's CliRunner (via typer.testing) swaps
# sys.stdout, and a live-logging handler outliving that swap breaks every CLI
# test with "I/O operation on closed file". Never set it globally.
test-debug *ARGS:
    uv run pytest -x -vvs -o log_cli=true -o log_level=INFO {{ARGS}}

# Fast local loop: reruns only tests touched since main. -n0 overrides the
# -n=auto in addopts so it really is one process. The FIRST run is a slow serial
# bootstrap that traces coverage into .fastest.coverage (gitignored, ~8MB, holds
# absolute local paths); later runs are the fast ones.
test-fast *ARGS:
    uv run pytest -n0 --fastest-mode=skip --fastest-commit=main {{ARGS}}

snapshots:
    uv run pytest tests/ -k snapshot --snapshot-update


# -------------
# Smoke
# -------------

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


# -------------
# Examples
# -------------

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

# Renders from real local transcripts, skipping loudly if none are found.
# `--mock` is dev-only synthetic data and must never be committed.
refresh-examples *ARGS:
    uv run python scripts/examples/refresh.py {{ARGS}}


# -------------
# Glyphs
# -------------

extract-glyphs:
    uv run python scripts/glyphs/extract.py

fetch-core-glyphs:
    uv run python scripts/glyphs/fetch.py

# Run after any registry rebuild. Needs Playwright.
glyph-audit:
    uv run python scripts/glyphs/audit.py


# -------------
# App
# -------------

serve:
    uv run hyperweave serve --port 8000 --reload

# not committed (wip)
registry OUT="apps/hw-app/public/registry":
    uv run python -m scripts.registry --out {{OUT}}

# not committed (wip)
# Indexes and glyphs only — skips the ~28MB render copy.
registry-fast OUT="apps/hw-app/public/registry":
    uv run python -m scripts.registry --out {{OUT}} --no-renders

# not committed (wip)
# http://localhost:5273 — NOT 3000, which another local tool holds.
app:
    cd apps/hw-app && bun run dev

# not committed (wip)
# Compile the registry, then start the app. Use after any diagram change.
app-fresh: registry app

# not committed (wip)
# The app's own gate: biome, tsc --noEmit, vitest.
app-gate:
    cd apps/hw-app && bun run gate

# not committed (wip)
app-build:
    cd apps/hw-app && bun run build


# -------------
# Release
# -------------

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
