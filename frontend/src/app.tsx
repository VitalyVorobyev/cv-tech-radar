// App root.
// Hash routing — radar (default), queue, timeline, tracks, pipeline, settings,
// score-debug, digest. `#/board` is a legacy alias for `#/radar` so old links
// keep working.

import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { QueueView } from "./views/QueueView";
import { RadarView } from "./views/RadarView";
import { TimelineView } from "./views/TimelineView";
import { TracksView } from "./views/TracksView";
import { PipelineView } from "./views/PipelineView";
import { SettingsLandingView } from "./views/SettingsLandingView";
import { SettingsSourcesView } from "./views/SettingsSourcesView";
import { SettingsTopicsView } from "./views/SettingsTopicsView";
import { SettingsNegativeTopicsView } from "./views/SettingsNegativeTopicsView";
import { SettingsScoringView } from "./views/SettingsScoringView";
import { ScoreDebugView } from "./views/ScoreDebugView";
import { DigestView } from "./views/DigestView";
import { ManualAddView } from "./views/ManualAddView";

type Route =
  | "radar"
  | "queue"
  | "timeline"
  | "tracks"
  | "manual-add"
  | "pipeline"
  | "score-debug"
  | "digest"
  | "settings"
  | "settings/sources"
  | "settings/topics"
  | "settings/negative-topics"
  | "settings/scoring";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

function parseRoute(): Route {
  const raw = window.location.hash.replace(/^#\/?/, "").split("?")[0] ?? "";
  // `digest/2026-05-13` → "digest"; we read the date inside DigestView.
  if (raw.startsWith("digest")) return "digest";
  if (raw === "settings/sources") return "settings/sources";
  if (raw === "settings/topics") return "settings/topics";
  if (raw === "settings/negative-topics") return "settings/negative-topics";
  if (raw === "settings/scoring") return "settings/scoring";
  if (raw === "settings") return "settings";
  if (raw === "pipeline") return "pipeline";
  if (raw === "score-debug") return "score-debug";
  if (raw === "queue") return "queue";
  if (raw === "timeline") return "timeline";
  if (raw === "tracks") return "tracks";
  if (raw === "manual-add") return "manual-add";
  // `board` is the legacy slug; treat any unknown route as the radar.
  return "radar";
}

interface TabSpec {
  value: Route;
  label: string;
  /** Routes considered "active" for highlighting this tab. */
  matches?: (route: Route) => boolean;
}

const PRIMARY_TABS: TabSpec[] = [
  { value: "radar", label: "Radar" },
  { value: "queue", label: "Queue" },
  { value: "timeline", label: "Timeline" },
  { value: "tracks", label: "Tracks" },
  { value: "manual-add", label: "Add paper" },
  { value: "pipeline", label: "Pipeline" },
  { value: "score-debug", label: "Score debug" },
  { value: "digest", label: "Digest" },
  {
    value: "settings",
    label: "Settings",
    matches: (route) => route === "settings" || route.startsWith("settings/"),
  },
];

function NavTabs({
  route,
  onNavigate,
}: {
  route: Route;
  onNavigate: (next: Route) => void;
}) {
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
        flexWrap: "wrap",
      }}
    >
      {PRIMARY_TABS.map((tab) => {
        const active = tab.matches ? tab.matches(route) : tab.value === route;
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
    case "manual-add":
      return <ManualAddView />;
    case "pipeline":
      return <PipelineView />;
    case "score-debug":
      return <ScoreDebugView />;
    case "digest":
      return <DigestView />;
    case "settings":
      return <SettingsLandingView />;
    case "settings/sources":
      return <SettingsSourcesView />;
    case "settings/topics":
      return <SettingsTopicsView />;
    case "settings/negative-topics":
      return <SettingsNegativeTopicsView />;
    case "settings/scoring":
      return <SettingsScoringView />;
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
