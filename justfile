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
    uv run hyperweave compose badge "build" "passing" --genome brutalist-emerald

smoke-receipt:
    uv run hyperweave render --template receipt --data tests/fixtures/session.json

proof-set:
    #!/usr/bin/env bash
    for genome in $(uv run hyperweave genomes list --ids-only); do
        for frame in badge strip banner icon divider marquee-horizontal marquee-vertical marquee-counter; do
            uv run hyperweave compose $frame "test" "value" --genome $genome > /dev/null || echo "FAIL: $genome/$frame"
        done
    done

serve:
    uv run hyperweave serve --port 8000 --reload

extract-glyphs:
    uv run python scripts/extract_glyphs.py

docs:
    cd docs && mintlify dev

build:
    uv build
