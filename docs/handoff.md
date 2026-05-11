# CV Technology Radar — Claude Code Handoff Spec

## 0. Purpose

Build a personal-first computer-vision technology radar that monitors papers, tools, vendor news, and selected industry/research sources, then produces a compact daily/weekly radar view.

The system is for one primary user initially, but it should be structured so selected outputs can later become public pages or posts on `vitavision.dev`.

The project is not a generic AI news summarizer. It is a relevance-filtered, evidence-based radar for computer vision, industrial vision, calibration, 3D geometry, sensors, robotics guidance, and practical CV tooling.

## 1. Product intention

### 1.1 Main user

The initial user is a computer vision engineer/team lead who wants to stay aware of relevant technical movement without reading professional news daily.

The radar should help answer:

* What should I notice?
* What should I ignore?
* What deserves reading later?
* What deserves a small prototype?
* What might become useful for my CV Atlas or public writing?

### 1.2 Secondary/public direction

If the project works, selected radar outputs should be publishable as:

* A public “CV Radar” page.
* Weekly/monthly curated radar posts.
* Input material for the user’s CV Atlas.
* Evidence for future algorithm/model/concept pages.

The raw radar should remain private-first. Public output should be explicitly curated.

### 1.3 Relationship to LLM wiki / CV Atlas

The radar should follow an “LLM-readable knowledge base” style:

* Raw incoming items are stored as structured records.
* Curated knowledge is compiled into Markdown notes.
* Radar tracks become persistent pages that agents can read and update.
* The system should be queryable by Claude Code or a local LLM.

The CV Atlas is a curated, stable knowledge product. The radar is a moving signal detector. The radar can feed Atlas candidates, but should not automatically publish Atlas pages.

Recommended relationship:

```text
raw sources → candidate queue → radar tracks → weekly synthesis → Atlas candidates
```

## 2. MVP scope

### 2.1 Sources for MVP

Start with source scope B:

1. arXiv computer vision / related categories.
2. Selected RSS/blog/vendor feeds.

Do not start with broad social media scraping.

Possible MVP arXiv categories:

* `cs.CV`
* selected `cs.RO`
* selected `eess.IV`
* optionally selected `cs.LG` only when vision-related

Possible RSS/source groups:

* OpenCV blog/releases
* Edge AI and Vision Alliance
* NVIDIA developer/research posts relevant to vision/edge AI
* Basler / IDS / Allied Vision / Teledyne / Zivid / Photoneo / SICK / ifm / Balluff / Lucid Vision Labs
* MVTec
* Fraunhofer applied vision sources where available
* GenICam / EMVA / standards-related sources
* CVF / conference news pages where practical

Defer until after MVP:

* Hugging Face Papers
* Papers with Code
* Semantic Scholar enrichment beyond basic metadata
* GitHub trend enrichment
* OpenReview conference tracking
* social/blog mention tracking

### 2.2 Output style

The system should generate:

1. A compact daily radar update.
2. A richer weekly radar report.
3. Persistent radar track notes.
4. Candidate queues for human/Claude review.
5. JSON export for a React UI.

### 2.3 UI scope

Build a local React/Vite dashboard that reads generated JSON files.

It should be compatible with later integration into `vitavision.dev`:

* Use reusable React components.
* Keep data access simple and file/API-agnostic.
* Prefer static JSON exports first.
* Avoid tight coupling to local-only scripts.

## 3. Radar model

### 3.1 Radar rings

Use these rings:

* `Use`
* `Prototype`
* `Evaluate`
* `Watch`
* `Ignore`

Definitions:

#### Use

Mature enough to influence current technical decisions or toolchain choices.

Examples:

* Stable library release that solves a known problem.
* Vendor/standard update relevant to real systems.
* Method already validated by strong independent evidence.

#### Prototype

Worth a small implementation or experiment.

Examples:

* Relevant method with code and plausible benefits.
* New detector or calibration technique that can be tested on synthetic/real data.
* Tooling that may improve workflow but needs validation.

#### Evaluate

Worth reading, comparing, or adding to a reading queue.

Examples:

* Relevant new paper with interesting method.
* New dataset/benchmark in an important area.
* New library/release that may matter but is not urgent.

#### Watch

Weak or early signal. Track only.

Examples:

* Several papers indicate a possible trend.
* A vendor hints at upcoming support.
* A topic is gaining attention but practical value is unclear.

#### Ignore

Explicitly deprioritized for this radar.

Examples:

* Irrelevant topic.
* Generic hype with no practical signal.
* Weak paper with no code, weak evaluation, and low relevance.

### 3.2 Radar tracks

Initial tracks:

1. Calibration & Camera Models
2. Target Detection & Fiducials
3. 3D Geometry & Reconstruction
4. 3D Sensors
5. Robotics Vision
6. Robot Guidance
7. Object Tracking
8. Industrial Vision Inspection
9. Edge AI & Deployment
10. Vision Foundation Models
11. Open-Source CV Tooling
12. Sensors, Cameras & Standards
13. Synthetic Data & Simulation
14. Datasets & Benchmarks

Each item may belong to multiple tracks.

### 3.3 Item types

Supported item types:

* `paper`
* `blog_post`
* `vendor_news`
* `library_release`
* `standard_update`
* `dataset`
* `benchmark`
* `conference_item`
* `github_repo`
* `atlas_candidate`

MVP may implement only:

* `paper`
* `blog_post`
* `vendor_news`
* `library_release`

## 4. Processing philosophy

Do not deeply process hundreds of papers per day.

Pipeline design:

```text
raw items → deterministic filters → embedding/topic filters → candidate queue → Claude Code curation → radar output
```

The system should reduce volume before any expensive LLM step.

Target daily flow:

```text
hundreds of raw items
→ 50–100 rough matches
→ 10–25 candidates
→ 3–7 daily visible items
```

Claude Code should not browse raw sources manually. Scripts should prepare candidate files. Claude Code should curate, write, and update radar state.

## 5. Technical stack

### 5.1 MVP stack

Use:

* Python 3.12+
* `uv` for package management
* SQLite for persistence
* `SQLModel` or `SQLAlchemy` for DB layer
* `pydantic` for schemas
* `httpx` for HTTP
* `feedparser` for RSS
* `typer` for CLI
* `rich` for CLI output
* `pytest` for tests
* `ruff` for lint/format
* React + Vite + TypeScript for UI
* Tailwind optional, but keep components portable

### 5.2 Local inference

The user has both Ollama and LM Studio available.

MVP should work without local LLM inference.

Optional local LLM roles:

* topic classification
* rough summary generation
* contribution extraction
* initial relevance judgment
* clustering similar items

Preferred design:

* deterministic mode first
* optional local LLM enrichment behind a feature flag

Example config:

```yaml
llm:
  enabled: false
  provider: ollama
  model: qwen2.5:7b
```

Do not require cloud LLM APIs.

### 5.3 Claude Code role

Claude Code may:

* run collectors and pipeline scripts
* inspect generated candidate queues
* curate radar decisions
* update Markdown radar track files
* generate daily/weekly digest Markdown
* generate static JSON exports
* run tests/lints
* optionally commit generated outputs

Claude Code should not be responsible for fragile raw scraping logic.

## 6. Repository structure

Recommended structure:

```text
cv-radar/
  README.md
  pyproject.toml
  uv.lock
  CLAUDE.md

  config/
    sources.yaml
    topics.yaml
    priority_sources.yaml
    negative_topics.yaml
    scoring.yaml

  data/
    radar.sqlite
    raw/
    exports/
      latest.json
      daily/
      weekly/
      tracks.json

  radar/
    __init__.py
    cli.py
    db.py
    models.py
    schemas.py

    collectors/
      __init__.py
      arxiv.py
      rss.py

    enrichers/
      __init__.py
      links.py
      github.py
      semanticscholar.py

    filters/
      __init__.py
      keyword_filter.py
      topic_filter.py
      negative_filter.py
      embedding_filter.py

    scoring/
      __init__.py
      score_item.py
      score_paper.py

    reports/
      __init__.py
      candidate_queue.py
      daily_digest.py
      weekly_report.py
      export_json.py

  radar_state/
    tracks/
      calibration-camera-models.md
      target-detection-fiducials.md
      3d-geometry-reconstruction.md
      3d-sensors.md
      robotics-vision.md
      robot-guidance.md
      object-tracking.md
      industrial-vision-inspection.md
      edge-ai-deployment.md
      vision-foundation-models.md
      open-source-cv-tooling.md
      sensors-cameras-standards.md
      synthetic-data-simulation.md
      datasets-benchmarks.md
    watchlist.md
    atlas-candidates.md
    decisions-log.md

  reports/
    candidates/
    daily/
    weekly/

  ui/
    package.json
    src/
      App.tsx
      components/
        RadarOverview.tsx
        RadarRingBoard.tsx
        TrackPage.tsx
        ItemCard.tsx
        CandidateQueue.tsx
        DigestView.tsx
      data/
      types.ts

  agent/
    prompts/
      curate_daily.md
      update_track.md
      weekly_synthesis.md
      review_candidate.md
```

## 7. Data model

### 7.1 Core tables

#### sources

Fields:

* `id`
* `name`
* `kind`
* `url`
* `enabled`
* `priority`
* `notes`

#### raw_items

Fields:

* `id`
* `source_id`
* `external_id`
* `url`
* `raw_payload_json`
* `fetched_at`

#### items

Fields:

* `id`
* `type`
* `title`
* `abstract_or_summary`
* `url`
* `pdf_url`
* `published_at`
* `updated_at`
* `source_name`
* `external_id`
* `doi`
* `arxiv_id`
* `authors_json`
* `organizations_json`
* `metadata_json`
* `created_at`

#### item_classifications

Fields:

* `id`
* `item_id`
* `tracks_json`
* `positive_keywords_json`
* `negative_keywords_json`
* `relevance_score`
* `novelty_score`
* `source_priority_score`
* `implementation_score`
* `attention_score`
* `final_score`
* `recommended_ring`
* `confidence`
* `rationale`
* `created_at`

#### radar_decisions

Fields:

* `id`
* `item_id`
* `ring`
* `tracks_json`
* `decision_reason`
* `action`
* `decided_by`
* `created_at`

#### digests

Fields:

* `id`
* `kind`
* `date`
* `title`
* `markdown_path`
* `json_path`
* `created_at`

### 7.2 JSON export shape

`data/exports/latest.json`:

```json
{
  "generated_at": "2026-05-10T20:00:00+02:00",
  "daily_digest": {
    "date": "2026-05-10",
    "summary": "Short text summary",
    "items": []
  },
  "tracks": [],
  "rings": ["Use", "Prototype", "Evaluate", "Watch", "Ignore"],
  "candidates": []
}
```

Item shape:

```json
{
  "id": "item_...",
  "type": "paper",
  "title": "...",
  "url": "...",
  "pdf_url": "...",
  "published_at": "...",
  "source": "arXiv",
  "tracks": ["Calibration & Camera Models"],
  "ring": "Evaluate",
  "scores": {
    "relevance": 82,
    "source_priority": 4,
    "implementation": 0,
    "attention": 0,
    "final": 74
  },
  "summary": "...",
  "why_it_matters": "...",
  "skepticism": "...",
  "action": "Read abstract and check PDF later"
}
```

## 8. Configuration files

### 8.1 `config/topics.yaml`

Example:

```yaml
tracks:
  - id: calibration-camera-models
    name: Calibration & Camera Models
    positive_keywords:
      - calibration
      - camera model
      - intrinsic
      - extrinsic
      - distortion
      - rolling shutter
      - bundle adjustment
      - hand-eye
      - homography
    negative_keywords: []

  - id: target-detection-fiducials
    name: Target Detection & Fiducials
    positive_keywords:
      - checkerboard
      - chessboard
      - fiducial
      - aruco
      - charuco
      - calibration target
      - marker detection
      - corner detection
      - subpixel
    negative_keywords: []
```

### 8.2 `config/negative_topics.yaml`

Example:

```yaml
negative_topics:
  - face recognition
  - person re-identification
  - fashion retrieval
  - medical segmentation
  - remote sensing
  - diffusion art generation
  - video generation
```

Negative topics do not hard-delete items by default. They reduce score unless an item strongly matches a positive track.

### 8.3 `config/priority_sources.yaml`

Example:

```yaml
organizations:
  high:
    - OpenCV
    - CVF
    - ETH Zurich
    - Oxford VGG
    - TU Munich
    - NVIDIA Research
    - Meta FAIR
    - Google DeepMind
    - MVTec
    - Fraunhofer
    - Basler
    - GenICam
    - EMVA
  medium:
    - Microsoft Research
    - Apple Machine Learning Research
    - Adobe Research
    - EPFL
    - INRIA
    - Max Planck Institute
    - CMU
    - Stanford
    - MIT CSAIL

vendors:
  high:
    - Basler
    - IDS Imaging
    - Allied Vision
    - Teledyne
    - Zivid
    - Photoneo
    - SICK
    - ifm
    - Balluff
    - Lucid Vision Labs
```

Priority sources should be weak boosts, not automatic promotion.

## 9. Scoring

### 9.1 Basic scoring formula

Initial formula:

```text
final_score =
  relevance_score * 0.55
  + source_priority_score * 0.10
  + implementation_score * 0.10
  + attention_score * 0.10
  + novelty_score * 0.10
  - negative_topic_penalty * 0.15
```

For MVP, many fields may be zero.

### 9.2 Hard rules

* Irrelevant items should not be promoted by source priority alone.
* Source priority boost must be capped.
* Negative topic matches should not hard-delete items if strong positive relevance exists.
* The system should preserve ignored items for audit/debugging.

### 9.3 Recommended thresholds

Initial thresholds:

```yaml
thresholds:
  use: 90
  prototype: 80
  evaluate: 65
  watch: 45
  ignore: 0
```

For MVP, most items should end up in `Watch`, `Evaluate`, or `Ignore`.

`Use` and `Prototype` should be rare.

## 10. Daily workflow

### 10.1 CLI commands

Implement CLI commands:

```bash
uv run radar fetch --date today
uv run radar classify --date today
uv run radar score --date today
uv run radar candidates --date today
uv run radar export --date today
```

Convenience command:

```bash
uv run radar daily --date today
```

### 10.2 Generated candidate queue

Path:

```text
reports/candidates/YYYY-MM-DD.md
```

Format:

```markdown
# Candidate Queue — YYYY-MM-DD

## Candidate 1: Title

- Type: paper
- Source: arXiv
- URL: ...
- PDF: ...
- Date: ...
- Tracks: Calibration & Camera Models, Target Detection & Fiducials
- Suggested ring: Evaluate
- Scores:
  - relevance: 82
  - source priority: 4
  - implementation: 0
  - attention: 0
  - final: 74

### Abstract / Summary

...

### Pipeline rationale

...

### Claude decision

TODO
```

Claude Code should fill or update `Claude decision` sections and generate the digest.

### 10.3 Daily digest

Path:

```text
reports/daily/YYYY-MM-DD.md
```

Format:

```markdown
# CV Radar — YYYY-MM-DD

## Summary

Short synthesis of what changed today.

## Radar changes

### Evaluate — Item title

- Tracks: ...
- Why it matters: ...
- Skepticism: ...
- Action: ...

## Watch

...

## Ignore / noise pattern

Short note on what was intentionally ignored.

## Atlas candidates

...
```

Daily digest should be short.

## 11. Weekly workflow

Weekly report should synthesize trends, not list all items.

Path:

```text
reports/weekly/YYYY-WW.md
```

Format:

```markdown
# CV Radar Weekly — YYYY-WW

## Executive summary

## Track movements

## Strongest papers/items

## Weak signals

## Noise and hype patterns

## Candidate Atlas pages

## Suggested actions for next week
```

## 12. UI requirements

### 12.1 UI goals

The UI should be a decent local dashboard, not a throwaway table.

It should help answer:

* What changed today?
* Which radar tracks are active?
* Which items are worth evaluating?
* What was ignored and why?
* Which items may become Atlas/public content?

### 12.2 First screens

#### Dashboard

* Date selector
* Summary card
* Counts by ring
* Active tracks
* Top daily radar changes
* Link to candidate queue

#### Radar board

* Columns for rings: Use, Prototype, Evaluate, Watch, Ignore
* Cards grouped by ring
* Filter by track/source/type/date

#### Track page

For one radar track:

* Current status
* Recent items
* Open questions
* Candidate Atlas links
* Timeline of changes

#### Candidate queue

* Items sorted by score
* Expandable abstract/summary
* Pipeline rationale
* Manual decision display

#### Digest view

* Render daily/weekly Markdown-derived content
* Good reading experience

### 12.3 UI data mode

MVP UI reads static JSON from:

```text
data/exports/latest.json
```

Optionally support selecting historical JSON files later.

Do not build authentication or backend API in MVP.

## 13. Agent prompts

### 13.1 `agent/prompts/curate_daily.md`

Purpose:

Claude Code reads candidate queue and writes daily digest.

Instructions:

* Be selective.
* Do not promote items by hype alone.
* Prefer practical relevance to the radar tracks.
* Keep daily output short.
* Explicitly mention uncertainty.
* Use rings: Use, Prototype, Evaluate, Watch, Ignore.
* Update relevant `radar_state/tracks/*.md` files when a track has meaningful movement.
* Add possible Atlas items to `radar_state/atlas-candidates.md`.

### 13.2 `agent/prompts/update_track.md`

Purpose:

Update a persistent radar track note.

Track note format:

```markdown
# Track Name

## Current status

## Current ring

## Why it matters

## Recent evidence

## Open questions

## Candidate actions

## Related Atlas candidates
```

### 13.3 `agent/prompts/weekly_synthesis.md`

Purpose:

Read the week’s daily digests and decisions log. Produce a synthesis.

Focus on:

* trends
* track movements
* repeated weak signals
* hype/noise patterns
* candidates for reading/prototyping
* candidates for public posts

## 14. `CLAUDE.md` project instructions

Create a root `CLAUDE.md` with these rules:

```markdown
# Claude Code Instructions

You are working on a computer-vision technology radar.

The goal is not to summarize everything. The goal is to decide what is worth attention.

Use these radar rings:

- Use
- Prototype
- Evaluate
- Watch
- Ignore

Do not promote items based only on famous authors, famous labs, social attention, or large claims.

Prefer practical relevance to:

- calibration
- target detection
- 3D geometry
- 3D sensors
- robot guidance
- industrial vision inspection
- object tracking
- edge AI deployment
- open-source CV tooling
- sensors/cameras/standards
- synthetic data
- datasets/benchmarks

When curating:

1. Read generated candidate queues.
2. Keep daily digest short.
3. Update radar state only when there is meaningful evidence.
4. Explicitly mark uncertainty.
5. Put speculative items into Watch, not Evaluate.
6. Put implementation-worthy items into Prototype only if there is code, data, or a clear test path.
7. Never automatically publish public content.

Before finishing:

- Run tests if code changed.
- Run lint/format if available.
- Ensure generated JSON is valid.
- Ensure Markdown files are readable.
```

## 15. Implementation phases

### Phase 1 — Skeleton and config

Deliverables:

* repo structure
* Python package setup with `uv`
* config YAML files
* SQLite schema
* CLI skeleton
* initial tests

Acceptance criteria:

* `uv run radar --help` works
* DB can be initialized
* config files load and validate

### Phase 2 — arXiv collector

Deliverables:

* arXiv fetcher
* stores raw items and normalized items
* deduplicates by arXiv ID/title
* supports date filtering

Acceptance criteria:

* can fetch recent `cs.CV` entries
* stores items in SQLite
* repeated runs do not duplicate items

### Phase 3 — RSS collector

Deliverables:

* source config for RSS feeds
* RSS parser
* normalized item storage

Acceptance criteria:

* can fetch configured RSS sources
* stores blog/vendor/library items
* handles failed feeds gracefully

### Phase 4 — filtering and scoring

Deliverables:

* keyword/topic classifier
* negative topic penalty
* priority source boost
* score computation
* recommended ring

Acceptance criteria:

* each item receives tracks, scores, and suggested ring
* irrelevant items are mostly ignored
* relevant calibration/geometry/industrial items are surfaced

### Phase 5 — candidate queue and digest generation

Deliverables:

* candidate queue Markdown generator
* daily digest Markdown generator
* JSON export

Acceptance criteria:

* `uv run radar daily --date today` produces candidate queue, digest stub, and JSON export
* output is deterministic given stored data

### Phase 6 — React UI

Deliverables:

* Vite React TypeScript app
* reads static JSON export
* dashboard screen
* radar board screen
* candidate queue screen
* digest view

Acceptance criteria:

* `npm/bun install` and dev server work
* UI renders latest export
* filters by ring/track/type/source work

### Phase 7 — Claude curation workflow

Deliverables:

* root `CLAUDE.md`
* agent prompts
* documented daily workflow
* example curated daily digest
* updated radar track note example

Acceptance criteria:

* Claude Code can run pipeline, inspect candidates, write digest, update radar state
* generated files remain schema-valid

## 16. Non-goals for MVP

Do not implement yet:

* social media scraping
* full PDF ingestion for all papers
* automatic public publishing
* authentication
* cloud deployment
* multi-user support
* Postgres/pgvector
* complex RAG system
* automatic Atlas page generation
* citation velocity tracking
* OpenReview integration
* Papers with Code/Hugging Face integration

## 17. Future extensions

Possible later features:

* Semantic Scholar citation and influential citation enrichment
* GitHub repo/star/fork enrichment
* Hugging Face Papers ingestion
* Papers with Code ingestion
* OpenReview conference tracking
* PDF fetching for shortlisted items
* local embedding search over radar history
* public CV Radar page on `vitavision.dev`
* monthly public radar posts
* Atlas candidate promotion workflow
* Obsidian/Markdown wiki export
* local LLM Q&A over radar state

## 18. First Claude Code task prompt

Use this prompt to start implementation:

```markdown
We are building `cv-radar`, a personal-first computer-vision technology radar.

Read this spec and implement Phase 1 and Phase 2 only.

Constraints:

- Python 3.12+
- use `uv`
- SQLite persistence
- pydantic/SQLModel or SQLAlchemy
- Typer CLI
- tests with pytest
- keep implementation simple and deterministic
- no cloud LLM API
- no UI yet

Phase 1:

- create repo structure
- create config YAML files
- implement config loading/validation
- implement SQLite schema
- implement CLI skeleton
- add tests

Phase 2:

- implement arXiv collector for configured categories
- normalize papers into DB items
- deduplicate by arXiv ID and title
- add command: `uv run radar fetch-arxiv --days 1`
- add command: `uv run radar candidates --date YYYY-MM-DD`
- generate a candidate queue Markdown file

Acceptance:

- `uv run radar --help` works
- `uv run radar init-db` creates database
- `uv run radar fetch-arxiv --days 1` stores recent papers
- repeated fetch does not duplicate papers
- candidate queue file is generated under `reports/candidates/`
- tests pass

Do not implement RSS, UI, local LLM, GitHub, Semantic Scholar, or web publishing yet.
```

## 19. Open questions

These can be resolved after Phase 1–2:

1. Exact RSS/vendor source list.
2. Exact public website format.
3. Whether public output should be a live radar page, periodic posts, or both.
4. Which local embedding model to use.
5. Whether to store PDFs locally for shortlisted candidates.
6. How strongly to integrate with the CV Atlas content model.
7. Whether radar track notes should eventually share frontmatter conventions with `vitavision.dev` Atlas pages.

