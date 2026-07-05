// Ecosystem radar view — a separate monitoring lane for software artifacts
// (libraries) tracked across GitHub / PyPI / crates.io / npm. Papers and
// packages never share a visualization: this reuses the polar `RadarPlot`
// component but with the four fixed CAPABILITY quadrants and the same five
// rings. Three surfaces — radar board, release-event feed, artifact table —
// are selected by the ecosystem lane's tabs (see app.tsx) and passed in as the
// `surface` prop. Filter state is mirrored to the URL, exactly like RadarView.

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  ArtifactBoardItem,
  EcosystemBoardRings,
  EcosystemEventItem,
  Ring,
} from "../lib/api";
import { api, isStaticMode } from "../lib/api";
import { Chrome } from "../ui/Chrome";
import { ArtifactPanel } from "../ui/ArtifactPanel";
import { ArtifactTable } from "../ui/ArtifactTable";
import { EcosystemBadge } from "../ui/EcosystemBadge";
import { SeverityDot } from "../ui/SeverityDot";
import { RadarPlot, type RadarDot } from "../ui/RadarPlot";
import {
  ECOSYSTEM_QUADRANTS,
  type Quadrant,
  RING_COPY,
  RING_ORDER,
  radarVolume,
} from "../lib/constants";
import { readUrlParams, writeUrlParams } from "../lib/urlState";
import { useTweaks } from "../lib/tweaks";

export type EcoSurface = "radar" | "releases" | "artifacts";

function usePrefersReducedMotion(): boolean {
  // Seed from the media query lazily so the effect only subscribes (no
  // synchronous setState in the effect body).
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== "undefined" &&
      !!window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)");
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
  const q = params.get("q") ?? "";
  return {
    quad: ECOSYSTEM_QUADRANTS.some((qd) => qd.id === quad) ? quad : null,
    ring: RING_ORDER.includes(ring as Ring) ? (ring as Ring) : null,
    q,
  };
}

function flattenBoard(rings: EcosystemBoardRings): ArtifactBoardItem[] {
  return [...rings.Use, ...rings.Prototype, ...rings.Evaluate, ...rings.Watch];
}

// Adapt an ecosystem artifact into the minimal RadarDot shape RadarPlot
// expects. `item_id` carries the artifact id; `tracks` carries the artifact's
// `capability` so the default `quadrantOf` (= tracks[0]) places — and dims —
// each dot by capability. RadarPlot is reused, not forked.
function toRadarDot(artifact: ArtifactBoardItem): RadarDot {
  return {
    item_id: artifact.artifact_id,
    title: artifact.name,
    ring: artifact.ring,
    tracks: [artifact.capability],
    decided_at: artifact.decided_at ?? "",
    movement: artifact.movement,
  };
}

function searchMatches(it: ArtifactBoardItem, ql: string): boolean {
  if (!ql) return true;
  const hay = `${it.name} ${it.description} ${it.tracks.join(" ")} ${it.ecosystems.join(
    " ",
  )}`.toLowerCase();
  return hay.includes(ql);
}

export function EcosystemView({ surface }: { surface: EcoSurface }) {
  const reducedMotion = usePrefersReducedMotion();
  const initial = useMemo(() => readInitialFilters(), []);
  const [focusedQuad, setFocusedQuad] = useState<string | null>(initial.quad);
  const [focusedRing, setFocusedRing] = useState<Ring | null>(initial.ring);
  const [capabilityFilter, setCapabilityFilter] = useState<string | null>(null);
  const [search, setSearch] = useState<string>(initial.q);
  const [hoveredId, setHoveredId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tweaks, setTweaks] = useTweaks();

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["ecosystem-board"],
    queryFn: () => api.ecosystemBoard(),
  });

  // Drag-to-change-ring is a curator action — only when a write API exists.
  const canEdit = !isStaticMode();
  const queryClient = useQueryClient();

  // Mirror filter state to the URL. The surface is the route, not a param.
  useEffect(() => {
    writeUrlParams({
      quad: focusedQuad,
      ring: focusedRing,
      q: search || null,
    });
  }, [focusedQuad, focusedRing, search]);

  const allArtifacts = useMemo(() => {
    if (!data) return [] as ArtifactBoardItem[];
    return flattenBoard(data.rings);
  }, [data]);

  // Dropping a dot in a new ring band records a decision; "Ignore" removes it.
  const changeRing = useMutation({
    mutationFn: ({ artifactId, ring }: { artifactId: number; ring: Ring }) => {
      const a = allArtifacts.find((x) => x.artifact_id === artifactId);
      return api.postEcosystemDecision({
        artifact_id: artifactId,
        ring,
        reason: `Moved to ${ring} from the ecosystem radar.`,
        tracks: a?.tracks ?? [],
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ecosystem-board"] });
    },
  });

  const visibleDots = useMemo<RadarDot[]>(() => {
    const ql = search.toLowerCase();
    return allArtifacts
      .filter((a) => searchMatches(a, ql))
      .map(toRadarDot);
  }, [allArtifacts, search]);

  // The artifact table honours the same sidebar focus (ring / capability) and
  // the search box — there is no radar to dim, so filtering is explicit here.
  const tableArtifacts = useMemo<ArtifactBoardItem[]>(() => {
    const ql = search.toLowerCase();
    return allArtifacts.filter(
      (a) =>
        searchMatches(a, ql) &&
        (focusedRing === null || a.ring === focusedRing) &&
        (focusedQuad === null || a.capability === focusedQuad),
    );
  }, [allArtifacts, search, focusedRing, focusedQuad]);

  const ringCounts = useMemo(() => {
    const counts: Record<Ring, number> = {
      Use: 0,
      Prototype: 0,
      Evaluate: 0,
      Watch: 0,
      Ignore: 0,
    };
    for (const a of allArtifacts) counts[a.ring] = (counts[a.ring] ?? 0) + 1;
    return counts;
  }, [allArtifacts]);

  const capabilityCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const a of allArtifacts) {
      counts.set(a.capability, (counts.get(a.capability) ?? 0) + 1);
    }
    return counts;
  }, [allArtifacts]);

  const onBoardCount =
    ringCounts.Use + ringCounts.Prototype + ringCounts.Evaluate + ringCounts.Watch;
  const today = new Date();
  const dateLine = today.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  const hasFocus =
    focusedQuad !== null || focusedRing !== null || capabilityFilter !== null;

  function resetFocus() {
    setFocusedQuad(null);
    setFocusedRing(null);
    setCapabilityFilter(null);
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
          <header
            style={{
              display: "flex",
              justifyContent: "space-between",
              gap: "1rem",
              alignItems: "flex-end",
            }}
          >
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
                Ecosystem Radar · Vol. {radarVolume(today)}
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
                {dateLine} · {onBoardCount} artifacts on the board
              </div>
            </div>
            <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter…"
                aria-label="Filter artifacts"
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
            <div
              role="alert"
              style={{
                fontFamily: "var(--font-display)",
                fontStyle: "italic",
                color: "var(--color-muted)",
              }}
            >
              Could not load the ecosystem radar:{" "}
              {error instanceof Error ? error.message : "unknown error"}.
            </div>
          )}

          {surface === "radar" && (
            <>
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
                  items={visibleDots}
                  quadrants={ECOSYSTEM_QUADRANTS}
                  focusedQuad={focusedQuad}
                  focusedRing={focusedRing}
                  trackFilter={capabilityFilter}
                  hoveredId={hoveredId}
                  selectedId={selectedId}
                  showLabels={tweaks.showLabels}
                  reducedMotion={reducedMotion}
                  canEdit={canEdit}
                  unmappedKeyWarning={(key, dot) =>
                    `[EcosystemRadar] Capability "${key}" is not a known quadrant — ` +
                    `artifact #${dot.item_id} (${dot.title}) will not appear on the radar. ` +
                    `Capabilities are a fixed enum: cv-imaging, ml-runtimes, ` +
                    `build-tooling, viz-3d-sensors.`
                  }
                  onHoverDot={setHoveredId}
                  onSelectDot={(id) =>
                    setSelectedId((prev) => (prev === id ? null : id))
                  }
                  onFocusQuad={setFocusedQuad}
                  onFocusRing={setFocusedRing}
                  onTrackFilter={setCapabilityFilter}
                  onChangeRing={(artifactId, ring) =>
                    changeRing.mutate({ artifactId, ring })
                  }
                />
              </div>
              <Legend
                showLabels={tweaks.showLabels}
                onToggleLabels={() => setTweaks({ showLabels: !tweaks.showLabels })}
              />
            </>
          )}
          {surface === "releases" && (
            <ReleaseFeed
              onSelectArtifact={(id) => {
                setSelectedId(id);
              }}
            />
          )}
          {surface === "artifacts" && (
            <ArtifactTable
              artifacts={tableArtifacts}
              isLoading={isLoading}
              selectedId={selectedId}
              onSelect={(id) => setSelectedId((prev) => (prev === id ? null : id))}
            />
          )}
        </section>

        <Sidebar
          ringCounts={ringCounts}
          capabilityCounts={capabilityCounts}
          focusedQuad={focusedQuad}
          focusedRing={focusedRing}
          capabilityFilter={capabilityFilter}
          onFocusQuad={setFocusedQuad}
          onFocusRing={setFocusedRing}
        />
      </main>

      {selectedId !== null && (
        <ArtifactPanel artifactId={selectedId} onClose={() => setSelectedId(null)} />
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
      <LegendDot color="currentColor" filled label="watched (Evaluate / Watch)" />
      <LegendDot color="var(--color-accent)" filled={false} label="recently moved" />
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
  ringCounts,
  capabilityCounts,
  focusedQuad,
  focusedRing,
  capabilityFilter,
  onFocusQuad,
  onFocusRing,
}: {
  ringCounts: Record<Ring, number>;
  capabilityCounts: Map<string, number>;
  focusedQuad: string | null;
  focusedRing: Ring | null;
  capabilityFilter: string | null;
  onFocusQuad(id: string | null): void;
  onFocusRing(r: Ring | null): void;
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
        <SidebarHeading>Capabilities</SidebarHeading>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          {ECOSYSTEM_QUADRANTS.map((q: Quadrant) => {
            const quadFocused = focusedQuad === q.id;
            const sectorActive = capabilityFilter === q.id;
            const highlighted = quadFocused || sectorActive;
            return (
              <button
                key={q.id}
                type="button"
                onClick={() => onFocusQuad(quadFocused ? null : q.id)}
                aria-pressed={quadFocused}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  width: "100%",
                  textAlign: "left",
                  background: highlighted ? "var(--color-rule)" : "transparent",
                  border: "none",
                  borderRadius: "var(--radius-sm)",
                  cursor: "pointer",
                  padding: "0.375rem 0.5rem",
                  fontFamily: "var(--font-sans)",
                  fontSize: "var(--text-small)",
                  color: highlighted ? "var(--color-accent)" : "inherit",
                }}
              >
                <span>{q.label}</span>
                <span
                  style={{
                    color: "var(--color-muted)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {capabilityCounts.get(q.id) ?? 0}
                </span>
              </button>
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

// --- Release-event feed ----------------------------------------------------

const FEED_WINDOW_DAYS = 30;

function ReleaseFeed({
  onSelectArtifact,
}: {
  onSelectArtifact(artifactId: number): void;
}) {
  const [relevantOnly, setRelevantOnly] = useState(true);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["ecosystem-events", FEED_WINDOW_DAYS, relevantOnly],
    queryFn: () =>
      api.ecosystemEvents({ days: FEED_WINDOW_DAYS, relevant_only: relevantOnly }),
  });

  // In static mode the events file ships everything; apply the toggle here so
  // the control still works without a backend.
  const events = useMemo<EcosystemEventItem[]>(() => {
    const all = data?.events ?? [];
    return relevantOnly ? all.filter((e) => e.relevant) : all;
  }, [data, relevantOnly]);

  const groups = useMemo(() => groupByDate(events), [events]);

  return (
    <section style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          gap: "1rem",
        }}
      >
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
          }}
        >
          Releases · last {FEED_WINDOW_DAYS} days
        </div>
        <label
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.375rem",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: relevantOnly ? "var(--color-accent)" : "var(--color-muted)",
            cursor: "pointer",
            userSelect: "none",
          }}
        >
          <input
            type="checkbox"
            checked={relevantOnly}
            onChange={(e) => setRelevantOnly(e.target.checked)}
          />
          relevant only
        </label>
      </div>

      {isLoading && (
        <div className="skeleton-block" style={{ height: "8rem" }} aria-hidden="true" />
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
          Could not load releases:{" "}
          {error instanceof Error ? error.message : "unknown error"}.
        </div>
      )}
      {data && events.length === 0 && (
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            lineHeight: 1.5,
          }}
        >
          No release events in the last {FEED_WINDOW_DAYS} days. Run{" "}
          <code style={{ fontFamily: "var(--font-mono)" }}>radar fetch-ecosystem</code>{" "}
          to populate.
        </div>
      )}

      {groups.map((group) => (
        <div key={group.date}>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              borderBottom: "1px solid var(--color-rule)",
              paddingBottom: "0.25rem",
              marginBottom: "0.5rem",
            }}
          >
            {group.label}
          </div>
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: "0.75rem",
            }}
          >
            {group.events.map((event) => (
              <ReleaseRow
                key={event.id}
                event={event}
                onSelectArtifact={onSelectArtifact}
              />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

interface DateGroup {
  date: string;
  label: string;
  events: EcosystemEventItem[];
}

function groupByDate(events: EcosystemEventItem[]): DateGroup[] {
  const buckets = new Map<string, EcosystemEventItem[]>();
  for (const event of events) {
    const key = event.event_date.slice(0, 10);
    const bucket = buckets.get(key) ?? [];
    bucket.push(event);
    buckets.set(key, bucket);
  }
  return [...buckets.entries()]
    .sort((a, b) => (a[0] < b[0] ? 1 : -1))
    .map(([date, group]) => ({
      date,
      label: formatGroupLabel(date),
      events: group,
    }));
}

function formatGroupLabel(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(d.getTime())) return isoDate;
  return d.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

function ReleaseRow({
  event,
  onSelectArtifact,
}: {
  event: EcosystemEventItem;
  onSelectArtifact(artifactId: number): void;
}) {
  const [open, setOpen] = useState(false);
  const hasBody = event.body.trim().length > 0;
  return (
    <li
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.25rem",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: "0.5rem", flexWrap: "wrap" }}>
        <SeverityDot severity={event.severity} />
        <button
          type="button"
          onClick={() => onSelectArtifact(event.artifact_id)}
          style={{
            background: "transparent",
            border: "none",
            padding: 0,
            cursor: "pointer",
            fontFamily: "var(--font-display)",
            fontSize: "1.05rem",
            color: "inherit",
            textDecoration: "underline",
            textUnderlineOffset: "2px",
          }}
        >
          {event.artifact_name}
        </button>
        <EcosystemBadge ecosystem={event.ecosystem} />
        {event.version && (
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-small)",
              color: "var(--color-accent)",
            }}
          >
            {event.version}
          </span>
        )}
        {event.event_type === "major_release" && (
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              letterSpacing: "0.04em",
              textTransform: "uppercase",
              color: "var(--color-muted)",
              border: "1px solid var(--color-rule)",
              borderRadius: "var(--radius-sm)",
              padding: "0.0625rem 0.375rem",
            }}
          >
            major
          </span>
        )}
        <a
          href={event.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{
            marginLeft: "auto",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            whiteSpace: "nowrap",
          }}
        >
          open ↗
        </a>
      </div>
      {event.summary && (
        <div
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-small)",
            color: "var(--color-muted)",
            lineHeight: 1.45,
            marginLeft: "1rem",
          }}
        >
          {event.summary}
        </div>
      )}
      {hasBody && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          style={{
            alignSelf: "flex-start",
            marginLeft: "1rem",
            background: "transparent",
            border: "none",
            padding: 0,
            cursor: "pointer",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-accent)",
            letterSpacing: "0.04em",
          }}
        >
          {open ? "hide release notes ↑" : "release notes ↓"}
        </button>
      )}
      {open && hasBody && (
        <pre
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            lineHeight: 1.5,
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            margin: "0.25rem 0 0 1rem",
            padding: "0.5rem",
            border: "1px solid var(--color-rule)",
            borderRadius: "var(--radius-sm)",
            maxHeight: "20rem",
            overflowY: "auto",
          }}
        >
          {event.body}
        </pre>
      )}
    </li>
  );
}
