import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReviewInbox } from "../src/views/ReviewInbox";
import type { ReviewItem, ReviewResponse } from "../src/lib/api";

function jsonOk(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  });
}

function makeItem(
  id: number,
  decisionId: number,
  title: string,
  ring: ReviewItem["proposal"]["ring"],
): ReviewItem {
  return {
    id,
    type: "paper",
    title,
    abstract: `Abstract for ${title}.`,
    url: `https://arxiv.org/abs/${id}`,
    pdf_url: null,
    source: "arXiv",
    published_at: "2026-09-01",
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
    proposal: {
      decision_id: decisionId,
      ring,
      reason: `Proposed ${ring}.`,
      action: "",
      uncertain: false,
      decided_by: "claude-curator",
      created_at: "2026-09-11T08:00:00Z",
      tracks: ["Calibration"],
    },
    previous_confirmed_ring: null,
    llm_judgment: null,
  };
}

const ITEM_A = makeItem(142, 5, "Robust Bundle Adjustment for Camera Rigs", "Watch");
const ITEM_B = makeItem(143, 6, "Learned Checkerboard Corner Refinement", "Evaluate");

const REVIEW: ReviewResponse = {
  pending_total: 2,
  counts: { Use: 2, Prototype: 9, Evaluate: 41, Watch: 330, Ignore: 92 },
  items: [ITEM_A, ITEM_B],
};

let fetchMock: ReturnType<typeof vi.fn>;

interface Routes {
  review?: ReviewResponse;
  confirmBulk?: unknown;
  dismissBulk?: unknown;
  confirm?: unknown;
}

function stubRoutes(routes: Routes = {}) {
  fetchMock = vi.fn((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith("/api/review/confirm-bulk")) {
      return jsonOk(routes.confirmBulk ?? { confirmed: [5, 6], failed: [] });
    }
    if (url.startsWith("/api/review/dismiss-bulk")) {
      return jsonOk(routes.dismissBulk ?? { dismissed: [142, 143], failed: [] });
    }
    if (url.startsWith("/api/review/confirm")) {
      return jsonOk(
        routes.confirm ?? {
          decision_id: 5,
          item_id: 142,
          ring: "Watch",
          confirmed_at: "2026-09-12T09:00:00Z",
        },
      );
    }
    if (url.startsWith("/api/review")) {
      return jsonOk(routes.review ?? REVIEW);
    }
    return jsonOk({});
  });
  vi.stubGlobal("fetch", fetchMock);
}

function renderInbox() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ReviewInbox />
    </QueryClientProvider>,
  );
}

function reviewUrls(): string[] {
  return fetchMock.mock.calls
    .map((c) => String(c[0]))
    .filter((u) => u.startsWith("/api/review?") || u === "/api/review");
}

function bodyOf(prefix: string): Record<string, unknown> {
  const call = fetchMock.mock.calls.find((c) => String(c[0]).startsWith(prefix));
  if (!call) throw new Error(`no request to ${prefix}`);
  return JSON.parse((call[1] as RequestInit).body as string);
}

beforeEach(() => {
  window.history.replaceState({}, "", "/");
  window.localStorage.clear();
  stubRoutes();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("ReviewInbox — listing", () => {
  it("renders every pending proposal with the backlog total", async () => {
    renderInbox();
    expect(
      await screen.findByText(/Robust Bundle Adjustment for Camera Rigs/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Learned Checkerboard Corner Refinement/),
    ).toBeInTheDocument();
    expect(screen.getByText(/2 pending/)).toBeInTheDocument();
  });

  it("shows the unfiltered pending count on each ring chip", async () => {
    renderInbox();
    await screen.findByText(/Robust Bundle Adjustment/);
    const rings = screen.getByRole("group", { name: "Ring filters" });
    expect(within(rings).getByRole("button", { name: "Watch 330" })).toBeInTheDocument();
    expect(within(rings).getByRole("button", { name: "Use 2" })).toBeInTheDocument();
  });

  it("marks rows as proposed rather than decided", async () => {
    renderInbox();
    await screen.findByText(/Robust Bundle Adjustment/);
    expect(
      screen.getAllByLabelText("Proposed, not on the radar"),
    ).toHaveLength(2);
    expect(screen.queryByLabelText("Decision saved")).not.toBeInTheDocument();
  });

  it("hides Ignore proposals until the toggle is on", async () => {
    renderInbox();
    await screen.findByText(/Robust Bundle Adjustment/);
    expect(reviewUrls()[0]).not.toContain("include_ignore");

    fireEvent.click(screen.getByLabelText("include Ignore"));
    await waitFor(() =>
      expect(reviewUrls().some((u) => u.includes("include_ignore=true"))).toBe(true),
    );
  });

  it("filters by ring and mirrors it into the query string", async () => {
    renderInbox();
    await screen.findByText(/Robust Bundle Adjustment/);
    const rings = screen.getByRole("group", { name: "Ring filters" });
    fireEvent.click(within(rings).getByRole("button", { name: "Evaluate 41" }));

    await waitFor(() =>
      expect(reviewUrls().some((u) => u.includes("ring=Evaluate"))).toBe(true),
    );
    expect(window.location.search).toContain("ring=Evaluate");
  });

  it("loads another page against limit", async () => {
    stubRoutes({ review: { ...REVIEW, pending_total: 60 } });
    renderInbox();
    await screen.findByText(/Robust Bundle Adjustment/);
    fireEvent.click(screen.getByRole("button", { name: /Load 50 more/ }));
    await waitFor(() =>
      expect(reviewUrls().some((u) => u.includes("limit=100"))).toBe(true),
    );
  });

  it("shows an inbox-zero state when nothing is pending", async () => {
    stubRoutes({
      review: {
        pending_total: 0,
        counts: { Use: 0, Prototype: 0, Evaluate: 0, Watch: 0, Ignore: 0 },
        items: [],
      },
    });
    renderInbox();
    expect(
      await screen.findByText(/Inbox zero\. Nothing is waiting for a human decision\./),
    ).toBeInTheDocument();
  });
});

describe("ReviewInbox — single confirm", () => {
  it("confirms the expanded proposal through /api/review/confirm", async () => {
    renderInbox();
    const row = await screen.findByRole("button", {
      name: /Robust Bundle Adjustment/,
    });
    fireEvent.click(row);
    fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));

    await waitFor(() => expect(bodyOf("/api/review/confirm")).toEqual({ decision_id: 5 }));
  });

  it("confirms the focused row with the c hotkey", async () => {
    renderInbox();
    await screen.findByText(/Robust Bundle Adjustment/);
    fireEvent.keyDown(document, { key: "c" });
    await waitFor(() => expect(bodyOf("/api/review/confirm")).toEqual({ decision_id: 5 }));
  });

  it("dismisses the focused row with the d hotkey", async () => {
    renderInbox();
    await screen.findByText(/Robust Bundle Adjustment/);
    fireEvent.keyDown(document, { key: "d" });
    await waitFor(() =>
      expect(bodyOf("/api/review/dismiss-bulk")).toEqual({ item_ids: [142] }),
    );
  });
});

describe("ReviewInbox — bulk actions", () => {
  it("confirms every selected proposal in one request", async () => {
    renderInbox();
    await screen.findByText(/Robust Bundle Adjustment/);

    fireEvent.click(
      screen.getByLabelText("Select Robust Bundle Adjustment for Camera Rigs"),
    );
    fireEvent.click(
      screen.getByLabelText("Select Learned Checkerboard Corner Refinement"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm 2" }));

    await waitFor(() =>
      expect(bodyOf("/api/review/confirm-bulk")).toEqual({ decision_ids: [5, 6] }),
    );
  });

  it("select-all covers every loaded row", async () => {
    renderInbox();
    await screen.findByText(/Robust Bundle Adjustment/);
    fireEvent.click(screen.getByLabelText("Select all loaded proposals"));
    expect(screen.getByRole("button", { name: "Confirm 2" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Dismiss 2" }));
    await waitFor(() =>
      expect(bodyOf("/api/review/dismiss-bulk")).toEqual({ item_ids: [142, 143] }),
    );
  });

  it("toggles selection on the focused row with the x hotkey", async () => {
    renderInbox();
    await screen.findByText(/Robust Bundle Adjustment/);
    fireEvent.keyDown(document, { key: "x" });
    expect(
      await screen.findByRole("button", { name: "Confirm 1" }),
    ).toBeInTheDocument();
  });

  it("reports partial failures instead of silently succeeding", async () => {
    stubRoutes({
      confirmBulk: {
        confirmed: [5],
        failed: [{ decision_id: 6, error: "already confirmed" }],
      },
    });
    renderInbox();
    await screen.findByText(/Robust Bundle Adjustment/);
    fireEvent.click(screen.getByLabelText("Select all loaded proposals"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm 2" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("1 confirmed, 1 failed");
    expect(alert).toHaveTextContent("already confirmed");
    // The failed row stays selected so it can be retried.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Confirm 1" })).toBeInTheDocument(),
    );
  });

  it("surfaces a transport failure on the bulk endpoint", async () => {
    stubRoutes();
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/review/confirm-bulk")) {
        return jsonOk({ detail: "database is locked" }, 500);
      }
      return jsonOk(REVIEW);
    });
    renderInbox();
    await screen.findByText(/Robust Bundle Adjustment/);
    fireEvent.click(screen.getByLabelText("Select all loaded proposals"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm 2" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("database is locked");
  });
});
