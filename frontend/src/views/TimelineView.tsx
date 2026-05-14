// Timeline view — 12-week stacked-area chart of items entering each ring,
// plus a "recent movers" strip below sourced from the board (movement != null).

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { BoardItem, Ring, TimelineWeek } from "../lib/api";
import { api } from "../lib/api";
import { Chrome } from "../ui/Chrome";
import { ItemPanel } from "../ui/ItemPanel";

const SVG_W = 1000;
const SVG_H = 360;
const PAD = { l: 60, r: 16, t: 24, b: 40 };
const INNER_W = SVG_W - PAD.l - PAD.r;
const INNER_H = SVG_H - PAD.t - PAD.b;

const STACK_ORDER: Ring[] = ["Use", "Prototype", "Evaluate", "Watch", "Ignore"];

const RING_FILL: Record<Ring, { color: string; opacity: number }> = {
  Use: { color: "var(--color-accent)", opacity: 0.9 },
  Prototype: { color: "var(--color-accent)", opacity: 0.55 },
  Evaluate: { color: "currentColor", opacity: 0.25 },
  Watch: { color: "currentColor", opacity: 0.15 },
  Ignore: { color: "var(--color-muted)", opacity: 0.08 },
};

interface Stacked {
  band: Ring;
  pathD: string;
}

function buildStacks(weeks: TimelineWeek[]): { stacks: Stacked[]; maxTotal: number; xs: number[] } {
  const n = weeks.length;
  if (n === 0) return { stacks: [], maxTotal: 0, xs: [] };

  const totals = weeks.map((w) => STACK_ORDER.reduce((sum, r) => sum + (w[r] ?? 0), 0));
  const maxTotal = Math.max(1, ...totals);

  const xs = weeks.map((_, i) =>
    n === 1 ? PAD.l + INNER_W / 2 : PAD.l + (INNER_W / (n - 1)) * i,
  );

  // For each band, compute y-top and y-bottom per week, then stitch a closed path.
  let baselines = weeks.map(() => 0);
  const stacks: Stacked[] = [];
  for (const band of STACK_ORDER) {
    const tops: number[] = baselines.map((b, i) => b + (weeks[i]![band] ?? 0));
    const upper = tops.map((t) => PAD.t + INNER_H - (t / maxTotal) * INNER_H);
    const lower = baselines.map((b) => PAD.t + INNER_H - (b / maxTotal) * INNER_H);
    const top = upper.map((y, i) => `${i === 0 ? "M" : "L"} ${xs[i]} ${y}`).join(" ");
    const bottom = [...lower]
      .map((_y, i) => {
        const j = lower.length - 1 - i;
        return `L ${xs[j]} ${lower[j]}`;
      })
      .join(" ");
    stacks.push({ band, pathD: `${top} ${bottom} Z` });
    baselines = tops;
  }
  return { stacks, maxTotal, xs };
}

export function TimelineView() {
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const timeline = useQuery({ queryKey: ["timeline", 12], queryFn: () => api.timeline(12) });
  const board = useQuery({ queryKey: ["board"], queryFn: () => api.board() });

  const movers = useMemo<BoardItem[]>(() => {
    if (!board.data) return [];
    const all: BoardItem[] = [
      ...board.data.rings.Use,
      ...board.data.rings.Prototype,
      ...board.data.rings.Evaluate,
      ...board.data.rings.Watch,
    ];
    return all.filter((it) => it.movement !== null).slice(0, 18);
  }, [board.data]);

  const weeks = useMemo<TimelineWeek[]>(
    () => timeline.data?.weeks ?? [],
    [timeline.data],
  );
  const { stacks, maxTotal, xs } = useMemo(() => buildStacks(weeks), [weeks]);

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
        }}
      >
        <header style={{ marginBottom: "1.5rem" }}>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            12-week movement
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
            How many items landed in each ring per week.
          </div>
        </header>

        {timeline.isError && (
          <div role="alert" style={{ fontFamily: "var(--font-display)", fontStyle: "italic", color: "var(--color-muted)" }}>
            Could not load timeline.
          </div>
        )}

        <div style={{ opacity: timeline.isLoading ? 0.4 : 1 }}>
          <svg
            viewBox={`0 0 ${SVG_W} ${SVG_H}`}
            width="100%"
            style={{ display: "block" }}
            role="img"
            aria-label="12-week ring throughput"
          >
            {/* Gridlines */}
            {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
              const y = PAD.t + INNER_H - frac * INNER_H;
              const value = Math.round(frac * maxTotal);
              return (
                <g key={frac}>
                  <line
                    x1={PAD.l}
                    x2={SVG_W - PAD.r}
                    y1={y}
                    y2={y}
                    stroke="var(--color-rule)"
                    strokeWidth="1"
                  />
                  <text
                    x={PAD.l - 8}
                    y={y + 3}
                    textAnchor="end"
                    fontSize="9"
                    fontFamily="var(--font-mono)"
                    fill="var(--color-muted)"
                  >
                    {value}
                  </text>
                </g>
              );
            })}

            {/* Stacked areas */}
            {stacks.map((s) => (
              <path
                key={s.band}
                d={s.pathD}
                fill={RING_FILL[s.band].color}
                fillOpacity={RING_FILL[s.band].opacity}
              />
            ))}

            {/* Week ticks */}
            {weeks.map((w, i) => (
              <text
                key={w.iso}
                x={xs[i]}
                y={SVG_H - PAD.b + 16}
                textAnchor="middle"
                fontSize="9"
                fontFamily="var(--font-mono)"
                fill="var(--color-muted)"
              >
                {w.label}
              </text>
            ))}
          </svg>
        </div>

        {/* Legend */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "1.25rem",
            marginTop: "0.75rem",
            fontFamily: "var(--font-mono)",
            fontSize: "10px",
            color: "var(--color-muted)",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          {STACK_ORDER.map((band) => (
            <span key={band} style={{ display: "inline-flex", alignItems: "center", gap: "0.375rem" }}>
              <svg width={10} height={10} aria-hidden="true">
                <rect
                  width={10}
                  height={10}
                  fill={RING_FILL[band].color}
                  fillOpacity={RING_FILL[band].opacity}
                />
              </svg>
              <span>{band}</span>
            </span>
          ))}
        </div>

        {/* Recent movers */}
        <section style={{ marginTop: "2rem" }}>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              marginBottom: "0.75rem",
            }}
          >
            Recent movers
          </div>
          {movers.length === 0 ? (
            <div
              style={{
                fontFamily: "var(--font-display)",
                fontStyle: "italic",
                color: "var(--color-muted)",
              }}
            >
              No recent movement on the radar.
            </div>
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                gap: "1rem",
              }}
            >
              {movers.map((it) => (
                <MoverCard
                  key={it.item_id}
                  item={it}
                  onOpen={() => setSelectedId(it.item_id)}
                />
              ))}
            </div>
          )}
        </section>
      </main>

      {selectedId !== null && (
        <ItemPanel itemId={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}

function MoverCard({ item, onOpen }: { item: BoardItem; onOpen(): void }) {
  return (
    <button
      type="button"
      onClick={onOpen}
      style={{
        background: "transparent",
        border: "1px solid var(--color-rule)",
        borderRadius: "var(--radius-sm)",
        padding: "0.75rem 0.875rem",
        cursor: "pointer",
        textAlign: "left",
        color: "inherit",
        display: "flex",
        flexDirection: "column",
        gap: "0.375rem",
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-micro)",
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--color-muted)",
        }}
      >
        {item.movement === "new"
          ? "new · "
          : item.movement === "in"
            ? "moved in · "
            : item.movement === "out"
              ? "moved out · "
              : ""}
        <span style={{ color: "var(--color-accent)" }}>{item.ring}</span>
      </div>
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "0.95rem",
          lineHeight: 1.3,
          overflow: "hidden",
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
        }}
      >
        {item.title}
      </div>
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-micro)",
          color: "var(--color-muted)",
        }}
      >
        {item.tracks[0] ?? "—"}
      </div>
    </button>
  );
}

