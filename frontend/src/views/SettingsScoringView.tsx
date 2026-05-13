// Scoring editor — weights, thresholds, and the candidate-queue cap.
// Numbers only for v1; sliders are a future enhancement.

import { useEffect, useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../lib/api";
import type { ScoringConfig } from "../lib/api";
import { Chrome } from "../ui/Chrome";
import { ConfigSection } from "../ui/ConfigSection";

type WeightKey = keyof ScoringConfig["weights"];
type ThresholdKey = keyof ScoringConfig["thresholds"];

const WEIGHT_KEYS: WeightKey[] = [
  "relevance",
  "source_priority",
  "implementation",
  "attention",
  "novelty",
  "negative_penalty",
];

const THRESHOLD_KEYS: ThresholdKey[] = [
  "use",
  "prototype",
  "evaluate",
  "watch",
  "ignore",
];

function configsEqual(a: ScoringConfig | null, b: ScoringConfig | null): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function SettingsScoringView() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["config", "scoring"],
    queryFn: () => api.getScoringConfig(),
  });

  const [draft, setDraft] = useState<ScoringConfig | null>(null);
  const [baseline, setBaseline] = useState<ScoringConfig | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setDraft(data);
      setBaseline(data);
    }
  }, [data]);

  const dirty = !configsEqual(draft, baseline);

  function updateWeight(key: WeightKey, value: number) {
    setDraft((prev) => {
      if (!prev) return prev;
      return { ...prev, weights: { ...prev.weights, [key]: value } };
    });
  }
  function updateThreshold(key: ThresholdKey, value: number) {
    setDraft((prev) => {
      if (!prev) return prev;
      return { ...prev, thresholds: { ...prev.thresholds, [key]: value } };
    });
  }
  function updateRoot<K extends keyof ScoringConfig>(key: K, value: ScoringConfig[K]) {
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));
  }
  function reset() {
    setDraft(baseline);
    setSaveError(null);
  }

  async function save() {
    if (!draft) return;
    setSaving(true);
    setSaveError(null);
    try {
      const res = await api.putScoringConfig(draft);
      setBaseline(draft);
      setSavedAt(res.saved_at);
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
        title="Scoring"
        description="Weights for each component, ring thresholds, and the candidate-queue cap. Thresholds must descend from Use to Ignore."
        configPath="config/scoring.yaml"
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
            Could not load scoring config:{" "}
            {error instanceof Error ? error.message : "unknown error"}.
          </div>
        )}
        {draft && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <fieldset style={fieldsetStyle}>
              <legend style={legendStyle}>Weights</legend>
              <div style={gridStyle}>
                {WEIGHT_KEYS.map((key) => (
                  <NumField
                    key={key}
                    label={key.replace("_", " ")}
                    value={draft.weights[key]}
                    onChange={(v) => updateWeight(key, v)}
                    step={0.05}
                    min={0}
                  />
                ))}
              </div>
            </fieldset>

            <fieldset style={fieldsetStyle}>
              <legend style={legendStyle}>Thresholds (final score → ring)</legend>
              <div style={gridStyle}>
                {THRESHOLD_KEYS.map((key) => (
                  <NumField
                    key={key}
                    label={key}
                    value={draft.thresholds[key]}
                    onChange={(v) => updateThreshold(key, v)}
                    step={1}
                    min={0}
                    max={100}
                  />
                ))}
              </div>
              <p
                style={{
                  margin: "0.5rem 0 0",
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-micro)",
                  color: "var(--color-muted)",
                }}
              >
                Must descend: use ≥ prototype ≥ evaluate ≥ watch ≥ ignore.
              </p>
            </fieldset>

            <fieldset style={fieldsetStyle}>
              <legend style={legendStyle}>Limits</legend>
              <div style={gridStyle}>
                <NumField
                  label="source priority cap"
                  value={draft.source_priority_cap}
                  onChange={(v) => updateRoot("source_priority_cap", v)}
                  step={1}
                  min={0}
                  max={100}
                />
                <NumField
                  label="candidate limit"
                  value={draft.candidate_limit}
                  onChange={(v) => updateRoot("candidate_limit", v)}
                  step={1}
                  min={1}
                  max={500}
                />
              </div>
            </fieldset>
          </div>
        )}
      </ConfigSection>
    </div>
  );
}

interface NumFieldProps {
  label: string;
  value: number;
  onChange: (next: number) => void;
  step?: number;
  min?: number;
  max?: number;
}

function NumField({ label, value, onChange, step, min, max }: NumFieldProps) {
  const id = useId();
  return (
    <label
      htmlFor={id}
      style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}
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
      <input
        id={id}
        type="number"
        value={value}
        step={step}
        min={min}
        max={max}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (Number.isFinite(n)) onChange(n);
        }}
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "var(--text-small)",
          background: "transparent",
          color: "inherit",
          border: "none",
          borderBottom: "1px solid var(--color-rule)",
          outline: "none",
          padding: "0.25rem 0",
          width: "100%",
        }}
      />
    </label>
  );
}

const fieldsetStyle: React.CSSProperties = {
  border: "1px solid var(--color-rule)",
  borderRadius: "var(--radius-sm)",
  padding: "0.875rem 1rem",
  display: "flex",
  flexDirection: "column",
  gap: "0.5rem",
};

const legendStyle: React.CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: "var(--text-micro)",
  color: "var(--color-muted)",
  letterSpacing: "var(--tracking-caps)",
  textTransform: "uppercase",
  padding: "0 0.25rem",
};

const gridStyle: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))",
  gap: "0.75rem",
};
