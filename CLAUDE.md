# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

CV Radar is a private-first computer-vision technology radar. The goal is **not** to summarize everything — it is to decide what is worth attention.

Use the radar rings: `Use`, `Prototype`, `Evaluate`, `Watch`, `Ignore`.

Do not promote items based only on famous authors, famous labs, social attention, or large claims. Prefer practical relevance to: calibration, target detection, 3D geometry, 3D sensors, robot guidance, industrial vision inspection, object tracking, edge AI deployment, open-source CV tooling, sensors/cameras/standards, synthetic data, datasets/benchmarks.

When curating:

1. Read generated candidate queues.
2. Keep daily digest short.
3. Update radar state only when there is meaningful evidence.
4. Explicitly mark uncertainty.
5. Put speculative items into Watch, not Evaluate.
6. Put implementation-worthy items into Prototype only if there is code, data, or a clear test path.
7. Never automatically publish public content.

## Common Commands

Dependency sync and validation (run before finishing any code change):

```bash
uv sync --locked --all-groups
uv run pytest
uv run ruff check .
uv run ruff format . --check
```

Run a single test file or test:

```bash
uv run pytest tests/test_classification.py
uv run pytest tests/test_classification.py::test_name -q
```

Auto-format:

```bash
uv run ruff format .
```

End-to-end local pipeline:

```bash
uv run radar init-db
uv run radar fetch-arxiv --days 1 --max-results 100
uv run radar classify --date today
uv run radar candidates --date today
uv run radar score-debug --date today
# Curate via the cv-radar-curator skill, filling TODO blocks in the candidate Markdown.
uv run radar apply reports/candidates/YYYY-MM-DD.md --dry-run
uv run radar apply reports/candidates/YYYY-MM-DD.md
uv run radar digest --date today
# Or for individual decisions:
uv run radar decide ITEM_ID --ring Watch --reason "..." --action "..."
uv run radar decisions --date today
```

`radar apply` is the bulk-decision bridge: the curator fills `### Claude decision` blocks
in the candidate Markdown with a small YAML payload (`ring`, `tracks`, `reason`, `action`,
`uncertain`), and `apply` parses + records them in a single transaction.
`radar digest` writes a short Markdown summary sectioned by ring. See [docs/daily-workflow.md](docs/daily-workflow.md).

Use `--date today` for the current local date, or an ISO date like `2026-05-07`. Every CLI command accepts `--db-path` and `--config-dir` overrides; the smoke-test recipe in [docs/skill-workflows.md](docs/skill-workflows.md) uses `.tmp-real-run/` for an isolated run.

## Architecture

The pipeline is a linear flow over a single SQLite database. The CLI (`radar/cli.py`) is the only entry point; each command is a thin wrapper that wires a config + session into one module.

Stages, with the module that owns each:

1. **Configuration** (`radar/config.py`, `radar/schemas.py`) — `config/*.yaml` is loaded into a single Pydantic `AppConfig` (sources, topics, negative_topics, priority_sources, scoring, embeddings). Schemas enforce invariants like descending ring thresholds and unique source/track ids. Treat `AppConfig` as immutable; do not mutate it inside pipeline stages.
2. **Ingestion** (`radar/collectors/`) — currently only `arxiv.py`. Collectors normalize external entries into `NormalizedItem` and persist both a `RawItem` (raw payload) and an `Item` (canonical record). RSS/vendor sources are planned in `config/sources.yaml` but not yet implemented.
3. **Classification** (`radar/filters/keyword_filter.py`) — deterministic keyword matching against `topics.yaml` tracks, with negative-topic penalties from `negative_topics.yaml`. Produces a `ClassificationResult`, upserted into `item_classifications` (unique per item).
4. **Scoring** (`radar/scoring/score_item.py`) — combines relevance, source priority, implementation signal, novelty, and negative penalty using weights from `scoring.yaml`, clamped to `[0, 100]`. `recommended_ring` maps the final score to a `RadarRing` via thresholds. Attention scoring is currently a stub (0.0).
5. **Reporting** (`radar/reports/`) — `candidate_queue.py` writes the human-review Markdown + a JSON debug export; `score_debug.py` exposes per-component scores via the CLI.
6. **Decisions** (`radar/decisions.py`) — durable curator decisions written to `radar_decisions`. Decisions are independent of classifications: a decision can override the suggested ring, and classifications can be re-run without touching decisions.
7. **Enrichers** (`radar/enrichers/ollama.py`) — optional Ollama embeddings, disabled in `embeddings.yaml` by default. Keep the deterministic path the default; do not introduce Ollama as a hard dependency.

Persistence (`radar/db.py`, `radar/models.py`) is SQLAlchemy 2.x with SQLite. The schema separates `raw_items` (source-of-truth payload) from `items` (normalized) so collectors can be re-run without losing classifications or decisions. `Item.normalized_title` is used for cross-source dedup; collectors should set it via `normalize_title()` in `radar/utils.py`. Sessions are scoped via `session_scope()` — always commit or rollback through the context manager.

Date handling: all timestamps are timezone-aware UTC (`utc_now()`); `parse_date_arg()` and `date_bounds()` in `radar/utils.py` convert CLI date strings to UTC day windows used by every "by date" query.

## Adding New Capabilities

- **New source kind**: extend `SourceConfig.kind` literal in `radar/schemas.py`, add a collector module under `radar/collectors/`, wire it into `radar/cli.py` alongside `fetch-arxiv`. Normalize into `NormalizedItem` and reuse `store_normalized_item()` so the dedup + raw-payload contract holds.
- **New radar track**: edit `config/topics.yaml` only; classification picks it up. Add a regression test in `tests/test_classification.py` covering at least one known false positive.
- **Scoring change**: never broaden a formula without a regression test that pins the old vs. new behavior on a concrete item. Use `uv run radar score-debug` to inspect component scores before/after.
- **New CLI command**: add to `radar/cli.py`, mirror the `_load(config_dir)` + `session_scope()` pattern; keep CLI commands thin (config load + session + one call into a domain module).

## Delegating Implementation Work

Reserve the main conversation's context for planning, integration, and verification.
Delegate routine implementation to subagents whenever the work is bounded enough that
a self-contained brief can replace a chat back-and-forth — especially when:

- a new module, package, or directory needs to be scaffolded from scratch
  (e.g. `radar/api/`, `frontend/`, a new collector under `radar/collectors/`),
- a change spans many files with predictable structure (e.g. adding a CLI command +
  its module + its tests + its docs),
- there is heavy file content to read that is incidental to the decision (dependency
  trees, generated bundles, large fixtures).

Brief subagents like a colleague who has not seen the conversation: paste the API
contract, the design tokens, the exact file paths to touch, the verification
commands, and the explicit instruction *not to commit* (commits and PRs are the
main agent's responsibility). When two halves are disjoint (e.g. backend API vs.
frontend app under separate directories) launch them in parallel.

Do **not** delegate: design decisions, cross-cutting refactors, anything that
requires understanding the conversation history, or the final verification +
commit + PR sequence. Trust-but-verify: subagents report what they intended to do,
not necessarily what they did — always re-run the tests and review the diff yourself
before committing.

## Before Finishing Any Change

- If code changed: `uv run pytest`, `uv run ruff check .`, `uv run ruff format . --check`.
- If a config or scoring weight changed: re-run the candidate pipeline on a real date to confirm the candidate Markdown still parses and JSON export is valid.
- Generated runtime artifacts (`data/radar.sqlite`, `reports/candidates/YYYY-MM-DD.md`, `data/exports/candidates/YYYY-MM-DD.json`, `.tmp-real-run/`) are gitignored — commit only fixture/example files under `reports/examples/` and `data/exports/examples/`.

## Related Docs

- [README.md](README.md) — user-facing overview and quickstart.
- [docs/daily-workflow.md](docs/daily-workflow.md) — the 5-minute daily ritual: candidate queue → curator skill → `apply` → `digest`.
- [docs/roadmap.md](docs/roadmap.md) — phase plan (currently Phase 2.5 signal calibration).
- [docs/skills.md](docs/skills.md), [docs/skill-workflows.md](docs/skill-workflows.md) — project-specific Codex skills (`cv-radar-curator`, `cv-radar-scoring-evaluator`, `cv-radar-source-onboarding`, `cv-radar-digest-writer`, `cv-radar-atlas-bridge`) and how to drive them.
- [docs/tasks.md](docs/tasks.md), [docs/handoff.md](docs/handoff.md) — active work items and handoff notes.
