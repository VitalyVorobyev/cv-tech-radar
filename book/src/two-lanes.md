# The two lanes

The radar runs as **two parallel monitoring lanes** over a single database. Both
share the five [rings](./radar-model.md) and the same skeptical curation discipline,
but they track fundamentally different objects and are never mixed into one
visualization.

- The **papers lane** watches research — one-shot publications, mostly from arXiv.
- The **ecosystem lane** watches software — the libraries the user adopts or is
  evaluating, followed by their releases over time.

## Why two lanes, not one

A paper and a library are different kinds of thing, and forcing them into one stream
distorts both.

A paper is a **one-shot event**. It appears once, is classified and scored once, and
either earns a place on the radar or does not. It does not change after publication.
The papers pipeline is therefore a funnel: many in, few out, each judged on its own.

A library is a **long-lived, re-polled entity**. It does not arrive and leave; it
persists, and the interesting thing about it is *change* — a new release, a major
version bump, a shift in what it supports. Modeling a library as a one-shot item
would either drop those changes or flood the feed with duplicates of the same
project. So the ecosystem lane treats each library as a durable record and emits its
version changes as a dated event stream.

Keeping the lanes separate lets each use the representation that fits it, while still
speaking the common language of rings.

## The papers lane

This is the pipeline the rest of the book describes: arXiv ingestion,
[deterministic classification](./sourcing-and-classification.md),
[multi-component scoring](./scoring.md), a candidate queue, curator decisions, and a
daily digest. Its unit is the item; its rhythm is the daily
[curation ritual](./curation-workflow.md).

## The ecosystem lane

The ecosystem lane is driven by a hand-maintained inventory of tracked projects.
Each entry names a project, marks its **status**, assigns it to a **capability**
quadrant and to radar tracks, and lists one or more **refs** — a ref being one
project on one registry.

- **Status** is either `adopted` (already in the stack) or `watchlist` (being
  evaluated upstream).
- **Capability** places the artifact in one of four ecosystem quadrants —
  imaging, ML runtimes, 3D/sensor visualization, and build tooling — the
  ecosystem's own analogue to the papers quadrants.
- **Refs** point at the registries where releases are visible: GitHub, PyPI,
  crates.io, and npm. One artifact often has several — a library tracked on both its
  GitHub repo and its package registry.

A collector polls each ref, compares the current version against the last version it
saw, and records a **release event** when they differ. The runner is idempotent —
re-polling an unchanged project emits nothing — and first-seen-safe — a newly added
project records its baseline without dumping its entire back-catalogue as fake news.
Each new event is then classified for relevance and severity, so a routine patch and
a major release are not treated alike.

## Seed rings

An artifact appears on the ecosystem radar immediately, before anyone curates it,
via a **seed ring** derived from its status:

| Status | Seed ring |
|--------|-----------|
| `adopted` | Use |
| `watchlist` | Watch |

The reasoning is direct: a library already in the stack is, by definition, something
you *use*; a library you are only evaluating is something you *watch*. A curator can
override the seed at any time — for instance, promoting a watchlist library to
`Prototype` when it ships a release worth a test-rig pass — but the seed means the
board is never empty and never waiting on a decision to be useful.

Curation here is intentionally lighter than the papers queue. Relevant release
events surface automatically; the curator glances at them and acts only when a
release genuinely warrants a ring change. Editing which libraries are tracked is a
configuration change, not a daily chore.
