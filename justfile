default:
    @just --list

qa: lint typecheck test

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

smoke:
    uv run hyperweave compose badge "build" "passing" --genome brutalist

smoke-receipt:
    uv run hyperweave compose receipt tests/fixtures/session.jsonl -o /tmp/hw-smoke-receipt.svg

proof-set:
    #!/usr/bin/env bash
    for genome in $(uv run hyperweave genomes list --ids-only); do
        for frame in badge strip icon divider marquee; do
            uv run hyperweave compose $frame "test" "value" --genome $genome > /dev/null || echo "FAIL: $genome/$frame"
        done
    done

# Build the visual acceptance surface under outputs/ — the genome and matrix
# galleries plus the cross-genome documents. Every gallery artifact is rendered
# through direct compose, the CLI, HTTP and MCP and must agree byte-for-byte;
# `just proofset direct` skips the three witnesses while iterating on content.
proofset SURFACES="all":
    uv run python -m scripts.examples --surfaces {{SURFACES}}

# The diagram galleries: one exhibit directory per topology family, the
# specimen board, the primer-language sweep, the card+label slots. Ends with the
# law sweep over every render — exits non-zero on a violation.
diagrams TARGET="all":
    uv run python -m scripts.examples.diagrams {{TARGET}}

# The Surface Modes cross-product (plate/inlay/twin x every primer variant).
surface-matrix:
    uv run python scripts/examples/surface_matrix.py

serve:
    uv run hyperweave serve --port 8000 --reload

extract-glyphs:
    uv run python scripts/glyphs/extract.py

fetch-core-glyphs:
    uv run python scripts/glyphs/fetch.py

# Run after any glyph registry rebuild: renders every entry in headless
# Chromium and asserts the geometry stays inside its viewBox (needs Playwright).
glyph-audit:
    uv run python scripts/glyphs/audit.py

# Re-render the committed telemetry example receipts (assets/examples/telemetry/).
# Default renders from real local transcripts (skips loudly if none found);
# `--mock` is dev-only synthetic data and must never be committed.
refresh-examples *ARGS:
    uv run python scripts/examples/refresh.py {{ARGS}}

build:
    uv build

version-refresh:
    uv pip install -e . --force-reinstall --no-deps --quiet
    @uv run python -c "import hyperweave; print(f'_version.py refreshed to {hyperweave.__version__}')"

tag VERSION MESSAGE:
    #!/usr/bin/env bash
    set -euo pipefail
    VER="{{VERSION}}"
    [[ "$VER" == v* ]] || VER="v$VER"
    git tag -a "$VER" -m "{{MESSAGE}}"
    just version-refresh
    echo ""
    echo "Tagged $VER. Push with: git push --follow-tags"
