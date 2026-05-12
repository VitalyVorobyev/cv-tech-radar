// Shortcut reference overlay.
// Uses <dialog> with backdrop — no portal libraries.

import { useEffect, useRef } from "react";

interface ShortcutSheetProps {
  open: boolean;
  onClose: () => void;
}

const SHORTCUTS: { key: string; label: string }[] = [
  { key: "j", label: "Next candidate" },
  { key: "k", label: "Previous candidate" },
  { key: "Enter", label: "Expand / collapse row" },
  { key: "1–5", label: "Set ring (Use → Ignore)" },
  { key: "u", label: "Toggle Uncertain" },
  { key: "⌘S / Ctrl+S", label: "Save decision" },
  { key: "/", label: "Focus filter" },
  { key: "?", label: "Show this sheet" },
  { key: "Esc", label: "Close / collapse" },
];

export function ShortcutSheet({ open, onClose }: ShortcutSheetProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = dialogRef.current;
    if (!el) return;
    if (open && !el.open) {
      el.showModal();
    } else if (!open && el.open) {
      el.close();
    }
  }, [open]);

  // Close on backdrop click
  function handleClick(e: React.MouseEvent<HTMLDialogElement>) {
    if (e.target === dialogRef.current) onClose();
  }

  return (
    <dialog
      ref={dialogRef}
      onClick={handleClick}
      onClose={onClose}
      style={{
        background: "var(--color-paper)",
        color: "var(--color-ink)",
        border: "1px solid var(--color-rule)",
        borderRadius: "var(--radius-sm)",
        padding: "2rem",
        maxWidth: "28rem",
        width: "100%",
        boxShadow: "none",
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        <div
          style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}
        >
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "var(--text-display-l)",
              fontWeight: 400,
              margin: 0,
            }}
          >
            Keyboard shortcuts
          </h2>
          <button
            onClick={onClose}
            aria-label="Close shortcut sheet"
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-small)",
              color: "var(--color-muted)",
              padding: 0,
            }}
          >
            Esc
          </button>
        </div>

        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <tbody>
            {SHORTCUTS.map(({ key, label }) => (
              <tr
                key={key}
                style={{ borderTop: "1px solid var(--color-rule)" }}
              >
                <td
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "var(--text-small)",
                    padding: "0.5rem 0.75rem 0.5rem 0",
                    whiteSpace: "nowrap",
                    width: "8rem",
                  }}
                >
                  {key}
                </td>
                <td
                  style={{
                    fontFamily: "var(--font-sans)",
                    fontSize: "var(--text-small)",
                    padding: "0.5rem 0",
                    color: "var(--color-muted)",
                  }}
                >
                  {label}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </dialog>
  );
}
