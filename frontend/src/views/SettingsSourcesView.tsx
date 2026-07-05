// Sources editor. Table of arXiv / RSS feeds with inline editing.
// Save writes config/sources.yaml; the backend reloads its in-memory cache.

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../lib/api";
import type { SourceConfig, SourcesConfig } from "../lib/api";
import { Button } from "../ui/Button";
import { Checkbox } from "../ui/Checkbox";
import { Chrome } from "../ui/Chrome";
import { ConfigSection } from "../ui/ConfigSection";
import { KeywordList } from "../ui/KeywordList";

function newSource(): SourceConfig {
  return {
    id: "",
    name: "",
    kind: "arxiv",
    url: "https://example.com",
    enabled: true,
    priority: 0,
    notes: "",
    categories: [],
  };
}

function rowsEqual(a: SourceConfig[], b: SourceConfig[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function SettingsSourcesView() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["config", "sources"],
    queryFn: () => api.getSourcesConfig(),
  });

  const [rows, setRows] = useState<SourceConfig[]>([]);
  const [baseline, setBaseline] = useState<SourceConfig[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  const [seeded, setSeeded] = useState(data?.sources);

  // Seed rows + baseline when the config first arrives or is refetched.
  // Adjusting state during render (guarded by identity) avoids a setState-in-effect.
  if (data && data.sources !== seeded) {
    setSeeded(data.sources);
    setRows(data.sources);
    setBaseline(data.sources);
  }

  const dirty = !rowsEqual(rows, baseline);

  function update(i: number, patch: Partial<SourceConfig>) {
    setRows((prev) => prev.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }
  function remove(i: number) {
    setRows((prev) => prev.filter((_, idx) => idx !== i));
  }
  function add() {
    setRows((prev) => [...prev, newSource()]);
  }
  function reset() {
    setRows(baseline);
    setSaveError(null);
  }

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      const payload: SourcesConfig = { sources: rows };
      const res = await api.putSourcesConfig(payload);
      setBaseline(rows);
      setSavedAt(res.saved_at);
      // Refresh so any server-side normalization (e.g. trimming) shows up.
      refetch();
    } catch (err) {
      if (err instanceof ApiError) {
        setSaveError(err.message);
      } else if (err instanceof Error) {
        setSaveError(err.message);
      } else {
        setSaveError("save failed");
      }
    } finally {
      setSaving(false);
    }
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
      <ConfigSection
        title="Sources"
        description="Feeds the radar polls. arXiv sources need at least one category; RSS sources need a URL."
        configPath="config/sources.yaml"
        dirty={dirty}
        saving={saving}
        saveError={saveError}
        savedAt={savedAt}
        onSave={save}
        onReset={reset}
      >
        {isLoading && (
          <div className="skeleton-block" style={{ height: "8rem" }} aria-hidden="true" />
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
            Could not load sources:{" "}
            {error instanceof Error ? error.message : "unknown error"}.
          </div>
        )}
        {!isLoading && !isError && (
          <>
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "0.75rem",
              }}
            >
              {rows.map((row, i) => (
                <article
                  key={i}
                  style={{
                    border: "1px solid var(--color-rule)",
                    borderRadius: "var(--radius-sm)",
                    padding: "0.875rem 1rem",
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))",
                    gap: "0.75rem",
                    alignItems: "start",
                  }}
                >
                  <Field label="id">
                    <input
                      type="text"
                      value={row.id}
                      onChange={(e) => update(i, { id: e.target.value })}
                      style={inputStyle}
                    />
                  </Field>
                  <Field label="name">
                    <input
                      type="text"
                      value={row.name}
                      onChange={(e) => update(i, { name: e.target.value })}
                      style={inputStyle}
                    />
                  </Field>
                  <Field label="kind">
                    <select
                      value={row.kind}
                      onChange={(e) =>
                        update(i, {
                          kind: e.target.value as SourceConfig["kind"],
                        })
                      }
                      style={inputStyle}
                    >
                      <option value="arxiv">arxiv</option>
                      <option value="rss">rss</option>
                    </select>
                  </Field>
                  <Field label="priority">
                    <input
                      type="number"
                      min={0}
                      max={5}
                      value={row.priority}
                      onChange={(e) => {
                        const n = Number(e.target.value);
                        if (Number.isFinite(n)) update(i, { priority: n });
                      }}
                      style={inputStyle}
                    />
                  </Field>
                  <Field label="url" wide>
                    <input
                      type="url"
                      value={row.url}
                      onChange={(e) => update(i, { url: e.target.value })}
                      style={inputStyle}
                    />
                  </Field>
                  <Field label="notes" wide>
                    <input
                      type="text"
                      value={row.notes}
                      onChange={(e) => update(i, { notes: e.target.value })}
                      style={inputStyle}
                    />
                  </Field>
                  {row.kind === "arxiv" && (
                    <Field label="categories" wide>
                      <KeywordList
                        value={row.categories}
                        onChange={(next) => update(i, { categories: next })}
                        placeholder="cs.CV"
                      />
                    </Field>
                  )}
                  <div
                    style={{
                      gridColumn: "1 / -1",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "1rem",
                      borderTop: "1px solid var(--color-rule)",
                      paddingTop: "0.5rem",
                    }}
                  >
                    <Checkbox
                      label="enabled"
                      checked={row.enabled}
                      onChange={(checked) => update(i, { enabled: checked })}
                    />
                    <Button variant="ghost" size="sm" onClick={() => remove(i)}>
                      Remove
                    </Button>
                  </div>
                </article>
              ))}
            </div>
            <div style={{ marginTop: "1rem" }}>
              <Button variant="ghost" size="sm" onClick={add}>
                + Add source
              </Button>
            </div>
          </>
        )}
      </ConfigSection>
    </div>
  );
}

function Field({
  label,
  wide = false,
  children,
}: {
  label: string;
  wide?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.25rem",
        gridColumn: wide ? "1 / -1" : undefined,
      }}
    >
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-micro)",
          color: "var(--color-muted)",
          letterSpacing: "var(--tracking-caps)",
          textTransform: "uppercase",
        }}
      >
        {label}
      </span>
      {children}
    </label>
  );
}

const inputStyle: React.CSSProperties = {
  fontFamily: "var(--font-sans)",
  fontSize: "var(--text-small)",
  background: "transparent",
  color: "inherit",
  border: "none",
  borderBottom: "1px solid var(--color-rule)",
  outline: "none",
  padding: "0.25rem 0",
  width: "100%",
};
