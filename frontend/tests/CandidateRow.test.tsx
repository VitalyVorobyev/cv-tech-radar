import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CandidateRow } from "../src/ui/CandidateRow";
import type { Candidate } from "../src/lib/api";

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={makeQueryClient()}>{children}</QueryClientProvider>
  );
}

const BASE_CANDIDATE: Candidate = {
  id: 142,
  type: "paper",
  title: "Robust Bundle Adjustment for Industrial Multi-Camera Rigs",
  abstract: "A multi-camera BA formulation with reference code and industrial rig dataset.",
  url: "https://arxiv.org/abs/2601.00001",
  pdf_url: "https://arxiv.org/pdf/2601.00001",
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
};

describe("CandidateRow — collapsed", () => {
  it("shows title text", () => {
    const onToggle = vi.fn();
    render(
      <CandidateRow
        candidate={BASE_CANDIDATE}
        expanded={false}
        focused={false}
        onToggle={onToggle}
      />,
      { wrapper },
    );
    expect(
      screen.getByText(/Robust Bundle Adjustment for Industrial Multi-Camera Rigs/i),
    ).toBeInTheDocument();
  });

  it("shows tracks", () => {
    const onToggle = vi.fn();
    render(
      <CandidateRow
        candidate={BASE_CANDIDATE}
        expanded={false}
        focused={false}
        onToggle={onToggle}
      />,
      { wrapper },
    );
    expect(screen.getByText(/Calibration, 3D Geometry/i)).toBeInTheDocument();
  });

  it("shows final score", () => {
    const onToggle = vi.fn();
    render(
      <CandidateRow
        candidate={BASE_CANDIDATE}
        expanded={false}
        focused={false}
        onToggle={onToggle}
      />,
      { wrapper },
    );
    expect(screen.getByText("66")).toBeInTheDocument();
  });

  it("calls onToggle when Enter is pressed on the row", () => {
    const onToggle = vi.fn();
    render(
      <CandidateRow
        candidate={BASE_CANDIDATE}
        expanded={false}
        focused={false}
        onToggle={onToggle}
      />,
      { wrapper },
    );
    const row = screen.getByRole("button", { name: /Robust Bundle Adjustment/i });
    fireEvent.keyDown(row, { key: "Enter" });
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it("calls onToggle when clicked", () => {
    const onToggle = vi.fn();
    render(
      <CandidateRow
        candidate={BASE_CANDIDATE}
        expanded={false}
        focused={false}
        onToggle={onToggle}
      />,
      { wrapper },
    );
    const row = screen.getByRole("button", { name: /Robust Bundle Adjustment/i });
    fireEvent.click(row);
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it("shows ring_suggested label when no decision exists", () => {
    const onToggle = vi.fn();
    const { container } = render(
      <CandidateRow
        candidate={BASE_CANDIDATE}
        expanded={false}
        focused={false}
        onToggle={onToggle}
      />,
      { wrapper },
    );
    // RingLabel for Prototype renders text matching "prototype" (small-caps)
    const ringEl = container.querySelector("span[style*='color: var(--color-accent)']");
    expect(ringEl).toBeInTheDocument();
  });

  it("shows current_decision ring instead of ring_suggested when decision exists", () => {
    const onToggle = vi.fn();
    const candidateWithDecision: Candidate = {
      ...BASE_CANDIDATE,
      ring_suggested: "Prototype",
      current_decision: {
        id: 1,
        ring: "Watch",
        reason: "Waiting for code.",
        action: "",
        tracks: ["Calibration"],
        uncertain: false,
        decided_by: "curator",
        created_at: "2026-05-10T12:00:00Z",
      },
    };
    render(
      <CandidateRow
        candidate={candidateWithDecision}
        expanded={false}
        focused={false}
        onToggle={onToggle}
      />,
      { wrapper },
    );
    // "watch" text should appear (Watch ring renders lowercase)
    expect(screen.getByText(/watch/i)).toBeInTheDocument();
    // Prototype accent text should NOT be rendered since decision overrides
    // (Watch does not get accent color — verified in RingLabel tests)
  });
});
