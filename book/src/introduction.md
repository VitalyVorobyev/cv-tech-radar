# Introduction

A technology radar is a decision tool disguised as a picture. It plots the things
you could pay attention to — techniques, tools, standards, datasets — as points
arranged by how ready they are to influence your work. The value is not the plot
itself; it is the discipline of deciding, for every candidate, *where it belongs*
and *why*.

CV Radar applies that discipline to one field: computer vision. It is
**private-first**. The raw feed of papers and releases stays local; only an
explicitly curated slice is ever published. Most of what flows through the
pipeline is never meant to be seen by anyone but the curator.

## The goal is not to summarize everything

This is the single principle the whole system is built around. There is no
shortage of computer-vision news, and a radar that tried to cover all of it would
just be another firehose. The goal is the opposite: **to decide what is worth
attention** — and, just as importantly, what is worth ignoring.

That framing changes every design choice downstream. The pipeline is tuned to
*reduce* volume, not maximize recall of "interesting" things. A famous author, a
prestigious lab, a viral thread, or a bold claim is not enough to promote an item.
The questions the radar answers for its user are narrow and practical:

- What should I notice?
- What should I ignore?
- What deserves reading later?
- What deserves a small prototype?

## Who it is for

The radar is built for a computer-vision engineer or team lead who wants to stay
aware of relevant technical movement without reading professional news every day.
It assumes a reader who prefers a short, skeptical daily note over an exhaustive
survey, and who values knowing *why* something was ignored as much as knowing what
was surfaced.

## What it focuses on

CV Radar is deliberately not a general AI-news aggregator. It is relevance-filtered
toward practical, industrial, and geometric computer vision. Its areas of interest
are concrete:

- Calibration and camera models
- Target detection and fiducials
- 3D geometry, reconstruction, and 3D sensors
- Robotics vision and robot guidance
- Industrial vision inspection
- Object tracking
- Edge AI and deployment
- Open-source CV tooling
- Sensors, cameras, and standards
- Synthetic data and simulation
- Datasets and benchmarks

Work that lands squarely in adjacent-but-different fields — face recognition,
medical imaging, autonomous driving, generative art, remote sensing — is actively
pushed *down*, not up. Those are real fields; they are just not this radar's job.

## What this book is, and is not

This book describes the **method**: the rings an item can occupy, the tracks it can
belong to, how candidates are sourced and classified, how they are scored, how a
human curates them, and how the result is rendered. It is a description of *how the
machine decides*, written so the reasoning is inspectable.

It is not the radar's current contents. Which specific items sit in which ring
today is exactly the private, moving part the system keeps to itself. For that,
read the live radar next to this book — the book explains the rules of the game,
the radar shows the current board.

The chapters that follow build up in order: the [radar model](./radar-model.md),
then [sourcing and classification](./sourcing-and-classification.md),
[scoring](./scoring.md), the [two lanes](./two-lanes.md), the
[curation workflow](./curation-workflow.md), how to [read the radar](./reading-the-radar.md),
and finally [how this site is built](./how-this-site-is-built.md).
