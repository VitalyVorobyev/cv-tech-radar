import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RingLabel } from "../src/ui/RingLabel";
import type { Ring } from "../src/lib/api";

const RINGS: Ring[] = ["Use", "Prototype", "Evaluate", "Watch", "Ignore"];

describe("RingLabel", () => {
  it.each(RINGS)("renders %s with visible text", (ring) => {
    render(<RingLabel ring={ring} />);
    // Each ring maps to its lowercase/cased text
    const lower = ring.toLowerCase();
    // The element text is either the ring name or its lowercase variant
    const el = screen.getByText(new RegExp(lower, "i"));
    expect(el).toBeInTheDocument();
  });

  it("applies accent color to Use", () => {
    const { container } = render(<RingLabel ring="Use" />);
    const span = container.querySelector("span");
    expect(span).toHaveStyle({ color: "var(--color-accent)" });
  });

  it("applies accent color to Prototype", () => {
    const { container } = render(<RingLabel ring="Prototype" />);
    const span = container.querySelector("span");
    expect(span).toHaveStyle({ color: "var(--color-accent)" });
  });

  it("does NOT apply accent color to Watch", () => {
    const { container } = render(<RingLabel ring="Watch" />);
    const span = container.querySelector("span");
    // Watch should not have the accent color inline
    expect(span).not.toHaveStyle({ color: "var(--color-accent)" });
  });

  it("applies line-through to Ignore", () => {
    const { container } = render(<RingLabel ring="Ignore" />);
    const span = container.querySelector("span");
    expect(span).toHaveStyle({ textDecoration: "line-through" });
  });

  it("applies italic to Evaluate", () => {
    const { container } = render(<RingLabel ring="Evaluate" />);
    const span = container.querySelector("span");
    expect(span).toHaveStyle({ fontStyle: "italic" });
  });

  it("applies uppercase to Use", () => {
    const { container } = render(<RingLabel ring="Use" />);
    const span = container.querySelector("span");
    expect(span).toHaveStyle({ textTransform: "uppercase" });
  });
});
