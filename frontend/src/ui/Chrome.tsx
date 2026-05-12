// Header and footer chrome.
// Header: title, date, theme toggle.
// Footer: review counts + keyboard hints.

import { useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";

function applyTheme(theme: Theme) {
  const html = document.documentElement;
  if (theme === "dark") {
    html.setAttribute("data-theme", "dark");
  } else if (theme === "light") {
    html.setAttribute("data-theme", "light");
  } else {
    html.removeAttribute("data-theme");
  }
}

interface FooterStats {
  total: number;
  reviewed: number;
  uncertain: number;
}

interface ChromeProps {
  stats?: FooterStats;
  /** Slot for filter bar or any header-level content */
  filterSlot?: React.ReactNode;
}

export function Chrome({ stats, filterSlot }: ChromeProps) {
  const [theme, setTheme] = useState<Theme>(() => {
    const stored = localStorage.getItem("cvradar.theme");
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
    return "system";
  });

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem("cvradar.theme", theme);
  }, [theme]);

  const today = new Date().toLocaleDateString("en-US", {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  });

  const todo = stats ? stats.total - stats.reviewed : 0;

  return (
    <>
      {/* Header */}
      <header
        style={{
          borderBottom: "1px solid var(--color-rule)",
          padding: "1rem 1.5rem",
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "1rem",
        }}
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "0.125rem" }}>
          <h1
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "var(--text-display-l)",
              fontWeight: 400,
              margin: 0,
              letterSpacing: "var(--tracking-tight)",
            }}
          >
            CV Tech Radar
          </h1>
          <time
            dateTime={new Date().toISOString().slice(0, 10)}
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
            }}
          >
            {today}
          </time>
        </div>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "1.5rem",
          }}
        >
          {/* Filter slot */}
          {filterSlot}

          {/* Theme toggle — typographic radio */}
          <div
            role="radiogroup"
            aria-label="Color theme"
            style={{ display: "flex", gap: "0.75rem" }}
          >
            {(["Light", "Dark", "System"] as const).map((label) => {
              const val = label.toLowerCase() as Theme;
              const active = theme === val;
              return (
                <label
                  key={val}
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "var(--text-micro)",
                    color: active ? "var(--color-ink)" : "var(--color-muted)",
                    cursor: "pointer",
                    userSelect: "none",
                    borderBottom: active
                      ? "1px solid var(--color-ink)"
                      : "1px solid transparent",
                  }}
                >
                  <input
                    type="radio"
                    name="theme"
                    value={val}
                    checked={active}
                    onChange={() => setTheme(val)}
                    style={{ position: "absolute", opacity: 0, width: 0, height: 0 }}
                  />
                  {label}
                </label>
              );
            })}
          </div>
        </div>
      </header>

      {/* Footer — rendered at the bottom by QueueView; exposed here so Chrome owns the chrome */}
      {stats !== undefined && (
        <footer
          style={{
            position: "sticky",
            bottom: 0,
            borderTop: "1px solid var(--color-rule)",
            padding: "0.5rem 1.5rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "var(--color-paper)",
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
            {stats.reviewed} reviewed
            {stats.uncertain > 0 && <> · {stats.uncertain} uncertain</>}
            {todo > 0 && <> · {todo} still TODO</>}
          </span>

          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
            }}
          >
            j/k navigate · enter expand · ? shortcuts
          </span>
        </footer>
      )}
    </>
  );
}
