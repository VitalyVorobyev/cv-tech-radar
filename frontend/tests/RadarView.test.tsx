import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, waitFor, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RadarView } from "../src/views/RadarView";

function stubBoard() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          rings: {
            Use: [],
            Prototype: [],
            Evaluate: [],
            Watch: [],
            Ignore: [],
          },
          counts: { Use: 0, Prototype: 0, Evaluate: 0, Watch: 0, Ignore: 0 },
          decided_since: null,
          include_ignore: false,
        }),
    }),
  );
}

function renderWith(initialUrl: string) {
  window.history.replaceState({}, "", initialUrl);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RadarView />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  stubBoard();
  window.localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("RadarView", () => {
  it("renders the radar header and SVG", async () => {
    renderWith("/");
    await waitFor(() => {
      expect(screen.getByLabelText("CV Tech Radar")).toBeTruthy();
    });
  });

  it("initializes ring focus from URL", async () => {
    renderWith("/?ring=Use");
    await waitFor(() => {
      // The sidebar Use button's copy uniquely contains "In production".
      const sidebarUse = screen.getByRole("button", { name: /In production/ });
      expect(sidebarUse.getAttribute("aria-pressed")).toBe("true");
    });
  });

  it("preserves window.location.hash on URL writes", async () => {
    renderWith("/#/radar");
    await waitFor(() => {
      expect(screen.getByLabelText("CV Tech Radar")).toBeTruthy();
    });
    expect(window.location.hash).toBe("#/radar");
  });
});
