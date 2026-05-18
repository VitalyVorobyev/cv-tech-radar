# CV Radar Roadmap

CV Radar is a private-first computer-vision technology radar. It now runs as
**two parallel monitoring lanes** over one SQLite database:

- **Papers radar** — arXiv `cs.CV` ingestion → deterministic classification →
  scoring → candidate queue → curator decisions → daily digest.
- **Ecosystem radar** — a hand-maintained inventory of software *artifacts*
  (libraries) polled across GitHub / PyPI / crates.io / npm for release events.

Both lanes share the five rings (`Use` / `Prototype` / `Evaluate` / `Watch` /
`Ignore`), a FastAPI + React UI, and a static-export build.

## Current State — what works

### Papers pipeline

- arXiv `cs.CV` ingestion, SQLite persistence, raw/normalized split, dedup.
- Deterministic keyword classification + multi-component scoring.
- Candidate queue Markdown/JSON; `radar score-debug` for per-component inspection.
- Curator decisions: `radar decide`, the `radar apply` bulk-decision bridge,
  and `radar decisions`.
- `radar digest` — a short, ring-sectioned daily digest.
- `radar daily-fetch` / `daily-publish` umbrella commands.
- `radar eval` — precision/recall against a labeled set.

### Ecosystem lane

- `config/artifacts.yaml` inventory; GitHub/PyPI/crates/npm collectors with an
  idempotent, first-seen-safe diff runner.
- Release events with relevance/severity classification.
- `radar fetch-ecosystem`, `radar ecosystem`, `radar artifact-decide`.
- Folded into `daily-fetch`; the digest gains an `## Ecosystem` section.
- See [ecosystem.md](ecosystem.md).

### Local semantic assist (optional, off by default)

- Ollama embeddings + `radar embed` + `radar near-duplicates`.
- LLM second-opinion `radar relevance-check` — shadow mode only, never affects
  the candidate queue.

### UI

- FastAPI HTTP API + React/Vite frontend, with two-lane navigation.
- Papers lane: radar board, queue, timeline, tracks, digest, pipeline,
  score-debug, manual-add, settings.
- Ecosystem lane: radar board, release feed, artifact table.
- Date-grid landings for the Queue and Digest views.
- Static export build (`radar build-static`) — the radar, tracks, timeline and
  ecosystem surfaces run with no backend.

## Open work

### Signal calibration (papers lane)

Goal: make the candidate queue trustworthy.

- [ ] Grow `tests/fixtures/labeled_items.yaml` past the initial 2026-05-08 seed.
- [ ] Tune `topics.yaml` / `negative_topics.yaml` / `scoring.yaml` against
      observed false positives; `radar eval` is the yardstick before/after.

Baseline (2026-05-11, pre-tuning, on the 2026-05-08 queue): precision@25 0.05,
recall@25 1.00. Dominant noise classes: `broad_vlm` (8), `generative_editing`
(2), `medical_imaging` (2), `out_of_domain_3d` (2).

### RSS and vendor sources

Goal: add high-signal non-paper inputs without becoming a scraper.

- [ ] Implement RSS loading from `config/sources.yaml`; `radar fetch-rss`.
- [ ] Normalize RSS entries into `items` with blog/vendor/release type detection.
- [ ] Graceful per-feed failure reporting and source-level fetch stats.

Hand-picked starting set: OpenCV, MVTec, NVIDIA developer/research feeds,
selected camera/sensor vendors, standards bodies. Out of scope: broad social
media and fragile scraping.

### Ecosystem radar follow-ups

- [ ] GitHub collector tag-support: fall back to the `/tags` API when a repo
      publishes no GitHub *Releases* (candle, image, nalgebra, opencv-rust),
      and add a per-ref tag/release prefix filter so monorepos (vite, tauri)
      select the right sub-package. Then re-add the 6 dropped `github` refs.
- [ ] Calibrate ecosystem event volume; add a weekly synthesis if warranted.

### Local LLM filter mode

- [ ] Run `radar relevance-check` shadow mode ~5 days on real candidates; extend
      `radar eval` with `--with-llm` to compute hypothetical filtered precision.
- [ ] Add a filter mode that demotes confidently-`no` items to `Watch` and lists
      them in a separate "LLM-rejected" digest/queue section — ships only after
      eval shows ≥0.9 noise-class rejection precision and ≈1.0 relevant-class
      acceptance recall.
- [ ] Pick the `near_duplicate_threshold` value by hand once embeddings are
      populated on real candidate runs.

### Atlas and public output

Goal: promote only curated radar output into durable public material.

- [ ] Atlas candidate workflow; public-safe export fields separate from private notes.
- [ ] Weekly/monthly public radar posts drafted only from explicitly accepted items.

Preserve a hard boundary between the private raw radar and public Vitavision
content — private notes, ignored items, and raw payloads are never published by
default.

## Deferred

Re-evaluate when the work above lands:

- LLM-written digest narrative.
- LLM-drafted per-card gloss in the queue UI.
- LLM-driven track reassignment.
- Anything that changes `final_score` directly without eval evidence.
