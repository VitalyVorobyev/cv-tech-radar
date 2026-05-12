// Compact candidate row with inline expand.
// Collapsed: ID · ring · title · tracks · score · source · date.
// Expanded: CandidatePanel inline beneath, row-panel animation.

import { useRef } from "react";
import type { Candidate } from "../lib/api";
import { RingLabel } from "./RingLabel";
import { CandidatePanel } from "./CandidatePanel";
import { formatDate, formatScore, formatId, formatTracks } from "../lib/format";

interface CandidateRowProps {
  candidate: Candidate;
  expanded: boolean;
  focused: boolean;
  onToggle: () => void;
}

export function CandidateRow({
  candidate,
  expanded,
  focused,
  onToggle,
}: CandidateRowProps) {
  const rowRef = useRef<HTMLDivElement>(null);

  // Active ring: current decision wins over suggestion
  const activeRing = candidate.current_decision?.ring ?? candidate.ring_suggested;
  const hasDecision = candidate.current_decision !== null;

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onToggle();
    }
  }

  // mod+s inside panel: click the Save button
  function handlePanelSave() {
    const saveBtn = rowRef.current?.querySelector<HTMLButtonElement>("[data-save='true']");
    saveBtn?.click();
  }

  return (
    <div
      ref={rowRef}
      style={{
        borderBottom: "1px solid var(--color-rule)",
        outline: focused ? "none" : undefined,
      }}
    >
      {/* Collapsed row — the clickable / keyboard-focusable surface */}
      <div
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={`${candidate.title}, ring ${activeRing}`}
        onClick={onToggle}
        onKeyDown={handleKeyDown}
        style={{
          display: "grid",
          gridTemplateColumns: "4rem 7rem 1fr 8rem 3rem 10rem",
          alignItems: "center",
          gap: "0 1rem",
          padding: "0.625rem 1.5rem",
          cursor: "pointer",
          outline: focused
            ? "1.5px solid var(--color-accent)"
            : "none",
          outlineOffset: "-2px",
          background: expanded ? "var(--color-rule)" : "transparent",
          transition: `background var(--duration-expand) var(--easing-expand)`,
        }}
      >
        {/* ID */}
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {formatId(candidate.id)}
        </span>

        {/* Ring — decision overrides suggestion */}
        <span style={{ display: "flex", alignItems: "center", gap: "0.375rem" }}>
          <RingLabel ring={activeRing} />
          {hasDecision && (
            <span
              aria-label="Decision saved"
              title="Decision saved"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-accent)",
              }}
            >
              ·
            </span>
          )}
        </span>

        {/* Title */}
        <span
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "1rem",
            lineHeight: "1.5",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            letterSpacing: "var(--tracking-tight)",
          }}
        >
          {candidate.title}
        </span>

        {/* Tracks */}
        <span
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {formatTracks(candidate.tracks)}
        </span>

        {/* Score */}
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            textAlign: "right",
          }}
        >
          {formatScore(candidate.scores.final)}
        </span>

        {/* Source · date */}
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            textAlign: "right",
          }}
        >
          {candidate.source} · {formatDate(candidate.published_at)}
        </span>
      </div>

      {/* Expanded panel — animated open/close */}
      <div
        className="row-panel"
        data-open={expanded ? "true" : "false"}
        aria-hidden={!expanded}
        id={`panel-${candidate.id}`}
      >
        {expanded && (
          <CandidatePanel
            candidate={candidate}
            onSave={() => handlePanelSave()}
          />
        )}
      </div>
    </div>
  );
}
