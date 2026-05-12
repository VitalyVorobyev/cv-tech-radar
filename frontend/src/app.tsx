// App root.
// Hash routing — radar (default), queue, timeline, tracks. `#/board` is a legacy
// alias for `#/radar` so old links keep working.

import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { QueueView } from "./views/QueueView";
import { RadarView } from "./views/RadarView";
import { TimelineView } from "./views/TimelineView";
import { TracksView } from "./views/TracksView";

type Route = "radar" | "queue" | "timeline" | "tracks";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

function parseRoute(): Route {
  const hash = window.location.hash.replace(/^#\/?/, "").split("?")[0];
  if (hash === "queue") return "queue";
  if (hash === "timeline") return "timeline";
  if (hash === "tracks") return "tracks";
  // `board` is the legacy slug; treat any unknown route as the radar.
  return "radar";
}

function NavTabs({
  route,
  onNavigate,
}: {
  route: Route;
  onNavigate: (next: Route) => void;
}) {
  const tabs: { value: Route; label: string }[] = [
    { value: "radar", label: "Radar" },
    { value: "queue", label: "Queue" },
    { value: "timeline", label: "Timeline" },
    { value: "tracks", label: "Tracks" },
  ];
  return (
    <nav
      aria-label="Primary"
      style={{
        position: "sticky",
        top: 0,
        zIndex: 20,
        background: "var(--color-paper)",
        borderBottom: "1px solid var(--color-rule)",
        padding: "0.5rem 1.5rem",
        display: "flex",
        gap: "1.25rem",
        maxWidth: "80rem",
        margin: "0 auto",
      }}
    >
      {tabs.map((tab) => {
        const active = tab.value === route;
        return (
          <button
            key={tab.value}
            type="button"
            onClick={() => onNavigate(tab.value)}
            aria-current={active ? "page" : undefined}
            style={{
              background: "transparent",
              border: "none",
              padding: 0,
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-small)",
              color: active ? "var(--color-ink)" : "var(--color-muted)",
              borderBottom: active ? "1px solid currentColor" : "1px solid transparent",
              letterSpacing: "var(--tracking-caps)",
              textTransform: "lowercase",
            }}
          >
            {tab.label}
          </button>
        );
      })}
    </nav>
  );
}

function renderRoute(route: Route) {
  switch (route) {
    case "queue":
      return <QueueView />;
    case "timeline":
      return <TimelineView />;
    case "tracks":
      return <TracksView />;
    case "radar":
    default:
      return <RadarView />;
  }
}

export function App() {
  const [route, setRoute] = useState<Route>(parseRoute);

  useEffect(() => {
    const handler = () => setRoute(parseRoute());
    window.addEventListener("hashchange", handler);
    return () => window.removeEventListener("hashchange", handler);
  }, []);

  function navigate(next: Route) {
    const search = window.location.search;
    window.location.hash = `#/${next}${search}`;
  }

  return (
    <QueryClientProvider client={queryClient}>
      <NavTabs route={route} onNavigate={navigate} />
      {renderRoute(route)}
    </QueryClientProvider>
  );
}
