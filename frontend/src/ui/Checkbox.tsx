// Minimal checkbox — hairline border, no shadows.
// Used for the "Uncertain" toggle in the decision panel.

interface CheckboxProps {
  id?: string;
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}

export function Checkbox({ id, label, checked, onChange, disabled = false }: CheckboxProps) {
  return (
    <label
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.5rem",
        cursor: disabled ? "default" : "pointer",
        userSelect: "none",
        fontFamily: "var(--font-sans)",
        fontSize: "var(--text-small)",
      }}
    >
      <span
        style={{
          position: "relative",
          display: "inline-block",
          width: "14px",
          height: "14px",
          flexShrink: 0,
        }}
      >
        <input
          id={id}
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          disabled={disabled}
          style={{
            position: "absolute",
            inset: 0,
            opacity: 0,
            width: "100%",
            height: "100%",
            cursor: disabled ? "default" : "pointer",
            margin: 0,
          }}
        />
        {/* Custom box */}
        <span
          aria-hidden="true"
          style={{
            position: "absolute",
            inset: 0,
            border: "1px solid var(--color-muted)",
            borderRadius: "var(--radius-sm)",
            background: checked ? "var(--color-ink)" : "transparent",
            transition: `background var(--duration-focus)`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {checked && (
            <svg
              width="8"
              height="6"
              viewBox="0 0 8 6"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M1 3l2 2 4-4"
                stroke="var(--color-paper)"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </span>
      </span>
      {label}
    </label>
  );
}
