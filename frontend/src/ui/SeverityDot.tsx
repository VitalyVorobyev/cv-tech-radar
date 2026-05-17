// Small filled dot indicating an ecosystem release event's severity.
// high → accent, medium → ink, low → muted. Used in the release-event feed
// and the artifact detail panel.

const SEVERITY_COLOR: Record<string, string> = {
  high: "var(--color-accent)",
  medium: "currentColor",
  low: "var(--color-muted)",
};

export function SeverityDot({ severity }: { severity: string }) {
  const color = SEVERITY_COLOR[severity] ?? "var(--color-muted)";
  return (
    <svg
      width={8}
      height={8}
      aria-label={`${severity} severity`}
      role="img"
      style={{ flexShrink: 0, alignSelf: "center" }}
    >
      <circle cx={4} cy={4} r={3} fill={color} />
    </svg>
  );
}
