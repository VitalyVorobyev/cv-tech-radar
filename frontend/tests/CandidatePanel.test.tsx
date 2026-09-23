import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CandidatePanel } from "../src/ui/CandidatePanel";
import type { Candidate, QueueResponse, ReviewProposal } from "../src/lib/api";

// The panel owns every decision POST in the app, so the assertions here are
// mostly "what did it send, and to which endpoint".

function jsonOk(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

function stubRoutes(overrides: Record<string, () => Promise<unknown>> = {}) {
  fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    const override = overrides[url];
    if (override) return override();
    if (url === "/api/decisions") {
      return jsonOk({ decision_id: 99, created_at: "2026-09-12T09:00:00Z" }, 201);
    }
    if (url === "/api/review/confirm") {
      return jsonOk({
        decision_id: 5,
        item_id: 142,
        ring: "Watch",
        confirmed_at: "2026-09-12T09:00:00Z",
      });
    }
    return jsonOk({});
  });
  vi.stubGlobal("fetch", fetchMock);
}

function bodyOf(url: string): Record<string, unknown> {
  const call = fetchMock.mock.calls.find((c) => String(c[0]) === url);
  if (!call) throw new Error(`no request to ${url}`);
  return JSON.parse((call[1] as RequestInit).body as string);
}

const PROPOSAL: ReviewProposal = {
  decision_id: 5,
  ring: "Watch",
  reason: "Interesting but no code released yet.",
  action: "",
  uncertain: false,
  decided_by: "claude-curator",
  created_at: "2026-09-11T08:00:00Z",
  tracks: ["Calibration"],
};

const PLAIN_CANDIDATE: Candidate = {
  id: 142,
  type: "paper",
  title: "Robust Bundle Adjustment for Industrial Multi-Camera Rigs",
  abstract: "A multi-camera BA formulation with reference code.",
  url: "https://arxiv.org/abs/2601.00001",
  pdf_url: null,
  source: "arXiv",
  published_at: "2026-05-10",
  tracks: ["Calibration", "3D Geometry"],
  scores: {
    relevance: 70,
    source_priority: 0,
    implementation: 45,
    attention: 0,
    novelty: 80,
    negative_penalty: 0,
    final: 66,
  },
  ring_suggested: "Prototype",
  pipeline_rationale: "Matched tracks: Calibration, 3D Geometry.",
  current_decision: null,
  llm_judgment: null,
};

const PROPOSAL_CANDIDATE: Candidate = {
  ...PLAIN_CANDIDATE,
  ring_suggested: "Watch",
  pipeline_rationale: "",
  proposal: PROPOSAL,
  previous_confirmed_ring: null,
};

function renderPanel(candidate: Candidate, client?: QueryClient) {
  const qc =
    client ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <CandidatePanel candidate={candidate} />
    </QueryClientProvider>,
  );
  return { ...utils, queryClient: qc };
}

beforeEach(() => {
  stubRoutes();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("CandidatePanel — plain candidate (date queue)", () => {
  it("shows only Save: no Confirm, no Dismiss", () => {
    renderPanel(PLAIN_CANDIDATE);
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Confirm/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Dismiss/ })).not.toBeInTheDocument();
  });

  it("refuses to save without a reason and sends nothing", async () => {
    renderPanel(PLAIN_CANDIDATE);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Reason is required.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts the picked ring and reason to /api/decisions", async () => {
    renderPanel(PLAIN_CANDIDATE);
    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: "Code released, worth a spike." },
    });
    fireEvent.click(screen.getByLabelText("Prototype"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(bodyOf("/api/decisions")).toMatchObject({
      item_id: 142,
      ring: "Prototype",
      reason: "Code released, worth a spike.",
    });
  });

  it("patches the cached queue page under its real ['queue', date] key", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    // The queue query is registered as ["queue", "2026-05-13"] — never
    // ["queue", "today"], which is what the panel used to write to.
    qc.setQueryData<QueueResponse>(["queue", "2026-05-13"], {
      date: "2026-05-13",
      candidates: [PLAIN_CANDIDATE],
    });

    renderPanel(PLAIN_CANDIDATE, qc);
    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: "Waiting for code." },
    });
    fireEvent.click(screen.getByLabelText("Watch"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      const cached = qc.getQueryData<QueueResponse>(["queue", "2026-05-13"]);
      expect(cached?.candidates[0]?.current_decision?.ring).toBe("Watch");
    });
    expect(qc.getQueryData(["queue", "today"])).toBeUndefined();
  });

  it("marks the queue and review caches stale after a save", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidate = vi.spyOn(qc, "invalidateQueries");
    renderPanel(PLAIN_CANDIDATE, qc);
    fireEvent.change(screen.getByLabelText(/Reason/), {
      target: { value: "Waiting for code." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(invalidate).toHaveBeenCalled());
    const keys = invalidate.mock.calls.map((c) => JSON.stringify(c[0]?.queryKey));
    expect(keys).toContain(JSON.stringify(["queue"]));
    expect(keys).toContain(JSON.stringify(["review"]));
  });
});

describe("CandidatePanel — pending proposal (review inbox)", () => {
  it("seeds the form from the proposal and flags it as not on the radar", () => {
    renderPanel(PROPOSAL_CANDIDATE);
    expect(
      screen.getByText(/Proposed Watch by claude-curator — not on the radar/),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Reason/)).toHaveValue(
      "Interesting but no code released yet.",
    );
  });

  it("Confirm accepts the proposal as-is via /api/review/confirm", async () => {
    renderPanel(PROPOSAL_CANDIDATE);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(bodyOf("/api/review/confirm")).toEqual({ decision_id: 5 });
    // Confirm must never write a new decision.
    expect(
      fetchMock.mock.calls.some((c) => String(c[0]) === "/api/decisions"),
    ).toBe(false);
  });

  it("Save overrides the proposed ring through /api/decisions", async () => {
    renderPanel(PROPOSAL_CANDIDATE);
    fireEvent.click(screen.getByLabelText("Evaluate"));
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(bodyOf("/api/decisions")).toMatchObject({
      item_id: 142,
      ring: "Evaluate",
      reason: "Interesting but no code released yet.",
    });
  });

  it("Dismiss records Ignore with a default reason", async () => {
    const candidate: Candidate = {
      ...PROPOSAL_CANDIDATE,
      proposal: { ...PROPOSAL, reason: "" },
    };
    renderPanel(candidate);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(bodyOf("/api/decisions")).toMatchObject({
      item_id: 142,
      ring: "Ignore",
      reason: "Dismissed in review.",
    });
  });

  it("surfaces a server error instead of pretending the confirm worked", async () => {
    stubRoutes({
      "/api/review/confirm": () =>
        jsonOk({ detail: "Decision 5 is not pending" }, 409),
    });
    renderPanel(PROPOSAL_CANDIDATE);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Decision 5 is not pending",
    );
  });
});
