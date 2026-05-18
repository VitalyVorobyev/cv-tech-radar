// Radar view — primary landing route. Renders the polar radar plot, a left
// header strip, a right context column (ring + track sidebars), and a slide-in
// detail panel on dot click. Filter state (focused quadrant, focused ring,
// active track filter, search) is mirrored to the URL.

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { BoardItem, BoardRings, Ring } from "../lib/api";
import { api, isStaticMode } from "../lib/api";
import { Chrome } from "../ui/Chrome";
import { ItemPanel } from "../ui/ItemPanel";
import { RadarPlot } from "../ui/RadarPlot";
import {
  type Quadrant,
  QUADRANT_DEFS,
  RING_COPY,
  RING_ORDER,
  radarVolume,
} from "../lib/constants";
import { readUrlParams, writeUrlParams } from "../lib/urlState";
import { useQuadrants } from "../lib/useQuadrants";
import { useTweaks } from "../lib/tweaks";

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mql.matches);
    const handler = (e: MediaQueryListEvent) => setReduced(e.matches);
    mql.addEventListener("change", handler);
    return () => mql.removeEventListener("change", handler);
  }, []);
  return reduced;
}

function readInitialFilters() {
  const params = readUrlParams();
  const quad = params.get("quad");
  const ring = params.get("ring") as Ring | null;
  const track = params.get("track");
  const q = params.get("q") ?? "";
  return {
    quad: QUADRANT_DEFS.some((qd) => qd.id === quad) ? quad : null,
    ring: RING_ORDER.includes(ring as Ring) ? (ring as Ring) : null,
    track: track ?? null,
    q,
  };
}

function flattenBoardItems(rings: BoardRings): BoardItem[] {
  return [...rings.Use, ...rings.Prototype, ...rings.Evaluate, ...rings.Watch];
}

function searchMatches(it: BoardItem, ql: string): boolean {
  if (!ql) return true;
  const hay = `${it.title} ${it.reason} ${it.tracks.join(" ")}`.toLowerCase();
  return hay.includes(ql);
}

export function RadarView() {
  const reducedMotion = usePrefersReducedMotion();
  const initial = useMemo(readInitialFilters, []);
  const [focusedQuad, setFocusedQuad] = useState<string | null>(initial.quad);
  const [focusedRing, setFocusedRing] = useState<Ring | null>(initial.ring);
  const [trackFilter, setTrackFilter] = useState<string | null>(initial.track);
  const [search, setSearch] = useState<string>(initial.q);
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tweaks, setTweaks] = useTweaks();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["board"],
    queryFn: () => api.board(),
  });
  const { quadrants } = useQuadrants();

  // Drag-to-change-ring is a curator action — only when a write API exists.
  const canEdit = !isStaticMode();
  const queryClient = useQueryClient();

  // Mirror state to URL.
  useEffect(() => {
    writeUrlParams({
      quad: focusedQuad,
      ring: focusedRing,
      track: trackFilter,
      q: search || null,
    });
  }, [focusedQuad, focusedRing, trackFilter, search]);

  const allItems = useMemo(() => {
    if (!data) return [] as BoardItem[];
    return flattenBoardItems(data.rings);
  }, [data]);

  // Dropping a dot in a new ring band records a decision; "Ignore" removes it.
  const changeRing = useMutation({
    mutationFn: ({ itemId, ring }: { itemId: number; ring: Ring }) => {
      const it = allItems.find((i) => i.item_id === itemId);
      return api.postDecision({
        item_id: itemId,
        ring,
        reason: it?.reason || `Moved to ${ring} from the radar.`,
        action: it?.action ?? "",
        tracks: it?.tracks ?? [],
        uncertain: it?.uncertain ?? false,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["board"] });
    },
  });

  const visibleItems = useMemo(() => {
    const ql = search.toLowerCase();
    return allItems.filter((it) => searchMatches(it, ql));
  }, [allItems, search]);

  const ringCounts = useMemo(() => {
    const counts: Record<Ring, number> = {
      Use: 0,
      Prototype: 0,
      Evaluate: 0,
      Watch: 0,
      Ignore: 0,
    };
    for (const it of allItems) counts[it.ring] = (counts[it.ring] ?? 0) + 1;
    return counts;
  }, [allItems]);

  // Count by any track membership so the sidebar matches users' intuition; the
  // plot still places each item once via its primary track.
  const trackCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const it of allItems) {
      for (const t of it.tracks) {
        counts.set(t, (counts.get(t) ?? 0) + 1);
      }
    }
    return counts;
  }, [allItems]);

  const onBoardCount =
    ringCounts.Use + ringCounts.Prototype + ringCounts.Evaluate + ringCounts.Watch;
  const today = new Date();
  const dateLine = today.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  const hasFocus = focusedQuad !== null || focusedRing !== null || trackFilter !== null;

  function resetFocus() {
    setFocusedQuad(null);
    setFocusedRing(null);
    setTrackFilter(null);
    setSearch("");
  }

  return (
    <div style={{ minHeight: "100dvh", display: "flex", flexDirection: "column" }}>
      <Chrome />
      <main
        style={{
          flex: 1,
          padding: "1.25rem 1.5rem",
          maxWidth: "1400px",
          width: "100%",
          margin: "0 auto",
          display: "grid",
          gridTemplateColumns: "minmax(0, 1fr) 320px",
          gap: "2rem",
          alignItems: "start",
        }}
      >
        <section style={{ display: "flex", flexDirection: "column", gap: "1.25rem", minWidth: 0 }}>
          <header style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "flex-end" }}>
            <div>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-micro)",
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  color: "var(--color-muted)",
                }}
              >
                CV Tech Radar · Vol. {radarVolume(today)}
              </div>
              <div
                style={{
                  fontFamily: "var(--font-display)",
                  fontStyle: "italic",
                  fontSize: "1.05rem",
                  color: "var(--color-muted)",
                  marginTop: "0.25rem",
                }}
              >
                {dateLine} · {onBoardCount} items on the board
              </div>
            </div>
            <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter…"
                aria-label="Filter items"
                className="queue-input queue-input--filter"
              />
              {hasFocus && (
                <button
                  type="button"
                  onClick={resetFocus}
                  style={{
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                    fontFamily: "var(--font-mono)",
                    fontSize: "var(--text-micro)",
                    color: "var(--color-accent)",
                    letterSpacing: "0.04em",
                  }}
                >
                  reset focus ↺
                </button>
              )}
            </div>
          </header>

          {isError && (
            <div role="alert" style={{ fontFamily: "var(--font-display)", fontStyle: "italic", color: "var(--color-muted)" }}>
              Could not load the radar: {error instanceof Error ? error.message : "unknown error"}.
            </div>
          )}

          <div
            style={{
              width: "100%",
              maxWidth: "820px",
              aspectRatio: "1 / 1",
              alignSelf: "center",
              opacity: isLoading ? 0.4 : 1,
            }}
          >
            <RadarPlot
              items={visibleItems}
              quadrants={quadrants}
              focusedQuad={focusedQuad}
              focusedRing={focusedRing}
              trackFilter={trackFilter}
              hoveredId={hoveredId}
              selectedId={selectedId}
              showLabels={tweaks.showLabels}
              reducedMotion={reducedMotion}
              canEdit={canEdit}
              onHoverDot={setHoveredId}
              onSelectDot={(id) => setSelectedId((prev) => (prev === id ? null : id))}
              onFocusQuad={setFocusedQuad}
              onFocusRing={setFocusedRing}
              onTrackFilter={setTrackFilter}
              onChangeRing={(itemId, ring) => changeRing.mutate({ itemId, ring })}
            />
          </div>

          <Legend
            showLabels={tweaks.showLabels}
            onToggleLabels={() => setTweaks({ showLabels: !tweaks.showLabels })}
          />
        </section>

        <Sidebar
          quadrants={quadrants}
          ringCounts={ringCounts}
          trackCounts={trackCounts}
          focusedQuad={focusedQuad}
          focusedRing={focusedRing}
          trackFilter={trackFilter}
          onFocusQuad={setFocusedQuad}
          onFocusRing={setFocusedRing}
          onTrackFilter={setTrackFilter}
        />
      </main>

      {selectedId !== null && (
        <ItemPanel
          itemId={selectedId}
          onClose={() => setSelectedId(null)}
          onTrackClick={(track) => {
            setTrackFilter(track);
            setSelectedId(null);
          }}
        />
      )}
    </div>
  );
}

function Legend({
  showLabels,
  onToggleLabels,
}: {
  showLabels: boolean;
  onToggleLabels(): void;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "1.25rem",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-micro)",
        color: "var(--color-muted)",
        letterSpacing: "0.04em",
      }}
    >
      <span>legend</span>
      <LegendDot color="var(--color-accent)" filled label="adopted (Use / Prototype)" />
      <LegendDot color="currentColor" filled label="tracked (Evaluate / Watch)" />
      <LegendDot color="var(--color-accent)" filled={false} label="new this week" />
      <button
        type="button"
        onClick={onToggleLabels}
        aria-pressed={showLabels}
        style={{
          marginLeft: "auto",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          fontFamily: "inherit",
          fontSize: "inherit",
          color: showLabels ? "var(--color-accent)" : "inherit",
          letterSpacing: "0.04em",
        }}
      >
        {showLabels ? "ids on" : "ids off"}
      </button>
    </div>
  );
}

function LegendDot({
  color,
  filled,
  label,
}: {
  color: string;
  filled: boolean;
  label: string;
}) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
      <svg width={10} height={10} aria-hidden="true">
        <circle
          cx={5}
          cy={5}
          r={4}
          fill={filled ? color : "none"}
          stroke={color}
          strokeWidth={1}
        />
      </svg>
      <span>{label}</span>
    </span>
  );
}

function Sidebar({
  quadrants,
  ringCounts,
  trackCounts,
  focusedQuad,
  focusedRing,
  trackFilter,
  onFocusQuad,
  onFocusRing,
  onTrackFilter,
}: {
  quadrants: readonly Quadrant[];
  ringCounts: Record<Ring, number>;
  trackCounts: Map<string, number>;
  focusedQuad: string | null;
  focusedRing: Ring | null;
  trackFilter: string | null;
  onFocusQuad(id: string | null): void;
  onFocusRing(r: Ring | null): void;
  onTrackFilter(track: string | null): void;
}) {
  return (
    <aside
      style={{
        position: "sticky",
        top: "4rem",
        display: "flex",
        flexDirection: "column",
        gap: "2rem",
      }}
    >
      <section>
        <SidebarHeading>Rings</SidebarHeading>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          {RING_ORDER.map((ring) => {
            const isFocused = focusedRing === ring;
            return (
              <button
                key={ring}
                type="button"
                aria-pressed={isFocused}
                onClick={() => onFocusRing(isFocused ? null : ring)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr auto",
                  gap: "0.5rem",
                  alignItems: "baseline",
                  background: isFocused ? "var(--color-rule)" : "transparent",
                  border: "none",
                  borderRadius: "var(--radius-sm)",
                  padding: "0.5rem 0.625rem",
                  cursor: "pointer",
                  textAlign: "left",
                  color: "inherit",
                }}
              >
                <span style={{ minWidth: 0 }}>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "var(--text-small)",
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      fontWeight: 500,
                      color: isFocused ? "var(--color-accent)" : "currentColor",
                    }}
                  >
                    {ring}
                  </span>
                  <span
                    style={{
                      display: "block",
                      fontFamily: "var(--font-display)",
                      fontStyle: "italic",
                      fontSize: "var(--text-small)",
                      color: "var(--color-muted)",
                      marginTop: "0.125rem",
                      lineHeight: 1.35,
                    }}
                  >
                    {ring === "Ignore" ? "" : RING_COPY[ring]}
                  </span>
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "var(--text-small)",
                    color: "var(--color-muted)",
                  }}
                >
                  {ringCounts[ring] ?? 0}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      <section>
        <SidebarHeading>Tracks</SidebarHeading>
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {quadrants.map((q) => {
            const quadFocused = focusedQuad === q.id;
            return (
              <div key={q.id}>
                <button
                  type="button"
                  onClick={() => onFocusQuad(quadFocused ? null : q.id)}
                  aria-pressed={quadFocused}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    background: "transparent",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                    fontFamily: "var(--font-mono)",
                    fontSize: "var(--text-micro)",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    color: quadFocused ? "var(--color-accent)" : "var(--color-muted)",
                    marginBottom: "0.25rem",
                  }}
                >
                  {q.label}
                </button>
                <div style={{ display: "flex", flexDirection: "column" }}>
                  {q.tracks.map((track) => {
                    const isActive = trackFilter === track;
                    return (
                      <button
                        key={track}
                        type="button"
                        onClick={() => onTrackFilter(isActive ? null : track)}
                        aria-pressed={isActive}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          background: "transparent",
                          border: "none",
                          padding: "0.125rem 0",
                          cursor: "pointer",
                          fontFamily: "var(--font-sans)",
                          fontSize: "var(--text-small)",
                          color: isActive ? "var(--color-accent)" : "inherit",
                          borderBottom: isActive
                            ? "1px solid var(--color-accent)"
                            : "1px solid transparent",
                          textAlign: "left",
                        }}
                      >
                        <span>{track}</span>
                        <span style={{ color: "var(--color-muted)", fontFamily: "var(--font-mono)" }}>
                          {trackCounts.get(track) ?? 0}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </section>
    </aside>
  );
}

function SidebarHeading({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-micro)",
        color: "var(--color-muted)",
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        marginBottom: "0.625rem",
      }}
    >
      {children}
    </div>
  );
}
