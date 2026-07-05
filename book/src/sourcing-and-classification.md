# Sourcing & classification

Before anything can be ranked or curated, two things have to happen: candidates
have to come in, and each one has to be labeled with the tracks it belongs to. Both
steps are deliberately boring and deterministic — the interesting judgment is saved
for the human at the end.

## Where candidates come from

The primary source is **arXiv**, restricted to computer-vision categories (the
`cs.CV` feed, with room in the configuration for related categories such as
robotics and image/video processing when they are genuinely vision-relevant). Each
fetch pulls recent entries, stores the untouched source payload, and normalizes a
clean record alongside it. Storing the raw payload separately from the normalized
item means the fetch can be re-run without losing any downstream classification or
curator decision.

The source design leaves room for high-signal non-paper inputs — hand-picked RSS
and vendor feeds such as OpenCV, MVTec, NVIDIA developer and research posts,
selected camera and sensor vendors, and standards bodies. The guiding constraint is
to add *curated, high-signal* sources, never broad social-media scraping or fragile
crawlers. A manual entry path also exists so an item found by hand can be dropped
into the same pipeline.

Volume is reduced at every stage rather than at the end. A day begins with hundreds
of raw items and is meant to funnel down to a few daily-visible ones — the pipeline
is a filter, not an archive.

## Deterministic keyword classification

Classification maps an item onto the [radar tracks](./radar-model.md). It is plain,
inspectable keyword matching against the phrases each track declares — no model, no
embedding, no black box on the default path.

For every track, the item's title and abstract are scanned for that track's
positive keywords. A match in the **title** counts for more than a match in the
**body**, on the theory that a title term is a stronger statement of what the work
is actually about. A track that accumulates any positive weight is attached to the
item, and its matched keywords are recorded so the decision can be audited later.

Matching is phrase-aware. Keywords are matched on word boundaries and tolerate
hyphen/space variation, so `hand-eye` and `hand eye` both hit, but a keyword does
not fire on an unrelated substring. This precision is why several track keywords are
written as phrases (`camera calibration`, `lens distortion`) rather than bare words
(`calibration`, `distortion`) — the bare forms were observed false-positiving on
papers that used the word in an unrelated sense, and tightening the phrase removed
the noise without losing the real hits.

Because the whole step is deterministic, the same item always classifies the same
way, and any surprising label can be traced to the exact keyword that produced it.

## Negative topics: suppressing the noise

Positive keywords decide what an item *is about*; negative topics decide what the
radar *does not want*. These are phrases for adjacent fields that keep leaking into
a computer-vision feed — face recognition, person re-identification, medical
imaging, autonomous driving, remote sensing, image and video generation,
super-resolution, and vision-language-model evaluation, among others.

Negative topics do not hard-delete anything. A matched negative topic applies a
**score penalty**, and the penalty grows when several negative topics match at
once. The design is intentionally soft: an item with strong, genuine relevance to a
positive track can still survive a negative match, so a legitimately on-topic paper
that happens to mention a filtered field is not thrown away by accident. Nothing is
ever silently discarded — ignored items are kept for audit.

Two disciplines keep this list honest. Each negative phrase is chosen to fire on the
unwanted class *without* colliding with any positive track keyword — for example,
`autonomous driving` is filtered while `lidar` stays a valid industrial-3D-sensor
keyword. And the list grows empirically: entries are added in response to concrete
false positives observed in real candidate queues, not on speculation.

## What comes out

Each classified item carries its tracks, its matched positive and negative
keywords, and the raw material for [scoring](./scoring.md) — a relevance figure
derived from how strongly and how many tracks it matched, plus the negative penalty.
From here the numeric components are combined into a single score and a suggested
ring.
