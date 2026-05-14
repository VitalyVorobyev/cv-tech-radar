// Small typographic pill showing the local LLM's relevance verdict on an item.
// Shadow mode only — does not influence scoring; lets the curator *see* the
// judgment so it can be calibrated.

import type { LLMJudgment } from "../lib/api";

interface LLMBadgeProps {
  judgment: LLMJudgment | null | undefined;
}

export function LLMBadge({ judgment }: LLMBadgeProps) {
  if (!judgment) return null;

  const label = judgment.verdict === "yes" ? "llm: yes" : judgment.verdict === "no" ? "llm: no" : "llm: ?";
  const muted = judgment.verdict !== "yes";
  const tooltip = `Model ${judgment.model}: ${judgment.reason || "no rationale"}`;

  return (
    <span
      title={tooltip}
      aria-label={`Local LLM verdict: ${judgment.verdict}`}
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-micro)",
        letterSpacing: "var(--tracking-caps)",
        color: muted ? "var(--color-muted)" : "var(--color-accent)",
        fontStyle: judgment.verdict === "unknown" ? "italic" : "normal",
        textTransform: "lowercase",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </span>
  );
}
