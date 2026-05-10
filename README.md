# CV Radar

[![CI](https://github.com/VitalyVorobyev/cv-tech-radar/actions/workflows/ci.yml/badge.svg)](https://github.com/VitalyVorobyev/cv-tech-radar/actions/workflows/ci.yml)

Personal-first computer-vision technology radar.

CV Radar is a private-first signal detector for computer vision work: arXiv papers,
industrial vision sources, tooling, sensors, calibration, 3D geometry, robot guidance,
and practical deployment topics. It is not a generic AI news summarizer.

The current implementation is the Phase 1-2 backend slice:

- SQLite is the canonical state.
- arXiv `cs.CV` ingestion is implemented.
- Deterministic keyword scoring classifies items into radar tracks and rings.
- Candidate Markdown and JSON exports are generated for human/Claude review.
- Optional Ollama embedding plumbing exists, disabled by default.

## Quick Start

Install dependencies and run the checks:

```bash
uv sync --locked --all-groups
uv run pytest
uv run ruff check .
uv run ruff format . --check
```

Initialize the local database:

```bash
uv run radar init-db
```

Fetch recent arXiv entries, classify them, and generate a candidate queue:

```bash
uv run radar fetch-arxiv --days 1
uv run radar classify --date today
uv run radar candidates --date today
```

Generated outputs are written to:

- `data/radar.sqlite`
- `reports/candidates/YYYY-MM-DD.md`
- `data/exports/candidates/YYYY-MM-DD.json`

These runtime artifacts are intentionally ignored by git. Committed examples live under
`reports/examples/` and `data/exports/examples/`.

## CLI

```bash
uv run radar --help
uv run radar init-db
uv run radar fetch-arxiv --days 1 --max-results 100
uv run radar classify --date YYYY-MM-DD
uv run radar candidates --date YYYY-MM-DD
```

Use `--date today` for the current local date.

## Configuration

Configuration lives in `config/`:

- `sources.yaml` enables arXiv `cs.CV` for the first ingestion loop.
- `topics.yaml` defines radar tracks and keyword matches.
- `negative_topics.yaml` reduces scores for known noise areas.
- `priority_sources.yaml` adds capped, weak source boosts.
- `scoring.yaml` defines weights, thresholds, and candidate limits.
- `embeddings.yaml` keeps Ollama embeddings disabled by default.

## Development

This repository uses:

- Python `>=3.12`
- `uv` for dependency management
- SQLAlchemy + SQLite for persistence
- Pydantic for schemas and config validation
- Typer for the CLI
- Ruff and pytest for quality gates

CI runs on pull requests and pushes to `main` across Python `3.12` and `3.13`.
The workflow uses read-only repository permissions, dependency caching through
`astral-sh/setup-uv`, locked dependency sync, formatting checks, linting, and tests.

## What Works Now

You can already run the complete local Phase 1-2 loop:

1. Initialize SQLite.
2. Fetch recent `cs.CV` arXiv papers.
3. Classify papers into configured tracks.
4. Generate a top-25 candidate review queue.

If arXiv has no papers inside the requested date window, the commands still complete and
produce an empty candidate queue. Use a wider `--days` value for a visible demo.

## Next Steps

1. Tune the scoring thresholds against a few real candidate queues.
2. Add RSS/vendor ingestion for high-signal industrial vision sources.
3. Add explicit curation decisions and daily digest generation.
4. Stabilize the JSON export shape for the future React dashboard.
5. Build the static local dashboard once the backend signal quality is acceptable.
