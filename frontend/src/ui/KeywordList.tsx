// Tag-style array editor. Enter or comma adds a token; "×" removes one.
// Insertion order is preserved. Empty / whitespace-only inputs are ignored.
// Used by the topics / negative-topics / sources editors.

import { useState, useId } from "react";

interface KeywordListProps {
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  label?: string;
  /** Treat the empty list as valid (no asterisk on the label). */
  optional?: boolean;
  disabled?: boolean;
}

export function KeywordList({
  value,
  onChange,
  placeholder = "Add keyword…",
  label,
  optional = true,
  disabled = false,
}: KeywordListProps) {
  const inputId = useId();
  const [draft, setDraft] = useState("");

  function commit(raw: string) {
    const tokens = raw
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (tokens.length === 0) return;
    const seen = new Set(value);
    const next = [...value];
    for (const t of tokens) {
      if (seen.has(t)) continue;
      seen.add(t);
      next.push(t);
    }
    if (next.length !== value.length) onChange(next);
    setDraft("");
  }

  function remove(index: number) {
    const next = value.filter((_, i) => i !== index);
    onChange(next);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      commit(draft);
    } else if (e.key === "Backspace" && draft === "" && value.length > 0) {
      // Quick-remove the last token when the input is empty.
      onChange(value.slice(0, -1));
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
      {label && (
        <label
          htmlFor={inputId}
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            letterSpacing: "var(--tracking-caps)",
            textTransform: "uppercase",
          }}
        >
          {label}
          {!optional && <span aria-hidden="true"> *</span>}
        </label>
      )}

      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.375rem",
          alignItems: "center",
          padding: "0.375rem 0",
          borderBottom: "1px solid var(--color-rule)",
        }}
      >
        {value.map((token, i) => (
          <span
            key={`${token}-${i}`}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.25rem",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-small)",
              color: "var(--color-ink)",
              border: "1px solid var(--color-rule)",
              borderRadius: "var(--radius-sm)",
              padding: "0.125rem 0.375rem",
              background: "transparent",
            }}
          >
            {token}
            <button
              type="button"
              onClick={() => remove(i)}
              disabled={disabled}
              aria-label={`Remove ${token}`}
              style={{
                background: "transparent",
                border: "none",
                cursor: disabled ? "default" : "pointer",
                padding: 0,
                color: "var(--color-muted)",
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-small)",
                lineHeight: 1,
              }}
            >
              ×
            </button>
          </span>
        ))}

        <input
          id={inputId}
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => draft && commit(draft)}
          placeholder={placeholder}
          disabled={disabled}
          style={{
            flex: "1 1 8rem",
            minWidth: "6rem",
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-small)",
            background: "transparent",
            color: "inherit",
            border: "none",
            outline: "none",
            padding: "0.125rem 0",
          }}
        />
      </div>
    </div>
  );
}
