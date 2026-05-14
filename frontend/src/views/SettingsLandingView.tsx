// Settings hub. Lists the four config slices with short descriptions.

import { Chrome } from "../ui/Chrome";

interface SettingsCard {
  href: string;
  title: string;
  blurb: string;
  path: string;
}

const CARDS: SettingsCard[] = [
  {
    href: "#/settings/sources",
    title: "Sources",
    blurb: "arXiv categories and RSS feeds the radar polls.",
    path: "config/sources.yaml",
  },
  {
    href: "#/settings/topics",
    title: "Topics",
    blurb: "Tracks and the positive/negative keywords that map items to them.",
    path: "config/topics.yaml",
  },
  {
    href: "#/settings/negative-topics",
    title: "Negative topics",
    blurb: "Global penalty terms that pull scores down across all tracks.",
    path: "config/negative_topics.yaml",
  },
  {
    href: "#/settings/scoring",
    title: "Scoring",
    blurb: "Weights, ring thresholds, and the candidate-queue cap.",
    path: "config/scoring.yaml",
  },
];

export function SettingsLandingView() {
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
      <main style={{ padding: "1.5rem" }}>
        <h2
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "var(--text-display-l)",
            fontWeight: 400,
            margin: "0 0 0.5rem",
            letterSpacing: "var(--tracking-tight)",
          }}
        >
          Settings
        </h2>
        <p
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: "var(--text-small)",
            color: "var(--color-muted)",
            margin: "0 0 1.5rem",
            maxWidth: "44rem",
            lineHeight: 1.5,
          }}
        >
          Edit the four config slices that drive the pipeline. Saving rewrites the
          underlying YAML and reloads the cached config; existing classifications and
          decisions are unaffected.
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(18rem, 1fr))",
            gap: "1rem",
          }}
        >
          {CARDS.map((card) => (
            <a
              key={card.href}
              href={card.href}
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "0.375rem",
                border: "1px solid var(--color-rule)",
                borderRadius: "var(--radius-sm)",
                padding: "0.875rem 1rem",
                textDecoration: "none",
                color: "inherit",
                background: "transparent",
              }}
            >
              <h3
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: "1.15rem",
                  fontWeight: 400,
                  margin: 0,
                  letterSpacing: "var(--tracking-tight)",
                }}
              >
                {card.title}
              </h3>
              <p
                style={{
                  margin: 0,
                  fontFamily: "var(--font-sans)",
                  fontSize: "var(--text-small)",
                  color: "var(--color-muted)",
                  lineHeight: 1.5,
                }}
              >
                {card.blurb}
              </p>
              <code
                style={{
                  marginTop: "0.25rem",
                  fontFamily: "var(--font-mono)",
                  fontSize: "var(--text-micro)",
                  color: "var(--color-muted)",
                }}
              >
                {card.path}
              </code>
            </a>
          ))}
        </div>
      </main>
    </div>
  );
}
