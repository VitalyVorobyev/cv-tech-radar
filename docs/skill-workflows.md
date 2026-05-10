# Running CV Radar With Project Skills

The project-specific Codex skills are installed in:

```text
$CODEX_HOME/skills/
```

Implemented skills:

- `cv-radar-curator`
- `cv-radar-scoring-evaluator`
- `cv-radar-source-onboarding`
- `cv-radar-digest-writer`
- `cv-radar-atlas-bridge`

If a running Codex session does not show newly installed skills, start a fresh session
or explicitly name the skill in the request. The skill files are local agent
instructions; they do not change the Python package by themselves.

## Baseline Project Commands

Sync the environment:

```bash
uv sync --locked --all-groups
```

Run validation:

```bash
uv run pytest
uv run ruff check .
uv run ruff format . --check
```

Run a real arXiv pipeline smoke test:

```bash
rm -rf .tmp-real-run
mkdir -p .tmp-real-run/reports .tmp-real-run/exports

uv run radar init-db --db-path .tmp-real-run/radar.sqlite
uv run radar fetch-arxiv --days 365 --max-results 100 --db-path .tmp-real-run/radar.sqlite

latest_date=$(
  uv run python - <<'PY'
import sqlite3
conn = sqlite3.connect(".tmp-real-run/radar.sqlite")
print(conn.execute("select date(max(published_at)) from items").fetchone()[0])
PY
)

uv run radar classify --date "$latest_date" --db-path .tmp-real-run/radar.sqlite
uv run radar candidates \
  --date "$latest_date" \
  --db-path .tmp-real-run/radar.sqlite \
  --reports-dir .tmp-real-run/reports \
  --exports-dir .tmp-real-run/exports
```

Inspect:

```bash
sed -n '1,220p' ".tmp-real-run/reports/$latest_date.md"
```

## Workflow 1: Curate A Candidate Queue

Use skill: `cv-radar-curator`

Example request:

```text
Use cv-radar-curator. Review .tmp-real-run/reports/2026-05-07.md.
Assign rings, write concise decision reasons, identify noise patterns, and list
which items should become Watch/Evaluate/Ignore.
```

Current project limitation:

- Decisions are still Markdown/manual.
- The next implementation task is `radar decide`, which will persist decisions in SQLite.

Expected output:

- Short decision table.
- Noise patterns found.
- Candidate actions.
- Suggested scoring fixes, only when justified by examples.

## Workflow 2: Tune Scoring

Use skill: `cv-radar-scoring-evaluator`

Example request:

```text
Use cv-radar-scoring-evaluator. Compare the current candidate queue against the
top SQLite classification scores. Find false positives and propose the smallest
keyword/threshold changes. Add regression tests for any scoring change.
```

Useful commands:

```bash
uv run python - <<'PY'
import sqlite3
conn = sqlite3.connect(".tmp-real-run/radar.sqlite")
for row in conn.execute("""
select item_classifications.final_score,
       item_classifications.recommended_ring,
       item_classifications.tracks_json,
       items.title
from items
join item_classifications on item_classifications.item_id = items.id
order by item_classifications.final_score desc
limit 25
"""):
    print(row)
PY
```

Expected output:

- Before/after score behavior.
- Regression fixtures for concrete false positives/false negatives.
- No broad formula rewrite unless evidence demands it.

## Workflow 3: Add A Source

Use skill: `cv-radar-source-onboarding`

Example request:

```text
Use cv-radar-source-onboarding. Add a pilot RSS source for OpenCV releases.
Inspect the feed shape, update config, implement the smallest fetch path, and add
tests for duplicates and failed feeds.
```

Expected output:

- Source quality assessment.
- Config change in `config/sources.yaml`.
- Fetch/normalization code.
- Tests for malformed feeds, missing dates, duplicates, and source failure.

## Workflow 4: Write A Digest

Use skill: `cv-radar-digest-writer`

Example request:

```text
Use cv-radar-digest-writer. From the accepted decisions for YYYY-MM-DD, write a
short daily digest with Radar Changes, Watch, Ignore/noise patterns, and Atlas
candidates. Do not promote raw candidates.
```

Current project limitation:

- Digest writing should wait until decisions are explicit.
- Until `radar decide` exists, use reviewed candidate Markdown as the decision source.

Expected output:

- Short private Markdown digest.
- Uncertainty called out explicitly.
- No public-ready claims unless asked.

## Workflow 5: Promote To Atlas Candidate

Use skill: `cv-radar-atlas-bridge`

Example request:

```text
Use cv-radar-atlas-bridge. Evaluate these accepted radar items for Atlas
candidate status. Separate durable concepts from one-off papers and list missing
evidence before anything becomes public-facing.
```

Expected output:

- Promote / keep-in-radar / reject decision.
- Evidence and open questions.
- Private caveats separated from any public angle.

## Recommended Development Sequence

1. Run the real arXiv smoke test.
2. Use `cv-radar-scoring-evaluator` to tune false positives.
3. Implement `radar decide`.
4. Use `cv-radar-curator` to review real queues into persisted decisions.
5. Add one RSS source with `cv-radar-source-onboarding`.
6. Generate digest drafts with `cv-radar-digest-writer`.
7. Use `cv-radar-atlas-bridge` only for explicitly accepted, durable items.
