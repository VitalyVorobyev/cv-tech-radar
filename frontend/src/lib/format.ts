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
 * Truncate an item ID for display — show last 6 hex chars or full ID if short.
 * IDs from the backend are numeric strings; keep as-is with min 3 chars.
 */
export function formatId(id: string): string {
  if (id.length <= 6) return id.padStart(3, "0");
  return id.slice(-6);
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
