"""Relevance classification for freshly-created artifact events.

``classify_event`` is event *filtering*, not scoring — it never touches
``radar.scoring``. It reuses ``keyword_matches`` from the keyword filter so the
matching semantics stay identical to paper classification.
"""

from __future__ import annotations

from radar.filters.keyword_filter import keyword_matches
from radar.models import Artifact, ArtifactEvent
from radar.schemas import AppConfig, ArtifactConfig


def classify_event(
    event: ArtifactEvent,
    *,
    artifact: Artifact,
    artifact_config: ArtifactConfig,
    config: AppConfig,
) -> None:
    """Set ``relevant`` / ``severity`` / ``matched_keywords_json`` on ``event``.

    Mutates ``event`` in place. Rules:

    - Candidate keywords are the ``positive_keywords`` of every track named in
      ``artifact.tracks_json`` plus the artifact's ``extra_keywords``; each is
      matched against ``event.summary + " " + event.body``.
    - ``relevant`` is True if the event is a ``major_release``, OR the artifact
      is ``adopted``, OR at least one keyword matched.
    - ``severity`` is ``high`` for a major release, ``medium`` for any other
      relevant event, ``low`` otherwise.
    - If the artifact is ``track_major_only`` and the event is not a major
      release, ``relevant`` is forced False and ``severity`` to ``low`` (the
      matched keyword list is preserved for transparency).
    """
    text = f"{event.summary or ''} {event.body or ''}"

    track_keywords_by_name = {track.name: track.positive_keywords for track in config.topics.tracks}
    candidate_keywords: list[str] = []
    for track_name in artifact.tracks_json or []:
        candidate_keywords.extend(track_keywords_by_name.get(track_name, []))
    candidate_keywords.extend(artifact_config.extra_keywords)

    matched: list[str] = []
    seen: set[str] = set()
    for keyword in candidate_keywords:
        if keyword in seen:
            continue
        seen.add(keyword)
        if keyword_matches(keyword, text):
            matched.append(keyword)

    is_major = event.event_type == "major_release"
    relevant = is_major or artifact.status == "adopted" or bool(matched)

    if is_major:
        severity = "high"
    elif relevant:
        severity = "medium"
    else:
        severity = "low"

    if artifact_config.track_major_only and not is_major:
        relevant = False
        severity = "low"

    event.relevant = relevant
    event.severity = severity
    event.matched_keywords_json = matched


__all__ = ["classify_event"]
