// App root.
// Hash routing with two lanes. The papers lane (radar, queue, timeline,
// tracks, pipeline, settings, score-debug, digest, add-paper) and the
// ecosystem lane (radar, releases, artifacts) each have their own tab set,
// switched by a top-level lane control. `#/board` is a legacy alias for
// `#/radar`.

import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { isStaticMode } from "./lib/api";

const IS_STATIC = isStaticMode();
import { QueueView } from "./views/QueueView";
import { RadarView } from "./views/RadarView";
import { EcosystemView } from "./views/EcosystemView";
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
  | "ecosystem"
  | "ecosystem/releases"
  | "ecosystem/artifacts"
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

// The two parallel monitoring lanes. A route belongs to the ecosystem lane iff
// it is one of the ecosystem routes; everything else is the papers lane.
type Lane = "papers" | "ecosystem";

const ECOSYSTEM_ROUTES: ReadonlySet<Route> = new Set([
  "ecosystem",
  "ecosystem/releases",
  "ecosystem/artifacts",
]);

function laneOf(route: Route): Lane {
  return ECOSYSTEM_ROUTES.has(route) ? "ecosystem" : "papers";
}

// The route a lane lands on when you switch into it.
const LANE_HOME: Record<Lane, Route> = { papers: "radar", ecosystem: "ecosystem" };

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
    },
  },
});

// Routes available in the public static build — everything else falls back to radar.
const STATIC_ROUTES: ReadonlySet<Route> = new Set([
  "radar",
  "timeline",
  "tracks",
  "ecosystem",
  "ecosystem/releases",
  "ecosystem/artifacts",
]);

function parseRoute(): Route {
  const raw = window.location.hash.replace(/^#\/?/, "").split("?")[0] ?? "";
  const resolve = (): Route => {
    // `digest/2026-05-13` → "digest"; we read the date inside DigestView.
    if (raw.startsWith("digest")) return "digest";
    if (raw === "settings/sources") return "settings/sources";
    if (raw === "settings/topics") return "settings/topics";
    if (raw === "settings/negative-topics") return "settings/negative-topics";
    if (raw === "settings/scoring") return "settings/scoring";
    if (raw === "settings") return "settings";
    if (raw === "pipeline") return "pipeline";
    if (raw === "score-debug") return "score-debug";
    // `queue/2026-05-13` → "queue"; QueueView reads the date from the hash.
    if (raw.startsWith("queue")) return "queue";
    if (raw === "ecosystem/releases") return "ecosystem/releases";
    if (raw === "ecosystem/artifacts") return "ecosystem/artifacts";
    if (raw === "ecosystem") return "ecosystem";
    if (raw === "timeline") return "timeline";
    if (raw === "tracks") return "tracks";
    if (raw === "manual-add") return "manual-add";
    // `board` is the legacy slug; treat any unknown route as the radar.
    return "radar";
  };
  const route = resolve();
  if (IS_STATIC && !STATIC_ROUTES.has(route)) return "radar";
  return route;
}

interface TabSpec {
  value: Route;
  label: string;
  /** Routes considered "active" for highlighting this tab. */
  matches?: (route: Route) => boolean;
}

const PAPERS_TABS_FULL: TabSpec[] = [
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

const PAPERS_TABS_STATIC: TabSpec[] = [
  { value: "radar", label: "Radar" },
  { value: "tracks", label: "Tracks" },
  { value: "timeline", label: "Timeline" },
];

// The ecosystem lane's three surfaces. All three work in the static build —
// they read ecosystem-board.json / ecosystem-events.json from the bundle.
const ECOSYSTEM_TABS: TabSpec[] = [
  { value: "ecosystem", label: "Radar" },
  { value: "ecosystem/releases", label: "Releases" },
  { value: "ecosystem/artifacts", label: "Artifacts" },
];

function tabsForLane(lane: Lane): TabSpec[] {
  if (lane === "ecosystem") return ECOSYSTEM_TABS;
  return IS_STATIC ? PAPERS_TABS_STATIC : PAPERS_TABS_FULL;
}

function LaneNav({
  route,
  onNavigate,
}: {
  route: Route;
  onNavigate: (next: Route) => void;
}) {
  const lane = laneOf(route);
  const tabs = tabsForLane(lane);
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
        flexDirection: "column",
        gap: "0.5rem",
        maxWidth: "80rem",
        margin: "0 auto",
      }}
    >
      <LaneSwitch lane={lane} onSwitch={(next) => onNavigate(LANE_HOME[next])} />
      <div style={{ display: "flex", gap: "1.25rem", flexWrap: "wrap" }}>
        {tabs.map((tab) => {
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
      </div>
    </nav>
  );
}

function LaneSwitch({
  lane,
  onSwitch,
}: {
  lane: Lane;
  onSwitch: (next: Lane) => void;
}) {
  const lanes: { value: Lane; label: string }[] = [
    { value: "papers", label: "Papers" },
    { value: "ecosystem", label: "Ecosystem" },
  ];
  return (
    <div
      role="tablist"
      aria-label="Radar lane"
      style={{
        display: "inline-flex",
        alignSelf: "flex-start",
        border: "1px solid var(--color-rule)",
        borderRadius: "var(--radius-sm)",
        overflow: "hidden",
      }}
    >
      {lanes.map((entry) => {
        const active = lane === entry.value;
        return (
          <button
            key={entry.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onSwitch(entry.value)}
            style={{
              background: active ? "var(--color-ink)" : "transparent",
              color: active ? "var(--color-paper)" : "var(--color-muted)",
              border: "none",
              padding: "0.25rem 0.85rem",
              cursor: "pointer",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--text-micro)",
              letterSpacing: "var(--tracking-caps)",
              textTransform: "uppercase",
            }}
          >
            {entry.label}
          </button>
        );
      })}
    </div>
  );
}

function renderRoute(route: Route) {
  switch (route) {
    case "ecosystem":
      return <EcosystemView surface="radar" />;
    case "ecosystem/releases":
      return <EcosystemView surface="releases" />;
    case "ecosystem/artifacts":
      return <EcosystemView surface="artifacts" />;
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
      <LaneNav route={route} onNavigate={navigate} />
      {renderRoute(route)}
    </QueryClientProvider>
  );
}
