# The radar model

Every item on the radar is described by two coordinates: a **ring** that says how
ready it is to act on, and one or more **tracks** that say what it is about. A radar
item is exactly that pair — a ring plus its tracks. Everything else in the system
exists to help assign those two coordinates well.

## The five rings

Rings encode readiness, not quality. An excellent paper on an irrelevant topic
belongs in `Ignore`; a modest library that solves a real problem today can sit in
`Use`. The rings run from "acts on your decisions now" at the center to "explicitly
set aside" at the edge.

| Ring | Meaning | Typical trigger |
|------|---------|-----------------|
| **Use** | Mature enough to influence current technical or toolchain decisions. | A stable release that solves a known problem; a method validated by strong independent evidence. |
| **Prototype** | Worth a small implementation or experiment. | A relevant method with code and plausible benefit; a detector or calibration technique testable on your own data. |
| **Evaluate** | Worth reading, comparing, or adding to a reading queue. | A relevant new paper with an interesting method; a new dataset or benchmark in an important area. |
| **Watch** | Weak or early signal; track only. | Several papers hint at a trend; a vendor hints at upcoming support; attention is rising but practical value is unclear. |
| **Ignore** | Explicitly deprioritized. Kept for audit, not deleted. | Off-topic work; generic hype with no practical signal; weak evaluation with no code and low relevance. |

Two rules govern how items move between rings. First, **promotion requires
evidence, not attention** — nothing climbs toward the center on reputation or hype
alone. Second, the rings are ordered by *cost of being wrong on the reader's
behalf*: `Watch` costs nothing, `Prototype` asks for engineering time, `Use` asks
you to depend on something. So the bar rises sharply as an item moves inward.
Speculative things stay in `Watch`; `Prototype` is reserved for items with code,
data, or a clear test path; `Use` and `Prototype` are meant to be rare.

`Ignore` is a first-class decision, not a wastebasket. Ignored items are kept so
the radar can explain what it filtered out and why — the noise pattern is itself a
useful signal.

## The four quadrants

Tracks are grouped into four quadrants that split the field by *what part of the
vision problem* they address:

| Quadrant | What it covers |
|----------|----------------|
| **perception** | Turning sensors and optics into measurements — calibration, targets, 3D sensing, camera standards. |
| **scene** | Recovering and simulating the physical world — geometry, reconstruction, robotics, synthetic data. |
| **models** | Learned components and how they are measured — tracking, foundation models, datasets and benchmarks. |
| **tooling** | Shipping and running vision systems — inspection, edge deployment, open-source tooling. |

## The tracks

There are fourteen tracks. Each item may belong to several — a paper on hand-eye
calibration for bin picking legitimately spans perception and scene. Tracks are the
radar's vocabulary of interest; they are defined in configuration and drive
classification directly.

| Quadrant | Tracks |
|----------|--------|
| **perception** | Calibration & Camera Models · Target Detection & Fiducials · 3D Sensors · Sensors, Cameras & Standards |
| **scene** | 3D Geometry & Reconstruction · Robotics Vision · Robot Guidance · Synthetic Data & Simulation |
| **models** | Object Tracking · Vision Foundation Models · Datasets & Benchmarks |
| **tooling** | Industrial Vision Inspection · Edge AI & Deployment · Open-Source CV Tooling |

A track carries its own set of positive keywords (the phrases that place an item on
it) and, sometimes, negative keywords (phrases that specifically *disqualify* it —
for example, the Object Tracking track excludes person re-identification, and the
Vision Foundation Models track excludes image and video generation). Those keyword
sets are the seam between the abstract model here and the concrete
[classification](./sourcing-and-classification.md) that follows.

## Putting it together

An item enters as raw text, gets one or more tracks attached, receives a suggested
ring from [scoring](./scoring.md), and then a human confirms or overrides that ring
during [curation](./curation-workflow.md). The point on the radar — its quadrant,
its distance from the center, whether it is new or has moved — is the compact
result of that whole process. How to read that point visually is covered in
[Reading the radar](./reading-the-radar.md).
