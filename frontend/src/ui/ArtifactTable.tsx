// Ecosystem "Artifacts" surface — a flat, scannable inventory table of every
// tracked artifact. The radar board is the spatial view; this is the list view
// for quickly reading every library's ring, status, refs and latest release.
// A row click opens the same ArtifactPanel as a radar dot.

import { useMemo } from "react";
import type { ArtifactBoardItem } from "../lib/api";
import { CAPABILITY_LABEL, type CapabilityId, RING_ORDER } from "../lib/constants";
import { EcosystemBadge } from "./EcosystemBadge";

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

const headStyle = {
  fontFamily: "var(--font-mono)",
  fontSize: "var(--text-micro)",
  letterSpacing: "0.06em",
  textTransform: "uppercase" as const,
  color: "var(--color-muted)",
  fontWeight: 500,
  textAlign: "left" as const,
  padding: "0.4rem 0.6rem",
  borderBottom: "1px solid var(--color-rule)",
};

const cellStyle = {
  fontFamily: "var(--font-mono)",
  fontSize: "var(--text-small)",
  padding: "0.5rem 0.6rem",
  borderBottom: "1px solid var(--color-rule)",
  verticalAlign: "baseline" as const,
};

export function ArtifactTable({
  artifacts,
  isLoading,
  selectedId,
  onSelect,
}: {
  artifacts: ArtifactBoardItem[];
  isLoading: boolean;
  selectedId: number | null;
  onSelect(artifactId: number): void;
}) {
  // Inventory order: by ring (Use → Watch), then name — the same priority the
  // radar reads radially, but flattened.
  const rows = useMemo(() => {
    const rank = (ring: string) => {
      const i = RING_ORDER.indexOf(ring as (typeof RING_ORDER)[number]);
      return i < 0 ? RING_ORDER.length : i;
    };
    return [...artifacts].sort(
      (a, b) => rank(a.ring) - rank(b.ring) || a.name.localeCompare(b.name),
    );
  }, [artifacts]);

  if (isLoading) {
    return <div className="skeleton-block" style={{ height: "16rem" }} aria-hidden="true" />;
  }

  if (rows.length === 0) {
    return (
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-micro)",
          color: "var(--color-muted)",
          lineHeight: 1.5,
        }}
      >
        No artifacts match. Run{" "}
        <code style={{ fontFamily: "var(--font-mono)" }}>radar fetch-ecosystem</code> to populate,
        or clear the focus filters.
      </div>
    );
  }

  return (
    <table style={{ width: "100%", borderCollapse: "collapse" }}>
      <thead>
        <tr>
          <th style={headStyle}>Artifact</th>
          <th style={headStyle}>Status</th>
          <th style={headStyle}>Capability</th>
          <th style={headStyle}>Ring</th>
          <th style={headStyle}>Refs</th>
          <th style={headStyle}>Latest release</th>
          <th style={{ ...headStyle, textAlign: "right" }}>Recent</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((artifact) => {
          const ringAccent = artifact.ring === "Use" || artifact.ring === "Prototype";
          const capability =
            CAPABILITY_LABEL[artifact.capability as CapabilityId] ?? artifact.capability;
          const selected = artifact.artifact_id === selectedId;
          return (
            <tr
              key={artifact.artifact_id}
              onClick={() => onSelect(artifact.artifact_id)}
              style={{
                cursor: "pointer",
                background: selected ? "var(--color-rule)" : "transparent",
              }}
            >
              <td style={cellStyle}>
                <span style={{ fontFamily: "var(--font-sans)", fontWeight: 500 }}>
                  {artifact.name}
                </span>
                <span style={{ color: "var(--color-muted)", marginLeft: "0.5rem" }}>
                  {artifact.key}
                </span>
              </td>
              <td style={{ ...cellStyle, color: "var(--color-muted)" }}>{artifact.status}</td>
              <td style={{ ...cellStyle, color: "var(--color-muted)" }}>{capability}</td>
              <td
                style={{
                  ...cellStyle,
                  color: ringAccent ? "var(--color-accent)" : "currentColor",
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                }}
              >
                {artifact.ring}
              </td>
              <td style={cellStyle}>
                <span style={{ display: "inline-flex", flexWrap: "wrap", gap: "0.25rem" }}>
                  {artifact.ecosystems.map((eco) => (
                    <EcosystemBadge key={eco} ecosystem={eco} />
                  ))}
                </span>
              </td>
              <td style={{ ...cellStyle, color: "var(--color-muted)" }}>
                {artifact.latest_event ? (
                  <>
                    <span style={{ color: "var(--color-accent)" }}>
                      {artifact.latest_event.version ?? artifact.latest_event.event_type}
                    </span>
                    <span style={{ marginLeft: "0.5rem" }}>
                      {formatDate(artifact.latest_event.event_date)}
                    </span>
                  </>
                ) : (
                  "—"
                )}
              </td>
              <td
                style={{
                  ...cellStyle,
                  textAlign: "right",
                  color: artifact.recent_event_count > 0 ? "currentColor" : "var(--color-muted)",
                }}
              >
                {artifact.recent_event_count}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
