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
- [ ] Re-weight `negative_penalty` in `scoring.yaml`. Measured on the 2026-07-22
      backfill (07-15..07-21): one negative match moves an item only ~3.8 final
      points, so items keep out-scoring the threshold on breadth alone. After
      the wildlife/agronomy negatives landed, 6655 (global field delineation)
      still sat at 41.4 — rank 2 of its day — and 6707 (tomato phenotyping) at
      33.5. The breadth bonuses (`benchmark` + `dataset` + `github` + a spurious
      track match) are worth more than the penalty that is supposed to cancel
      them. Needs a labeled eval set first so the re-weight can be measured
      rather than guessed.
- [ ] Decide how to handle **false-context track matches** — a positive keyword
      firing on the same word used in an unrelated sense. Two were fixed on
      2026-07-23 with per-track `negative_keywords` (`checkerboard` → the image-
      compression context model, `manipulation` → "semantic manipulation" in
      image generation), but the general case stays open and recurs weekly:
      `multi-view` on "coordinated multi-view interface" (7153, still rank 3 of
      2026-07-22 after tuning), `reconstruction` on "reconstruction error" as a
      loss term (7141), `tracking` on "tracking greenhouse gas emissions"
      (7173), `visual inspection` on urban housing surveys (7127). Per-track
      negative keywords only work when the wrong sense has its own vocabulary;
      a general fix probably needs co-occurrence context, not more phrases.
      2026-07-24 adds `manipulation` → "camera and lighting manipulation" in 4D
      world generation (7215), fixed with a `world generation` track negative,
      and `reconstruction` → diffusion inpainting of an occluded iris (7212).
- [ ] **The scoring is better at demoting noise than at promoting on-domain
      work.** 2026-07-23 is the clean example: 7206 (synthetic defect generation
      for rotogravure print inspection) is the *only* on-domain item in the
      batch — Industrial Vision Inspection + Synthetic Data, with a real
      sim-to-real number — and it scored 39.94, ranked 6, and was recommended
      `Ignore`. Four off-domain benchmark papers out-scored it purely on
      breadth. Its relevance was only 50.8 because the industrial track fired on
      two keywords while dataset/benchmark/github breadth carries the items
      above it, and its implementation score was 20 (no code link) even though
      the paper describes a working generator. Two candidate levers, both
      needing the labeled eval set first: weight the *domain* tracks
      (calibration / inspection / 3D sensors / robot guidance) above the generic
      ones (`Datasets & Benchmarks`, `Open-Source CV Tooling`), or cap how much
      total relevance breadth alone can contribute.
- [ ] The bottom of the queue is a flat tie, so the top-25 cut is arbitrary
      there. Simulating the 2026-07-24 biometrics tuning on 2026-07-23 dropped
      two biometrics papers out of the top-25 and the two items that replaced
      them (7279 makeup-transfer diffusion, 7288 agentic design layout) both
      scored exactly 23.0 — as did the item they displaced. Below roughly 25
      points the ranking carries no information; consider cutting the queue on a
      score floor instead of a fixed count.
- [ ] **Negative topics are approaching their ceiling; the remaining Ignore mass
      needs the scoring re-weight, not more phrases.** Measured 2026-07-27 by
      mining the full decided corpus (1125 Ignore / 262 kept): 564 Ignore items
      (50%) carried *zero* negative penalty. Ranking every 1–2-gram in that
      residue by its Ignore-vs-kept rate found only two classes worth adding —
      VLM reasoning/QA benchmark vocabulary and a medical modality tail — and
      together they cover 47 items, 8.3% of the gap. What is left is mostly
      papers that use *on-domain vocabulary* for off-domain work (`tracking`,
      `reconstruction`, `manipulation` in the wrong sense) plus generic weak
      papers, and no phrase list can separate those. This is the same conclusion
      the two items above reach from the promotion side.
      The mining method is worth repeating rather than eyeballing batches: for
      each candidate phrase compare hits among Ignore items against hits among
      *kept* items, and reject anything that touches a kept item. It killed six
      plausible phrases this round — `embodied ai` (16 Ignore / 4 kept, one of
      them the kept EmbodiedGen V2), `world model` (17/2), `forest` (10/3, hits
      SelectAnyTree), `canopy` (4/1), `electron microscopy` (2/1, and SEM/TEM are
      semiconductor inspection instruments), `neuromorphic` (3/2, event cameras)
      — and two more on forward risk rather than measured damage: `diagnosis`
      (35/1, but "fault diagnosis" is industrial) and `success rate` (19/0, but
      grasping work reports it).
- [ ] Two of the phrases rejected on 2026-07-27 failed for a reason worth
      generalising: `brain` and `pathology` fire on *figurative ML usage* —
      "modular brain-skill-runtime architecture" (item 3447, the planner module)
      and "action-forgetting pathology" (item 3987, a defect of the method).
      This is the false-context problem above, but arriving through the negative
      list instead of the positive one, so per-track `negative_keywords` cannot
      fix it. Any future single-word negative should be checked for a figurative
      register before it lands.
      2026-07-28 adds the clearest instance yet: `fashion` measured 15 Ignore / 0
      kept, the best ratio of that round's batch, but 4 of the 15 hits are "in an
      autoregressive / end-to-end / offline fashion" and it also fires on the
      Fashion-MNIST dataset name. The Ignore/kept ratio alone would have shipped
      it. Grep a candidate phrase's *surrounding words* before trusting its
      ratio, not just its counts.
- [ ] **Whole-word matching silently halves a phrase's coverage when the natural
      form is plural.** `keyword_matches` wraps the phrase in `\b...\b`, so
      `visual token` does not fire on "redundant visual tokens" — the form most
      VLM abstracts actually use. Measured 2026-07-28: `visual token` 14 Ignore
      hits, `visual tokens` 11, and the config now lists both. The same trap
      applies to every multi-word phrase whose last token pluralises
      (`3d asset`/`3d assets`, `head avatar`/`head avatars`). Either list both
      forms when mining shows the plural is common, or teach `keyword_matches` an
      optional trailing `s?` — the latter is a one-line change but needs a sweep
      of the existing 97 phrases to check nothing over-matches.
- [ ] The false-context problem also arrives through a positive keyword whose
      *own* track is wrong, which per-track `negative_keywords` does fix.
      2026-07-28: `pruning` is an Edge AI & Deployment positive keyword, but
      VLM papers use it for dropping visual tokens from an LLM context window
      (7504 Omni-Prune, 7517, 7523, 7527, 7534 in the 07-25..26 window alone).
      Adding `token pruning` / `visual token` / `visual tokens` as track
      negatives dropped 7534 from 14.2 to 4.2 and 7504 from 18.6 to 8.8 by
      removing the track entirely, which is a much larger move than any negative
      *topic* can make — suppressing a spurious track beats penalising the item.
      Worth auditing the other generic positives (`deployment`, `benchmark`,
      `dataset`, `reconstruction`) the same way.

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
