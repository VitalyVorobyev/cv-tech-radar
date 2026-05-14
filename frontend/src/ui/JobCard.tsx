// One stage card for the pipeline view.
// Owns the current job_id, polls it via useJobPoller, renders the form,
// status badge, last-run time, and expandable log tail.

import { useState, type ReactNode } from "react";
import type { JobState, JobSubmitResponse } from "../lib/api";
import { useJobPoller } from "../lib/jobs";
import { Button } from "./Button";
import { StatusBadge } from "./StatusBadge";

interface JobCardProps {
  stage: string;
  description?: string;
  /** Stage-specific input controls; usually a vertical stack of TextFields. */
  inputs?: ReactNode;
  /** Submit callback. Returns the new job_id, which the card polls. */
  submit: () => Promise<JobSubmitResponse>;
  /** Disable the Run button (e.g. when required inputs are empty). */
  disabled?: boolean;
  submitLabel?: string;
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleTimeString();
}

export function JobCard({
  stage,
  description,
  inputs,
  submit,
  disabled = false,
  submitLabel = "Run",
}: JobCardProps) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [logOpen, setLogOpen] = useState(false);

  const poll = useJobPoller(jobId);

  const state: JobState | "idle" = poll.data?.state ?? (jobId ? "queued" : "idle");
  const log = poll.data?.log ?? [];
  const lastRun = poll.data?.finished_at ?? poll.data?.started_at ?? null;
  const errMsg = poll.data?.error ?? null;

  async function onRun() {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const res = await submit();
      setJobId(res.job_id);
      setLogOpen(true);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "submit failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <article
      style={{
        border: "1px solid var(--color-rule)",
        borderRadius: "var(--radius-sm)",
        padding: "0.875rem 1rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.625rem",
        background: "transparent",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "0.75rem",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "0.125rem" }}>
          <h3
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "1.05rem",
              fontWeight: 400,
              margin: 0,
              letterSpacing: "var(--tracking-tight)",
              textTransform: "capitalize",
            }}
          >
            {stage}
          </h3>
          {description && (
            <p
              style={{
                margin: 0,
                fontFamily: "var(--font-sans)",
                fontSize: "var(--text-small)",
                color: "var(--color-muted)",
                lineHeight: 1.4,
              }}
            >
              {description}
            </p>
          )}
        </div>
        <StatusBadge state={state} />
      </header>

      {inputs && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {inputs}
        </div>
      )}

      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "0.75rem",
        }}
      >
        <Button
          variant="primary"
          size="sm"
          onClick={onRun}
          disabled={disabled || submitting || state === "running" || state === "queued"}
        >
          {submitting ? "Submitting…" : submitLabel}
        </Button>
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
          }}
        >
          last: {formatTime(lastRun)}
        </span>
      </div>

      {submitError && (
        <div
          role="alert"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-accent)",
          }}
        >
          {submitError}
        </div>
      )}

      {errMsg && state === "error" && (
        <div
          role="alert"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-accent)",
            wordBreak: "break-word",
          }}
        >
          {errMsg}
        </div>
      )}

      {(log.length > 0 || jobId) && (
        <details
          open={logOpen}
          onToggle={(e) => setLogOpen((e.target as HTMLDetailsElement).open)}
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
          }}
        >
          <summary
            style={{
              cursor: "pointer",
              color: "var(--color-muted)",
              letterSpacing: "var(--tracking-caps)",
              textTransform: "uppercase",
              outline: "none",
            }}
          >
            log ({log.length})
          </summary>
          <pre
            style={{
              marginTop: "0.5rem",
              maxHeight: "10rem",
              overflow: "auto",
              border: "1px solid var(--color-rule)",
              borderRadius: "var(--radius-sm)",
              padding: "0.5rem",
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
              color: "var(--color-ink)",
              background: "transparent",
            }}
          >
            {log.length === 0 ? "(no output yet)" : log.join("\n")}
          </pre>
        </details>
      )}
    </article>
  );
}
