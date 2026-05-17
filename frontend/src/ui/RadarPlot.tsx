// Polar radar plot — 4 rings × 4 quadrants × 3 tracks per quadrant.
//
// GEOMETRY NOTES (read before editing):
//
//   - SVG y-axis grows DOWN, not up. Math.cos(rad)/Math.sin(rad) use radians
//     measured from the +x axis clockwise. The four quadrants sit at:
//       TL: 180..270°   TR: 270..360°   BR: 0..90°   BL: 90..180°
//   - Render order (z-stack) — DO NOT REORDER without thinking about
//     hit-testing and dimming:
//       1) quadrant fills (subtle background tint)
//       2) quadrant cross-lines
//       3) track-sector hit areas — fill="transparent" is INTENTIONAL.
//          Transparent fills receive pointer events. fill="none" does NOT.
//       4) ring circles
//       5) ring labels (clickable, on paper-pill background)
//       6) quadrant corner labels
//       7) dots (drawn LAST so they win the hit-test over sector overlays)
//       8) pulse rings (sibling of dot; lower z than next dot)
//       9) sector tooltip (rendered last so it overlays everything)
//   - Dot placement is deterministic. Items sorted by decided_at desc per
//     (quadrant, ring) cell, then golden-angle phyllotaxis distributes them
//     inside the cell. The same item lands in the same pixel across renders.

import type {
  CSSProperties,
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
} from "react";
import { useMemo, useRef, useState } from "react";
import type { Movement, Ring } from "../lib/api";
import {
  GOLDEN_ANGLE_DEG,
  GOLDEN_RATIO,
  type Quadrant,
  RING_ORDER,
  RING_RADII_NORMALIZED,
} from "../lib/constants";

// Minimal structural shape a radar dot must satisfy. Both the papers
// `BoardItem` and an adapted ecosystem `ArtifactBoardItem` (see EcosystemView)
// fit this interface — `RadarPlot` is shared, not forked. The `tracks` array
// is the default quadrant-placement key; override it with the `quadrantOf`
// prop (e.g. the ecosystem radar places by `capability`).
export interface RadarDot {
  item_id: number;
  title: string;
  ring: Ring;
  tracks: string[];
  decided_at: string;
  movement: Movement | null;
}

const SIZE = 760;
const PAD = 28;
const CX = SIZE / 2;
const CY = SIZE / 2;
const MAX_R = SIZE / 2 - PAD;

// Pointer travel (in SVG units) past which a press becomes a drag rather than
// a click. Below it, pointerup falls through to the normal select-on-click.
const DRAG_THRESHOLD = 6;

// Map a radius (SVG units, from centre) to the ring whose band contains it.
// Beyond the outer ring → "Ignore" (drop = remove from the board).
function ringAtRadius(r: number): Ring {
  const norm = r / MAX_R;
  for (let i = 0; i < RING_ORDER.length; i += 1) {
    if (norm <= RING_RADII_NORMALIZED[i + 1]!) return RING_ORDER[i]!;
  }
  return "Ignore";
}

// Convert a viewport pointer position into the SVG's internal coordinate space
// (the 760×760 viewBox), accounting for the element's on-screen scale.
function toSvgPoint(
  svg: SVGSVGElement,
  clientX: number,
  clientY: number,
): { x: number; y: number } | null {
  const ctm = svg.getScreenCTM();
  if (!ctm) return null;
  const p = new DOMPoint(clientX, clientY).matrixTransform(ctm.inverse());
  return { x: p.x, y: p.y };
}

const QUAD_ANGLES: Array<{ start: number; end: number }> = [
  { start: 180, end: 270 }, // TL — perception
  { start: 270, end: 360 }, // TR — scene
  { start: 0, end: 90 }, // BR — models
  { start: 90, end: 180 }, // BL — tooling
];

interface Placed {
  item: RadarDot;
  x: number;
  y: number;
  quadIndex: number;
  ringIndex: number;
}

// Default placement key: a dot's primary track. The ecosystem radar passes a
// `quadrantOf` that returns the artifact `capability` instead.
const defaultQuadrantOf = (dot: RadarDot): string | undefined => dot.tracks[0];

export interface RadarPlotProps {
  items: RadarDot[];
  // Papers radar: built once from /api/tracks by useQuadrants(). Ecosystem
  // radar: the fixed CAPABILITY quadrants — see lib/constants.ts.
  quadrants: readonly Quadrant[];
  focusedQuad: string | null;
  focusedRing: Ring | null;
  trackFilter: string | null;
  hoveredId: number | null;
  selectedId: number | null;
  showLabels: boolean;
  reducedMotion?: boolean;
  // When true, dots can be dragged radially to record a new-ring decision.
  // False in the public static build (no write API).
  canEdit?: boolean;
  // Picks the quadrant-membership key for each dot. Defaults to the dot's
  // first track (papers radar); the ecosystem radar supplies `capability`.
  quadrantOf?: (dot: RadarDot) => string | undefined;
  // Dev-only message logged once per unmapped quadrant key. Defaults to the
  // papers-radar topics.yaml hint; the ecosystem radar overrides it.
  unmappedKeyWarning?: (key: string, dot: RadarDot) => string;
  onHoverDot(id: number | null): void;
  onSelectDot(id: number): void;
  onFocusQuad(quadId: string | null): void;
  onFocusRing(ring: Ring | null): void;
  onTrackFilter(track: string | null): void;
  // Fired when a dot is dropped in a different ring band. `ring` may be
  // "Ignore" (dropped beyond the outer ring), which removes it from the board.
  onChangeRing?(itemId: number, ring: Ring): void;
}

function defaultUnmappedKeyWarning(key: string, dot: RadarDot): string {
  return (
    `[RadarPlot] Track "${key}" is not mapped to any quadrant — ` +
    `item #${dot.item_id} (${dot.title}) will not appear on the radar. ` +
    `Add a "quadrant:" field to that track in config/topics.yaml.`
  );
}

function polar(r: number, deg: number): { x: number; y: number } {
  const rad = (deg * Math.PI) / 180;
  return { x: CX + r * Math.cos(rad), y: CY + r * Math.sin(rad) };
}

function sectorPath(startA: number, endA: number, rIn: number, rOut: number): string {
  const s1 = polar(rOut, startA);
  const e1 = polar(rOut, endA);
  const s2 = polar(rIn, endA);
  const e2 = polar(rIn, startA);
  const largeArc = endA - startA <= 180 ? 0 : 1;
  return [
    `M ${s1.x} ${s1.y}`,
    `A ${rOut} ${rOut} 0 ${largeArc} 1 ${e1.x} ${e1.y}`,
    `L ${s2.x} ${s2.y}`,
    `A ${rIn} ${rIn} 0 ${largeArc} 0 ${e2.x} ${e2.y}`,
    "Z",
  ].join(" ");
}

function ringBand(index: number): { inner: number; outer: number; ring: Ring } {
  return {
    ring: RING_ORDER[index]!,
    inner: RING_RADII_NORMALIZED[index]! * MAX_R,
    outer: RING_RADII_NORMALIZED[index + 1]! * MAX_R,
  };
}

function quadIndexOfTrack(track: string, quadrants: readonly Quadrant[]): number {
  return quadrants.findIndex((q) => q.tracks.includes(track));
}

function placeDots(
  items: RadarDot[],
  quadrants: readonly Quadrant[],
  quadrantOf: (dot: RadarDot) => string | undefined,
  unmappedKeyWarning: (key: string, dot: RadarDot) => string,
): Placed[] {
  const cells = new Map<string, RadarDot[]>();
  const warnedTracks = new Set<string>();
  // While the /api/tracks request is in-flight, quadrants is empty — skip the
  // warning so we don't shout for every item on first render.
  const ready = quadrants.length > 0;
  for (const item of items) {
    const track = quadrantOf(item);
    if (!track) continue;
    const qi = quadIndexOfTrack(track, quadrants);
    if (qi < 0) {
      if (ready && import.meta.env.DEV && !warnedTracks.has(track)) {
        warnedTracks.add(track);
        console.warn(unmappedKeyWarning(track, item));
      }
      continue;
    }
    const ri = RING_ORDER.indexOf(item.ring);
    if (ri < 0) continue;
    const key = `${qi}-${ri}`;
    const bucket = cells.get(key) ?? [];
    bucket.push(item);
    cells.set(key, bucket);
  }
  const placed: Placed[] = [];
  for (const [key, bucket] of cells.entries()) {
    const [qiStr, riStr] = key.split("-");
    const qi = Number(qiStr);
    const ri = Number(riStr);
    const ang = QUAD_ANGLES[qi]!;
    const band = ringBand(ri);
    // Stable order: newest first.
    bucket.sort((a, b) => (a.decided_at < b.decided_at ? 1 : -1));
    bucket.forEach((item, idx) => {
      const sub = idx + 0.5;
      const aPad = 6;
      const angRange = ang.end - ang.start - aPad * 2;
      const a = ang.start + aPad + ((sub * GOLDEN_ANGLE_DEG) % angRange);
      const rPad = (band.outer - band.inner) * 0.08;
      const rRange = band.outer - band.inner - rPad * 2;
      const rNorm = (sub * GOLDEN_RATIO) % 1;
      const r = band.inner + rPad + rNorm * rRange;
      const { x, y } = polar(r, a);
      placed.push({ item, x, y, quadIndex: qi, ringIndex: ri });
    });
  }
  return placed;
}

function handleActivate(
  event: ReactKeyboardEvent<SVGElement>,
  action: () => void,
): void {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    event.stopPropagation();
    action();
  }
}

export function RadarPlot({
  items,
  quadrants,
  focusedQuad,
  focusedRing,
  trackFilter,
  hoveredId,
  selectedId,
  showLabels,
  reducedMotion = false,
  canEdit = false,
  quadrantOf = defaultQuadrantOf,
  unmappedKeyWarning = defaultUnmappedKeyWarning,
  onHoverDot,
  onSelectDot,
  onFocusQuad,
  onFocusRing,
  onTrackFilter,
  onChangeRing,
}: RadarPlotProps) {
  const [hoveredTrack, setHoveredTrack] = useState<string | null>(null);

  // Drag state. `drag` (React state) holds the live pointer position so the
  // dragged dot re-renders as it moves; `dragRef` is the source of truth read
  // inside pointer handlers without waiting for a render. `didDragRef` lets the
  // click handler that fires after pointerup tell a drag from a plain click.
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{
    id: number;
    pointerId: number;
    startX: number;
    startY: number;
    moved: boolean;
  } | null>(null);
  const didDragRef = useRef(false);
  const [drag, setDrag] = useState<{ id: number; x: number; y: number } | null>(
    null,
  );

  const dots = useMemo(
    () => placeDots(items, quadrants, quadrantOf, unmappedKeyWarning),
    [items, quadrants, quadrantOf, unmappedKeyWarning],
  );

  const ringBands = useMemo(
    () => RING_ORDER.map((_, i) => ringBand(i)),
    [],
  );

  const dotR = 5.5;
  const hoverR = dotR + 3;

  // Per-sector counts (for tooltip + a11y), keyed by the same quadrant key
  // used to place each dot.
  const trackCounts = useMemo(() => {
    const counts = new Map<string, { total: number; byRing: Record<string, number> }>();
    for (const it of items) {
      const track = quadrantOf(it);
      if (!track) continue;
      const entry = counts.get(track) ?? { total: 0, byRing: {} };
      entry.total += 1;
      entry.byRing[it.ring] = (entry.byRing[it.ring] ?? 0) + 1;
      counts.set(track, entry);
    }
    return counts;
  }, [items, quadrantOf]);

  // Ring the dragged dot would land in, recomputed each render from `drag`.
  const dragTargetRing: Ring | null = drag
    ? ringAtRadius(Math.hypot(drag.x - CX, drag.y - CY))
    : null;

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${SIZE} ${SIZE}`}
      width="100%"
      height="100%"
      style={{ display: "block", fontFamily: "var(--font-mono)" }}
      role="img"
      aria-label="CV Tech Radar"
    >
      <defs>
        <filter id="cvradar-dot-glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* 1) Quadrant background fills — subtle tint, deepens on focus, dims siblings. */}
      {quadrants.map((q, qi) => {
        const isFocus = focusedQuad === q.id;
        const isDim = focusedQuad !== null && !isFocus;
        const opacity = isFocus ? 0.04 : isDim ? 0 : 0.015;
        return (
          <path
            key={q.id}
            d={sectorPath(QUAD_ANGLES[qi]!.start, QUAD_ANGLES[qi]!.end, 0, MAX_R)}
            fill="var(--color-accent)"
            fillOpacity={opacity}
            onClick={() => onFocusQuad(isFocus ? null : q.id)}
            style={{ cursor: "pointer" }}
            aria-hidden="true"
          />
        );
      })}

      {/* 2) Quadrant dividers (cross-lines through centre). */}
      <line x1={CX} y1={CY - MAX_R} x2={CX} y2={CY + MAX_R} stroke="var(--color-rule)" strokeWidth="1" />
      <line x1={CX - MAX_R} y1={CY} x2={CX + MAX_R} y2={CY} stroke="var(--color-rule)" strokeWidth="1" />

      {/* 3) Track sector hit-areas. fill="transparent" is intentional — it receives pointer events. */}
      {quadrants.map((q, qi) => {
        const ang = QUAD_ANGLES[qi]!;
        const sliceDeg = (ang.end - ang.start) / q.tracks.length;
        return q.tracks.map((track, ti) => {
          const sa = ang.start + ti * sliceDeg;
          const ea = sa + sliceDeg;
          const isHover = hoveredTrack === track;
          const isFiltered = trackFilter === track;
          const counts = trackCounts.get(track);
          const total = counts?.total ?? 0;
          return (
            <path
              key={track}
              d={sectorPath(sa, ea, 0, MAX_R)}
              fill={isHover || isFiltered ? "var(--color-accent)" : "transparent"}
              fillOpacity={isFiltered ? 0.1 : isHover ? 0.06 : 0}
              stroke={isFiltered ? "var(--color-accent)" : "transparent"}
              strokeOpacity={isFiltered ? 0.4 : 0}
              strokeWidth="1"
              role="button"
              tabIndex={0}
              aria-label={`${track} — ${total} items`}
              style={{ cursor: "pointer", transition: "fill-opacity 120ms ease-out" }}
              onMouseEnter={() => setHoveredTrack(track)}
              onMouseLeave={() => setHoveredTrack(null)}
              onFocus={() => setHoveredTrack(track)}
              onBlur={() => setHoveredTrack(null)}
              onClick={(e) => {
                e.stopPropagation();
                onTrackFilter(trackFilter === track ? null : track);
              }}
              onKeyDown={(e) =>
                handleActivate(e, () =>
                  onTrackFilter(trackFilter === track ? null : track),
                )
              }
            >
              <title>{`${track} — ${total} items`}</title>
            </path>
          );
        });
      })}

      {/* 4) Ring boundary circles. */}
      {ringBands.map((band) => (
        <circle
          key={band.ring}
          cx={CX}
          cy={CY}
          r={band.outer}
          fill="none"
          stroke="var(--color-rule)"
          strokeWidth="1"
        />
      ))}

      {/* 5) Ring labels (vertical axis). */}
      {ringBands.map((band) => {
        const yPos = CY + (band.inner + band.outer) / 2 + 4;
        const isFocused = focusedRing === band.ring;
        return (
          <g key={band.ring}>
            <rect
              x={CX - 26}
              y={yPos - 12}
              width="52"
              height="16"
              fill="var(--color-paper)"
              fillOpacity="0.85"
              rx="2"
              pointerEvents="none"
            />
            <text
              x={CX}
              y={yPos}
              textAnchor="middle"
              fontSize="10"
              letterSpacing="0.1em"
              fill={isFocused ? "var(--color-accent)" : "var(--color-muted)"}
              style={{ textTransform: "uppercase", cursor: "pointer", userSelect: "none" }}
              role="button"
              tabIndex={0}
              aria-label={`Toggle ${band.ring} ring focus`}
              onClick={() => onFocusRing(isFocused ? null : band.ring)}
              onKeyDown={(e) =>
                handleActivate(e, () => onFocusRing(isFocused ? null : band.ring))
              }
            >
              {band.ring}
            </text>
          </g>
        );
      })}

      {/* 6) Quadrant corner labels + their stacked track sublabels. */}
      {quadrants.map((q, qi) => {
        const positions = [
          { x: 20, y: 24, anchor: "start" as const, isTop: true },
          { x: SIZE - 20, y: 24, anchor: "end" as const, isTop: true },
          { x: SIZE - 20, y: SIZE - 12, anchor: "end" as const, isTop: false },
          { x: 20, y: SIZE - 12, anchor: "start" as const, isTop: false },
        ];
        const p = positions[qi]!;
        const isFocused = focusedQuad === q.id;
        const labelY = p.isTop ? p.y : p.y - q.tracks.length * 11 - 6;
        return (
          <g key={q.id}>
            <text
              x={p.x}
              y={labelY}
              textAnchor={p.anchor}
              fontSize="11"
              letterSpacing="0.08em"
              fontWeight="500"
              fill={isFocused ? "var(--color-accent)" : "currentColor"}
              style={{ textTransform: "uppercase", cursor: "pointer", userSelect: "none" }}
              role="button"
              tabIndex={0}
              aria-label={`Toggle ${q.label} quadrant focus`}
              onClick={() => onFocusQuad(isFocused ? null : q.id)}
              onKeyDown={(e) =>
                handleActivate(e, () => onFocusQuad(isFocused ? null : q.id))
              }
            >
              {q.label}
            </text>
            {q.tracks.map((track, ti) => (
              <text
                key={track}
                x={p.x}
                y={
                  p.isTop
                    ? p.y + 14 + ti * 11
                    : p.y - (q.tracks.length - 1 - ti) * 11 - 4
                }
                textAnchor={p.anchor}
                fontSize="9"
                fill="var(--color-muted)"
                style={{ userSelect: "none" }}
              >
                {track}
              </text>
            ))}
          </g>
        );
      })}

      {/* 6.5) Drag-target band — highlights the ring the dragged dot will land
          in. Drawn under the dots so the dot stays legible on top. */}
      {drag &&
        dragTargetRing &&
        dragTargetRing !== "Ignore" &&
        (() => {
          const band = ringBands[RING_ORDER.indexOf(dragTargetRing)]!;
          const mid = (band.inner + band.outer) / 2;
          return (
            <circle
              cx={CX}
              cy={CY}
              r={mid}
              fill="none"
              stroke="var(--color-accent)"
              strokeOpacity={0.1}
              strokeWidth={band.outer - band.inner}
              pointerEvents="none"
            />
          );
        })()}

      {/* 7) Dots — drawn last so they win the hit-test. */}
      {dots.map((d) => {
        const isHover = hoveredId === d.item.item_id;
        const isSelected = selectedId === d.item.item_id;
        const isDragging = drag?.id === d.item.item_id;
        // While dragging, the dot follows the pointer; otherwise it sits at its
        // deterministic placed position.
        const cx = isDragging ? drag!.x : d.x;
        const cy = isDragging ? drag!.y : d.y;
        const dimmed =
          !isDragging &&
          ((focusedQuad !== null && quadrants[d.quadIndex]!.id !== focusedQuad) ||
            (focusedRing !== null && d.item.ring !== focusedRing) ||
            (trackFilter !== null && !d.item.tracks.includes(trackFilter)));
        const ringIsAccent = d.item.ring === "Use" || d.item.ring === "Prototype";
        const isPulsing =
          !reducedMotion &&
          !isDragging &&
          (d.item.movement === "new" || d.item.movement === "in");
        const pulseStyle = isPulsing
          ? ({
              "--pulse-r-min": `${dotR + 2}`,
              "--pulse-r-max": `${dotR + 9}`,
            } as CSSProperties)
          : undefined;

        function onPointerDown(e: ReactPointerEvent<SVGGElement>) {
          if (!canEdit || !onChangeRing) return;
          const svg = svgRef.current;
          if (!svg) return;
          const p = toSvgPoint(svg, e.clientX, e.clientY);
          if (!p) return;
          didDragRef.current = false;
          dragRef.current = {
            id: d.item.item_id,
            pointerId: e.pointerId,
            startX: p.x,
            startY: p.y,
            moved: false,
          };
          e.currentTarget.setPointerCapture(e.pointerId);
        }

        function onPointerMove(e: ReactPointerEvent<SVGGElement>) {
          const st = dragRef.current;
          if (!st || st.id !== d.item.item_id) return;
          const svg = svgRef.current;
          if (!svg) return;
          const p = toSvgPoint(svg, e.clientX, e.clientY);
          if (!p) return;
          if (
            !st.moved &&
            Math.hypot(p.x - st.startX, p.y - st.startY) > DRAG_THRESHOLD
          ) {
            st.moved = true;
          }
          if (st.moved) setDrag({ id: st.id, x: p.x, y: p.y });
        }

        function onPointerUp(e: ReactPointerEvent<SVGGElement>) {
          const st = dragRef.current;
          if (!st || st.id !== d.item.item_id) return;
          dragRef.current = null;
          e.currentTarget.releasePointerCapture?.(e.pointerId);
          if (!st.moved) return; // a plain click — let onClick select it.
          // Suppress the click event that fires right after this pointerup.
          didDragRef.current = true;
          const svg = svgRef.current;
          const p = svg ? toSvgPoint(svg, e.clientX, e.clientY) : null;
          setDrag(null);
          if (!p) return;
          const target = ringAtRadius(Math.hypot(p.x - CX, p.y - CY));
          if (target !== d.item.ring) onChangeRing?.(d.item.item_id, target);
        }

        return (
          <g
            key={d.item.item_id}
            role="button"
            tabIndex={0}
            aria-label={`#${d.item.item_id} ${d.item.title} in ${d.item.ring}`}
            style={{
              cursor: isDragging ? "grabbing" : canEdit ? "grab" : "pointer",
              touchAction: canEdit ? "none" : undefined,
            }}
            onMouseEnter={() => onHoverDot(d.item.item_id)}
            onMouseLeave={() => onHoverDot(null)}
            onFocus={() => onHoverDot(d.item.item_id)}
            onBlur={() => onHoverDot(null)}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onClick={() => {
              // A drag just ended — swallow the trailing click so it doesn't
              // also open the detail panel.
              if (didDragRef.current) {
                didDragRef.current = false;
                return;
              }
              onSelectDot(d.item.item_id);
            }}
            onKeyDown={(e) => handleActivate(e, () => onSelectDot(d.item.item_id))}
          >
            {/* Native SVG tooltip — surfaces title, ring, and first track on hover
                without forcing a click to open the side panel. */}
            <title>
              {`${d.item.title}\n${d.item.ring}${
                d.item.tracks[0] ? ` · ${d.item.tracks[0]}` : ""
              }`}
            </title>
            {isPulsing && (
              <circle
                className="cvradar-pulse-ring"
                cx={cx}
                cy={cy}
                r={dotR + 4}
                fill="none"
                stroke="var(--color-accent)"
                strokeOpacity={dimmed ? 0.12 : 0.45}
                strokeWidth="1"
                style={pulseStyle}
                pointerEvents="none"
              />
            )}
            <circle
              cx={cx}
              cy={cy}
              r={isHover || isSelected || isDragging ? hoverR : dotR}
              fill={ringIsAccent ? "var(--color-accent)" : "currentColor"}
              fillOpacity={dimmed ? 0.18 : 1}
              stroke={isSelected || isDragging ? "var(--color-accent)" : "none"}
              strokeWidth={isSelected || isDragging ? 2 : 0}
              filter={
                isHover || isSelected || isDragging
                  ? "url(#cvradar-dot-glow)"
                  : undefined
              }
            />
            {showLabels && !dimmed && (
              <text
                x={cx + dotR + 4}
                y={cy + 3}
                fontSize="9"
                fill={isHover || isSelected ? "currentColor" : "var(--color-muted)"}
                style={{ pointerEvents: "none", userSelect: "none" }}
              >
                {d.item.item_id}
              </text>
            )}
            {/* Target-ring caption that tracks the dot while it is dragged. */}
            {isDragging && dragTargetRing && (
              <text
                x={cx + dotR + 6}
                y={cy - dotR - 4}
                fontSize="10"
                fontWeight="500"
                fill={
                  dragTargetRing === "Ignore"
                    ? "var(--color-muted)"
                    : "var(--color-accent)"
                }
                letterSpacing="0.08em"
                style={{
                  textTransform: "uppercase",
                  pointerEvents: "none",
                  userSelect: "none",
                }}
              >
                {dragTargetRing === "Ignore"
                  ? "remove"
                  : dragTargetRing === d.item.ring
                    ? `${dragTargetRing} ·`
                    : `→ ${dragTargetRing}`}
              </text>
            )}
          </g>
        );
      })}

      {/* 8) Sector tooltip (overlays everything). */}
      {hoveredTrack &&
        (() => {
          const qi = quadIndexOfTrack(hoveredTrack, quadrants);
          if (qi < 0) return null;
          const q = quadrants[qi]!;
          const ti = q.tracks.indexOf(hoveredTrack);
          const ang = QUAD_ANGLES[qi]!;
          const sliceDeg = (ang.end - ang.start) / q.tracks.length;
          const midA = ang.start + ti * sliceDeg + sliceDeg / 2;
          const midR = MAX_R * 0.62;
          const { x: tx, y: ty } = polar(midR, midA);
          const counts = trackCounts.get(hoveredTrack);
          const total = counts?.total ?? 0;
          const byRing = counts?.byRing ?? {};
          const lines = RING_ORDER.filter((r) => (byRing[r] ?? 0) > 0).map((r) => ({
            ring: r,
            n: byRing[r] ?? 0,
          }));
          const boxW = 180;
          const boxH = 24 + 14 + lines.length * 13;
          const bx = Math.min(Math.max(tx - boxW / 2, 8), SIZE - boxW - 8);
          const by = Math.min(Math.max(ty - boxH / 2, 8), SIZE - boxH - 8);
          return (
            <g pointerEvents="none">
              <rect
                x={bx}
                y={by}
                width={boxW}
                height={boxH}
                fill="var(--color-paper)"
                stroke="var(--color-rule)"
                strokeWidth="1"
                rx="2"
              />
              <text
                x={bx + 10}
                y={by + 16}
                fontSize="10"
                fill="var(--color-accent)"
                letterSpacing="0.08em"
                style={{ textTransform: "uppercase" }}
              >
                {q.label}
              </text>
              <text
                x={bx + 10}
                y={by + 32}
                fontSize="12"
                fontFamily="var(--font-display)"
              >
                {hoveredTrack}
              </text>
              <text
                x={bx + boxW - 10}
                y={by + 32}
                textAnchor="end"
                fontSize="11"
                fill="var(--color-muted)"
              >
                {total} {total === 1 ? "item" : "items"}
              </text>
              {lines.map((line, i) => (
                <g key={line.ring}>
                  <text
                    x={bx + 10}
                    y={by + 48 + i * 13}
                    fontSize="9"
                    fill="var(--color-muted)"
                    letterSpacing="0.08em"
                    style={{ textTransform: "uppercase" }}
                  >
                    {line.ring}
                  </text>
                  <text
                    x={bx + boxW - 10}
                    y={by + 48 + i * 13}
                    textAnchor="end"
                    fontSize="9"
                  >
                    {line.n}
                  </text>
                </g>
              ))}
            </g>
          );
        })()}
    </svg>
  );
}
