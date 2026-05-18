import type { QuadrantId, Ring, TrackInfo } from "./api";

export const RING_ORDER: Ring[] = ["Use", "Prototype", "Evaluate", "Watch"];
export const RING_ORDER_WITH_IGNORE: Ring[] = [...RING_ORDER, "Ignore"];

export const RING_RADII_NORMALIZED = [0, 0.3, 0.55, 0.78, 1.0] as const;
export const GOLDEN_ANGLE_DEG = 137.508;
export const GOLDEN_RATIO = 0.6180339;

export interface Quadrant {
  // Papers radar uses QuadrantId; the ecosystem radar uses CapabilityId.
  // Both are plain string slugs, so `string` keeps RadarPlot generic.
  id: string;
  label: string;
  tracks: readonly string[];
}

// Visual ordering + display labels for the four quadrants. The set of tracks
// inside each is built at runtime from /api/tracks via assembleQuadrants(),
// so adding a track to config/topics.yaml is enough — no parallel list here.
export const QUADRANT_DEFS: ReadonlyArray<{ id: QuadrantId; label: string }> = [
  { id: "perception", label: "Perception & Sensing" },
  { id: "scene", label: "Scene & World" },
  { id: "models", label: "Models & Data" },
  { id: "tooling", label: "Tooling & Deployment" },
] as const;

export function assembleQuadrants(tracks: readonly TrackInfo[]): Quadrant[] {
  return QUADRANT_DEFS.map((def) => ({
    id: def.id,
    label: def.label,
    tracks: tracks.filter((t) => t.quadrant === def.id).map((t) => t.name),
  }));
}

export function quadrantOfTrack(
  track: string,
  quadrants: readonly Quadrant[],
): Quadrant | null {
  for (const q of quadrants) {
    if (q.tracks.includes(track)) return q;
  }
  return null;
}

export const RING_COPY: Record<Exclude<Ring, "Ignore">, string> = {
  Use: "In production. Validated, trusted, default choice.",
  Prototype: "Active spike. Has code + a clear test path.",
  Evaluate: "Worth a closer look. Benchmark or read-through.",
  Watch: "Adjacent. Track upstream development.",
};

// --- Ecosystem radar quadrants ---------------------------------------------
// The ecosystem radar's four quadrants are the artifact `capability` values —
// a fixed backend enum (radar/schemas.py CapabilityId), NOT config-driven, so
// they are hardcoded here. Order maps to RadarPlot's TL, TR, BR, BL positions.

export type CapabilityId =
  | "cv-imaging"
  | "ml-runtimes"
  | "build-tooling"
  | "viz-3d-sensors";

export const CAPABILITY_QUADRANTS: ReadonlyArray<{
  id: CapabilityId;
  label: string;
}> = [
  { id: "cv-imaging", label: "CV & imaging" }, // TL
  { id: "ml-runtimes", label: "ML runtimes & models" }, // TR
  { id: "build-tooling", label: "Build & app tooling" }, // BR
  { id: "viz-3d-sensors", label: "3D, sensors & viz" }, // BL
] as const;

// One Quadrant per capability whose `tracks` array contains exactly that
// capability id — the ecosystem radar places each dot by `capability`, so the
// quadrant's membership list IS the single capability id.
export const ECOSYSTEM_QUADRANTS: readonly Quadrant[] = CAPABILITY_QUADRANTS.map(
  (cap) => ({ id: cap.id, label: cap.label, tracks: [cap.id] as const }),
);

export const CAPABILITY_LABEL: Record<CapabilityId, string> = Object.fromEntries(
  CAPABILITY_QUADRANTS.map((cap) => [cap.id, cap.label]),
) as Record<CapabilityId, string>;

export const LAUNCH_DATE = new Date("2025-12-01T00:00:00Z");

export function radarVolume(now: Date = new Date()): number {
  const ms = now.getTime() - LAUNCH_DATE.getTime();
  return Math.max(1, Math.floor(ms / (7 * 86_400_000)));
}
