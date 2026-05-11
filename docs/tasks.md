# CV Radar Development Tasks

Tasks are grouped by implementation order. Completed items document the current baseline;
open items are meant to be small enough to turn into GitHub issues.

## Completed

- [x] Create Python package skeleton with `uv`, Typer, SQLAlchemy, Pydantic, Ruff, and pytest.
- [x] Add SQLite schema for sources, raw items, normalized items, classifications,
      decisions, and digests.
- [x] Add config validation for sources, topics, negative topics, source priorities,
      scoring, and embeddings.
- [x] Implement arXiv `cs.CV` fetch, normalization, raw storage, and dedupe.
- [x] Implement deterministic keyword classification and scoring.
- [x] Generate candidate Markdown and JSON debug exports.
- [x] Add disabled-by-default Ollama embedding client with mocked tests.
- [x] Add CI, Dependabot, PR template, README, and committed examples.
- [x] Run a real 100-paper arXiv smoke test.
- [x] Fix substring keyword false positives from the real run.
- [x] Include top nonzero scored items in candidate queues, even when the suggested
      ring is `Ignore`, so early scoring can be tuned from real examples.
- [x] Add `radar decide` to record ring, tracks, decision reason, and action in SQLite.
- [x] Add `radar decisions` to list persisted decisions for a date.
- [x] Add `radar score-debug --date YYYY-MM-DD` to inspect score components and keyword matches.

## Immediate Tasks

- [ ] Add candidate queue parsing or a separate review input format so Markdown TODOs
      are not the only review surface.
- [ ] Add regression fixtures for the first real false positives:
      event-camera tracking, generic video editing, broad multimodal benchmarks,
      vehicle re-identification, and crop disease edge-AI papers.
- [ ] Add an evaluation command that compares scored candidates against a labeled YAML
      or JSON review set.
- [ ] Decide whether `Watch` should mean "review queue item" or "visible radar item";
      right now the queue is broader than the final radar view, which is useful but
      should be explicit in naming.

## RSS And Source Tasks

- [ ] Extend `sources.yaml` with a small RSS pilot set.
- [ ] Implement `radar fetch-rss`.
- [ ] Normalize RSS entries into `items` with type detection for blog posts, vendor news,
      and library releases.
- [ ] Add feed failure reporting and source-level fetch stats.
- [ ] Add tests for malformed feeds, missing dates, duplicate links, and source priority.

## Curation And Reporting Tasks

- [ ] Generate daily digest drafts from accepted decisions.
- [ ] Add persistent track note templates under `radar_state/tracks/`.
- [ ] Add `radar daily --date YYYY-MM-DD` once decisions and digest generation exist.
- [ ] Add weekly synthesis after at least several daily digests exist.
- [ ] Keep Atlas/public candidates separate from private radar decisions.

## Export And UI Tasks

- [ ] Define `data/exports/latest.json` as the stable UI contract.
- [ ] Generate historical export files by date.
- [ ] Build the Vite/React dashboard after signal calibration.
- [ ] Add dashboard, radar board, track page, candidate queue, and digest views.
- [ ] Verify the UI with real exports and Playwright screenshots.

## Local LLM Tasks

- [ ] Add optional embedding storage schema only after the scoring evaluation command exists.
- [ ] Compare deterministic scoring against embedding-assisted ranking on labeled examples.
- [ ] Add an Ollama chat summarizer only after a local chat model is installed.
- [ ] Keep all local inference disabled by default.

## Repo Hygiene Tasks

- [ ] Add issue templates once the first task batch is turned into GitHub issues.
- [ ] Add `CONTRIBUTING.md` only if the repository becomes more than personal-first.
- [ ] Add release notes once there is a user-facing versioned CLI.
