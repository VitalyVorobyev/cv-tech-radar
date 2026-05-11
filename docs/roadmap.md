# CV Radar Roadmap

This roadmap starts from the current Phase 1-2 implementation: arXiv `cs.CV`
ingestion, SQLite persistence, deterministic classification, candidate queues, CI,
and a real 100-paper arXiv smoke test.

## Current State

The local loop works:

```bash
uv run radar init-db
uv run radar fetch-arxiv --days 365 --max-results 100
uv run radar classify --date 2026-05-07
uv run radar candidates --date 2026-05-07
uv run radar score-debug --date 2026-05-07
uv run radar decide ITEM_ID --ring Watch --reason "..." --action "..."
```

The latest real smoke test fetched 100 arXiv entries and generated a 25-item
candidate queue. That queue is useful for tuning, not yet for daily reading. The
top candidates are mostly borderline object tracking, edge deployment, dataset,
and open-source tooling items. This is exactly the right failure mode for the
next phase: we can inspect real noise instead of guessing.

## Phase 2.5 - Signal Calibration

Goal: make the candidate queue trustworthy before adding more sources.

- Build a small labeled evaluation set from real candidate queues.
- Add a review import format so Markdown TODOs are not the only bulk-review surface.
- Extend score-debug output into a reusable scoring evaluation report.
- Tune keywords, negative topics, and thresholds against observed false positives.
- Add regression tests for known noise patterns such as broad VLM papers, video
  generation, person re-identification, and generic dataset papers.

Exit criteria:

- A daily 100-paper arXiv batch yields a manageable review queue.
- Obvious hype/noise stays visible for calibration but does not look promoted.
- A few genuinely relevant calibration, 3D geometry, edge, robotics, or
  industrial-vision items surface when present.
- Explicit decisions can be persisted and listed from SQLite.

## Phase 3 - RSS And Vendor Sources

Goal: add high-signal non-paper inputs without turning the project into a scraper.

- Implement RSS source loading from `config/sources.yaml`.
- Normalize RSS entries into the same `items` table.
- Start with a small hand-picked source set: OpenCV, MVTec, NVIDIA developer or
  research feeds, selected camera/sensor vendors, and standards bodies where RSS
  is practical.
- Add graceful feed failure reporting and per-source fetch stats.
- Keep broad social media and fragile scraping out of scope.

Exit criteria:

- `uv run radar fetch-rss` stores normalized blog/vendor/library items.
- Failed feeds do not fail the whole run.
- Candidate queues include source type and source-specific rationale.

## Phase 4 - Curation Workflow

Goal: make the radar useful as a daily engineering habit.

- Add durable radar decisions with ring, tracks, reason, and action.
- Generate short daily digest drafts from accepted decisions.
- Update persistent track notes only when evidence is meaningful.
- Keep public/Atlas output explicitly manual.

Exit criteria:

- A user can review candidates, record decisions, and generate a daily digest.
- The digest is short enough to read in a few minutes.
- Track notes summarize movement rather than mirroring every item.

## Phase 5 - Static Export And UI

Goal: make the radar easier to browse after the backend signal is acceptable.

- Stabilize `data/exports/latest.json`.
- Add historical exports by date.
- Build a Vite/React dashboard that reads static JSON.
- Include dashboard, radar board, track page, candidate queue, and digest view.

Exit criteria:

- The UI shows current radar state without a backend server.
- Filtering by ring, track, type, source, and date works.
- The UI helps review and navigate; it does not hide weak scoring.

## Phase 6 - Local Semantic Assist

Goal: use local inference where it improves filtering without creating a cloud dependency.

- Add optional Ollama embeddings for similarity to track descriptions and known
  accepted/rejected items.
- Keep deterministic mode as the default.
- Add cached embedding storage only after the scoring value is demonstrated.
- Add optional local chat summarization only when a suitable chat model is installed.

Exit criteria:

- Embeddings improve ranking on a labeled evaluation set.
- Running without Ollama remains fully supported.

## Phase 7 - Atlas And Public Output

Goal: promote only curated radar output into durable public material.

- Add an Atlas candidate workflow.
- Add public-safe export fields separate from private notes.
- Draft weekly/monthly public radar posts only from explicitly accepted items.
- Preserve a hard boundary between private raw radar and public Vitavision content.

Exit criteria:

- Public candidates are explicitly selected.
- Private notes, ignored items, and raw source payloads are never published by default.
