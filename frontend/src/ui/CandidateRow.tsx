// Compact candidate row with inline expand.
// Collapsed: ID · ring · title · tracks · score · source · date.
// Expanded: CandidatePanel inline beneath, row-panel animation.

import { useRef } from "react";
import type { Candidate } from "../lib/api";
import { RingLabel } from "./RingLabel";
import { LLMBadge } from "./LLMBadge";
import { CandidatePanel } from "./CandidatePanel";
import { formatDate, formatScore, formatId, formatTracks } from "../lib/format";

interface CandidateRowProps {
  candidate: Candidate;
  expanded: boolean;
  focused: boolean;
  onToggle: () => void;
  /** Review inbox: a proposal was confirmed as-is from the expanded panel. */
  onConfirm?: () => void;
  /** Review inbox: a proposal was dismissed from the expanded panel. */
  onDismiss?: () => void;
}

export function CandidateRow({
  candidate,
  expanded,
  focused,
  onToggle,
  onConfirm,
  onDismiss,
}: CandidateRowProps) {
  const rowRef = useRef<HTMLDivElement>(null);

  // Active ring: a confirmed decision wins over a proposal, which wins over
  // the pipeline suggestion.
  const proposal = candidate.proposal ?? null;
  const activeRing =
    candidate.current_decision?.ring ?? proposal?.ring ?? candidate.ring_suggested;
  const hasDecision = candidate.current_decision !== null;
  // "Proposed, not on the radar" — an agent wrote this decision and no human
  // has confirmed it yet. Visually distinct from the saved-decision accent:
  // an outlined marker plus a muted inset rule down the left edge of the row.
  const isProposal = proposal !== null && !hasDecision;

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onToggle();
    }
  }

  return (
    <div
      ref={rowRef}
      style={{
        borderBottom: "1px solid var(--color-rule)",
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
          // Spec widths: 60/90/1fr/200/50/140. Column 5 widened to 80px to fit
          // the LLM badge alongside the score; everything else matches spec.
          gridTemplateColumns: "60px 90px 1fr 200px 80px 140px",
          alignItems: "center",
          gap: "0 1rem",
          padding: "0.65rem 1.5rem",
          cursor: "pointer",
          border: focused
            ? "1px solid var(--color-accent)"
            : "1px solid transparent",
          borderRadius: "var(--radius-sm)",
          background: "transparent",
          boxShadow: isProposal ? "inset 2px 0 0 var(--color-muted)" : "none",
          transition: `border-color var(--duration-focus) ease-out`,
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
          {isProposal && (
            <span
              aria-label="Proposed, not on the radar"
              title={`Proposed by ${proposal.decided_by} — not on the radar`}
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-muted)",
              }}
            >
              ◦
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

        {/* Score + LLM signal */}
        <span
          style={{
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "baseline",
            gap: "0.5rem",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
          }}
        >
          {candidate.llm_judgment && <LLMBadge judgment={candidate.llm_judgment} />}
          <span>{formatScore(candidate.scores.final)}</span>
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
            onConfirm={onConfirm}
            onDismiss={onDismiss}
          />
        )}
      </div>
    </div>
  );
}
