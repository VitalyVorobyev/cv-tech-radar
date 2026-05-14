// Tiny colored pill for job lifecycle states.
// Used by JobCard, the pipeline view, and the recent-jobs list.

import type { JobState } from "../lib/api";

type BadgeState = JobState | "idle";

interface StatusBadgeProps {
  state: BadgeState;
}

function styleFor(state: BadgeState): React.CSSProperties {
  // "color" is the foreground; we use a 1px border in the same color and a
  // transparent fill so the badge stays flat on both light and dark themes.
  const base: React.CSSProperties = {
    fontFamily: "var(--font-mono)",
    fontSize: "var(--text-micro)",
    letterSpacing: "var(--tracking-caps)",
    textTransform: "uppercase",
    padding: "0.125rem 0.5rem",
    borderRadius: "var(--radius-sm)",
    border: "1px solid currentColor",
    background: "transparent",
    display: "inline-block",
    lineHeight: 1.2,
  };
  switch (state) {
    case "ok":
      return { ...base, color: "var(--color-accent)" };
    case "error":
      return { ...base, color: "var(--color-accent)", fontWeight: 600 };
    case "rate_limited":
      return { ...base, color: "var(--color-accent)", fontStyle: "italic" };
    case "running":
      return { ...base, color: "var(--color-ink)" };
    case "queued":
      return { ...base, color: "var(--color-muted)" };
    case "idle":
    default:
      return { ...base, color: "var(--color-muted)" };
  }
}

function labelFor(state: BadgeState): string {
  switch (state) {
    case "rate_limited":
      return "rate-limited";
    default:
      return state;
  }
}

export function StatusBadge({ state }: StatusBadgeProps) {
  return (
    <span style={styleFor(state)} aria-label={`Status: ${labelFor(state)}`}>
      {labelFor(state)}
    </span>
  );
}
