// Digest view — render the pre-built digest Markdown for a date.
// A small "Run digest" button kicks off the digest job in the background.

import { useEffect, useId, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../lib/api";
import { useJobPoller, isTerminalState } from "../lib/jobs";
import { Button } from "../ui/Button";
import { Chrome } from "../ui/Chrome";
import { StatusBadge } from "../ui/StatusBadge";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const HASH_DATE_RE = /^#\/digest\/(\d{4}-\d{2}-\d{2})/;

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

function readHashDate(): string {
  const match = HASH_DATE_RE.exec(window.location.hash);
  return match ? match[1]! : "today";
}

export function DigestView() {
  const dateId = useId();
  const queryClient = useQueryClient();
  const [date, setDate] = useState<string>(readHashDate);
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Listen for hash changes so a deep link updates the date.
  useEffect(() => {
    const handler = () => setDate(readHashDate());
    window.addEventListener("hashchange", handler);
    return () => window.removeEventListener("hashchange", handler);
  }, []);

  const validDate = date === "today" || DATE_RE.test(date);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["digest", "markdown", date],
    queryFn: () => api.getDigestMarkdown(date),
    enabled: validDate,
  });

  const poll = useJobPoller(jobId);

  useEffect(() => {
    if (poll.data && isTerminalState(poll.data.state)) {
      // Refresh once the job finishes — the digest file should now exist.
      refetch();
      queryClient.invalidateQueries({ queryKey: ["jobs", "recent"] });
    }
  }, [poll.data, refetch, queryClient]);

  async function runDigest() {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const res = await api.postDigestJob({ date });
      setJobId(res.job_id);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "submit failed");
    } finally {
      setSubmitting(false);
    }
  }

  const state = poll.data?.state ?? (jobId ? "queued" : "idle");

  return (
    <div
      style={{
        minHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        maxWidth: "60rem",
        margin: "0 auto",
      }}
    >
      <Chrome />
      <main style={{ padding: "1.5rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <header
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            gap: "1rem",
            flexWrap: "wrap",
          }}
        >
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "var(--text-display-l)",
              fontWeight: 400,
              margin: 0,
              letterSpacing: "var(--tracking-tight)",
            }}
          >
            Digest
          </h2>
          <div style={{ display: "flex", gap: "1rem", alignItems: "baseline" }}>
            <label
              htmlFor={dateId}
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: "0.5rem",
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-muted)",
                letterSpacing: "var(--tracking-caps)",
                textTransform: "uppercase",
              }}
            >
              date
              <input
                id={dateId}
                type="date"
                value={date === "today" ? isoToday() : date}
                onChange={(e) => setDate(e.target.value || "today")}
                className="queue-input queue-input--date"
              />
            </label>
            <StatusBadge state={state} />
            <Button
              variant="ghost"
              size="sm"
              onClick={runDigest}
              disabled={submitting || state === "running" || state === "queued"}
            >
              {submitting ? "Submitting…" : "Run digest"}
            </Button>
          </div>
        </header>

        {submitError && (
          <div
            role="alert"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-small)",
              color: "var(--color-accent)",
            }}
          >
            {submitError}
          </div>
        )}

        {isLoading && (
          <div className="skeleton-block" style={{ height: "12rem" }} aria-hidden="true" />
        )}
        {isError && (
          <div
            role="alert"
            style={{
              fontFamily: "var(--font-display)",
              fontStyle: "italic",
              color: "var(--color-muted)",
            }}
          >
            Could not load digest:{" "}
            {error instanceof Error ? error.message : "unknown error"}.
          </div>
        )}
        {!isLoading && !isError && data && !data.exists && (
          <div
            style={{
              padding: "2rem 0",
              fontFamily: "var(--font-display)",
              fontStyle: "italic",
              fontSize: "var(--text-display-l)",
              color: "var(--color-muted)",
              lineHeight: 1.4,
            }}
          >
            No digest for{" "}
            <code
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.875em",
                fontStyle: "normal",
              }}
            >
              {data.date}
            </code>
            . Click <strong>Run digest</strong> above, or visit the{" "}
            <a
              href="#/pipeline"
              style={{
                color: "var(--color-accent)",
                textDecoration: "underline",
                textUnderlineOffset: "2px",
              }}
            >
              pipeline
            </a>{" "}
            to run the full daily iteration first.
          </div>
        )}
        {!isLoading && !isError && data && data.exists && (
          <article
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "var(--text-body)",
              lineHeight: 1.6,
            }}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.markdown}</ReactMarkdown>
          </article>
        )}
      </main>
    </div>
  );
}
