import { describe, it, expect, afterEach, vi } from "vitest";
import { api, ApiError } from "../src/lib/api";

// Stub global fetch
function stubFetch(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: status >= 200 && status < 300,
      status,
      json: () => Promise.resolve(body),
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api.health", () => {
  it("returns health object on 200", async () => {
    stubFetch(200, { ok: true, version: "0.1.0" });
    const result = await api.health();
    expect(result.ok).toBe(true);
    expect(result.version).toBe("0.1.0");
  });
});

describe("api.queue", () => {
  it("returns queue on 200", async () => {
    const payload = {
      date: "2026-05-11",
      candidates: [
        {
          id: "1",
          type: "paper",
          title: "Test Paper",
          abstract: "Abstract text.",
          url: "https://example.com",
          pdf_url: null,
          source: "arXiv",
          published_at: "2026-05-11",
          tracks: ["Calibration"],
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
          pipeline_rationale: "Matched.",
          current_decision: null,
        },
      ],
    };
    stubFetch(200, payload);
    const result = await api.queue("today");
    expect(result.date).toBe("2026-05-11");
    expect(result.candidates).toHaveLength(1);
    expect(result.candidates[0]?.title).toBe("Test Paper");
  });

  it("throws ApiError with status 404 on not-found", async () => {
    stubFetch(404, { detail: "Queue not found" });
    await expect(api.queue("2000-01-01")).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "Queue not found",
    });
  });
});

describe("api.postDecision", () => {
  it("returns decision_id on 201", async () => {
    stubFetch(201, { decision_id: 123, created_at: "2026-05-11T10:00:00Z" });
    const result = await api.postDecision({
      item_id: 1,
      ring: "Watch",
      reason: "Waiting for code.",
    });
    expect(result.decision_id).toBe(123);
  });

  it("throws ApiError with status 422 on validation error", async () => {
    stubFetch(422, { detail: "ring: Input should be one of Use, Prototype…" });
    await expect(
      api.postDecision({ item_id: 1, ring: "Watch", reason: "" }),
    ).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
    });
  });

  it("throws ApiError with status 404 when item is unknown", async () => {
    stubFetch(404, { detail: "Item 999 not found" });
    await expect(
      api.postDecision({ item_id: 999, ring: "Ignore", reason: "Gone." }),
    ).rejects.toMatchObject({
      name: "ApiError",
      status: 404,
      message: "Item 999 not found",
    });
  });

  it("includes server message in ApiError when body has no detail", async () => {
    stubFetch(500, { message: "Internal server error" });
    await expect(api.health()).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
      message: "Internal server error",
    });
  });
});

describe("api.board", () => {
  function stubBoard() {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          rings: { Use: [], Prototype: [], Evaluate: [], Watch: [], Ignore: [] },
          counts: { Use: 0, Prototype: 0, Evaluate: 0, Watch: 0, Ignore: 2 },
          decided_since: null,
          include_ignore: false,
        }),
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("calls /api/board with no params by default", async () => {
    const fetchMock = stubBoard();
    await api.board();
    expect(fetchMock).toHaveBeenCalledWith("/api/board", undefined);
  });

  it("forwards decided_since and include_ignore as query params", async () => {
    const fetchMock = stubBoard();
    await api.board({ decided_since: "2026-05-01T00:00:00Z", include_ignore: true });
    const url = fetchMock.mock.calls[0]?.[0] ?? "";
    expect(url).toContain("/api/board?");
    expect(url).toContain("decided_since=2026-05-01T00%3A00%3A00Z");
    expect(url).toContain("include_ignore=true");
  });
});

describe("ApiError", () => {
  it("is an instance of Error", () => {
    const err = new ApiError(404, "not found");
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("ApiError");
    expect(err.status).toBe(404);
    expect(err.message).toBe("not found");
  });
});

describe("api static-mode branch", () => {
  it("reads BASE_URL/data/board.json when VITE_STATIC=1", async () => {
    vi.stubEnv("VITE_STATIC", "1");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          rings: { Use: [], Prototype: [], Evaluate: [], Watch: [], Ignore: [] },
          counts: { Use: 0, Prototype: 0, Evaluate: 0, Watch: 0, Ignore: 0 },
          decided_since: null,
          include_ignore: false,
        }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await api.board();
    const url = fetchMock.mock.calls[0]?.[0] ?? "";
    // Should fetch the static snapshot, not the API route.
    expect(String(url)).toContain("data/board.json");
    expect(String(url)).not.toContain("/api/");
  });

  it("static-mode postDecision throws ApiError", async () => {
    vi.stubEnv("VITE_STATIC", "1");
    await expect(
      api.postDecision({ item_id: 1, ring: "Watch", reason: "x" }),
    ).rejects.toMatchObject({ name: "ApiError", status: 405 });
  });

  it("falls back to /api in non-static mode", async () => {
    vi.stubEnv("VITE_STATIC", "");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          rings: { Use: [], Prototype: [], Evaluate: [], Watch: [], Ignore: [] },
          counts: { Use: 0, Prototype: 0, Evaluate: 0, Watch: 0, Ignore: 0 },
          decided_since: null,
          include_ignore: false,
        }),
    });
    vi.stubGlobal("fetch", fetchMock);
    await api.board();
    expect(fetchMock).toHaveBeenCalledWith("/api/board", undefined);
  });
});

// --- review inbox (the manual human gate) -----------------------------------

function stubJson(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

const EMPTY_REVIEW = {
  pending_total: 0,
  counts: { Use: 0, Prototype: 0, Evaluate: 0, Watch: 0, Ignore: 0 },
  items: [],
};

describe("api.review", () => {
  it("calls /api/review with no params by default", async () => {
    const fetchMock = stubJson(EMPTY_REVIEW);
    await api.review();
    expect(fetchMock).toHaveBeenCalledWith("/api/review", undefined);
  });

  it("forwards ring, track, q, include_ignore, limit and offset", async () => {
    const fetchMock = stubJson(EMPTY_REVIEW);
    await api.review({
      ring: "Watch",
      track: "Calibration",
      q: "bundle adjustment",
      include_ignore: true,
      limit: 50,
      offset: 100,
    });
    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("/api/review?");
    expect(url).toContain("ring=Watch");
    expect(url).toContain("track=Calibration");
    expect(url).toContain("q=bundle+adjustment");
    expect(url).toContain("include_ignore=true");
    expect(url).toContain("limit=50");
    expect(url).toContain("offset=100");
  });

  it("omits include_ignore when false", async () => {
    const fetchMock = stubJson(EMPTY_REVIEW);
    await api.review({ include_ignore: false, limit: 25 });
    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(url).not.toContain("include_ignore");
    expect(url).toContain("limit=25");
  });

  it("returns pending_total, counts and items", async () => {
    stubJson({
      pending_total: 474,
      counts: { Use: 2, Prototype: 9, Evaluate: 41, Watch: 330, Ignore: 92 },
      items: [],
    });
    const result = await api.review();
    expect(result.pending_total).toBe(474);
    expect(result.counts.Watch).toBe(330);
  });
});

describe("api.reviewSummary", () => {
  it("returns the pending counts for both lanes", async () => {
    const fetchMock = stubJson({ papers_pending: 474, ecosystem_pending: 17 });
    const result = await api.reviewSummary();
    expect(fetchMock).toHaveBeenCalledWith("/api/review/summary", undefined);
    expect(result.papers_pending).toBe(474);
    expect(result.ecosystem_pending).toBe(17);
  });
});

describe("api.confirmReview", () => {
  it("posts the decision id", async () => {
    const fetchMock = stubJson({
      decision_id: 7,
      item_id: 142,
      ring: "Watch",
      confirmed_at: "2026-09-12T09:00:00Z",
    });
    const result = await api.confirmReview(7);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/review/confirm");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ decision_id: 7 });
    expect(result.item_id).toBe(142);
  });

  it("throws ApiError when the proposal is gone", async () => {
    stubJson({ detail: "Decision 7 is not pending" }, 409);
    await expect(api.confirmReview(7)).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      message: "Decision 7 is not pending",
    });
  });
});

describe("api.confirmReviewBulk", () => {
  it("posts decision_ids and surfaces partial failures", async () => {
    const fetchMock = stubJson({
      confirmed: [1, 2],
      failed: [{ decision_id: 3, error: "already confirmed" }],
    });
    const result = await api.confirmReviewBulk([1, 2, 3]);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/review/confirm-bulk");
    expect(JSON.parse(init?.body as string)).toEqual({ decision_ids: [1, 2, 3] });
    expect(result.confirmed).toEqual([1, 2]);
    expect(result.failed[0]?.error).toBe("already confirmed");
  });
});

describe("api.dismissReviewBulk", () => {
  it("posts item_ids without a reason by default", async () => {
    const fetchMock = stubJson({ dismissed: [10], failed: [] });
    await api.dismissReviewBulk([10]);
    const init = fetchMock.mock.calls[0]?.[1];
    expect(JSON.parse(init?.body as string)).toEqual({ item_ids: [10] });
  });

  it("includes the reason when given", async () => {
    const fetchMock = stubJson({ dismissed: [10, 11], failed: [] });
    await api.dismissReviewBulk([10, 11], "Off-domain.");
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/review/dismiss-bulk");
    expect(JSON.parse(init?.body as string)).toEqual({
      item_ids: [10, 11],
      reason: "Off-domain.",
    });
  });
});

describe("api ecosystem review", () => {
  it("reads the pending artifact queue", async () => {
    const fetchMock = stubJson({ pending_total: 17, items: [] });
    const result = await api.ecosystemReview();
    expect(fetchMock).toHaveBeenCalledWith("/api/ecosystem/review", undefined);
    expect(result.pending_total).toBe(17);
  });

  it("posts an artifact confirmation", async () => {
    const fetchMock = stubJson(
      { decision_id: 55, created_at: "2026-09-12T09:00:00Z" },
      201,
    );
    const result = await api.confirmEcosystemReview({
      artifact_id: 4,
      ring: "Use",
      reason: "Already in production.",
    });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/ecosystem/review/confirm");
    expect(JSON.parse(init?.body as string)).toEqual({
      artifact_id: 4,
      ring: "Use",
      reason: "Already in production.",
    });
    expect(result.decision_id).toBe(55);
  });
});

describe("review endpoints in static mode", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  // Every review endpoint is a curator action; the public static build has no
  // backend, so all of them must refuse rather than fetch a 404 page.
  const cases: [string, () => Promise<unknown>][] = [
    ["review", () => api.review()],
    ["reviewSummary", () => api.reviewSummary()],
    ["confirmReview", () => api.confirmReview(1)],
    ["confirmReviewBulk", () => api.confirmReviewBulk([1])],
    ["dismissReviewBulk", () => api.dismissReviewBulk([1])],
    ["ecosystemReview", () => api.ecosystemReview()],
    [
      "confirmEcosystemReview",
      () => api.confirmEcosystemReview({ artifact_id: 1 }),
    ],
  ];

  for (const [name, call] of cases) {
    it(`${name} refuses without fetching`, async () => {
      vi.stubEnv("VITE_STATIC", "1");
      const fetchMock = stubJson({});
      await expect(call()).rejects.toMatchObject({
        name: "ApiError",
        status: 405,
      });
      expect(fetchMock).not.toHaveBeenCalled();
    });
  }
});
