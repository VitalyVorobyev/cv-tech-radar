# CV Radar Development Tasks

Completed items document the current baseline; open items are meant to be small
enough to turn into GitHub issues. Grouped by area.

## Completed

### Foundation

- [x] Python package skeleton with `uv`, Typer, SQLAlchemy, Pydantic, Ruff, pytest.
- [x] SQLite schema for sources, raw items, normalized items, classifications,
      decisions, and digests.
- [x] Config validation for sources, topics, negative topics, source priorities,
      scoring, and embeddings.
- [x] CI, Dependabot, PR template, README, and committed examples.

### Papers pipeline

- [x] arXiv `cs.CV` fetch, normalization, raw storage, and dedup.
- [x] Deterministic keyword classification and multi-component scoring.
- [x] Candidate queue Markdown and JSON debug exports.
- [x] Include top nonzero-scored items in candidate queues even when the
      suggested ring is `Ignore`, so early scoring can be tuned from real data.
- [x] `radar score-debug`, `radar decide`, `radar decisions`.
- [x] `radar apply` bulk-decision bridge — the curator fills YAML decision blocks.
- [x] `radar digest` ring-sectioned digest; `daily-fetch` / `daily-publish`.
- [x] `radar eval` — precision/recall, per-class false positives, and missing
      relevant ids against `tests/fixtures/labeled_items.yaml`.
- [x] Real 100-paper arXiv smoke test; substring keyword false-positive fixes.

### Local semantic assist

- [x] Ollama embedding client; `radar embed`; `item_embeddings` table
      (idempotent on `(item_id, model)`, disabled by default).
- [x] `radar near-duplicates` cosine grouping — does not feed `final_score`.
- [x] `OllamaChatClient` + `radar relevance-check` shadow-mode LLM judgments
      in `item_llm_judgments`; the candidate queue is untouched.

### UI

- [x] FastAPI HTTP API; React/Vite frontend.
- [x] Radar board, queue, timeline, tracks, digest, pipeline, score-debug,
      manual-add, and settings views.
- [x] Static export bundle (`radar build-static`).
- [x] Two-lane navigation — a Papers / Ecosystem lane switch, each lane with
      its own tab set.
- [x] `/api/content-dates` + date-grid landings for the Queue and Digest views.

### Ecosystem radar

- [x] `config/artifacts.yaml` inventory with schema validation.
- [x] GitHub/PyPI/crates/npm collectors; idempotent, first-seen-safe diff runner.
- [x] `Artifact` / `ArtifactRef` / `ArtifactState` / `ArtifactEvent` /
      `ArtifactDecision` schema; relevance/severity event filter.
- [x] `radar fetch-ecosystem`, `radar ecosystem`, `radar artifact-decide`.
- [x] Ecosystem API routes and ecosystem static-bundle files.
- [x] Folded into `daily-fetch`; digest `## Ecosystem` section.
- [x] Ecosystem UI lane: radar board, release feed, artifact table.

## Open tasks

### Signal calibration

- [ ] Grow `tests/fixtures/labeled_items.yaml` past the 2026-05-08 seed
      (1 relevant / 5 borderline / 19 noise) so the eval reflects more than one day.
- [ ] Tune `topics.yaml`, `negative_topics.yaml`, and `scoring.yaml` to lift
      `radar eval` precision above the 0.05 baseline. Dominant noise classes:
      `broad_vlm` (8), `generative_editing` (2), `medical_imaging` (2),
      `out_of_domain_3d` (2).
- [ ] Decide whether `Watch` means "review queue item" or "visible radar item";
      the queue is currently broader than the final radar view.

### RSS and vendor sources

- [ ] Extend `sources.yaml` with a small RSS pilot set.
- [ ] Implement `radar fetch-rss`; normalize RSS entries into `items` with type
      detection for blog posts, vendor news, and library releases.
- [ ] Add per-feed failure reporting and source-level fetch stats.
- [ ] Tests for malformed feeds, missing dates, duplicate links, source priority.

### Ecosystem radar follow-ups

- [ ] GitHub collector: fall back to the `/tags` API when a repo publishes no
      GitHub *Releases*, and add a per-ref tag/release prefix filter so
      monorepos select the right sub-package. Then re-add the 6 dropped
      `github` refs (candle, image, nalgebra, opencv-rust, tauri, vite).
- [ ] Calibrate ecosystem event volume; add a weekly synthesis if warranted.

### Local LLM filter mode

- [ ] Run `radar relevance-check` shadow mode ~5 days on real candidates; then
      extend `radar eval` with `--with-llm`.
- [ ] Add a "filter" mode that demotes confidently-`no` items to `Watch` and
      surfaces them in a separate "LLM-rejected" section — ship only after the
      eval shows ≥0.9 noise-class rejection precision and ≈1.0 relevant-class
      acceptance recall.
- [ ] Pick the `near_duplicate_threshold` value by hand once embeddings are
      populated on the on-disk candidate runs.

### Atlas and public output

- [ ] Atlas candidate workflow; public-safe export fields separate from private notes.
- [ ] Weekly synthesis after several daily digests exist.

### Repo hygiene

- [ ] Issue templates once the first task batch is turned into GitHub issues.
- [ ] `CONTRIBUTING.md` only if the repository becomes more than personal-first.
- [ ] Release notes once there is a user-facing versioned CLI.

## Deferred

Re-evaluate when the work above lands:

- LLM-written digest narrative.
- LLM-drafted per-card gloss in the queue UI.
- LLM-driven track reassignment.
