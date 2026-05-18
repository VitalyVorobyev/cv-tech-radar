// Typed fetch client for the CV Radar backend API.
// Mirrors the contract in the Phase A spec exactly.

export type Ring = "Use" | "Prototype" | "Evaluate" | "Watch" | "Ignore";

export type QuadrantId = "perception" | "scene" | "models" | "tooling";

// Lightweight track record returned by /api/tracks. The settings editor uses
// the heavier TrackConfig type (with keywords) — keep them distinct.
export interface TrackInfo {
  id: string;
  name: string;
  quadrant: QuadrantId;
}

export interface TracksResponse {
  tracks: TrackInfo[];
}

export interface Scores {
  relevance: number;
  source_priority: number;
  implementation: number;
  attention: number;
  novelty: number;
  negative_penalty: number;
  final: number;
}

export interface Decision {
  id: number;
  ring: Ring;
  reason: string;
  action: string;
  tracks: string[];
  uncertain: boolean;
  decided_by: string;
  created_at: string;
}

export type LLMVerdict = "yes" | "no" | "unknown";

export interface LLMJudgment {
  verdict: LLMVerdict;
  model: string;
  reason: string;
  judged_at: string;
}

export interface Candidate {
  id: number;
  type: string;
  title: string;
  abstract: string;
  url: string;
  pdf_url: string | null;
  source: string;
  published_at: string;
  tracks: string[];
  scores: Scores;
  ring_suggested: Ring;
  pipeline_rationale: string;
  current_decision: Decision | null;
  llm_judgment: LLMJudgment | null;
}

export interface QueueResponse {
  date: string;
  candidates: Candidate[];
}

// Non-empty content days — backs the Queue/Digest date-grid landing.
export interface QueueDate {
  date: string;
  candidate_count: number;
  decided_count: number;
}

export interface DigestDate {
  date: string;
  title: string;
  item_count: number;
}

export interface ContentDatesResponse {
  queue: QueueDate[];
  digest: DigestDate[];
}

export interface HealthResponse {
  ok: boolean;
  version: string;
}

export interface DecisionRequest {
  item_id: number;
  ring: Ring;
  reason: string;
  action?: string;
  tracks?: string[];
  uncertain?: boolean;
  decided_by?: string;
}

export interface DecisionResponse {
  decision_id: number;
  created_at: string;
}

export type Movement = "new" | "in" | "out";

export interface BoardItem {
  item_id: number;
  title: string;
  url: string;
  tracks: string[];
  reason: string;
  action: string;
  uncertain: boolean;
  ring: Ring;
  decided_by: string;
  decided_at: string;
  score: number | null;
  llm_judgment: LLMJudgment | null;
  movement: Movement | null;
}

export interface HistoryEntry {
  ring: Ring;
  at: string;
}

export interface ItemDetail {
  id: number;
  title: string;
  abstract: string;
  url: string;
  ring: Ring | "";
  track: string;
  tracks: string[];
  reason: string;
  uncertain: boolean;
  source: string;
  published_at: string;
  decided_at: string;
  decided_by: string | null;
  history: HistoryEntry[];
  movement: Movement | null;
}

export interface TimelineWeek {
  iso: string;
  label: string;
  Use: number;
  Prototype: number;
  Evaluate: number;
  Watch: number;
  Ignore: number;
}

export interface TimelineResponse {
  weeks: TimelineWeek[];
}

export interface BoardRings {
  Use: BoardItem[];
  Prototype: BoardItem[];
  Evaluate: BoardItem[];
  Watch: BoardItem[];
  Ignore: BoardItem[];
}

export interface BoardCounts {
  Use: number;
  Prototype: number;
  Evaluate: number;
  Watch: number;
  Ignore: number;
}

export interface BoardResponse {
  rings: BoardRings;
  counts: BoardCounts;
  decided_since: string | null;
  include_ignore: boolean;
}

export interface BoardQuery {
  decided_since?: string | null;
  include_ignore?: boolean;
}

// FastAPI validation error item — `detail` is a list of these on 422 responses.
export interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

// API error with a server-provided message and HTTP status.
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly validationErrors?: ValidationErrorItem[],
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function summarizeValidationErrors(items: ValidationErrorItem[]): string {
  const first = items[0];
  if (!first) return "validation failed";
  const field = first.loc
    .slice(1) // drop the "body" prefix FastAPI prepends
    .map((part) => String(part))
    .join(".");
  return field ? `${field}: ${first.msg}` : first.msg;
}

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(path, options);

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    let validationErrors: ValidationErrorItem[] | undefined;
    try {
      const body = (await res.json()) as {
        detail?: string | ValidationErrorItem[];
        message?: string;
      };
      if (Array.isArray(body.detail)) {
        validationErrors = body.detail;
        message = summarizeValidationErrors(body.detail);
      } else if (typeof body.detail === "string") {
        message = body.detail;
      } else if (body.message) {
        message = body.message;
      }
    } catch {
      // swallow JSON parse failures; keep the default message
    }
    throw new ApiError(res.status, message, validationErrors);
  }

  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Static mode — for the public no-backend build.
// ---------------------------------------------------------------------------

// `import.meta.env.VITE_STATIC` is "1" when built with `vite --mode static`.
// In that mode the public fetchers read from `${BASE_URL}data/*.json` and
// every write/curator endpoint throws. Exposed as a function (not a const) so
// tests can flip the env via `vi.stubEnv` at runtime.
export function isStaticMode(): boolean {
  return import.meta.env.VITE_STATIC === "1";
}

function staticDataUrl(path: string): string {
  // `BASE_URL` is the Vite `base` config — e.g. "/" or "/cv-radar/" — and
  // always ends with a slash.
  return `${import.meta.env.BASE_URL}data/${path}`;
}

function readStatic<T>(path: string): Promise<T> {
  return request<T>(staticDataUrl(path));
}

function refuseInStatic<T>(name: string): Promise<T> {
  return Promise.reject(
    new ApiError(
      405,
      `${name} is not available in the public static build`,
    ),
  );
}

// ---------------------------------------------------------------------------
// Phase 1 additions: jobs, config slices, score debug, candidate/digest files.
// ---------------------------------------------------------------------------

export type JobState = "queued" | "running" | "ok" | "error" | "rate_limited";

export const TERMINAL_JOB_STATES: ReadonlyArray<JobState> = [
  "ok",
  "error",
  "rate_limited",
];

export interface Job {
  id: string;
  stage: string;
  state: JobState;
  submitted_at: string;
  started_at: string | null;
  finished_at: string | null;
  log: string[];
  error: string | null;
  result: Record<string, unknown> | null;
}

export interface JobSubmitResponse {
  job_id: string;
  stage: string;
  state: JobState;
}

export interface JobListResponse {
  jobs: Job[];
}

export interface FetchPayload {
  days?: number;
  max_results?: number;
  max_pages?: number;
  page_delay_seconds?: number;
}

export interface DatePayload {
  date?: string;
}

export interface ApplyPayload {
  markdown_path: string;
  decided_by?: string;
  dry_run?: boolean;
}

export interface DigestPayload {
  date?: string;
  days?: number;
}

export interface RelevanceCheckPayload {
  date?: string;
  limit?: number | null;
  rejudge?: boolean;
}

export interface DailyIterationPayload {
  date?: string;
  fetch?: FetchPayload;
}

// Config slices — mirror radar/schemas.py exactly.

export interface SourceConfig {
  id: string;
  name: string;
  kind: "arxiv" | "rss";
  url: string;
  enabled: boolean;
  priority: number;
  notes: string;
  categories: string[];
}

export interface SourcesConfig {
  sources: SourceConfig[];
}

export interface TrackConfig {
  id: string;
  name: string;
  quadrant: QuadrantId;
  positive_keywords: string[];
  negative_keywords: string[];
}

export interface TopicsConfig {
  tracks: TrackConfig[];
}

export interface NegativeTopicsConfig {
  negative_topics: string[];
}

export interface ScoreWeights {
  relevance: number;
  source_priority: number;
  implementation: number;
  attention: number;
  novelty: number;
  negative_penalty: number;
}

export interface ScoreThresholds {
  use: number;
  prototype: number;
  evaluate: number;
  watch: number;
  ignore: number;
}

export interface ScoringConfig {
  weights: ScoreWeights;
  thresholds: ScoreThresholds;
  source_priority_cap: number;
  candidate_limit: number;
}

export interface ConfigSaveResponse {
  path: string;
  saved_at: string;
}

export interface ConfigReloadResponse {
  reloaded_at: string;
}

// Score debug ----------------------------------------------------------------

export interface ScoreDebugItem {
  item_id: number;
  title: string;
  ring: Ring;
  final: number;
  relevance: number;
  source_priority: number;
  implementation: number;
  novelty: number;
  negative_penalty: number;
  tracks: string[];
  matched_keywords: string[];
}

export interface ScoreDebugResponse {
  date: string;
  items: ScoreDebugItem[];
}

// Candidate / digest file readers --------------------------------------------

export interface CandidateMarkdownResponse {
  date: string;
  markdown: string;
  mtime: string | null;
  exists: boolean;
}

export interface CandidateExportResponse {
  date: string;
  candidates: unknown[];
  generated_at?: string | null;
  mtime: string | null;
  exists: boolean;
}

export interface DigestMarkdownResponse {
  date: string;
  markdown: string;
  mtime: string | null;
  exists: boolean;
}

// Ollama chat & manual draft -------------------------------------------------

export interface OllamaHealthResponse {
  ok: boolean;
  base_url: string;
  chat_model: string;
  chat_enabled: boolean;
  embeddings_model: string;
  embeddings_enabled: boolean;
  error?: string | null;
}

export type OllamaChatRole = "system" | "user" | "assistant";

export interface OllamaChatMessage {
  role: OllamaChatRole;
  content: string;
}

export interface OllamaChatRequest {
  messages: OllamaChatMessage[];
  model?: string;
  system?: string;
  temperature?: number;
  max_tokens?: number;
}

export interface OllamaChatResponse {
  reply: string;
  model: string;
  latency_ms: number;
}

export interface ManualDraftRequest {
  url?: string;
  title?: string;
  abstract?: string;
  hint?: string;
}

export interface ManualDraftResponse {
  title: string;
  abstract: string;
  suggested_tracks: string[];
  suggested_ring: Ring;
  reason: string;
  action: string;
  uncertain: boolean;
  model: string;
  latency_ms: number;
  raw_response: string;
}

// Near-duplicates ------------------------------------------------------------

export interface NearDuplicatePair {
  item_a_id: number;
  item_a_title: string;
  item_a_external_id: string | null;
  item_b_id: number;
  item_b_title: string;
  item_b_external_id: string | null;
  cosine: number;
}

export interface NearDuplicatesResponse {
  date: string;
  days: number;
  threshold: number;
  model: string;
  pairs: NearDuplicatePair[];
}

// Manual-add ----------------------------------------------------------------

export type ManualItemType =
  | "paper"
  | "blog_post"
  | "vendor_news"
  | "library_release"
  | "standard_update"
  | "dataset"
  | "benchmark"
  | "conference_item"
  | "github_repo"
  | "atlas_candidate";

export interface ManualItemPayload {
  title: string;
  url: string;
  abstract?: string;
  published_at: string;
  authors?: string[];
  pdf_url?: string | null;
  doi?: string | null;
  external_id?: string | null;
  item_type?: ManualItemType;
}

export interface ManualItemResponse {
  item_id: number;
  created: boolean;
  tracks: string[];
  positive_keywords: string[];
  recommended_ring: Ring;
  final_score: number;
}

// Ecosystem monitoring ------------------------------------------------------
// A separate radar lane: software artifacts (libraries) tracked across
// GitHub / PyPI / crates.io / npm. Mirrors radar/api/schemas.py exactly.

export type Ecosystem = "github" | "pypi" | "crates" | "npm";

export type Capability =
  | "cv-imaging"
  | "ml-runtimes"
  | "viz-3d-sensors"
  | "build-tooling";

export type EventSeverity = "high" | "medium" | "low";

export interface EcosystemLatestEvent {
  event_type: string;
  version: string | null;
  event_date: string;
  summary: string;
  url: string;
}

export interface ArtifactBoardItem {
  artifact_id: number;
  key: string;
  name: string;
  description: string;
  status: string;
  ring: Ring;
  capability: string;
  tracks: string[];
  ecosystems: string[];
  latest_event: EcosystemLatestEvent | null;
  recent_event_count: number;
  decided_at: string | null;
  movement: Movement | null;
}

export interface EcosystemBoardRings {
  Use: ArtifactBoardItem[];
  Prototype: ArtifactBoardItem[];
  Evaluate: ArtifactBoardItem[];
  Watch: ArtifactBoardItem[];
  Ignore: ArtifactBoardItem[];
}

export interface EcosystemBoardResponse {
  rings: EcosystemBoardRings;
  counts: BoardCounts;
  include_ignore: boolean;
}

export interface EcosystemEventItem {
  id: number;
  artifact_id: number;
  artifact_key: string;
  artifact_name: string;
  ecosystem: string;
  event_type: string;
  version: string | null;
  event_date: string;
  summary: string;
  body: string;
  url: string;
  severity: string;
  relevant: boolean;
  matched_keywords: string[];
}

export interface EcosystemEventsResponse {
  date: string;
  days: number;
  events: EcosystemEventItem[];
}

export interface EcosystemEventsQuery {
  date?: string;
  days?: number;
  relevant_only?: boolean;
  artifact_key?: string | null;
  ecosystem?: string | null;
}

export interface ArtifactRefDetail {
  ecosystem: string;
  ref: string;
  last_version: string | null;
  last_release_at: string | null;
  last_status: string;
  last_checked_at: string | null;
}

export interface ArtifactDecisionEntry {
  ring: Ring;
  tracks: string[];
  reason: string;
  action: string;
  decided_by: string;
  uncertain: boolean;
  decided_at: string;
}

export interface ArtifactDetail {
  artifact_id: number;
  key: string;
  name: string;
  description: string;
  status: string;
  capability: string;
  homepage_url: string;
  ring: Ring;
  tracks: string[];
  refs: ArtifactRefDetail[];
  events: EcosystemEventItem[];
  decisions: ArtifactDecisionEntry[];
}

export interface ArtifactDecisionRequest {
  artifact_id: number;
  ring: Ring;
  reason: string;
  action?: string;
  tracks?: string[];
  uncertain?: boolean;
  decided_by?: string;
}

export const api = {
  health(): Promise<HealthResponse> {
    return request<HealthResponse>("/api/health");
  },

  queue(date: string = "today", limit = 25): Promise<QueueResponse> {
    const params = new URLSearchParams({ date, limit: String(limit) });
    return request<QueueResponse>(`/api/queue?${params}`);
  },

  // Non-empty content days, for the Queue/Digest date-grid landing. The Queue
  // and Digest views exist only in the served (non-static) build, so static
  // mode just yields an empty listing.
  contentDates(): Promise<ContentDatesResponse> {
    if (isStaticMode()) {
      return Promise.resolve({ queue: [], digest: [] });
    }
    return request<ContentDatesResponse>("/api/content-dates");
  },

  postDecision(body: DecisionRequest): Promise<DecisionResponse> {
    if (isStaticMode()) return refuseInStatic<DecisionResponse>("postDecision");
    return request<DecisionResponse>("/api/decisions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  board(query: BoardQuery = {}): Promise<BoardResponse> {
    if (isStaticMode()) return readStatic<BoardResponse>("board.json");
    const params = new URLSearchParams();
    if (query.decided_since) params.set("decided_since", query.decided_since);
    if (query.include_ignore) params.set("include_ignore", "true");
    const qs = params.toString();
    return request<BoardResponse>(`/api/board${qs ? `?${qs}` : ""}`);
  },

  item(id: number): Promise<ItemDetail> {
    if (isStaticMode()) {
      return readStatic<ItemDetail>(`items/${encodeURIComponent(String(id))}.json`);
    }
    return request<ItemDetail>(`/api/items/${encodeURIComponent(String(id))}`);
  },

  timeline(weeks = 12): Promise<TimelineResponse> {
    if (isStaticMode()) return readStatic<TimelineResponse>("timeline.json");
    const params = new URLSearchParams({ weeks: String(weeks) });
    return request<TimelineResponse>(`/api/timeline?${params}`);
  },

  // Track list (id, name, quadrant). In static mode tracks.json carries extra
  // fields (item_ids); the structural subset that matches TracksResponse is
  // what we keep — the extra fields are ignored.
  tracks(): Promise<TracksResponse> {
    if (isStaticMode()) return readStatic<TracksResponse>("tracks.json");
    return request<TracksResponse>("/api/tracks");
  },

  // ---- jobs ---------------------------------------------------------------

  postFetchJob(payload: FetchPayload = {}): Promise<JobSubmitResponse> {
    return request<JobSubmitResponse>("/api/jobs/fetch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  postClassifyJob(payload: DatePayload = {}): Promise<JobSubmitResponse> {
    return request<JobSubmitResponse>("/api/jobs/classify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  postCandidatesJob(payload: DatePayload = {}): Promise<JobSubmitResponse> {
    return request<JobSubmitResponse>("/api/jobs/candidates", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  postApplyJob(payload: ApplyPayload): Promise<JobSubmitResponse> {
    return request<JobSubmitResponse>("/api/jobs/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  postDigestJob(payload: DigestPayload = {}): Promise<JobSubmitResponse> {
    return request<JobSubmitResponse>("/api/jobs/digest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  postEmbedJob(payload: DatePayload = {}): Promise<JobSubmitResponse> {
    return request<JobSubmitResponse>("/api/jobs/embed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  postRelevanceCheckJob(
    payload: RelevanceCheckPayload = {},
  ): Promise<JobSubmitResponse> {
    return request<JobSubmitResponse>("/api/jobs/relevance-check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  postDailyIterationJob(
    payload: DailyIterationPayload = {},
  ): Promise<JobSubmitResponse> {
    return request<JobSubmitResponse>("/api/jobs/daily-iteration", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  getJob(jobId: string): Promise<Job> {
    return request<Job>(`/api/jobs/${encodeURIComponent(jobId)}`);
  },

  listJobs(limit = 20): Promise<JobListResponse> {
    const params = new URLSearchParams({ limit: String(limit) });
    return request<JobListResponse>(`/api/jobs?${params}`);
  },

  // ---- config -------------------------------------------------------------

  getSourcesConfig(): Promise<SourcesConfig> {
    return request<SourcesConfig>("/api/config/sources");
  },

  putSourcesConfig(payload: SourcesConfig): Promise<ConfigSaveResponse> {
    return request<ConfigSaveResponse>("/api/config/sources", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  getTopicsConfig(): Promise<TopicsConfig> {
    return request<TopicsConfig>("/api/config/topics");
  },

  putTopicsConfig(payload: TopicsConfig): Promise<ConfigSaveResponse> {
    return request<ConfigSaveResponse>("/api/config/topics", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  getNegativeTopicsConfig(): Promise<NegativeTopicsConfig> {
    return request<NegativeTopicsConfig>("/api/config/negative-topics");
  },

  putNegativeTopicsConfig(
    payload: NegativeTopicsConfig,
  ): Promise<ConfigSaveResponse> {
    return request<ConfigSaveResponse>("/api/config/negative-topics", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  getScoringConfig(): Promise<ScoringConfig> {
    return request<ScoringConfig>("/api/config/scoring");
  },

  putScoringConfig(payload: ScoringConfig): Promise<ConfigSaveResponse> {
    return request<ConfigSaveResponse>("/api/config/scoring", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  postConfigReload(): Promise<ConfigReloadResponse> {
    return request<ConfigReloadResponse>("/api/config/reload", {
      method: "POST",
    });
  },

  // ---- score debug / candidates / digest files ---------------------------

  getScoreDebug(
    date: string = "today",
    limit = 25,
    includeZero = false,
  ): Promise<ScoreDebugResponse> {
    const params = new URLSearchParams({
      date,
      limit: String(limit),
      include_zero: includeZero ? "true" : "false",
    });
    return request<ScoreDebugResponse>(`/api/score-debug?${params}`);
  },

  getCandidateMarkdown(date: string = "today"): Promise<CandidateMarkdownResponse> {
    const params = new URLSearchParams({ date });
    return request<CandidateMarkdownResponse>(
      `/api/candidates/markdown?${params}`,
    );
  },

  getCandidateExport(date: string = "today"): Promise<CandidateExportResponse> {
    const params = new URLSearchParams({ date });
    return request<CandidateExportResponse>(
      `/api/candidates/export?${params}`,
    );
  },

  getDigestMarkdown(date: string = "today"): Promise<DigestMarkdownResponse> {
    const params = new URLSearchParams({ date });
    return request<DigestMarkdownResponse>(`/api/digest/markdown?${params}`);
  },

  // ---- manual add ---------------------------------------------------------

  postManualItem(payload: ManualItemPayload): Promise<ManualItemResponse> {
    return request<ManualItemResponse>("/api/items/manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  // ---- ollama -------------------------------------------------------------

  getOllamaHealth(): Promise<OllamaHealthResponse> {
    return request<OllamaHealthResponse>("/api/ollama/health");
  },

  postOllamaChat(payload: OllamaChatRequest): Promise<OllamaChatResponse> {
    return request<OllamaChatResponse>("/api/ollama/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  postManualDraft(payload: ManualDraftRequest): Promise<ManualDraftResponse> {
    return request<ManualDraftResponse>("/api/items/manual/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },

  // ---- near-duplicates ----------------------------------------------------

  getNearDuplicates(
    date: string = "today",
    days = 14,
    threshold?: number,
  ): Promise<NearDuplicatesResponse> {
    const params = new URLSearchParams({ date, days: String(days) });
    if (threshold !== undefined) params.set("threshold", String(threshold));
    return request<NearDuplicatesResponse>(
      `/api/near-duplicates?${params}`,
    );
  },

  // ---- ecosystem ----------------------------------------------------------

  ecosystemBoard(includeIgnore = false): Promise<EcosystemBoardResponse> {
    if (isStaticMode()) {
      return readStatic<EcosystemBoardResponse>("ecosystem-board.json");
    }
    const params = new URLSearchParams();
    if (includeIgnore) params.set("include_ignore", "true");
    const qs = params.toString();
    return request<EcosystemBoardResponse>(
      `/api/ecosystem/board${qs ? `?${qs}` : ""}`,
    );
  },

  ecosystemEvents(query: EcosystemEventsQuery = {}): Promise<EcosystemEventsResponse> {
    // The static bundle ships one events file (relevant + irrelevant, a wide
    // window); the `relevant only` toggle and ecosystem filter are applied
    // client-side in EcosystemView when there is no backend.
    if (isStaticMode()) {
      return readStatic<EcosystemEventsResponse>("ecosystem-events.json");
    }
    const params = new URLSearchParams();
    if (query.date) params.set("date", query.date);
    if (query.days !== undefined) params.set("days", String(query.days));
    if (query.relevant_only !== undefined) {
      params.set("relevant_only", query.relevant_only ? "true" : "false");
    }
    if (query.artifact_key) params.set("artifact_key", query.artifact_key);
    if (query.ecosystem) params.set("ecosystem", query.ecosystem);
    const qs = params.toString();
    return request<EcosystemEventsResponse>(
      `/api/ecosystem/events${qs ? `?${qs}` : ""}`,
    );
  },

  ecosystemArtifact(id: number): Promise<ArtifactDetail> {
    if (isStaticMode()) {
      return readStatic<ArtifactDetail>(
        `ecosystem-artifacts/${encodeURIComponent(String(id))}.json`,
      );
    }
    return request<ArtifactDetail>(
      `/api/ecosystem/artifacts/${encodeURIComponent(String(id))}`,
    );
  },

  postEcosystemDecision(
    body: ArtifactDecisionRequest,
  ): Promise<DecisionResponse> {
    if (isStaticMode()) {
      return refuseInStatic<DecisionResponse>("postEcosystemDecision");
    }
    return request<DecisionResponse>("/api/ecosystem/decisions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },
};
