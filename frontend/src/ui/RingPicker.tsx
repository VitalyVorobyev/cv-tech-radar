// Keyboard-driven segmented ring selector.
// Each option is rendered via RingLabel — typographic, not chromatic.
// Pressing 1–5 maps to Use/Prototype/Evaluate/Watch/Ignore.

import type { Ring } from "../lib/api";
import { RingLabel } from "./RingLabel";

const RINGS: Ring[] = ["Use", "Prototype", "Evaluate", "Watch", "Ignore"];

interface RingPickerProps {
  value: Ring;
  onChange: (ring: Ring) => void;
  disabled?: boolean;
}

export function RingPicker({ value, onChange, disabled = false }: RingPickerProps) {
  return (
    <div
      role="radiogroup"
      aria-label="Ring"
      style={{ display: "flex", gap: "1.5rem", flexWrap: "wrap" }}
    >
      {RINGS.map((ring, i) => {
        const checked = ring === value;
        return (
          <label
            key={ring}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.375rem",
              cursor: disabled ? "default" : "pointer",
              userSelect: "none",
            }}
          >
            <input
              type="radio"
              name="ring"
              value={ring}
              checked={checked}
              disabled={disabled}
              onChange={() => onChange(ring)}
              aria-label={ring}
              style={{ position: "absolute", opacity: 0, width: 0, height: 0 }}
            />
            {/* Keyboard hint */}
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "var(--text-micro)",
                color: "var(--color-muted)",
                minWidth: "0.875rem",
              }}
            >
              {i + 1}
            </span>
            <span
              style={{
                paddingBottom: "1px",
                borderBottom: checked
                  ? "1.5px solid currentColor"
                  : "1.5px solid transparent",
                transition: "border-color 0ms",
              }}
            >
              <RingLabel ring={ring} />
            </span>
          </label>
        );
      })}
    </div>
  );
}
