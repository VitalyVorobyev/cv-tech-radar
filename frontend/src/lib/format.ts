// Date, score, and track formatters for display.

/**
 * Format an ISO date string as "May 10" or "2026-05-10" fallback.
 */
export function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  } catch {
    return iso;
  }
}

/**
 * Format a final score as a zero-padded two-digit integer.
 * Scores are 0–100 from the backend.
 */
export function formatScore(score: number): string {
  return String(Math.round(score)).padStart(2, "0");
}

/**
 * Render an item ID for the row gutter — backend integer, zero-padded to 3.
 */
export function formatId(id: number): string {
  return String(id).padStart(3, "0");
}

/**
 * Format a comma-separated track list for compact row display.
 */
export function formatTracks(tracks: string[]): string {
  return tracks.join(", ");
}

/**
 * Source label — strip leading "arXiv" to just "arXiv", normalise vendor names, etc.
 */
export function formatSource(source: string): string {
  return source;
}

const TIME_BUCKETS: { limit: number; label: (n: number) => string }[] = [
  { limit: 60, label: () => "just now" },
  { limit: 3600, label: (n) => `${Math.floor(n / 60)}m ago` },
  { limit: 86_400, label: (n) => `${Math.floor(n / 3600)}h ago` },
  { limit: 30 * 86_400, label: (n) => `${Math.floor(n / 86_400)}d ago` },
];

/**
 * Format an ISO datetime as a coarse relative-time string (e.g. "3d ago").
 * Falls back to a short date for older timestamps.
 */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const then = new Date(iso);
  const seconds = Math.max(0, Math.floor((now.getTime() - then.getTime()) / 1000));
  for (const bucket of TIME_BUCKETS) {
    if (seconds < bucket.limit) return bucket.label(seconds);
  }
  return then.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}
