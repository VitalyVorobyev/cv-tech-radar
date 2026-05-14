// Slide-in detail panel. Opens on radar-dot click; shows abstract, decision
// history, and Promote/Demote actions. Animation is gated by prefers-reduced-motion
// via the `.cvradar-slide-in` keyframes in styles.css.

import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ItemDetail,
  Movement,
  NearDuplicatePair,
  Ring,
} from "../lib/api";
import { api, isStaticMode } from "../lib/api";

const IS_STATIC = isStaticMode();
import { RING_ORDER } from "../lib/constants";

interface ItemPanelProps {
  itemId: number;
  onClose(): void;
  onTrackClick?(track: string): void;
  /** Optional: navigate to a different item from within the panel (e.g.
   *  clicking a near-duplicate match). When omitted, the panel falls back to
   *  a hash link the user can open in a new tab. */
  onSelectItem?(itemId: number): void;
}

const MOVEMENT_LABEL: Record<Movement, string> = {
  new: "new",
  in: "moved in",
  out: "moved out",
};

function nextRing(current: Ring, direction: "promote" | "demote"): Ring | null {
  const idx = RING_ORDER.indexOf(current);
  if (idx < 0) return null;
  const target = direction === "promote" ? idx - 1 : idx + 1;
  if (target < 0 || target >= RING_ORDER.length) return null;
  return RING_ORDER[target]!;
}

function formatHistoryAt(at: string): string {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return at;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function ItemPanel({
  itemId,
  onClose,
  onTrackClick,
  onSelectItem,
}: ItemPanelProps) {
  const queryClient = useQueryClient();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["item", itemId],
    queryFn: () => api.item(itemId),
  });

  const promote = useMutation({
    mutationFn: async (target: Ring) => {
      if (!data) throw new Error("no item");
      return api.postDecision({
        item_id: itemId,
        ring: target,
        reason: data.reason || `Moved to ${target}.`,
        action: "",
        tracks: data.tracks,
        uncertain: data.uncertain,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["item", itemId] });
      queryClient.invalidateQueries({ queryKey: ["board"] });
    },
  });

  // Esc to close.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-label="Item detail"
      className="cvradar-slide-in"
      style={{
        position: "fixed",
        top: 0,
        right: 0,
        height: "100dvh",
        width: "min(440px, 95vw)",
        zIndex: 40,
        padding: "1.5rem",
        background: "var(--color-paper)",
        borderLeft: "1px solid var(--color-rule)",
        overflowY: "auto",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
          }}
        >
          {data ? `#${data.id} · ${data.source}` : `#${itemId}`}
        </span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          style={{
            background: "transparent",
            border: "none",
            cursor: "pointer",
            padding: 0,
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-small)",
            color: "var(--color-muted)",
          }}
        >
          ✕
        </button>
      </header>

      {isLoading && (
        <div className="skeleton-block" style={{ height: "3.5rem" }} aria-hidden="true" />
      )}
      {isError && (
        <div
          role="alert"
          style={{
            fontFamily: "var(--font-display)",
            fontStyle: "italic",
            color: "var(--color-muted)",
          }}
        >
          Could not load: {error instanceof Error ? error.message : "unknown error"}.
        </div>
      )}

      {data && (
        <ItemPanelBody
          data={data}
          onTrackClick={onTrackClick}
          onPromote={promote.mutate}
          onSelectItem={onSelectItem}
        />
      )}
    </aside>
  );
}

function ItemPanelBody({
  data,
  onTrackClick,
  onPromote,
  onSelectItem,
}: {
  data: ItemDetail;
  onTrackClick?(track: string): void;
  onPromote(target: Ring): void;
  onSelectItem?(itemId: number): void;
}) {
  const ringIsAccent = data.ring === "Use" || data.ring === "Prototype";
  const promoteTarget =
    data.ring && data.ring !== "Ignore" ? nextRing(data.ring as Ring, "promote") : null;
  const demoteTarget =
    data.ring && data.ring !== "Ignore" ? nextRing(data.ring as Ring, "demote") : null;
  return (
    <>
      <h2
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "1.6rem",
          fontWeight: 400,
          letterSpacing: "-0.01em",
          lineHeight: 1.2,
          margin: 0,
        }}
      >
        {data.title}
      </h2>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
        {data.ring && (
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: ringIsAccent ? "var(--color-accent)" : "currentColor",
              border: "1px solid var(--color-rule)",
              borderRadius: "var(--radius-sm)",
              padding: "0.125rem 0.5rem",
            }}
          >
            {data.ring}
          </span>
        )}
        {data.track && (
          <button
            type="button"
            onClick={() => onTrackClick?.(data.track)}
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              letterSpacing: "0.04em",
              color: "var(--color-muted)",
              background: "transparent",
              border: "1px solid var(--color-rule)",
              borderRadius: "var(--radius-sm)",
              padding: "0.125rem 0.5rem",
              cursor: "pointer",
            }}
          >
            {data.track}
          </button>
        )}
        {data.uncertain && (
          <span style={pillMutedStyle}>uncertain</span>
        )}
        {data.movement && <span style={pillMutedStyle}>{MOVEMENT_LABEL[data.movement]}</span>}
      </div>

      {data.reason && (
        <blockquote
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontStyle: "italic",
            fontSize: "1.05rem",
            opacity: 0.85,
            lineHeight: 1.5,
          }}
        >
          &ldquo;{data.reason}&rdquo;
        </blockquote>
      )}

      {data.history.length > 0 && (
        <div
          aria-label="Decision history"
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.25rem",
            alignItems: "baseline",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-small)",
          }}
        >
          {data.history.map((entry, i) => {
            const last = i === data.history.length - 1;
            return (
              <span
                key={`${entry.ring}-${entry.at}`}
                style={{ display: "inline-flex", alignItems: "baseline", gap: "0.25rem" }}
              >
                {i > 0 && (
                  <span style={{ color: "var(--color-muted)" }} aria-hidden="true">
                    →
                  </span>
                )}
                <span
                  style={{
                    color: last ? "var(--color-accent)" : "var(--color-muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                  }}
                  title={formatHistoryAt(entry.at)}
                >
                  {entry.ring}
                </span>
              </span>
            );
          })}
        </div>
      )}

      <section>
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            marginBottom: "0.5rem",
          }}
        >
          Abstract
        </div>
        {data.abstract ? (
          <p
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "var(--text-body)",
              lineHeight: 1.5,
              margin: 0,
            }}
          >
            {data.abstract}
          </p>
        ) : (
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
            }}
          >
            ↳ abstract not yet stored for this source
          </div>
        )}
      </section>

      {!IS_STATIC && (
        <NearDuplicatesSection
          itemId={data.id}
          anchorDate={data.published_at}
          onSelectItem={onSelectItem}
        />
      )}

      <footer style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "auto" }}>
        <a
          href={data.url}
          target="_blank"
          rel="noopener noreferrer"
          style={actionStyle}
        >
          Open paper ↗
        </a>
        {!IS_STATIC && promoteTarget && (
          <button type="button" style={actionStyle} onClick={() => onPromote(promoteTarget)}>
            Promote to {promoteTarget}
          </button>
        )}
        {!IS_STATIC && demoteTarget && (
          <button type="button" style={actionStyle} onClick={() => onPromote(demoteTarget)}>
            Demote to {demoteTarget}
          </button>
        )}
      </footer>
    </>
  );
}

function toIsoDate(value: string): string {
  // ItemDetail.published_at is an ISO datetime; the near-duplicates
  // endpoint wants YYYY-MM-DD. Fall back to "today" if parsing fails so
  // the panel never blows up on an unexpected payload.
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "today";
  return d.toISOString().slice(0, 10);
}

function NearDuplicatesSection({
  itemId,
  anchorDate,
  onSelectItem,
}: {
  itemId: number;
  anchorDate: string;
  onSelectItem?(itemId: number): void;
}) {
  const date = toIsoDate(anchorDate);
  const { data, isLoading, isError } = useQuery({
    queryKey: ["near-duplicates", date, 30],
    queryFn: () => api.getNearDuplicates(date, 30),
    staleTime: 60_000,
  });

  // The endpoint returns every pair in the window; filter to the current item.
  const matches: { pair: NearDuplicatePair; other: { id: number; title: string } }[] = [];
  if (data) {
    for (const pair of data.pairs) {
      if (pair.item_a_id === itemId) {
        matches.push({
          pair,
          other: { id: pair.item_b_id, title: pair.item_b_title },
        });
      } else if (pair.item_b_id === itemId) {
        matches.push({
          pair,
          other: { id: pair.item_a_id, title: pair.item_a_title },
        });
      }
    }
  }

  return (
    <section aria-label="Near-duplicates">
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-micro)",
          color: "var(--color-muted)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          marginBottom: "0.5rem",
        }}
      >
        Near-duplicates
      </div>
      {isLoading && (
        <div
          className="skeleton-block"
          style={{ height: "1.5rem" }}
          aria-hidden="true"
        />
      )}
      {isError && (
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
          }}
        >
          Could not load near-duplicates.
        </div>
      )}
      {data && matches.length === 0 && (
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            lineHeight: 1.5,
          }}
        >
          No near-duplicates found in the last 30 days. Run{" "}
          <code style={{ fontFamily: "var(--font-mono)" }}>radar embed</code>{" "}
          to populate.
        </div>
      )}
      {data && matches.length > 0 && (
        <ul
          style={{
            listStyle: "none",
            padding: 0,
            margin: 0,
            display: "flex",
            flexDirection: "column",
            gap: "0.375rem",
          }}
        >
          {matches.map(({ pair, other }) => {
            const href = `#/score-debug?item=${other.id}`;
            const handleClick = onSelectItem
              ? (e: React.MouseEvent) => {
                  e.preventDefault();
                  onSelectItem(other.id);
                }
              : undefined;
            return (
              <li
                key={`${pair.item_a_id}-${pair.item_b_id}`}
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  gap: "0.5rem",
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "var(--text-micro)",
                    color: "var(--color-accent)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {pair.cosine.toFixed(3)}
                </span>
                <a
                  href={href}
                  onClick={handleClick}
                  style={{
                    fontFamily: "var(--font-sans)",
                    fontSize: "var(--text-small)",
                    color: "inherit",
                    textDecoration: "underline",
                    textUnderlineOffset: "2px",
                    lineHeight: 1.4,
                  }}
                >
                  {other.title}
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

const pillMutedStyle = {
  fontFamily: "var(--font-mono)",
  fontSize: "var(--text-micro)",
  letterSpacing: "0.04em",
  color: "var(--color-muted)",
  border: "1px solid var(--color-rule)",
  borderRadius: "var(--radius-sm)",
  padding: "0.125rem 0.5rem",
} as const;

const actionStyle = {
  display: "inline-block",
  background: "transparent",
  border: "1px solid var(--color-rule)",
  color: "inherit",
  fontFamily: "var(--font-mono)",
  fontSize: "var(--text-small)",
  letterSpacing: "0.04em",
  padding: "0.5rem 0.875rem",
  borderRadius: "var(--radius-sm)",
  textDecoration: "none",
  cursor: "pointer",
} as const;
