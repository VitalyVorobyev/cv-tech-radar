// Minimal text input — single line that grows to 3 rows on focus.
// Follows the hairline-rule aesthetic: no box-shadow, 1px border.

import { useRef, useState } from "react";

interface TextFieldProps {
  id?: string;
  label?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  multiline?: boolean;
  required?: boolean;
  disabled?: boolean;
  error?: string;
  "aria-describedby"?: string;
}

export function TextField({
  id,
  label,
  value,
  onChange,
  placeholder,
  multiline = false,
  required = false,
  disabled = false,
  error,
  "aria-describedby": ariaDescribedBy,
}: TextFieldProps) {
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const errorId = id ? `${id}-error` : undefined;
  const describedBy = [ariaDescribedBy, error ? errorId : undefined]
    .filter(Boolean)
    .join(" ") || undefined;

  const baseStyle: React.CSSProperties = {
    width: "100%",
    fontFamily: "var(--font-sans)",
    fontSize: "var(--text-small)",
    lineHeight: "1.5",
    background: "transparent",
    color: "inherit",
    border: "none",
    borderBottom: `1px solid ${error ? "var(--color-accent)" : "var(--color-rule)"}`,
    borderRadius: 0,
    padding: "0.25rem 0",
    resize: "none",
    outline: "none",
    transition: `border-color var(--duration-focus)`,
  };

  if (focused) {
    baseStyle.borderBottomColor = error ? "var(--color-accent)" : "var(--color-ink)";
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
      {label && (
        <label
          htmlFor={id}
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
            letterSpacing: "var(--tracking-caps)",
            textTransform: "uppercase",
          }}
        >
          {label}
          {required && <span aria-hidden="true"> *</span>}
        </label>
      )}

      {multiline ? (
        <textarea
          ref={textareaRef}
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          required={required}
          disabled={disabled}
          rows={focused ? 3 : 1}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          aria-invalid={error ? "true" : undefined}
          aria-describedby={describedBy}
          style={baseStyle}
        />
      ) : (
        <input
          id={id}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          required={required}
          disabled={disabled}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          aria-invalid={error ? "true" : undefined}
          aria-describedby={describedBy}
          style={baseStyle}
        />
      )}

      {error && (
        <span
          id={errorId}
          role="alert"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-accent)",
          }}
        >
          {error}
        </span>
      )}
    </div>
  );
}
