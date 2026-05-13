// Page shell for a settings sub-route. Title + form area + sticky footer.
// The footer Save/Reset only appears when `dirty` is true.
// `configPath` is the on-disk path the save will rewrite (e.g. "config/sources.yaml").

import { useEffect, type ReactNode } from "react";
import { Button } from "./Button";

interface ConfigSectionProps {
  title: string;
  description?: ReactNode;
  configPath?: string;
  dirty: boolean;
  saving?: boolean;
  saveError?: string | null;
  savedAt?: string | null;
  onSave: () => void;
  onReset: () => void;
  children: ReactNode;
}

export function ConfigSection({
  title,
  description,
  configPath,
  dirty,
  saving = false,
  saveError = null,
  savedAt = null,
  onSave,
  onReset,
  children,
}: ConfigSectionProps) {
  // Guard against navigating away with unsaved changes — both real page
  // unloads and hash-route changes warn the user before discarding.
  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    const hashChange = (e: HashChangeEvent) => {
      const ok = window.confirm(
        "You have unsaved changes. Discard them and leave this page?",
      );
      if (!ok) {
        // Restore the previous hash without spawning a new entry.
        const prev = e.oldURL.split("#")[1] ?? "";
        window.history.replaceState({}, "", `${window.location.pathname}#${prev}`);
        // Force the router to reparse — fire a synthetic event next tick.
        window.dispatchEvent(new HashChangeEvent("hashchange"));
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    window.addEventListener("hashchange", hashChange);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      window.removeEventListener("hashchange", hashChange);
    };
  }, [dirty]);

  return (
    <section
      style={{
        maxWidth: "60rem",
        margin: "0 auto",
        padding: "1.5rem 1.5rem 6rem",
        display: "flex",
        flexDirection: "column",
        gap: "1.5rem",
      }}
    >
      <header style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
        <h2
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "var(--text-display-l)",
            fontWeight: 400,
            letterSpacing: "var(--tracking-tight)",
            margin: 0,
          }}
        >
          {title}
        </h2>
        {description && (
          <p
            style={{
              fontFamily: "var(--font-sans)",
              fontSize: "var(--text-small)",
              color: "var(--color-muted)",
              margin: 0,
              maxWidth: "44rem",
              lineHeight: 1.5,
            }}
          >
            {description}
          </p>
        )}
      </header>

      <div>{children}</div>

      {saveError && (
        <div
          role="alert"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-small)",
            color: "var(--color-accent)",
            border: "1px solid var(--color-rule)",
            padding: "0.5rem 0.75rem",
            borderRadius: "var(--radius-sm)",
          }}
        >
          Save failed: {saveError}
        </div>
      )}

      {savedAt && !dirty && !saveError && (
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "var(--text-micro)",
            color: "var(--color-muted)",
          }}
        >
          Saved {new Date(savedAt).toLocaleTimeString()}.
        </div>
      )}

      {dirty && (
        <footer
          style={{
            position: "sticky",
            bottom: 0,
            background: "var(--color-paper)",
            borderTop: "1px solid var(--color-rule)",
            padding: "0.75rem 0",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "1rem",
            marginLeft: "-1.5rem",
            marginRight: "-1.5rem",
            paddingLeft: "1.5rem",
            paddingRight: "1.5rem",
            zIndex: 10,
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
            }}
          >
            Unsaved changes
            {configPath ? ` — saving rewrites ${configPath}` : ""}
          </span>
          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <Button variant="ghost" size="sm" onClick={onReset} disabled={saving}>
              Reset
            </Button>
            <Button variant="primary" size="sm" onClick={onSave} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </Button>
          </div>
        </footer>
      )}
    </section>
  );
}
