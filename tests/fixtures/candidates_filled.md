# Candidate Queue - 2026-05-11

## Candidate 1: Robust Bundle Adjustment for Industrial Multi-Camera Rigs

- Item ID: 101
- Type: paper
- Source: arXiv
- URL: https://arxiv.org/abs/2601.00001
- PDF: https://arxiv.org/pdf/2601.00001
- Date: 2026-05-11
- Tracks: Calibration, 3D Geometry
- Suggested ring: Prototype
- Scores:
  - relevance: 70
  - source priority: 0
  - implementation: 45
  - attention: 0
  - novelty: 80
  - negative penalty: 0
  - final: 65

### Abstract / Summary

A multi-camera BA formulation with reference code and an industrial rig dataset.

### Pipeline rationale

Matched tracks: Calibration, 3D Geometry.

### Claude decision

```yaml
ring: Prototype
tracks: [Calibration, 3D Geometry]
reason: Has code and an industrial-grade dataset; worth a test rig pass.
action: Run on our calibration rig next sprint.
uncertain: false
```

## Candidate 2: Niche Tracker Without Code

- Item ID: 202
- Type: paper
- Source: arXiv
- URL: https://arxiv.org/abs/2601.00002
- PDF:
- Date: 2026-05-11
- Tracks: Object Tracking
- Suggested ring: Watch
- Scores:
  - relevance: 40
  - source priority: 0
  - implementation: 0
  - attention: 0
  - novelty: 80
  - negative penalty: 0
  - final: 45

### Abstract / Summary

Niche tracker, no code release. Authors hint at later release.

### Pipeline rationale

Matched tracks: Object Tracking.

### Claude decision

```yaml
ring: Watch
tracks: [Object Tracking]
reason: Worth watching the arxiv thread for a code drop.
action: Re-check next month.
uncertain: true
```

## Candidate 3: Generic Diffusion-Based Detector

- Item ID: 303
- Type: paper
- Source: arXiv
- URL: https://arxiv.org/abs/2601.00003
- PDF: https://arxiv.org/pdf/2601.00003
- Date: 2026-05-11
- Tracks: 
- Suggested ring: Ignore
- Scores:
  - relevance: 5
  - source priority: 0
  - implementation: 0
  - attention: 0
  - novelty: 60
  - negative penalty: 25
  - final: 10

### Abstract / Summary

Yet another diffusion-based detector with broad claims.

### Pipeline rationale

No configured radar track keywords matched.

### Claude decision

```yaml
ring: Ignore
reason: Generic diffusion detector, no industrial relevance.
action: ""
```

## Candidate 4: Still Pending Review

- Item ID: 404
- Type: paper
- Source: arXiv
- URL: https://arxiv.org/abs/2601.00004
- PDF: https://arxiv.org/pdf/2601.00004
- Date: 2026-05-11
- Tracks: Edge AI Deployment
- Suggested ring: Watch
- Scores:
  - relevance: 30
  - source priority: 0
  - implementation: 20
  - attention: 0
  - novelty: 60
  - negative penalty: 0
  - final: 40

### Abstract / Summary

A potentially relevant edge AI deployment paper.

### Pipeline rationale

Matched tracks: Edge AI Deployment.

### Claude decision

TODO
