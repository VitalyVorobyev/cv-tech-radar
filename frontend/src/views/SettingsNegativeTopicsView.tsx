// Negative topics editor — one flat array of penalty terms.

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../lib/api";
import type { NegativeTopicsConfig } from "../lib/api";
import { Chrome } from "../ui/Chrome";
import { ConfigSection } from "../ui/ConfigSection";
import { KeywordList } from "../ui/KeywordList";

function listsEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] !== b[i]) return false;
  }
  return true;
}

export function SettingsNegativeTopicsView() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["config", "negative-topics"],
    queryFn: () => api.getNegativeTopicsConfig(),
  });

  const [terms, setTerms] = useState<string[]>([]);
  const [baseline, setBaseline] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setTerms(data.negative_topics);
      setBaseline(data.negative_topics);
    }
  }, [data]);

  const dirty = !listsEqual(terms, baseline);

  function reset() {
    setTerms(baseline);
    setSaveError(null);
  }

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      const payload: NegativeTopicsConfig = { negative_topics: terms };
      const res = await api.putNegativeTopicsConfig(payload);
      setBaseline(terms);
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
        title="Negative topics"
        description="Global penalty terms. Items mentioning any of these in their abstract are pushed down — useful for filtering out adjacent fields like autonomous driving or medical imaging."
        configPath="config/negative_topics.yaml"
        dirty={dirty}
        saving={saving}
        saveError={saveError}
        savedAt={savedAt}
        onSave={save}
        onReset={reset}
      >
        {isLoading && (
          <div className="skeleton-block" style={{ height: "4rem" }} aria-hidden="true" />
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
            Could not load negative topics:{" "}
            {error instanceof Error ? error.message : "unknown error"}.
          </div>
        )}
        {!isLoading && !isError && (
          <KeywordList
            value={terms}
            onChange={setTerms}
            placeholder="add a penalty term…"
          />
        )}
      </ConfigSection>
    </div>
  );
}
