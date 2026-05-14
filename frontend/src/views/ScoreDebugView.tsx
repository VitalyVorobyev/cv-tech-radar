// Score debug — per-item score breakdown for a date.
// Row click opens the existing ItemPanel slide-in.

import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Chrome } from "../ui/Chrome";
import { ItemPanel } from "../ui/ItemPanel";
import { ScoreBreakdownTable } from "../ui/ScoreBreakdownTable";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function isoToday(): string {
  return new Date().toISOString().slice(0, 10);
}

export function ScoreDebugView() {
  const dateId = useId();
  const limitId = useId();
  const [date, setDate] = useState<string>("today");
  const [limit, setLimit] = useState<number>(50);
  const [includeZero, setIncludeZero] = useState<boolean>(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const validDate = date === "today" || DATE_RE.test(date);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["score-debug", date, limit, includeZero],
    queryFn: () => api.getScoreDebug(date, limit, includeZero),
    enabled: validDate,
  });

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
            Score debug
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
            <label
              htmlFor={limitId}
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
              limit
              <input
                id={limitId}
                type="number"
                min={1}
                max={500}
                value={limit}
                onChange={(e) => {
                  const n = Number(e.target.value);
                  if (Number.isFinite(n)) setLimit(n);
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
            <label
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: "0.5rem",
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-muted)",
                letterSpacing: "var(--tracking-caps)",
                textTransform: "uppercase",
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={includeZero}
                onChange={(e) => setIncludeZero(e.target.checked)}
              />
              include zero
            </label>
          </div>
        </header>

        {isLoading && (
          <div className="skeleton-block" style={{ height: "12rem" }} aria-hidden="true" />
        )}
        {isError && (
          <div
            role="alert"
            style={{
              padding: "1rem 0",
              fontFamily: "var(--font-display)",
              fontStyle: "italic",
              color: "var(--color-muted)",
            }}
          >
            Could not load score debug:{" "}
            {error instanceof Error ? error.message : "unknown error"}.
          </div>
        )}
        {!isLoading && !isError && data && (
          <ScoreBreakdownTable
            items={data.items}
            onSelect={(id) => setSelectedId(id)}
          />
        )}
      </main>
      {selectedId !== null && (
        <ItemPanel itemId={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  );
}
