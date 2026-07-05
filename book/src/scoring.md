# Scoring methodology

Scoring turns the signals gathered during [classification](./sourcing-and-classification.md)
into one number in the range 0–100, and maps that number to a *suggested* ring. The
emphasis is on *suggested*: the score is an ordering and triage aid, never the final
word. The final word belongs to the human [curator](./curation-workflow.md).

## The components

Five positive components and one penalty feed the score. Each is computed on its own
scale before weighting.

| Component | What it measures |
|-----------|------------------|
| **relevance** | How strongly the item matches the radar tracks — built from the per-track keyword weights, dominated by the strongest track with diminishing credit for additional tracks. This is the main driver. |
| **source priority** | A weak boost for high-value organizations and vendors named in the item. Capped so priority alone can never carry an off-topic item upward. |
| **implementation** | Evidence the work is buildable: available code, a dataset or benchmark, real-time or open-source signals in the text. |
| **novelty** | A recency proxy — brand-new work scores highest, older work decays toward a small floor. |
| **attention** | Reserved for external attention signals. Currently a stub fixed at zero; it holds a slot in the formula without yet contributing. |
| **negative penalty** | The [negative-topic](./sourcing-and-classification.md) penalty, subtracted rather than added. |

## The formula

The components are combined as a weighted sum, then clamped to `[0, 100]`:

```text
final =  relevance        × 0.55
       + source_priority  × 0.10
       + implementation   × 0.10
       + attention        × 0.10
       + novelty          × 0.10
       - negative_penalty × 0.15
```

| Weight | Value |
|--------|-------|
| relevance | 0.55 |
| source_priority | 0.10 |
| implementation | 0.10 |
| attention | 0.10 |
| novelty | 0.10 |
| negative_penalty | 0.15 |

Relevance carries more than half the weight on purpose: this is a relevance radar,
and topical fit should dominate provenance, recency, and buzz combined. The negative
penalty is the only term that subtracts, and it is weighted heavily enough to pull a
weakly-relevant item down out of contention while still being *survivable* by an item
with strong genuine relevance.

The weights live in configuration, not code. Changing them is a policy decision, and
the project's rule is that no scoring formula is broadened without a regression test
pinning the old versus new behavior on a concrete item — so tuning stays honest and
its effects stay visible.

## From score to ring

Descending thresholds map the final score to a suggested ring. An item lands in the
highest ring whose threshold it clears:

| Suggested ring | Score ≥ |
|----------------|---------|
| Use | 90 |
| Prototype | 80 |
| Evaluate | 65 |
| Watch | 45 |
| Ignore | 0 |

The thresholds are set so `Use` and `Prototype` are genuinely hard to reach —
clearing 80 or 90 out of 100 requires strong relevance *and* corroborating signals
like available code or recency, not any single factor. Most items are expected to
settle into `Watch`, `Evaluate`, or `Ignore`, which is the intended shape: the rare
inner rings stay rare.

## Scoring only suggests

Three hard rules keep the number in its place. An irrelevant item is never promoted
by source priority alone. The source-priority boost is capped. A negative-topic
match never hard-deletes an item that has strong positive relevance. Together they
ensure the score is a *starting proposal* — it orders the candidate queue and offers
a default ring, but every item still passes under human eyes before any decision is
recorded. How that decision is made, and why it is kept independent of the score, is
the subject of the [curation workflow](./curation-workflow.md).
