# The curation workflow

Everything upstream — sourcing, classification, scoring — exists to prepare a short,
well-ordered list so a human can make good decisions quickly. The curation workflow
is that human step, plus the durable record it produces. The machine proposes; the
curator decides; nothing is ever published automatically.

## The daily rhythm

The radar is built around one short daily ritual. Two umbrella actions wrap the
deterministic stages around a single point of judgment:

1. **Fetch and prepare.** The pipeline fetches new papers, classifies and scores
   them, writes a candidate queue, and polls the ecosystem lane — all in one pass.
   The result is a candidate queue file: the day's items, ordered by score, each with
   its tracks, its component scores, its suggested ring, and the pipeline's rationale.
2. **Curate.** The curator reads the queue top to bottom and, for each item worth a
   decision, assigns a ring and writes a short reason and a concrete next action.
3. **Publish the digest.** The recorded decisions are applied and a short daily
   digest is written, sectioned by ring.

The funnel is steep by design — a day that starts with hundreds of raw items is
meant to end with a handful of visible ones. Most of the curator's decisions are to
*ignore*, and that is the system working as intended.

## What a decision contains

A decision is small and opinionated. Each one carries:

- **ring** — the required verdict: `Use`, `Prototype`, `Evaluate`, `Watch`, or
  `Ignore`. This may confirm or override the suggested ring.
- **reason** — required, short, and skeptical. Why this ring, in one or two lines.
- **action** — the concrete next step (read the PDF, run it on our rig), or empty
  for an ignore.
- **tracks** — optional; defaults to the classifier's tracks, overridden only when
  the curator disagrees.
- **uncertain** — an optional flag that surfaces the item in the digest's
  open-questions section regardless of its ring.

Items the curator has not yet reviewed are simply left untouched and skipped — the
apply step reports how many it passed over without recording anything.

## The curation principles

The curator (a human editor, assisted by a proposing skill) works under a fixed set
of rules that encode the radar's philosophy:

- Do not promote on famous authors, famous labs, social attention, or big claims.
- Prefer practical relevance to the radar's [tracks](./radar-model.md).
- Keep the daily digest short.
- Put speculative items in `Watch`, not `Evaluate`.
- Put an item in `Prototype` only when there is code, data, or a clear test path.
- Mark uncertainty explicitly rather than hiding it.
- Never publish public content automatically.

These are the same rules the scoring thresholds enforce numerically — the human step
is where they are applied with judgment the keyword matcher cannot supply.

## Decisions are durable and independent

The key architectural choice is that **decisions live apart from classification**.
Classification and scoring can be re-run at any time — after tuning keywords,
adjusting weights, or re-fetching a source — without disturbing a single recorded
decision. A decision can override the suggested ring and it stays put.

The decision log is append-only and latest-wins: to change your mind, you record a
new decision and it supersedes the old one, with the history preserved. This keeps a
durable, auditable record of not just *what* the radar concluded but *when* and
*why* — including everything it deliberately chose to ignore.

## Weekly synthesis, and the public boundary

On a longer cadence the daily digests are synthesized into trends rather than a
re-list of items — track movements, repeated weak signals, and noise patterns worth
naming. Above all, the workflow preserves a hard boundary: the raw radar is
private-first, and public output is only ever drawn from items a curator has
*explicitly* accepted for it. Private notes, ignored items, and raw payloads are
never published by default. What a reader eventually sees is covered in
[Reading the radar](./reading-the-radar.md).
