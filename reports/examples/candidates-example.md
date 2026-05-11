# Candidate Queue - 2026-05-10

This file is a committed example only. Routine generated candidate queues are ignored.

It mirrors what `radar candidates` writes, with the `### Claude decision` block filled in
the way `cv-radar-curator` should: a small YAML payload that `radar apply` parses in
bulk. Leave any unreviewed candidate as `TODO`.

## Candidate 1: Robust Bundle Adjustment for Industrial Multi-Camera Rigs

- Item ID: 142
- Type: paper
- Source: arXiv
- URL: https://arxiv.org/abs/2601.00001
- PDF: https://arxiv.org/pdf/2601.00001
- Date: 2026-05-10
- Tracks: Calibration, 3D Geometry
- Suggested ring: Prototype
- Scores:
  - relevance: 70
  - source priority: 0
  - implementation: 45
  - attention: 0
  - novelty: 80
  - negative penalty: 0
  - final: 66

### Abstract / Summary

A multi-camera BA formulation with reference code and an industrial rig dataset.

### Pipeline rationale

Matched tracks: Calibration, 3D Geometry. Positive keywords: bundle adjustment,
calibration, multi-camera.

### Claude decision

```yaml
ring: Prototype
tracks: [Calibration, 3D Geometry]
reason: Has code and an industrial rig dataset; worth a test pass.
action: Run on our calibration rig next sprint.
uncertain: false
```

## Candidate 2: Niche Tracker Without Code

- Item ID: 198
- Type: paper
- Source: arXiv
- URL: https://arxiv.org/abs/2601.00002
- PDF:
- Date: 2026-05-10
- Tracks: Object Tracking
- Suggested ring: Watch
- Scores:
  - relevance: 40
  - source priority: 0
  - implementation: 0
  - attention: 0
  - novelty: 80
  - negative penalty: 0
  - final: 46

### Abstract / Summary

Niche tracker, no code release. Authors hint at later release.

### Pipeline rationale

Matched tracks: Object Tracking.

### Claude decision

```yaml
ring: Watch
reason: Worth watching the arxiv thread for a code drop.
action: Re-check next month.
uncertain: true
```
