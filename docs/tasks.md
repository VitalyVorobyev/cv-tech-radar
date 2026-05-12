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
- [x] Add `radar eval --date YYYY-MM-DD` comparing the candidate queue against a labeled
      YAML set at `tests/fixtures/labeled_items.yaml`, with precision, recall, per-class
      false-positive counts, and missing-relevant-id reporting.

## Immediate Tasks

- [ ] Add candidate queue parsing or a separate review input format so Markdown TODOs
      are not the only review surface.
- [ ] Grow `tests/fixtures/labeled_items.yaml` past the initial 2026-05-08 seed
      (1 relevant / 5 borderline / 19 noise) so the eval reflects more than one day.
- [ ] Tune topics.yaml, negative_topics.yaml, and scoring.yaml to lift `radar eval`
      precision above the current 0.05 baseline on the seeded set. Dominant noise classes:
      `broad_vlm` (8), `generative_editing` (2), `medical_imaging` (2), `out_of_domain_3d` (2).
      Re-run `radar eval --date 2026-05-08` after each change to track movement.
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

Eval harness now exists (`radar eval`), so these tasks have a measurable gate.
Honest priority order:

- [x] Add `ItemEmbedding` model + `radar embed --date YYYY-MM-DD` populating it via
      the existing `OllamaEmbeddingClient`. `(item_id, model)` is unique so the
      command is idempotent and can be re-run safely; `embeddings.enabled` stays
      `false` by default (no auto-embedding from other commands).
- [x] Add `radar near-duplicates --days 14 [--threshold X]` reporting cosine
      groupings above `embeddings.near_duplicate_threshold` (default 0.92). Does
      not feed into `final_score`.
- [ ] Pick the actual `near_duplicate_threshold` value by hand on the on-disk
      candidate runs once embeddings are populated.
- [x] Add `OllamaChatClient` (`radar/enrichers/ollama_chat.py`) and a `chat:` stanza
      in `config/embeddings.yaml` for `gemma4:e2b`. Default `enabled: false`.
- [x] Add `radar relevance-check --date today` writing per-item LLM yes/no judgments
      into the new `item_llm_judgments` table. Shadow only: judgments never affect
      the candidate queue. Idempotent on `(item_id, model)`; per-item exceptions
      are caught so a single LLM hiccup never breaks the run.
- [ ] Run shadow mode for ~5 days on real candidates; then extend `radar eval`
      with `--with-llm` to compute hypothetical precision/recall if we used the
      LLM as a filter on top of the deterministic classifier.
- [ ] Add a "filter" mode that demotes confidently-`no` items to Watch in the
      candidate queue, AND surface them in a separate "LLM-rejected" section of
      the candidate Markdown so the curator can audit. Ship only after the eval
      shows ≥0.9 noise-class rejection precision and ≈1.0 relevant-class
      acceptance recall.
- [ ] Keep all local inference disabled by default; the pipeline must run end-to-end
      with Ollama stopped.

Explicitly deferred (re-evaluate when the above lands):

- LLM-written digest narrative.
- LLM-drafted per-card gloss in the queue UI.
- LLM-driven track reassignment.

## Repo Hygiene Tasks

- [ ] Add issue templates once the first task batch is turned into GitHub issues.
- [ ] Add `CONTRIBUTING.md` only if the repository becomes more than personal-first.
- [ ] Add release notes once there is a user-facing versioned CLI.
