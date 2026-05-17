# Ecosystem Radar

A second radar lane, parallel to the arXiv papers radar. Where the papers radar
tracks one-shot publications, the ecosystem radar tracks **software artifacts** —
the libraries the user *adopts* or *watches* — and surfaces their release /
version changes as a dated event stream.

Same rings (`Use` / `Prototype` / `Evaluate` / `Watch` / `Ignore`), same
skeptical curation discipline (see [CLAUDE.md](../CLAUDE.md)). The two lanes
never share a visualization: papers and packages are different objects.

## The inventory

`config/artifacts.yaml` is the hand-maintained list of tracked projects. It is
an *optional* config file — deployments without it load unchanged. Each entry:

| field              | meaning                                                            |
|--------------------|--------------------------------------------------------------------|
| `key`              | stable slug, the artifact's identity                               |
| `name`             | display name                                                       |
| `status`           | `adopted` (in the stack) or `watchlist` (evaluating upstream)       |
| `capability`       | radar quadrant: `cv-imaging` / `ml-runtimes` / `viz-3d-sensors` / `build-tooling` |
| `tracks`           | radar track names — must match `config/topics.yaml`                |
| `refs`             | one or more ecosystem refs: `{ecosystem, ref}`                     |
| `track_major_only` | emit events only for major version bumps                           |
| `extra_keywords`   | widen release-note relevance matching for this artifact            |

A *ref* is one project on one registry: `github` (`owner/repo`), `pypi`,
`crates`, or `npm` (package name). One artifact usually has several — e.g.
`opencv` is tracked on both GitHub and PyPI.

Curate this file to match what is actually used and watched. Adding a track
referenced by no `topics.yaml` track fails config validation.

## Pipeline

```
config/artifacts.yaml
        │  sync_artifacts()
        ▼
   artifacts ── artifact_refs ── artifact_state   (last-seen version, the diff baseline)
        │                            │  poll each ref
        │                            ▼
        │                       artifact_events   (dated release / version change)
        │  curator decision          │  classify_event()
        ▼                            ▼
 artifact_decisions            relevant / severity
```

- **Collectors** (`radar/collectors/ecosystem/`) — one module per registry,
  all exposing `fetch_ref(client, ref, *, token=None) -> EcosystemRefResult`.
  Shared HTTP plumbing in `base.py`: descriptive User-Agent, per-ecosystem rate
  gate, HTTP 429/5xx retry with backoff. A bad ref records a failure and the
  run continues — it never aborts.
- **Runner** (`runner.py`) — syncs artifacts from config, polls every enabled
  ref, diffs the current version against `artifact_state`. **Idempotent**
  (re-polling an unchanged ref emits nothing) and **first-seen-safe** (a newly
  added artifact records its baseline but never dumps its back-catalogue).
- **Event filter** (`event_filter.py`) — sets `relevant` / `severity` /
  `matched_keywords` on each new event. Reuses `keyword_matches` from the
  paper classifier. An event is relevant if it is a major release, OR the
  artifact is `adopted`, OR a track/`extra_keywords` keyword matched. Severity:
  `high` for major releases, `medium` for other relevant events, else `low`.
- **Decisions** (`artifact_decisions.py`) — append-only curator ring
  assignments, latest-wins, mirroring `radar/decisions.py`.

Before any decision, an artifact shows a **seed ring**: `adopted` → `Use`,
`watchlist` → `Watch`, so it appears on the board immediately.

## CLI

```bash
uv run radar fetch-ecosystem      # poll all artifacts, emit new release events
uv run radar ecosystem --days 7   # list recent events (--all to include non-relevant)
```

`fetch-ecosystem` accepts `--db-path` / `--config-dir`. GitHub polls
unauthenticated unless `CV_RADAR_GITHUB_TOKEN` is set (lifts the 60 req/hr cap;
~37 refs/run fits comfortably either way).

## API and UI

`radar/api/routes/ecosystem.py` mirrors the papers routes:
`/ecosystem/board`, `/ecosystem/events`, `/ecosystem/artifacts/{id}`, and
`POST /ecosystem/decisions`. The frontend `EcosystemView` reuses the polar
`RadarPlot` with the four fixed capability quadrants, plus a release-event feed.
The static bundle ships `ecosystem-board.json`, `ecosystem-events.json`, and
one `ecosystem-artifacts/<id>.json` per artifact.

## Known limitations

- **GitHub releases, not tags.** The GitHub collector polls `/releases`. Many
  projects publish via git tags only and create no GitHub *Release* objects —
  those refs resolve to "no version". Currently affects `candle`, `image`,
  `nalgebra`, `opencv-rust` (all also tracked on crates.io, which is correct).
- **Monorepos.** The GitHub collector takes the newest release across the whole
  repo. In a monorepo that may be a sibling sub-package — e.g. `vitejs/vite`
  resolves to a `plugin-legacy@…` release, not vite core. Prefer the registry
  ref (`npm`/`crates`) for monorepo projects.
- **No changelog on PyPI / crates.io.** Those registries expose no per-release
  notes, so event `summary`/`body` fall back to the package description.
  Release notes are only rich for GitHub refs.
