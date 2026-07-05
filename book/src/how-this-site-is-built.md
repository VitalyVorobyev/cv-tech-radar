# How this site is built

The live radar you can browse and this book are two static artifacts published side
by side. Neither talks to a server at view time — and that is deliberate, because it
is what lets the public site exist without exposing the private pipeline behind it.

## A React app with a static mode

The radar's interface is a React application. In day-to-day private use it runs
against a small local backend that reads the SQLite database directly, offering the
full set of surfaces — the curator's queue, manual entry, settings, score debugging,
and the reading views.

For publishing, the same app has a **static mode**. In this mode there is no backend
at all. The app reads a pre-rendered **JSON snapshot** of the board and its views,
fetched as plain files. Every write path — recording a decision, adding an item,
changing configuration — is switched off, and the curator-only routes simply
resolve back to the public radar. What ships publicly is only ever the reading
experience described in [Reading the radar](./reading-the-radar.md).

## The snapshot is the curated board, minus Ignore

The published data is generated from the private database by a snapshot step
(`radar build-static`). It walks the current state and writes a small set of JSON
files: the radar board, the per-track grouping, the timeline window, a little
metadata, and one file per public item.

Two properties matter here. First, the snapshot contains only the **curated** board
— the result of the [curation workflow](./curation-workflow.md), not the raw feed.
Second, it **excludes every item whose latest decision is `Ignore`**. The slush pile
never leaves the private database; a public viewer sees only what a curator
deliberately kept. The result is deliberately tiny — a snapshot well under a few
hundred kilobytes — which is what makes fully static, backend-free hosting practical.

Publishing is therefore an explicit act: regenerate the snapshot from the private
database, build the app in static mode, and deploy. Nothing about the private radar
is exposed except the JSON that was intentionally rendered for the public.

## The book is an mdBook

The book you are reading is separate from the app. It is written as plain Markdown
chapters and rendered by **mdBook** into a static site. It documents the *method*;
it contains no private data and no snapshot — deliberately, so it can describe how
the radar decides without revealing what it currently holds.

## Both deployed to GitHub Pages

The radar's static bundle and this book are published together to GitHub Pages, the
book living at a sub-path beside the app. The build accounts for that sub-path
hosting so links and asset paths resolve correctly wherever the site is mounted.

The important line to hold onto: the public site is a *snapshot* of a private
system. The database, the raw payloads, the ignored items, and the curator's private
notes stay local; only an explicitly rendered, Ignore-free JSON view is ever
committed and served. For the actual commands and file layout, see the repository —
this chapter is meant to convey the shape, not to be a build script.
