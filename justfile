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

serve:
    uv run hyperweave serve --port 8000 --reload

extract-glyphs:
    uv run python scripts/extract_glyphs.py

fetch-core-glyphs:
    uv run python scripts/fetch_core_glyphs.py

# Run after any glyph registry rebuild: renders every entry in headless
# Chromium and asserts the geometry stays inside its viewBox (needs Playwright).
glyph-audit:
    uv run python scripts/glyph_audit.py

# Re-render the committed telemetry example receipts (assets/examples/telemetry/).
# Default renders from real local transcripts (skips loudly if none found);
# `--mock` is dev-only synthetic data and must never be committed.
refresh-examples *ARGS:
    uv run python scripts/refresh_examples.py {{ARGS}}


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
