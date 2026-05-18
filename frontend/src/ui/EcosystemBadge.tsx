// Small pill identifying a package ecosystem — github / pypi / crates / npm.
// Used in the release-event feed and the artifact detail panel.

const ECOSYSTEM_LABEL: Record<string, string> = {
  github: "GitHub",
  pypi: "PyPI",
  crates: "crates.io",
  npm: "npm",
};

export function EcosystemBadge({ ecosystem }: { ecosystem: string }) {
  const label = ECOSYSTEM_LABEL[ecosystem] ?? ecosystem;
  return (
    <span
      title={`${label} ecosystem`}
      style={{
        display: "inline-block",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-micro)",
        letterSpacing: "0.04em",
        color: "var(--color-muted)",
        border: "1px solid var(--color-rule)",
        borderRadius: "var(--radius-sm)",
        padding: "0.0625rem 0.375rem",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}
