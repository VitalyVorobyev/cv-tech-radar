// Pipeline view. Each stage is a JobCard with stage-specific inputs.
// At the top, a single "Run today's iteration" button drives the
// daily-iteration job. At the bottom, a recent-jobs list polls /api/jobs.

import { useEffect, useId, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { Job, JobState } from "../lib/api";
import { useJobPoller, isTerminalState } from "../lib/jobs";
import { Chrome } from "../ui/Chrome";
import { Button } from "../ui/Button";
import { JobCard } from "../ui/JobCard";
import { StatusBadge } from "../ui/StatusBadge";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

interface DateInputProps {
  label: string;
  value: string;
  onChange: (next: string) => void;
}

function StageDateInput({ label, value, onChange }: DateInputProps) {
  const id = useId();
  return (
    <label
      htmlFor={id}
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
      {label}
      <input
        id={id}
        type="date"
        value={value === "today" ? isoToday() : value}
        onChange={(e) => onChange(e.target.value || "today")}
        className="queue-input queue-input--date"
      />
    </label>
  );
}

interface NumInputProps {
  label: string;
  value: number;
  onChange: (next: number) => void;
  min?: number;
  max?: number;
}

function NumberInput({ label, value, onChange, min, max }: NumInputProps) {
  const id = useId();
  return (
    <label
      htmlFor={id}
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
      {label}
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => {
          const next = Number(e.target.value);
          if (Number.isFinite(next)) onChange(next);
        }}
        style={{
          width: "5rem",
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-small)",
          background: "transparent",
          color: "inherit",
          border: "none",
          borderBottom: "1px solid var(--color-rule)",
          outline: "none",
          padding: "0.125rem 0",
        }}
      />
    </label>
  );
}

interface TextInputProps {
  label: string;
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
}

function PathInput({ label, value, onChange, placeholder }: TextInputProps) {
  const id = useId();
  return (
    <label
      htmlFor={id}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.25rem",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-micro)",
        color: "var(--color-muted)",
        letterSpacing: "var(--tracking-caps)",
        textTransform: "uppercase",
      }}
    >
      {label}
      <input
        id={id}
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-small)",
          background: "transparent",
          color: "inherit",
          border: "none",
          borderBottom: "1px solid var(--color-rule)",
          outline: "none",
          padding: "0.125rem 0",
          textTransform: "none",
          letterSpacing: 0,
        }}
      />
    </label>
  );
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleTimeString();
}

function RecentJobsList() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["jobs", "recent"],
    queryFn: () => api.listJobs(20),
    refetchInterval: 1500,
  });

  if (isLoading) {
    return (
      <div className="skeleton-block" style={{ height: "6rem" }} aria-hidden="true" />
    );
  }
  if (isError) {
    return (
      <div
        role="alert"
        style={{
          fontFamily: "var(--font-display)",
          fontStyle: "italic",
          color: "var(--color-muted)",
        }}
      >
        Could not load recent jobs:{" "}
        {error instanceof Error ? error.message : "unknown error"}.
      </div>
    );
  }

  const jobs = data?.jobs ?? [];
  if (jobs.length === 0) {
    return (
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontStyle: "italic",
          color: "var(--color-muted)",
        }}
      >
        No jobs yet. Run a stage above to populate this list.
      </div>
    );
  }

  return (
    <table
      style={{
        width: "100%",
        borderCollapse: "collapse",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--text-small)",
      }}
    >
      <thead>
        <tr style={{ borderBottom: "1px solid var(--color-rule)" }}>
          {["stage", "state", "submitted", "finished", "id"].map((h) => (
            <th
              key={h}
              scope="col"
              style={{
                textAlign: "left",
                padding: "0.5rem 0.5rem",
                fontSize: "var(--text-micro)",
                fontWeight: 400,
                letterSpacing: "var(--tracking-caps)",
                textTransform: "uppercase",
                color: "var(--color-muted)",
              }}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {jobs.map((job: Job) => (
          <tr key={job.id} style={{ borderBottom: "1px solid var(--color-rule)" }}>
            <td style={{ padding: "0.375rem 0.5rem" }}>{job.stage}</td>
            <td style={{ padding: "0.375rem 0.5rem" }}>
              <StatusBadge state={job.state} />
            </td>
            <td style={{ padding: "0.375rem 0.5rem", color: "var(--color-muted)" }}>
              {formatTime(job.submitted_at)}
            </td>
            <td style={{ padding: "0.375rem 0.5rem", color: "var(--color-muted)" }}>
              {formatTime(job.finished_at)}
            </td>
            <td
              style={{
                padding: "0.375rem 0.5rem",
                color: "var(--color-muted)",
                fontSize: "var(--text-micro)",
              }}
            >
              {job.id.slice(0, 8)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DailyIterationStrip() {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [date, setDate] = useState<string>("today");
  const [days, setDays] = useState<number>(1);
  const [maxResults, setMaxResults] = useState<number>(100);

  const poll = useJobPoller(jobId);

  // When the daily-iteration finishes, refresh the recent-jobs list once.
  useEffect(() => {
    if (poll.data && isTerminalState(poll.data.state)) {
      queryClient.invalidateQueries({ queryKey: ["jobs", "recent"] });
    }
  }, [poll.data, queryClient]);

  async function run() {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const res = await api.postDailyIterationJob({
        date,
        fetch: { days, max_results: maxResults },
      });
      setJobId(res.job_id);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "submit failed");
    } finally {
      setSubmitting(false);
    }
  }

  const state: JobState | "idle" = poll.data?.state ?? (jobId ? "queued" : "idle");
  const log = poll.data?.log ?? [];

  return (
    <section
      style={{
        border: "1px solid var(--color-rule)",
        borderRadius: "var(--radius-sm)",
        padding: "1rem 1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
        background: "transparent",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "0.75rem",
          flexWrap: "wrap",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "0.125rem" }}>
          <h3
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "1.25rem",
              fontWeight: 400,
              margin: 0,
              letterSpacing: "var(--tracking-tight)",
            }}
          >
            Run today&rsquo;s iteration
          </h3>
          <p
            style={{
              margin: 0,
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-small)",
              color: "var(--color-muted)",
            }}
          >
            Fetch arXiv, classify, and rebuild the candidate queue in a single job.
          </p>
        </div>
        <StatusBadge state={state} />
      </header>
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "1rem",
          alignItems: "baseline",
        }}
      >
        <StageDateInput label="date" value={date} onChange={setDate} />
        <NumberInput label="days" value={days} onChange={setDays} min={1} />
        <NumberInput
          label="max"
          value={maxResults}
          onChange={setMaxResults}
          min={1}
        />
        <Button
          variant="primary"
          size="sm"
          onClick={run}
          disabled={submitting || state === "running" || state === "queued"}
        >
          {submitting ? "Submitting…" : "Run daily iteration"}
        </Button>
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
      {poll.data?.error && state === "error" && (
        <div
          role="alert"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-accent)",
            wordBreak: "break-word",
          }}
        >
          {poll.data.error}
        </div>
      )}
      {log.length > 0 && (
        <pre
          style={{
            margin: 0,
            maxHeight: "10rem",
            overflow: "auto",
            border: "1px solid var(--color-rule)",
            borderRadius: "var(--radius-sm)",
            padding: "0.5rem",
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
          }}
        >
          {log.join("\n")}
        </pre>
      )}
    </section>
  );
}

export function PipelineView() {
  const [fetchDays, setFetchDays] = useState<number>(1);
  const [fetchMaxResults, setFetchMaxResults] = useState<number>(100);
  const [classifyDate, setClassifyDate] = useState<string>("today");
  const [candidatesDate, setCandidatesDate] = useState<string>("today");
  const [applyPath, setApplyPath] = useState<string>("");
  const [digestDate, setDigestDate] = useState<string>("today");
  const [digestDays, setDigestDays] = useState<number>(1);
  const [embedDate, setEmbedDate] = useState<string>("today");
  const [relevanceDate, setRelevanceDate] = useState<string>("today");

  function validDate(d: string): boolean {
    return d === "today" || DATE_RE.test(d);
  }

  return (
    <div
      style={{
        minHeight: "100dvh",
        display: "flex",
        flexDirection: "column",
        maxWidth: "80rem",
        margin: "0 auto",
      }}
    >
      <Chrome />
      <main
        style={{
          padding: "1.5rem",
          display: "flex",
          flexDirection: "column",
          gap: "1.5rem",
        }}
      >
        <DailyIterationStrip />

        <section>
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "var(--text-display-l)",
              fontWeight: 400,
              margin: "0 0 0.75rem",
              letterSpacing: "var(--tracking-tight)",
            }}
          >
            Individual stages
          </h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(20rem, 1fr))",
              gap: "1rem",
            }}
          >
            <JobCard
              stage="fetch"
              description="Pull new arXiv items into the local DB."
              inputs={
                <>
                  <NumberInput
                    label="days"
                    value={fetchDays}
                    onChange={setFetchDays}
                    min={1}
                  />
                  <NumberInput
                    label="max-results"
                    value={fetchMaxResults}
                    onChange={setFetchMaxResults}
                    min={1}
                  />
                </>
              }
              submit={() =>
                api.postFetchJob({
                  days: fetchDays,
                  max_results: fetchMaxResults,
                })
              }
            />

            <JobCard
              stage="classify"
              description="Run keyword matching on items for a date."
              inputs={
                <StageDateInput
                  label="date"
                  value={classifyDate}
                  onChange={setClassifyDate}
                />
              }
              disabled={!validDate(classifyDate)}
              submit={() => api.postClassifyJob({ date: classifyDate })}
            />

            <JobCard
              stage="candidates"
              description="Write the candidate Markdown + JSON for a date."
              inputs={
                <StageDateInput
                  label="date"
                  value={candidatesDate}
                  onChange={setCandidatesDate}
                />
              }
              disabled={!validDate(candidatesDate)}
              submit={() => api.postCandidatesJob({ date: candidatesDate })}
            />

            <JobCard
              stage="apply"
              description="Apply curator decisions from a candidate Markdown file."
              inputs={
                <PathInput
                  label="markdown_path"
                  value={applyPath}
                  onChange={setApplyPath}
                  placeholder="reports/candidates/2026-05-13.md"
                />
              }
              disabled={applyPath.trim() === ""}
              submit={() =>
                api.postApplyJob({ markdown_path: applyPath.trim() })
              }
            />

            <JobCard
              stage="digest"
              description="Render the digest Markdown for a date."
              inputs={
                <>
                  <StageDateInput
                    label="date"
                    value={digestDate}
                    onChange={setDigestDate}
                  />
                  <NumberInput
                    label="days"
                    value={digestDays}
                    onChange={setDigestDays}
                    min={1}
                  />
                </>
              }
              disabled={!validDate(digestDate)}
              submit={() =>
                api.postDigestJob({ date: digestDate, days: digestDays })
              }
            />

            <JobCard
              stage="embed"
              description="Compute embeddings for classified items (Ollama)."
              inputs={
                <StageDateInput
                  label="date"
                  value={embedDate}
                  onChange={setEmbedDate}
                />
              }
              disabled={!validDate(embedDate)}
              submit={() => api.postEmbedJob({ date: embedDate })}
            />

            <JobCard
              stage="relevance-check"
              description="Ask the LLM to shadow-judge today's candidates."
              inputs={
                <StageDateInput
                  label="date"
                  value={relevanceDate}
                  onChange={setRelevanceDate}
                />
              }
              disabled={!validDate(relevanceDate)}
              submit={() =>
                api.postRelevanceCheckJob({ date: relevanceDate })
              }
            />
          </div>
        </section>

        <section>
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "var(--text-display-l)",
              fontWeight: 400,
              margin: "0 0 0.75rem",
              letterSpacing: "var(--tracking-tight)",
            }}
          >
            Recent jobs
          </h2>
          <RecentJobsList />
        </section>
      </main>
    </div>
  );
}
