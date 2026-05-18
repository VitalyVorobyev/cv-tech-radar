"""Ecosystem (package-registry) collectors.

A second monitoring lane alongside the arXiv collector: this subpackage polls
known software artifacts across GitHub, PyPI, crates.io, and npm, and surfaces
their release / version changes as ``ArtifactEvent`` rows.

``base`` defines the normalization contract (:class:`NormalizedEvent`,
:class:`EcosystemRefResult`) and the shared HTTP plumbing; each ecosystem module
exposes a uniform ``fetch_ref(client, ref, *, token=None)`` entry point; and
``runner`` orchestrates a full, idempotent poll. See ``docs/ecosystem.md``.
"""

from __future__ import annotations

from radar.collectors.ecosystem.base import (
    EcosystemRefResult,
    NormalizedEvent,
    build_ecosystem_client,
)

__all__ = [
    "EcosystemRefResult",
    "NormalizedEvent",
    "build_ecosystem_client",
]
