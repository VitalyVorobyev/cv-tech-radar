// Main queue view — the only view in Phase A.
// Renders the candidate list, filter bar, hotkeys, and shortcut sheet.
// Extension points: Chrome accepts a filterSlot; app.tsx can switch views on URL hash.

import { useState, useCallback, useId } from "react";
import { useQuery } from "@tanstack/react-query";
import type { Candidate } from "../lib/api";
import { api } from "../lib/api";
import { useHotkeys } from "../lib/hotkeys";
import { Chrome } from "../ui/Chrome";
import { CandidateRow } from "../ui/CandidateRow";
import { ShortcutSheet } from "../ui/ShortcutSheet";
import type { Ring } from "../lib/api";
import { writeUrlParams } from "../lib/urlState";

const RINGS: Ring[] = ["Use", "Prototype", "Evaluate", "Watch", "Ignore"];

// Skeleton row shown during loading
function SkeletonRow({ index }: { index: number }) {
  return (
    <div
      key={index}
      className="skeleton-block"
      style={{
        margin: "0 1.5rem",
        height: "2.25rem",
        marginBottom: "1px",
      }}
      aria-hidden="true"
    />
  );
}

function filterCandidates(
  candidates: Candidate[],
  q: string,
  ringFilter: Ring | null,
  trackFilter: string | null,
): Candidate[] {
  const ql = q.toLowerCase();
  return candidates.filter((c) => {
    if (ringFilter) {
      const activeRing = c.current_decision?.ring ?? c.ring_suggested;
      if (activeRing !== ringFilter) return false;
    }
    if (trackFilter && !c.tracks.some((t) => t === trackFilter)) return false;
    if (ql) {
      const hay = `${c.title} ${c.tracks.join(" ")} ${c.source}`.toLowerCase();
      if (!hay.includes(ql)) return false;
    }
    return true;
  });
}

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function readDateParam(): string {
  const v = new URLSearchParams(window.location.search).get("date");
  if (!v) return "today";
  return v === "today" || DATE_RE.test(v) ? v : "today";
}

export function QueueView() {
  const filterId = useId();
  const dateId = useId();

  // Date is part of the route — drives the query and the empty-state copy.
  const [date, setDate] = useState<string>(readDateParam);

  // Server state — date is part of the cache key so changing it refetches.
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["queue", date],
    queryFn: () => api.queue(date),
  });

  // UI state
  const [focusedIndex, setFocusedIndex] = useState(0);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [shortcutOpen, setShortcutOpen] = useState(false);

  // Filter state — synced to URL search params for shareability
  const [q, setQ] = useState(() => new URLSearchParams(window.location.search).get("q") ?? "");
  const [ringFilter, setRingFilter] = useState<Ring | null>(() => {
    const r = new URLSearchParams(window.location.search).get("ring");
    return RINGS.includes(r as Ring) ? (r as Ring) : null;
  });
  const [trackFilter, setTrackFilter] = useState<string | null>(
    () => new URLSearchParams(window.location.search).get("track"),
  );

  function updateUrl(
    newQ: string,
    newRing: Ring | null,
    newTrack: string | null,
    newDate: string,
  ) {
    writeUrlParams(
      { date: newDate, q: newQ, ring: newRing, track: newTrack },
      { date: "today" },
    );
  }

  const candidates = data?.candidates ?? [];
  const visible = filterCandidates(candidates, q, ringFilter, trackFilter);

  // Collect all unique tracks for filter chips
  const allTracks = Array.from(new Set(candidates.flatMap((c) => c.tracks))).sort();

  // Stats for footer
  const reviewed = candidates.filter((c) => c.current_decision !== null).length;
  const uncertain = candidates.filter(
    (c) => c.current_decision?.uncertain === true,
  ).length;

  function toggleExpand(id: number) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  // Hotkey handlers
  const handleJ = useCallback(() => {
    setFocusedIndex((i) => Math.min(i + 1, visible.length - 1));
  }, [visible.length]);

  const handleK = useCallback(() => {
    setFocusedIndex((i) => Math.max(i - 1, 0));
  }, []);

  const handleEnter = useCallback(() => {
    const c = visible[focusedIndex];
    if (c) toggleExpand(c.id);
  }, [visible, focusedIndex]);

  const handleRing = useCallback(
    (digit: "1" | "2" | "3" | "4" | "5") => {
      const ringMap: Record<string, Ring> = {
        "1": "Use",
        "2": "Prototype",
        "3": "Evaluate",
        "4": "Watch",
        "5": "Ignore",
      };
      const c = visible[focusedIndex];
      if (!c || c.id !== expandedId) return;
      // Find the ring picker radio for the mapped ring and click it
      const ring = ringMap[digit];
      if (!ring) return;
      const row = document.querySelector<HTMLElement>(`[aria-label="${c.title}, ring ${c.current_decision?.ring ?? c.ring_suggested}"]`);
      if (!row) return;
      const radio = row
        .closest("[data-candidate-id]")
        ?.querySelector<HTMLInputElement>(`input[value="${ring}"]`);
      radio?.click();
    },
    [visible, focusedIndex, expandedId],
  );

  const handleU = useCallback(() => {
    const c = visible[focusedIndex];
    if (!c || c.id !== expandedId) return;
    const checkbox = document.querySelector<HTMLInputElement>(
      `[data-candidate-expanded="${c.id}"] input[type="checkbox"]`,
    );
    checkbox?.click();
  }, [visible, focusedIndex, expandedId]);

  const handleModS = useCallback(() => {
    if (!expandedId) return;
    const saveBtn = document.querySelector<HTMLButtonElement>(
      `[data-candidate-expanded="${expandedId}"] [data-save="true"]`,
    );
    saveBtn?.click();
  }, [expandedId]);

  const handleSlash = useCallback(() => {
    document.getElementById(filterId)?.focus();
  }, [filterId]);

  const handleQuestion = useCallback(() => setShortcutOpen(true), []);

  const handleEscape = useCallback(() => {
    if (shortcutOpen) {
      setShortcutOpen(false);
    } else if (expandedId) {
      setExpandedId(null);
    }
  }, [shortcutOpen, expandedId]);

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
    "mod+s": handleModS,
    "/": handleSlash,
    "?": handleQuestion,
    Escape: handleEscape,
  });

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
            <label
              htmlFor={dateId}
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-muted)",
              }}
            >
              date
            </label>
            <input
              id={dateId}
              type="date"
              value={date === "today" ? new Date().toISOString().slice(0, 10) : date}
              onChange={(e) => {
                const next = e.target.value || "today";
                setDate(next);
                updateUrl(q, ringFilter, trackFilter, next);
              }}
              aria-label="Queue date"
              className="queue-input queue-input--date"
            />
            <input
              id={filterId}
              type="search"
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                updateUrl(e.target.value, ringFilter, trackFilter, date);
              }}
              placeholder="Filter…"
              aria-label="Filter candidates"
              className="queue-input queue-input--filter"
            />
          </div>
        }
      />

      {/* Top stats bar — counts on the left, hotkey hint on the right */}
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
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-small)",
            color: "var(--color-muted)",
          }}
        >
          {reviewed} reviewed · {Math.max(0, candidates.length - reviewed)} still TODO
          {uncertain > 0 ? ` · ${uncertain} uncertain` : ""}
        </div>
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
          }}
        >
          j/k navigate · enter expand · ? shortcuts
        </div>
      </div>

      {/* Ring legend + track filter strip */}
      {!isLoading && !isError && candidates.length > 0 && (
        <div
          role="group"
          aria-label="Ring legend and track filters"
          style={{
            display: "flex",
            gap: "1.25rem",
            padding: "0.625rem 1.5rem",
            borderBottom: "1px solid var(--color-rule)",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
            }}
          >
            ring:
          </span>
          {RINGS.map((r) => {
            const active = ringFilter === r;
            return (
              <button
                key={r}
                onClick={() => {
                  const next = active ? null : r;
                  setRingFilter(next);
                  updateUrl(q, next, trackFilter, date);
                }}
                aria-pressed={active}
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  padding: 0,
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-micro)",
                  letterSpacing: "0.04em",
                  color: active ? "var(--color-accent)" : "var(--color-muted)",
                  borderBottom: active
                    ? "1px solid var(--color-accent)"
                    : "1px solid transparent",
                  textTransform: "lowercase",
                }}
              >
                {r}
              </button>
            );
          })}

          {allTracks.length > 0 && (
            <>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-micro)",
                  color: "var(--color-muted)",
                  marginLeft: "0.5rem",
                }}
              >
                track:
              </span>
              {allTracks.map((t) => {
                const active = trackFilter === t;
                return (
                  <button
                    key={t}
                    onClick={() => {
                      const next = active ? null : t;
                      setTrackFilter(next);
                      updateUrl(q, ringFilter, next, date);
                    }}
                    aria-pressed={active}
                    style={{
                      background: "transparent",
                      border: "none",
                      cursor: "pointer",
                      padding: 0,
                      fontFamily: "var(--font-mono)",
                      fontSize: "var(--text-micro)",
                      color: active ? "var(--color-accent)" : "var(--color-muted)",
                      borderBottom: active
                        ? "1px solid var(--color-accent)"
                        : "1px solid transparent",
                    }}
                  >
                    {t}
                  </button>
                );
              })}
            </>
          )}
        </div>
      )}

      {/* Main content */}
      <main style={{ flex: 1 }}>
        {/* Loading */}
        {isLoading && (
          <div
            aria-busy="true"
            aria-label="Loading candidates"
            style={{ padding: "1rem 0", display: "flex", flexDirection: "column", gap: "1px" }}
          >
            {Array.from({ length: 8 }, (_, i) => (
              <SkeletonRow key={i} index={i} />
            ))}
          </div>
        )}

        {/* Error */}
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
            Could not load queue:{" "}
            {error instanceof Error ? error.message : "unknown error"}.
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !isError && visible.length === 0 && (
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
            {candidates.length === 0 ? (
              <>
                No candidates for{" "}
                <code
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.875em",
                    fontStyle: "normal",
                  }}
                >
                  {date}
                </code>
                . Pick another date above, or run{" "}
                <code
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.875em",
                    fontStyle: "normal",
                  }}
                >
                  radar fetch-arxiv && radar classify --date {date === "today" ? "today" : date}
                </code>
                .
              </>
            ) : (
              "No candidates match the current filters."
            )}
          </div>
        )}

        {/* Candidate list */}
        {!isLoading && !isError && visible.length > 0 && (
          <div
            role="list"
            aria-label="Candidate queue"
            style={{ borderTop: "1px solid var(--color-rule)" }}
          >
            {visible.map((candidate, i) => (
              <div
                key={candidate.id}
                role="listitem"
                data-candidate-id={candidate.id}
                data-candidate-expanded={
                  expandedId === candidate.id ? candidate.id : undefined
                }
              >
                <CandidateRow
                  candidate={candidate}
                  expanded={expandedId === candidate.id}
                  focused={focusedIndex === i}
                  onToggle={() => {
                    setFocusedIndex(i);
                    toggleExpand(candidate.id);
                  }}
                />
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Footer is rendered inside Chrome when stats are provided — nothing extra here */}

      <ShortcutSheet open={shortcutOpen} onClose={() => setShortcutOpen(false)} />
    </div>
  );
}
