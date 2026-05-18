// Date-grid landing for the Queue and Digest views. Instead of probing a
// calendar input blind, the view shows one card per day that actually has
// content. Each card cross-links to the matching day in the *other* view —
// queue → digest and digest → queue — when that day has content there too.

import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

function formatCardDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

interface CardData {
  date: string;
  primary: string;
  secondary: string;
  crossAvailable: boolean;
}

export function ContentDateGrid({
  kind,
  onPick,
}: {
  kind: "queue" | "digest";
  onPick(date: string): void;
}) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["content-dates"],
    queryFn: () => api.contentDates(),
  });

  if (isLoading) {
    return <div className="skeleton-block" style={{ height: "12rem" }} aria-hidden="true" />;
  }
  if (isError) {
    return (
      <div
        role="alert"
        style={{
          fontFamily: "var(--font-display)",
          fontStyle: "italic",
          color: "var(--color-muted)",
        }}
      >
        Could not load content dates:{" "}
        {error instanceof Error ? error.message : "unknown error"}.
      </div>
    );
  }

  const digestDates = new Set((data?.digest ?? []).map((entry) => entry.date));
  const queueDates = new Set((data?.queue ?? []).map((entry) => entry.date));

  const cards: CardData[] =
    kind === "queue"
      ? (data?.queue ?? []).map((entry) => ({
          date: entry.date,
          primary: plural(entry.candidate_count, "candidate"),
          secondary: `${entry.decided_count} decided`,
          crossAvailable: digestDates.has(entry.date),
        }))
      : (data?.digest ?? []).map((entry) => ({
          date: entry.date,
          primary: entry.title,
          secondary: plural(entry.item_count, "decision"),
          crossAvailable: queueDates.has(entry.date),
        }));

  if (cards.length === 0) {
    return (
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontStyle: "italic",
          fontSize: "var(--text-display-l)",
          color: "var(--color-muted)",
          lineHeight: 1.4,
          padding: "2rem 0",
        }}
      >
        Nothing here yet. Run the daily pipeline to populate the{" "}
        {kind === "queue" ? "candidate queue" : "digest"}.
      </div>
    );
  }

  const crossKind = kind === "queue" ? "digest" : "queue";

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(13rem, 1fr))",
        gap: "0.75rem",
      }}
    >
      {cards.map((card) => (
        <div
          key={card.date}
          role="button"
          tabIndex={0}
          onClick={() => onPick(card.date)}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              onPick(card.date);
            }
          }}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "0.3rem",
            padding: "0.85rem 0.9rem",
            border: "1px solid var(--color-rule)",
            borderRadius: "var(--radius-sm)",
            cursor: "pointer",
            background: "transparent",
          }}
        >
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-small)",
              letterSpacing: "0.04em",
            }}
          >
            {formatCardDate(card.date)}
          </div>
          <div
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "var(--text-body)",
              lineHeight: 1.3,
            }}
          >
            {card.primary}
          </div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              gap: "0.5rem",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              color: "var(--color-muted)",
            }}
          >
            <span>{card.secondary}</span>
            {card.crossAvailable && (
              <a
                href={`#/${crossKind}/${card.date}`}
                onClick={(event) => event.stopPropagation()}
                style={{ color: "var(--color-accent)", whiteSpace: "nowrap" }}
              >
                {crossKind} →
              </a>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
