import type { Ring } from "./api";

export const RING_ORDER: Ring[] = ["Use", "Prototype", "Evaluate", "Watch"];
export const RING_ORDER_WITH_IGNORE: Ring[] = [...RING_ORDER, "Ignore"];

export const RING_RADII_NORMALIZED = [0, 0.3, 0.55, 0.78, 1.0] as const;
export const GOLDEN_ANGLE_DEG = 137.508;
export const GOLDEN_RATIO = 0.6180339;

export interface Quadrant {
  id: string;
  label: string;
  tracks: readonly string[];
}

export const QUADRANTS: readonly Quadrant[] = [
  {
    id: "perception",
    label: "Perception & Sensing",
    tracks: ["3D Sensors", "Sensors, Cameras & Standards", "Calibration & Camera Models"],
  },
  {
    id: "scene",
    label: "Scene & World",
    tracks: ["3D Geometry & Reconstruction", "Synthetic Data & Simulation", "Robotics Vision"],
  },
  {
    id: "models",
    label: "Models & Data",
    tracks: ["Vision Foundation Models", "Datasets & Benchmarks", "Object Tracking"],
  },
  {
    id: "tooling",
    label: "Tooling & Deployment",
    tracks: ["Edge AI & Deployment", "Open-Source CV Tooling", "Industrial Vision Inspection"],
  },
] as const;

export const RING_COPY: Record<Exclude<Ring, "Ignore">, string> = {
  Use: "In production. Validated, trusted, default choice.",
  Prototype: "Active spike. Has code + a clear test path.",
  Evaluate: "Worth a closer look. Benchmark or read-through.",
  Watch: "Adjacent. Track upstream development.",
};

export function quadrantOfTrack(track: string): Quadrant | null {
  for (const q of QUADRANTS) {
    if (q.tracks.includes(track)) return q;
  }
  return null;
}

export const LAUNCH_DATE = new Date("2025-12-01T00:00:00Z");

export function radarVolume(now: Date = new Date()): number {
  const ms = now.getTime() - LAUNCH_DATE.getTime();
  return Math.max(1, Math.floor(ms / (7 * 86_400_000)));
}
