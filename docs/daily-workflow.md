# Daily Workflow

The radar is built around one short daily ritual: read a candidate queue, fill in decisions,
apply them in bulk, and produce a short digest. Claude (via the `cv-radar-curator` skill) is
the proposer; you are the editor. The deterministic Python pipeline does the rest.

> Running the radar UI? See [Run the UI locally](../README.md#run-the-ui-locally)
> for the two-terminal `radar serve` + `npm run dev` recipe.

## Daily flow

Two umbrella commands wrap the deterministic stages around a single curation step:

```bash
uv run radar daily-fetch                 # fetch-arxiv → classify → candidates → fetch-ecosystem
# Curate via the cv-radar-curator skill — fill in TODO blocks in the candidate Markdown.
uv run radar daily-publish reports/candidates/$(date -I).md   # apply → digest
```

`daily-fetch` runs everything inside one SQLite transaction and prints a summary of
fetched / new / updated / skipped-old counts plus the candidate Markdown path. Pass
`--max-pages N` if you need to walk past the default 100-result arXiv cap.

It also polls the **ecosystem radar** — software artifacts (libraries) tracked
across GitHub / PyPI / crates.io / npm — and prints an `ecosystem:` line with the
new release-event count. See the [Ecosystem lane](#ecosystem-lane) below.

`daily-publish` applies the YAML blocks from the candidate Markdown and immediately
writes the digest. Use `--dry-run` to validate parsing without recording decisions
(the digest step is skipped in dry-run mode).

The individual stages remain available — `fetch-arxiv`, `classify`, `candidates`,
`apply`, `digest` — if you need to re-run a single step:

```bash
uv run radar fetch-arxiv --days 1
uv run radar classify --date today
uv run radar candidates --date today
uv run radar apply reports/candidates/$(date -I).md --dry-run
uv run radar apply reports/candidates/$(date -I).md
uv run radar digest --date today
```

Outputs:

- Candidate queue: `reports/candidates/YYYY-MM-DD.md` and `data/exports/candidates/YYYY-MM-DD.json`.
- Decisions: rows in `radar_decisions` (latest-wins by `created_at`).
- Digest: `reports/digests/YYYY-MM-DD.md` and `data/exports/digests/YYYY-MM-DD.json`; one
  `digests` row per `(kind, date)` — re-running overwrites the same row.

All four output directories are gitignored.

## Filling a decision

Each candidate in the Markdown ends with:

```markdown
### Claude decision

TODO
```

The curator replaces `TODO` with a fenced YAML block:

```yaml
ring: Prototype
tracks: [Calibration, 3D Geometry]
reason: Has code and an industrial-grade dataset; worth a test rig pass.
action: Run on our calibration rig next sprint.
uncertain: false
```

Field reference (one Pydantic model: `DecisionProposal`):

- `ring` — required. One of `Use`, `Prototype`, `Evaluate`, `Watch`, `Ignore`.
- `reason` — required, free text. Kept short and skeptical (CLAUDE.md rule 3).
- `tracks` — optional. Defaults to the classifier's tracks if omitted. Override only when
  the classifier disagrees with the curator.
- `action` — optional, default `""`. Concrete next step or `""` for Ignore.
- `uncertain` — optional, default `false`. Surfaces in the digest's
  *Uncertainty / Open Questions* section regardless of ring (CLAUDE.md rule 4).

Leave the block as `TODO` for any candidate you have not reviewed — `apply` skips them
and reports a skip count without writing anything.

## Catching up after a gap

`radar digest --days N` widens the window to the trailing N days, queried by
`Item.published_at`. A late-applied decision still lands in the digest for the day the
item was published, not the day you curated it — this is intentional so the
historical record stays anchored to the source date.

```bash
uv run radar digest --date today --days 7
```

## Ecosystem lane

Alongside the arXiv papers radar, `daily-fetch` polls a second lane: the
**ecosystem radar**, a hand-maintained inventory of software artifacts the user
adopts or watches (`config/artifacts.yaml`). It diffs each artifact's latest
version across GitHub / PyPI / crates.io / npm and records new release events.
See [ecosystem.md](ecosystem.md) for the architecture.

Curation here is deliberately lighter than the papers queue — there is no
per-event YAML decision block:

- New **relevant** release events appear automatically in the digest's
  `## Ecosystem` section; the relevance filter does the triage.
- The curator glances at that section. Most days nothing is needed.
- When a release warrants a ring change — e.g. a watchlist library cuts a major
  release worth prototyping — record it directly against the artifact:

  ```bash
  uv run radar artifact-decide candle --ring Prototype \
    --reason "Major release with a stable inference API; worth a test rig pass."
  ```

Standalone commands, outside the daily run:

```bash
uv run radar fetch-ecosystem          # poll all artifacts now
uv run radar ecosystem --days 7       # list recent release events (--all for non-relevant)
```

Editing the inventory — adding or removing a tracked library — is a config edit
to `config/artifacts.yaml`, not a daily action.

## Re-running and idempotency

- `radar apply` is **append-only**. Re-running on the same Markdown adds a second
  decision row per item and prints a warning per duplicate. Latest decision wins for
  digest and `radar decisions` output. If you want to undo a decision, edit the
  Markdown and re-apply — the new row will supersede the old one.
- `radar digest` upserts a single `digests` row per `(kind, date)`. Safe to re-run.

## Troubleshooting

`radar apply` parse errors include the candidate heading and line number:

```
Candidate 3: Generic Diffusion-Based Detector (line 84): ring: Input should be 'Use',
'Prototype', 'Evaluate', 'Watch' or 'Ignore'
```

Common failures:

- **Missing `- Item ID:` bullet** — the renderer adds this automatically; only happens
  if you authored the Markdown by hand. Add the line.
- **`ring: Maybe` (typo)** — Pydantic rejects unknown rings; fix the value.
- **Unterminated `` ```yaml `` fence** — close the fence.
- **Free-form notes immediately under `### Claude decision`** — start the YAML fence
  on the first non-blank line; put any free-form notes *after* the closing `` ``` ``.

## Where Claude fits

The `cv-radar-curator` skill is the read-side: it consumes `reports/candidates/*.md`
plus `radar decisions` history and produces filled-in YAML blocks. The skill enforces
the curation rules in [CLAUDE.md](../CLAUDE.md): no famous-author promotion, Watch over
Evaluate for speculative items, Prototype only when there is code/data/clear test path,
short reasons, explicit uncertainty.
