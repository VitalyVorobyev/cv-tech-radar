// Review inbox — the manual human gate over agent-authored proposals.
//
// `#/queue` with no date lands here: every pending proposal across every day,
// ranked by the backend, not date-scoped. A proposal is recorded but invisible
// on the radar until a human confirms it, so this is the only place the
// backlog gets cleared. The per-day candidate queue still lives at
// `#/queue/YYYY-MM-DD`; "browse by date" below reveals the date grid.
//
// The backlog is hundreds of items, so the two things that matter are bulk
// actions and keyboard flow: j/k to move, c to confirm, d to dismiss, x to
// select, then Confirm N / Dismiss N from the sticky bar.

import { useCallback, useId, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Candidate, ReviewItem, Ring } from "../lib/api";
import { api, ApiError } from "../lib/api";
import { useHotkeys } from "../lib/hotkeys";
import { Button } from "../ui/Button";
import { Chrome } from "../ui/Chrome";
import { CandidateRow } from "../ui/CandidateRow";
import { ContentDateGrid } from "../ui/ContentDateGrid";
import { ShortcutSheet } from "../ui/ShortcutSheet";
import { readUrlParams, writeUrlParams } from "../lib/urlState";

const RINGS: Ring[] = ["Use", "Prototype", "Evaluate", "Watch", "Ignore"];
const PAGE_SIZE = 50;

// A pending proposal renders through the same row as a candidate. The ring the
// row shows is the proposed one; `current_decision` stays null because nothing
// has been confirmed, and `proposal` is what flips the row into its
// "not on the radar" state.
function toCandidate(item: ReviewItem): Candidate {
  return {
    id: item.id,
    type: item.type,
    title: item.title,
    abstract: item.abstract,
    url: item.url,
    pdf_url: item.pdf_url,
    source: item.source,
    published_at: item.published_at,
    tracks: item.tracks,
    scores: item.scores,
    ring_suggested: item.proposal.ring,
    // The proposal's own reason is rendered in the panel's Reason field; a
    // duplicate rationale line above it would just be noise.
    pipeline_rationale: "",
    current_decision: null,
    llm_judgment: item.llm_judgment,
    proposal: item.proposal,
    previous_confirmed_ring: item.previous_confirmed_ring,
  };
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Unexpected error. Try again.";
}

function SkeletonRow() {
  return (
    <div
      className="skeleton-block"
      style={{ margin: "0 1.5rem", height: "2.25rem", marginBottom: "1px" }}
      aria-hidden="true"
    />
  );
}

const chipStyle = (active: boolean): React.CSSProperties => ({
  background: "transparent",
  border: "none",
  cursor: "pointer",
  padding: 0,
  fontFamily: "var(--font-mono)",
  fontSize: "var(--text-micro)",
  letterSpacing: "0.04em",
  color: active ? "var(--color-accent)" : "var(--color-muted)",
  borderBottom: active ? "1px solid var(--color-accent)" : "1px solid transparent",
});

const stripStyle: React.CSSProperties = {
  display: "flex",
  gap: "1.25rem",
  padding: "0.625rem 1.5rem",
  borderBottom: "1px solid var(--color-rule)",
  flexWrap: "wrap",
  alignItems: "center",
};

const labelStyle: React.CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: "var(--text-micro)",
  color: "var(--color-muted)",
};

export function ReviewInbox() {
  const filterId = useId();
  const queryClient = useQueryClient();

  // Filter state — mirrored to the query string, same as the date queue.
  const [q, setQ] = useState(() => readUrlParams().get("q") ?? "");
  const [ringFilter, setRingFilter] = useState<Ring | null>(() => {
    const r = readUrlParams().get("ring");
    return RINGS.includes(r as Ring) ? (r as Ring) : null;
  });
  const [trackFilter, setTrackFilter] = useState<string | null>(
    () => readUrlParams().get("track"),
  );
  const [includeIgnore, setIncludeIgnore] = useState(
    () => readUrlParams().get("include_ignore") === "true",
  );

  // UI state
  const [pageCount, setPageCount] = useState(1);
  const [selected, setSelected] = useState<ReadonlySet<number>>(new Set());
  const [focusedIndex, setFocusedIndex] = useState(0);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [shortcutOpen, setShortcutOpen] = useState(false);
  const [showDates, setShowDates] = useState(false);
  const [bulkError, setBulkError] = useState<string | undefined>();
  const [notice, setNotice] = useState<string | undefined>();

  const limit = PAGE_SIZE * pageCount;

  const { data, isLoading, isError, error, isFetching } = useQuery({
    queryKey: ["review", ringFilter, trackFilter, q, includeIgnore, limit],
    queryFn: () =>
      api.review({
        ring: ringFilter,
        track: trackFilter,
        q,
        include_ignore: includeIgnore,
        limit,
        offset: 0,
      }),
  });

  const items = useMemo(() => data?.items ?? [], [data]);
  const candidates = useMemo(() => items.map(toCandidate), [items]);
  const pendingTotal = data?.pending_total ?? 0;
  const counts = data?.counts;

  // Track chips come from the loaded rows — the endpoint does not enumerate
  // tracks, and an active filter must stay clickable even when it is the only
  // track left in view.
  const allTracks = useMemo(() => {
    const set = new Set(items.flatMap((it) => it.tracks));
    if (trackFilter) set.add(trackFilter);
    return Array.from(set).sort();
  }, [items, trackFilter]);

  function updateUrl(next: {
    q?: string;
    ring?: Ring | null;
    track?: string | null;
    includeIgnore?: boolean;
  }) {
    writeUrlParams({
      q: next.q ?? q,
      ring: next.ring !== undefined ? next.ring : ringFilter,
      track: next.track !== undefined ? next.track : trackFilter,
      include_ignore: (next.includeIgnore ?? includeIgnore) ? "true" : null,
    });
  }

  // A filter change invalidates the loaded window and the selection built on it.
  function resetPaging() {
    setPageCount(1);
    setSelected(new Set());
    setFocusedIndex(0);
    setExpandedId(null);
  }

  function refresh() {
    queryClient.invalidateQueries({ queryKey: ["review"] });
    queryClient.invalidateQueries({ queryKey: ["review-summary"] });
    queryClient.invalidateQueries({ queryKey: ["board"] });
  }

  const confirmOne = useMutation({
    mutationFn: (decisionId: number) => api.confirmReview(decisionId),
    onSuccess: () => {
      setBulkError(undefined);
      setNotice("Confirmed.");
      refresh();
    },
    onError: (err) => setBulkError(errorMessage(err)),
  });

  const dismissOne = useMutation({
    mutationFn: (itemId: number) => api.dismissReviewBulk([itemId]),
    onSuccess: (res) => {
      if (res.failed.length > 0) {
        setBulkError(res.failed[0]?.error ?? "Dismiss failed.");
      } else {
        setBulkError(undefined);
        setNotice("Dismissed.");
      }
      refresh();
    },
    onError: (err) => setBulkError(errorMessage(err)),
  });

  const selectedItems = useMemo(
    () => items.filter((it) => selected.has(it.id)),
    [items, selected],
  );

  const confirmBulk = useMutation({
    mutationFn: (decisionIds: number[]) => api.confirmReviewBulk(decisionIds),
    onSuccess: (res) => {
      // Anything that failed stays selected so it can be retried; everything
      // confirmed drops out of the selection with the next refetch.
      const failedDecisions = new Set(res.failed.map((f) => f.decision_id));
      setSelected(
        new Set(
          selectedItems
            .filter((it) => failedDecisions.has(it.proposal.decision_id))
            .map((it) => it.id),
        ),
      );
      if (res.failed.length > 0) {
        setNotice(undefined);
        setBulkError(
          `${res.confirmed.length} confirmed, ${res.failed.length} failed — ` +
            `${res.failed[0]?.error ?? "unknown error"}`,
        );
      } else {
        setBulkError(undefined);
        setNotice(`${res.confirmed.length} confirmed.`);
      }
      refresh();
    },
    onError: (err) => setBulkError(errorMessage(err)),
  });

  const dismissBulk = useMutation({
    mutationFn: (itemIds: number[]) => api.dismissReviewBulk(itemIds),
    onSuccess: (res) => {
      const failedItems = new Set(res.failed.map((f) => f.item_id));
      setSelected(new Set([...failedItems]));
      if (res.failed.length > 0) {
        setNotice(undefined);
        setBulkError(
          `${res.dismissed.length} dismissed, ${res.failed.length} failed — ` +
            `${res.failed[0]?.error ?? "unknown error"}`,
        );
      } else {
        setBulkError(undefined);
        setNotice(`${res.dismissed.length} dismissed.`);
      }
      refresh();
    },
    onError: (err) => setBulkError(errorMessage(err)),
  });

  const bulkPending = confirmBulk.isPending || dismissBulk.isPending;

  function toggleSelect(itemId: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  }

  const allLoadedSelected =
    items.length > 0 && items.every((it) => selected.has(it.id));

  function toggleSelectAll() {
    setSelected(allLoadedSelected ? new Set() : new Set(items.map((it) => it.id)));
  }

  function toggleExpand(id: number) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  // ---- hotkeys -------------------------------------------------------------

  const handleJ = useCallback(() => {
    setFocusedIndex((i) => Math.min(i + 1, candidates.length - 1));
  }, [candidates.length]);

  const handleK = useCallback(() => {
    setFocusedIndex((i) => Math.max(i - 1, 0));
  }, []);

  const handleEnter = useCallback(() => {
    const c = candidates[focusedIndex];
    if (c) toggleExpand(c.id);
  }, [candidates, focusedIndex]);

  const handleC = useCallback(() => {
    const it = items[focusedIndex];
    if (it) confirmOne.mutate(it.proposal.decision_id);
  }, [items, focusedIndex, confirmOne]);

  const handleD = useCallback(() => {
    const it = items[focusedIndex];
    if (it) dismissOne.mutate(it.id);
  }, [items, focusedIndex, dismissOne]);

  const handleX = useCallback(() => {
    const it = items[focusedIndex];
    if (it) toggleSelect(it.id);
  }, [items, focusedIndex]);

  // 1–5, u and mod+s act on the expanded panel; find it by its data attribute
  // rather than threading refs through the row.
  const panelEl = useCallback((): HTMLElement | null => {
    if (expandedId === null) return null;
    return document.querySelector<HTMLElement>(
      `[data-candidate-expanded="${expandedId}"]`,
    );
  }, [expandedId]);

  const handleRing = useCallback(
    (digit: "1" | "2" | "3" | "4" | "5") => {
      const ring = RINGS[Number(digit) - 1];
      if (!ring) return;
      panelEl()
        ?.querySelector<HTMLInputElement>(`input[value="${ring}"]`)
        ?.click();
    },
    [panelEl],
  );

  const handleU = useCallback(() => {
    panelEl()?.querySelector<HTMLInputElement>("input[type='checkbox']")?.click();
  }, [panelEl]);

  const handleModS = useCallback(() => {
    panelEl()?.querySelector<HTMLButtonElement>("[data-save='true']")?.click();
  }, [panelEl]);

  const handleSlash = useCallback(() => {
    document.getElementById(filterId)?.focus();
  }, [filterId]);

  const handleEscape = useCallback(() => {
    if (shortcutOpen) setShortcutOpen(false);
    else if (expandedId) setExpandedId(null);
    else if (selected.size > 0) setSelected(new Set());
  }, [shortcutOpen, expandedId, selected.size]);

  useHotkeys({
    j: handleJ,
    k: handleK,
    Enter: handleEnter,
    "1": () => handleRing("1"),
    "2": () => handleRing("2"),
    "3": () => handleRing("3"),
    "4": () => handleRing("4"),
    "5": () => handleRing("5"),
    u: handleU,
    c: handleC,
    d: handleD,
    x: handleX,
    "mod+s": handleModS,
    "/": handleSlash,
    "?": () => setShortcutOpen(true),
    Escape: handleEscape,
  });

  const hasFilters = Boolean(q || ringFilter || trackFilter);
  const showBar = selected.size > 0 || bulkError !== undefined || notice !== undefined;

  return (
    <div
      style={{
        minHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        maxWidth: "80rem",
        margin: "0 auto",
      }}
    >
      <Chrome
        filterSlot={
          <div style={{ display: "flex", alignItems: "baseline", gap: "1rem" }}>
            <label htmlFor={filterId} style={labelStyle}>
              search
            </label>
            <input
              id={filterId}
              type="search"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                updateUrl({ q: e.target.value });
                resetPaging();
              }}
              placeholder="Filter…"
              aria-label="Search pending proposals"
              className="queue-input queue-input--filter"
            />
          </div>
        }
      />

      {/* Headline: what is waiting, and the escape hatch to the date queue */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          padding: "0.625rem 1.5rem",
          borderTop: "1px solid var(--color-rule)",
          borderBottom: "1px solid var(--color-rule)",
          flexWrap: "wrap",
          gap: "1rem",
        }}
      >
        <div style={{ ...labelStyle, fontSize: "var(--text-small)" }}>
          {pendingTotal} pending
          {hasFilters ? " (filtered)" : ""} · {items.length} shown
          {isFetching ? " · refreshing…" : ""}
        </div>
        <div style={{ display: "flex", gap: "1.25rem", alignItems: "baseline" }}>
          <button
            type="button"
            onClick={() => setShowDates((v) => !v)}
            aria-expanded={showDates}
            style={chipStyle(showDates)}
          >
            browse by date
          </button>
          <span style={labelStyle}>
            j/k navigate · c confirm · d dismiss · x select · ? shortcuts
          </span>
        </div>
      </div>

      {showDates && (
        <div style={{ padding: "1rem 1.5rem", borderBottom: "1px solid var(--color-rule)" }}>
          <ContentDateGrid
            kind="queue"
            onPick={(picked) => {
              window.location.hash = `#/queue/${picked}${window.location.search}`;
            }}
          />
        </div>
      )}

      {/* Ring chips — counts are unfiltered pending totals per proposed ring */}
      <div role="group" aria-label="Ring filters" style={stripStyle}>
        <span style={labelStyle}>ring:</span>
        {RINGS.map((r) => {
          const active = ringFilter === r;
          const count = counts?.[r];
          return (
            <button
              key={r}
              type="button"
              onClick={() => {
                const next = active ? null : r;
                setRingFilter(next);
                // Selecting Ignore without the toggle would always be empty.
                const nextInclude = next === "Ignore" ? true : includeIgnore;
                setIncludeIgnore(nextInclude);
                updateUrl({ ring: next, includeIgnore: nextInclude });
                resetPaging();
              }}
              aria-pressed={active}
              style={chipStyle(active)}
            >
              {r}
              {count !== undefined ? ` ${count}` : ""}
            </button>
          );
        })}
        <label
          style={{
            ...labelStyle,
            display: "inline-flex",
            alignItems: "center",
            gap: "0.375rem",
            cursor: "pointer",
            userSelect: "none",
            color: includeIgnore ? "var(--color-accent)" : "var(--color-muted)",
          }}
        >
          <input
            type="checkbox"
            checked={includeIgnore}
            onChange={(e) => {
              setIncludeIgnore(e.target.checked);
              if (!e.target.checked && ringFilter === "Ignore") setRingFilter(null);
              updateUrl({
                includeIgnore: e.target.checked,
                ring: !e.target.checked && ringFilter === "Ignore" ? null : undefined,
              });
              resetPaging();
            }}
          />
          include Ignore
        </label>
      </div>

      {/* Track chips */}
      {allTracks.length > 0 && (
        <div role="group" aria-label="Track filters" style={stripStyle}>
          <span style={labelStyle}>track:</span>
          {allTracks.map((t) => {
            const active = trackFilter === t;
            return (
              <button
                key={t}
                type="button"
                onClick={() => {
                  const next = active ? null : t;
                  setTrackFilter(next);
                  updateUrl({ track: next });
                  resetPaging();
                }}
                aria-pressed={active}
                style={chipStyle(active)}
              >
                {t}
              </button>
            );
          })}
        </div>
      )}

      {/* Bulk selection header */}
      {items.length > 0 && (
        <div style={{ ...stripStyle, gap: "1rem" }}>
          <label
            style={{
              ...labelStyle,
              display: "inline-flex",
              alignItems: "center",
              gap: "0.5rem",
              cursor: "pointer",
              userSelect: "none",
            }}
          >
            <input
              type="checkbox"
              checked={allLoadedSelected}
              onChange={toggleSelectAll}
              aria-label="Select all loaded proposals"
            />
            select all {items.length} loaded
          </label>
          {selected.size > 0 && (
            <span style={labelStyle}>{selected.size} selected</span>
          )}
        </div>
      )}

      <main style={{ flex: 1 }}>
        {isLoading && (
          <div
            aria-busy="true"
            aria-label="Loading pending proposals"
            style={{ padding: "1rem 0", display: "flex", flexDirection: "column", gap: "1px" }}
          >
            {Array.from({ length: 8 }, (_, i) => (
              <SkeletonRow key={i} />
            ))}
          </div>
        )}

        {isError && (
          <div
            role="alert"
            style={{
              padding: "3rem 1.5rem",
              fontFamily: "var(--font-display)",
              fontStyle: "italic",
              color: "var(--color-muted)",
            }}
          >
            Could not load the review inbox:{" "}
            {error instanceof Error ? error.message : "unknown error"}.
          </div>
        )}

        {!isLoading && !isError && items.length === 0 && (
          <div
            style={{
              padding: "3rem 1.5rem",
              fontFamily: "var(--font-display)",
              fontStyle: "italic",
              fontSize: "var(--text-display-l)",
              fontWeight: 400,
              color: "var(--color-muted)",
              lineHeight: "1.4",
            }}
          >
            {hasFilters
              ? "No pending proposals match the current filters."
              : "Inbox zero. Nothing is waiting for a human decision."}
          </div>
        )}

        {!isLoading && !isError && items.length > 0 && (
          <div
            role="list"
            aria-label="Pending proposals"
            style={{ borderTop: "1px solid var(--color-rule)" }}
          >
            {candidates.map((candidate, i) => {
              const checked = selected.has(candidate.id);
              return (
                <div
                  key={candidate.id}
                  role="listitem"
                  data-candidate-id={candidate.id}
                  data-candidate-expanded={
                    expandedId === candidate.id ? candidate.id : undefined
                  }
                  style={{
                    display: "grid",
                    gridTemplateColumns: "2.5rem minmax(0, 1fr)",
                    alignItems: "stretch",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "center",
                      paddingTop: "0.85rem",
                      borderBottom: "1px solid var(--color-rule)",
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleSelect(candidate.id)}
                      aria-label={`Select ${candidate.title}`}
                      style={{ alignSelf: "flex-start" }}
                    />
                  </div>
                  <CandidateRow
                    candidate={candidate}
                    expanded={expandedId === candidate.id}
                    focused={focusedIndex === i}
                    onToggle={() => {
                      setFocusedIndex(i);
                      toggleExpand(candidate.id);
                    }}
                    onConfirm={() => {
                      setExpandedId(null);
                      setNotice("Confirmed.");
                    }}
                    onDismiss={() => {
                      setExpandedId(null);
                      setNotice("Dismissed.");
                    }}
                  />
                </div>
              );
            })}
          </div>
        )}

        {!isLoading && !isError && items.length > 0 && items.length < pendingTotal && (
          <div style={{ padding: "1.25rem 1.5rem" }}>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPageCount((n) => n + 1)}
              disabled={isFetching}
            >
              {isFetching
                ? "Loading…"
                : `Load ${Math.min(PAGE_SIZE, pendingTotal - items.length)} more`}
            </Button>
          </div>
        )}
      </main>

      {/* Sticky bulk action bar */}
      {showBar && (
        <div
          role="group"
          aria-label="Bulk actions"
          style={{
            position: "sticky",
            bottom: 0,
            zIndex: 10,
            display: "flex",
            alignItems: "center",
            gap: "1rem",
            flexWrap: "wrap",
            padding: "0.625rem 1.5rem",
            borderTop: "1px solid var(--color-rule)",
            background: "var(--color-paper)",
          }}
        >
          {selected.size > 0 && (
            <>
              <span style={labelStyle}>{selected.size} selected</span>
              <Button
                variant="primary"
                size="sm"
                disabled={bulkPending}
                aria-busy={confirmBulk.isPending}
                onClick={() =>
                  confirmBulk.mutate(
                    selectedItems.map((it) => it.proposal.decision_id),
                  )
                }
              >
                {confirmBulk.isPending ? "Confirming…" : `Confirm ${selected.size}`}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={bulkPending}
                aria-busy={dismissBulk.isPending}
                style={{ color: "var(--color-muted)", textDecoration: "none" }}
                onClick={() =>
                  dismissBulk.mutate(selectedItems.map((it) => it.id))
                }
              >
                {dismissBulk.isPending ? "Dismissing…" : `Dismiss ${selected.size}`}
              </Button>
              <button
                type="button"
                onClick={() => setSelected(new Set())}
                style={chipStyle(false)}
              >
                clear
              </button>
            </>
          )}
          {bulkError && (
            <span
              role="alert"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-accent)",
              }}
            >
              {bulkError}
            </span>
          )}
          {!bulkError && notice && <span style={labelStyle}>{notice}</span>}
          {(bulkError || notice) && (
            <button
              type="button"
              aria-label="Dismiss status message"
              onClick={() => {
                setBulkError(undefined);
                setNotice(undefined);
              }}
              style={{ ...chipStyle(false), marginLeft: "auto" }}
            >
              ✕
            </button>
          )}
        </div>
      )}

      <ShortcutSheet open={shortcutOpen} onClose={() => setShortcutOpen(false)} />
    </div>
  );
}
