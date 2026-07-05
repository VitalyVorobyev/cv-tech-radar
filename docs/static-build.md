# Public static build of the radar

This page describes how to produce a no-backend build of the radar UI that
can be uploaded to a personal website. Only the **public views** are
included — Radar board, Tracks, Timeline. Curator surfaces (queue, manual
add, settings, score-debug, digest, jobs) are stripped at build time and
their endpoints reject calls.

## Pipeline

The build is two commands. The first pre-renders the radar's current state
into JSON files under `frontend/public/data/`. The second runs the Vite build
with the static-mode flag.

```bash
# 1. Snapshot the radar state from SQLite.
uv run radar build-static --target frontend/public/data

# 2. Build the React app in static mode.
cd frontend && bun install    # bun is the canonical package manager
bun run build:static          # → frontend/dist/
```

`bun run build:static` runs `tsc -b && vite build --mode static`, which loads
`frontend/.env.static` (sets `VITE_STATIC=1`). The build emits to
`frontend/dist/`. Upload that directory to your host.

## Hosting at a subpath

If the radar lives under a path other than `/`, set `VITE_BASE_PATH` before
the Vite build:

```bash
VITE_BASE_PATH=/cv-tech-radar/ bun run build:static
```

The same env var feeds both Vite's asset paths (`<script src="…">`) and the
JSON-fetch URLs (`${BASE_URL}data/*.json`). No code change needed for
relocation.

## What gets emitted

```
frontend/public/data/
├── board.json     # BoardResponse (no Ignore items)
├── tracks.json    # { tracks: [{ id, name, item_ids: [...] }] }
├── timeline.json  # TimelineResponse (last N ISO weeks)
├── meta.json      # generated_at, ring_counts, tracks
└── items/<id>.json  # one ItemDetailOut per public item
```

`--weeks` (default `26`) controls the timeline window. The bundle excludes
every item whose latest decision is **Ignore** — public viewers never see
the slush pile. Today the bundle is well under 200 KB.

## Refreshing the snapshot

`build-static` reads the local SQLite DB (`data/radar.sqlite`) directly, so
each refresh is a re-run of the two commands above. No CI yet — the build
is on-demand. The bundle is regenerated atomically per file (no partial
state).

## What's stripped in static mode

- Routes: only `#/radar`, `#/tracks`, `#/timeline` resolve. Every other hash
  (`#/queue`, `#/manual-add`, `#/settings`, `#/digest`, `#/pipeline`,
  `#/score-debug`) silently falls back to `#/radar`.
- Nav: the top tabs only show Radar / Tracks / Timeline.
- Item panel: Promote/Demote buttons and the near-duplicates section are
  hidden.
- API calls: any write endpoint (`postDecision`, `postManualItem`, config
  PUTs, jobs) rejects with `ApiError(status=405)`. Public views never reach
  these paths because the routes are gone.

## Verification

After running both commands:

```bash
# Open the build locally — http://localhost:4173/
cd frontend && bun run preview
```

Browser checks:

1. `#/radar` renders the radar plot with all four rings populated.
2. `#/tracks` and `#/timeline` render.
3. DevTools → Network shows only static-asset fetches plus
   `data/board.json`, `data/timeline.json`, and `data/items/<id>.json` when
   you click a dot. Zero `/api/*` requests.
4. Hash `#/queue` or `#/settings` redirects to `#/radar`.

For the backend bundle writer:

```bash
uv run pytest tests/test_static_bundle.py -q
uv run radar build-static --target /tmp/cv-radar-snapshot
jq '.counts' /tmp/cv-radar-snapshot/board.json
```
