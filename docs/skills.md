# Proposed Codex Skills For CV Radar

These project-specific skills are implemented in `$CODEX_HOME/skills/`.
See [skill-workflows.md](skill-workflows.md) for a short tutorial on using them.

## 1. `cv-radar-curator`

Use when reviewing candidate queues, assigning rings, writing decision reasons, and
updating radar state.

Why it matters:

- This is the core habit of the project.
- It should encode the difference between a candidate queue, a visible radar item,
  and an Atlas/public candidate.
- It should keep daily output short and skeptical.

Useful bundled references:

- Ring definitions.
- Track definitions.
- Decision examples.
- Known noise patterns.

## 2. `cv-radar-scoring-evaluator`

Use when tuning keywords, thresholds, negative topics, or source boosts against real
candidate queues.

Why it matters:

- The first real run already showed false positives from naive matching.
- Scoring changes need regression examples, not vibes.
- The skill can require before/after score tables and prevent accidental promotion
  of broad AI hype.

Useful bundled resources:

- A labeled review-set format.
- A small script to compare old/new scores.
- Reference notes for false-positive categories.

## 3. `cv-radar-source-onboarding`

Use when adding RSS/vendor/source configurations.

Why it matters:

- Source quality will decide whether this stays useful.
- Vendor feeds need practical relevance checks, not just "has RSS".
- A repeatable onboarding flow prevents fragile scraping and noisy sources.

Useful bundled references:

- Source acceptance checklist.
- Normalization rules.
- Priority-source policy.
- Feed failure handling expectations.

## 4. `cv-radar-digest-writer`

Use when turning accepted decisions into daily or weekly Markdown digests.

Why it matters:

- Digest prose should be compact and useful, not a summary of everything.
- It should highlight uncertainty, actions, and noise patterns.
- It should avoid public-facing polish until items are explicitly curated.

Useful bundled references:

- Daily digest template.
- Weekly synthesis template.
- Examples of good and bad digest entries.

## 5. `cv-radar-atlas-bridge`

Use when deciding whether a radar item deserves an Atlas candidate note or future
public Vitavision page.

Why it matters:

- The radar is a moving signal detector; the Atlas should stay stable.
- This skill should enforce the manual promotion boundary.
- It can identify missing evidence before an item becomes public-facing material.

Useful bundled references:

- Atlas candidate criteria.
- Frontmatter/export conventions once `vitavision.dev` integration is known.
- Examples of "watch only" versus "Atlas candidate" decisions.

## Recommended Usage Order

1. Use `cv-radar-scoring-evaluator` now, while candidate quality is still being tuned.
2. Use `cv-radar-curator` after `radar decide` exists, or for manual Markdown review now.
3. Use `cv-radar-source-onboarding` before adding any RSS/vendor source.
4. Use `cv-radar-digest-writer` after explicit decisions exist.
5. Use `cv-radar-atlas-bridge` only for accepted, durable items.
