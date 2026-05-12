// Typed fetch client for the CV Radar backend API.
// Mirrors the contract in the Phase A spec exactly.

export type Ring = "Use" | "Prototype" | "Evaluate" | "Watch" | "Ignore";

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

// API error with a server-provided message and HTTP status.
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const res = await fetch(path, options);

  if (!res.ok) {
    let message = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string; message?: string };
      message = body.detail ?? body.message ?? message;
    } catch {
      // swallow JSON parse failures; keep the default message
    }
    throw new ApiError(res.status, message);
  }

  return res.json() as Promise<T>;
}

export const api = {
  health(): Promise<HealthResponse> {
    return request<HealthResponse>("/api/health");
  },

  queue(date: string = "today", limit = 25): Promise<QueueResponse> {
    const params = new URLSearchParams({ date, limit: String(limit) });
    return request<QueueResponse>(`/api/queue?${params}`);
  },

  postDecision(body: DecisionRequest): Promise<DecisionResponse> {
    return request<DecisionResponse>("/api/decisions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },

  board(query: BoardQuery = {}): Promise<BoardResponse> {
    const params = new URLSearchParams();
    if (query.decided_since) params.set("decided_since", query.decided_since);
    if (query.include_ignore) params.set("include_ignore", "true");
    const qs = params.toString();
    return request<BoardResponse>(`/api/board${qs ? `?${qs}` : ""}`);
  },

  item(id: number): Promise<ItemDetail> {
    return request<ItemDetail>(`/api/items/${encodeURIComponent(String(id))}`);
  },

  timeline(weeks = 12): Promise<TimelineResponse> {
    const params = new URLSearchParams({ weeks: String(weeks) });
    return request<TimelineResponse>(`/api/timeline?${params}`);
  },
};
