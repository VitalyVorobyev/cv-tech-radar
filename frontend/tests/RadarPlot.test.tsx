import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { RadarPlot } from "../src/ui/RadarPlot";
import type { BoardItem } from "../src/lib/api";

function mkItem(overrides: Partial<BoardItem>): BoardItem {
  return {
    item_id: 1,
    title: "t",
    url: "u",
    tracks: [],
    reason: "",
    action: "",
    uncertain: false,
    ring: "Watch",
    decided_by: "x",
    decided_at: "2026-05-01T00:00:00Z",
    score: null,
    llm_judgment: null,
    movement: null,
    ...overrides,
  };
}

const noop = () => {};

const baseProps = {
  focusedQuad: null,
  focusedRing: null,
  trackFilter: null,
  hoveredId: null,
  selectedId: null,
  showLabels: false,
  reducedMotion: true,
  onHoverDot: noop,
  onSelectDot: noop,
  onFocusQuad: noop,
  onFocusRing: noop,
  onTrackFilter: noop,
} as const;

describe("RadarPlot", () => {
  it("renders without items", () => {
    const { container } = render(<RadarPlot items={[]} {...baseProps} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("places dots inside their ring band radius", () => {
    // viewBox is 760x760; centre is (380, 380); MAX_R = 380 - 28 = 352.
    // Use ring is the innermost band: radii [0, 0.30] * 352 = [0, 105.6].
    const items: BoardItem[] = [
      mkItem({ item_id: 11, ring: "Use", tracks: ["3D Sensors"] }),
    ];
    const { container } = render(<RadarPlot items={items} {...baseProps} />);
    // The dot circle is the second <circle> in its <g role="button"> (pulse may precede it
    // when movement is set — here movement is null so only the dot is rendered).
    const dotGroup = container.querySelector('g[role="button"][aria-label^="#11"]');
    expect(dotGroup).toBeTruthy();
    const circle = dotGroup!.querySelector("circle");
    expect(circle).toBeTruthy();
    const cx = parseFloat(circle!.getAttribute("cx") ?? "0");
    const cy = parseFloat(circle!.getAttribute("cy") ?? "0");
    const r = Math.hypot(cx - 380, cy - 380);
    // Use band: r ∈ (0, 105.6) with 8% padding ⇒ inside (8.4, 97.2).
    expect(r).toBeGreaterThan(0);
    expect(r).toBeLessThan(106);
  });

  it("calls onSelectDot when a dot is clicked", () => {
    const onSelect = vi.fn();
    const items: BoardItem[] = [
      mkItem({ item_id: 42, ring: "Prototype", tracks: ["Robotics Vision"] }),
    ];
    const { container } = render(
      <RadarPlot items={items} {...baseProps} onSelectDot={onSelect} />,
    );
    const dot = container.querySelector('g[role="button"][aria-label^="#42"]');
    expect(dot).toBeTruthy();
    (dot as SVGElement).dispatchEvent(new MouseEvent("click", { bubbles: true }));
    expect(onSelect).toHaveBeenCalledWith(42);
  });

  it("skips items whose first track is not in any quadrant", () => {
    const items: BoardItem[] = [
      mkItem({ item_id: 1, ring: "Use", tracks: ["Unknown Track"] }),
    ];
    const { container } = render(<RadarPlot items={items} {...baseProps} />);
    expect(container.querySelector('g[role="button"][aria-label^="#1 "]')).toBeNull();
  });
});
