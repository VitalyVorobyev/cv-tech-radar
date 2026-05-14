// Tracks view — per-track drill-down. Left sidebar lists every track grouped
// by quadrant with item counts; main column shows the selected track's ring
// distribution and ranked item list.

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { BoardItem, Ring } from "../lib/api";
import { api } from "../lib/api";
import { Chrome } from "../ui/Chrome";
import { ItemPanel } from "../ui/ItemPanel";
import { QUADRANTS, RING_ORDER } from "../lib/constants";
import { readUrlParams, writeUrlParams } from "../lib/urlState";

const RING_BAND: Record<Ring, { color: string; opacity: number }> = {
  Use: { color: "var(--color-accent)", opacity: 1.0 },
  Prototype: { color: "var(--color-accent)", opacity: 0.7 },
  Evaluate: { color: "currentColor", opacity: 0.4 },
  Watch: { color: "currentColor", opacity: 0.2 },
  Ignore: { color: "var(--color-muted)", opacity: 0.2 },
};

function quadrantOfTrack(track: string): (typeof QUADRANTS)[number] | null {
  for (const q of QUADRANTS) {
    if (q.tracks.includes(track)) return q;
  }
  return null;
}

function defaultTrack(): string {
  const fromUrl = readUrlParams().get("track");
  if (fromUrl && quadrantOfTrack(fromUrl)) return fromUrl;
  return QUADRANTS[0]!.tracks[0]!;
}

export function TracksView() {
  const [track, setTrack] = useState<string>(defaultTrack);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["board"],
    queryFn: () => api.board(),
  });

  useEffect(() => {
    writeUrlParams({ track });
  }, [track]);

  const allItems = useMemo<BoardItem[]>(() => {
    if (!data) return [];
    return [
      ...data.rings.Use,
      ...data.rings.Prototype,
      ...data.rings.Evaluate,
      ...data.rings.Watch,
    ];
  }, [data]);

  // Tracks view treats track membership as a set — an item with multiple tracks
  // contributes to each. (The radar plot uses the first track only, since each
  // dot has a single position.)
  const trackCounts = useMemo(() => {
    const map = new Map<string, number>();
    for (const it of allItems) {
      for (const t of it.tracks) {
        map.set(t, (map.get(t) ?? 0) + 1);
      }
    }
    return map;
  }, [allItems]);

  const trackItems = useMemo(
    () => allItems.filter((it) => it.tracks.includes(track)),
    [allItems, track],
  );

  const ringCounts = useMemo(() => {
    const counts: Record<Ring, number> = {
      Use: 0,
      Prototype: 0,
      Evaluate: 0,
      Watch: 0,
      Ignore: 0,
    };
    for (const it of trackItems) counts[it.ring] += 1;
    return counts;
  }, [trackItems]);

  const total = trackItems.length;
  const quad = quadrantOfTrack(track);

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
          gridTemplateColumns: "260px 1fr",
          gap: "2rem",
          alignItems: "start",
        }}
      >
        <aside
          style={{
            borderRight: "1px solid var(--color-rule)",
            paddingRight: "1.25rem",
            position: "sticky",
            top: "4rem",
          }}
        >
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              marginBottom: "0.75rem",
            }}
          >
            Tracks
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {QUADRANTS.map((q) => (
              <div key={q.id}>
                <div
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "var(--text-micro)",
                    color: "var(--color-muted)",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                    marginBottom: "0.375rem",
                  }}
                >
                  {q.label}
                </div>
                {q.tracks.map((t) => {
                  const active = track === t;
                  return (
                    <button
                      key={t}
                      type="button"
                      onClick={() => setTrack(t)}
                      aria-pressed={active}
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                        width: "100%",
                        background: active ? "var(--color-rule)" : "transparent",
                        border: "none",
                        borderRadius: "var(--radius-sm)",
                        cursor: "pointer",
                        padding: "0.375rem 0.5rem",
                        fontFamily: "var(--font-sans)",
                        fontSize: "var(--text-small)",
                        color: active ? "var(--color-accent)" : "inherit",
                        textAlign: "left",
                      }}
                    >
                      <span>{t}</span>
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "var(--text-micro)",
                          color: "var(--color-muted)",
                        }}
                      >
                        {trackCounts.get(t) ?? 0}
                      </span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </aside>

        <section style={{ minWidth: 0 }}>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            {quad?.label ?? ""} / Track
          </div>
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "2rem",
              fontWeight: 400,
              letterSpacing: "-0.01em",
              margin: "0.5rem 0 1rem",
            }}
          >
            {track}
          </h2>

          {isError && (
            <div role="alert" style={{ fontFamily: "var(--font-display)", fontStyle: "italic", color: "var(--color-muted)" }}>
              Could not load.
            </div>
          )}

          {/* Distribution bar */}
          {total > 0 ? (
            <div
              style={{
                display: "flex",
                height: "6px",
                background: "var(--color-rule)",
                borderRadius: "var(--radius-sm)",
                overflow: "hidden",
                marginBottom: "0.75rem",
              }}
              aria-label="Ring distribution"
            >
              {RING_ORDER.map((ring) => {
                const w = (ringCounts[ring] / total) * 100;
                if (w <= 0) return null;
                return (
                  <div
                    key={ring}
                    style={{
                      width: `${w}%`,
                      background: RING_BAND[ring].color,
                      opacity: RING_BAND[ring].opacity,
                    }}
                    title={`${ring}: ${ringCounts[ring]}`}
                  />
                );
              })}
            </div>
          ) : (
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontStyle: "italic",
                color: "var(--color-muted)",
                marginBottom: "0.75rem",
                opacity: isLoading ? 0.4 : 1,
              }}
            >
              No items in this track yet.
            </div>
          )}

          {/* Legend */}
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "1.25rem",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
              letterSpacing: "0.04em",
              marginBottom: "1.5rem",
            }}
          >
            {RING_ORDER.map((ring) => (
              <span key={ring} style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
                <svg width={10} height={10} aria-hidden="true">
                  <rect
                    width={10}
                    height={10}
                    fill={RING_BAND[ring].color}
                    fillOpacity={RING_BAND[ring].opacity}
                  />
                </svg>
                <span>
                  {ring} · {ringCounts[ring]}
                </span>
              </span>
            ))}
          </div>

          {/* Item list */}
          <div style={{ display: "flex", flexDirection: "column" }}>
            {RING_ORDER.flatMap((ring) =>
              trackItems
                .filter((it) => it.ring === ring)
                .map((it) => (
                  <ItemRow key={it.item_id} item={it} onOpen={() => setSelectedId(it.item_id)} />
                )),
            )}
          </div>
        </section>
      </main>

      {selectedId !== null && (
        <ItemPanel
          itemId={selectedId}
          onClose={() => setSelectedId(null)}
          onTrackClick={(t) => {
            setTrack(t);
            setSelectedId(null);
          }}
        />
      )}
    </div>
  );
}

function ItemRow({ item, onOpen }: { item: BoardItem; onOpen(): void }) {
  const accent = item.ring === "Use" || item.ring === "Prototype";
  return (
    <button
      type="button"
      onClick={onOpen}
      style={{
        display: "grid",
        gridTemplateColumns: "100px 1fr 80px",
        gap: "1rem",
        alignItems: "baseline",
        background: "transparent",
        border: "none",
        borderBottom: "1px solid var(--color-rule)",
        padding: "0.75rem 0",
        cursor: "pointer",
        textAlign: "left",
        color: "inherit",
        width: "100%",
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-micro)",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: accent ? "var(--color-accent)" : "var(--color-muted)",
        }}
      >
        {item.ring}
      </span>
      <span
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "1.05rem",
          lineHeight: 1.35,
        }}
      >
        {item.title}
      </span>
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-micro)",
          color: "var(--color-muted)",
          textAlign: "right",
        }}
      >
        #{item.item_id}
      </span>
    </button>
  );
}
