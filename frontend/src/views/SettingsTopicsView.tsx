// Topics editor — tracks with their positive/negative keywords.
// Left rail: list of tracks (with rename and delete).
// Right pane: keyword lists for the selected track.

import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "../lib/api";
import type { TopicsConfig, TrackConfig } from "../lib/api";
import { Button } from "../ui/Button";
import { Chrome } from "../ui/Chrome";
import { ConfigSection } from "../ui/ConfigSection";
import { KeywordList } from "../ui/KeywordList";

function newTrack(): TrackConfig {
  return {
    id: "",
    name: "",
    positive_keywords: [],
    negative_keywords: [],
  };
}

function tracksEqual(a: TrackConfig[], b: TrackConfig[]): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function SettingsTopicsView() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["config", "topics"],
    queryFn: () => api.getTopicsConfig(),
  });

  const [tracks, setTracks] = useState<TrackConfig[]>([]);
  const [baseline, setBaseline] = useState<TrackConfig[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number>(0);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setTracks(data.tracks);
      setBaseline(data.tracks);
      setSelectedIdx(0);
    }
  }, [data]);

  const dirty = !tracksEqual(tracks, baseline);

  const selected = useMemo<TrackConfig | null>(() => {
    return tracks[selectedIdx] ?? null;
  }, [tracks, selectedIdx]);

  function updateSelected(patch: Partial<TrackConfig>) {
    setTracks((prev) =>
      prev.map((t, i) => (i === selectedIdx ? { ...t, ...patch } : t)),
    );
  }
  function addTrack() {
    setTracks((prev) => {
      const next = [...prev, newTrack()];
      setSelectedIdx(next.length - 1);
      return next;
    });
  }
  function deleteTrack(i: number) {
    setTracks((prev) => {
      const next = prev.filter((_, idx) => idx !== i);
      setSelectedIdx((cur) => Math.min(cur, next.length - 1));
      return next;
    });
  }
  function reset() {
    setTracks(baseline);
    setSelectedIdx(0);
    setSaveError(null);
  }

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      const payload: TopicsConfig = { tracks };
      const res = await api.putTopicsConfig(payload);
      setBaseline(tracks);
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
        title="Topics"
        description="Radar tracks. Each track has positive keywords that pull items in and negative keywords that push them out. Tracks need at least one positive keyword."
        configPath="config/topics.yaml"
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
            Could not load topics:{" "}
            {error instanceof Error ? error.message : "unknown error"}.
          </div>
        )}
        {!isLoading && !isError && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "16rem 1fr",
              gap: "1.5rem",
              alignItems: "start",
            }}
          >
            {/* Left rail */}
            <nav
              aria-label="Tracks"
              style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}
            >
              {tracks.length === 0 && (
                <div
                  style={{
                    fontFamily: "var(--font-display)",
                    fontStyle: "italic",
                    color: "var(--color-muted)",
                    fontSize: "var(--text-small)",
                  }}
                >
                  No tracks yet.
                </div>
              )}
              {tracks.map((t, i) => {
                const active = i === selectedIdx;
                return (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setSelectedIdx(i)}
                    aria-current={active ? "true" : undefined}
                    style={{
                      textAlign: "left",
                      background: "transparent",
                      border: "1px solid",
                      borderColor: active
                        ? "var(--color-ink)"
                        : "var(--color-rule)",
                      borderRadius: "var(--radius-sm)",
                      padding: "0.5rem 0.625rem",
                      cursor: "pointer",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.125rem",
                      color: "inherit",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--font-display)",
                        fontSize: "var(--text-body)",
                        lineHeight: 1.2,
                      }}
                    >
                      {t.name || t.id || "(unnamed)"}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "var(--text-micro)",
                        color: "var(--color-muted)",
                      }}
                    >
                      {t.id || "—"} · {t.positive_keywords.length} pos ·{" "}
                      {t.negative_keywords.length} neg
                    </span>
                  </button>
                );
              })}
              <Button variant="ghost" size="sm" onClick={addTrack}>
                + Add track
              </Button>
            </nav>

            {/* Right pane */}
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              {selected && (
                <>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))",
                      gap: "0.75rem",
                    }}
                  >
                    <label style={fieldStyle}>
                      <span style={labelStyle}>id</span>
                      <input
                        type="text"
                        value={selected.id}
                        onChange={(e) => updateSelected({ id: e.target.value })}
                        style={inputStyle}
                      />
                    </label>
                    <label style={fieldStyle}>
                      <span style={labelStyle}>name</span>
                      <input
                        type="text"
                        value={selected.name}
                        onChange={(e) => updateSelected({ name: e.target.value })}
                        style={inputStyle}
                      />
                    </label>
                  </div>
                  <KeywordList
                    label="positive keywords"
                    optional={false}
                    value={selected.positive_keywords}
                    onChange={(next) => updateSelected({ positive_keywords: next })}
                  />
                  <KeywordList
                    label="negative keywords"
                    value={selected.negative_keywords}
                    onChange={(next) => updateSelected({ negative_keywords: next })}
                  />
                  <div style={{ display: "flex", justifyContent: "flex-end" }}>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => deleteTrack(selectedIdx)}
                    >
                      Delete track
                    </Button>
                  </div>
                </>
              )}
              {!selected && (
                <div
                  style={{
                    fontFamily: "var(--font-display)",
                    fontStyle: "italic",
                    color: "var(--color-muted)",
                  }}
                >
                  Select a track on the left or add a new one.
                </div>
              )}
            </div>
          </div>
        )}
      </ConfigSection>
    </div>
  );
}

const fieldStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "0.25rem",
};

const labelStyle: React.CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: "var(--text-micro)",
  color: "var(--color-muted)",
  letterSpacing: "var(--tracking-caps)",
  textTransform: "uppercase",
};

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
