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

describe("ApiError", () => {
  it("is an instance of Error", () => {
    const err = new ApiError(404, "not found");
    expect(err).toBeInstanceOf(Error);
    expect(err.name).toBe("ApiError");
    expect(err.status).toBe(404);
    expect(err.message).toBe("not found");
  });
});
