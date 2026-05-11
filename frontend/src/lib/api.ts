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
};
