from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError
from sqlalchemy.orm import Session

from radar.decisions import DecisionError, has_prior_decision, record_decision
from radar.schemas import DecisionProposal

CANDIDATE_HEADING_RE = re.compile(r"^## Candidate \d+:\s*(.+)$")
ITEM_ID_RE = re.compile(r"^- Item ID:\s*(\d+)\s*$")
DECISION_MARKER = "### Claude decision"
FENCE_LANGS_ALLOWED = {"", "yaml", "yml"}


class ProposalParseError(RuntimeError):
    def __init__(self, heading: str | None, line_no: int, detail: str) -> None:
        self.heading = heading or "<no candidate heading>"
        self.line_no = line_no
        self.detail = detail
        super().__init__(f"{self.heading} (line {line_no}): {detail}")


@dataclass
class ParsedProposal:
    item_id: int | None
    heading: str
    proposal: DecisionProposal | None = None
    skipped_reason: str | None = None


@dataclass
class ApplyReport:
    applied: list[ParsedProposal] = field(default_factory=list)
    skipped: list[ParsedProposal] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_candidate_proposals(text: str) -> list[ParsedProposal]:
    lines = text.splitlines()
    proposals: list[ParsedProposal] = []
    heading: str | None = None
    item_id: int | None = None
    state = "outside"
    fence_buf: list[str] = []
    fence_start_line = 0
    recorded_for_current = False

    def push_skipped(reason: str) -> None:
        if heading is None:
            return
        proposals.append(ParsedProposal(item_id=item_id, heading=heading, skipped_reason=reason))

    for line_no, line in enumerate(lines, start=1):
        heading_match = CANDIDATE_HEADING_RE.match(line)
        if heading_match:
            if heading is not None and not recorded_for_current:
                push_skipped("missing '### Claude decision' section")
            heading = heading_match.group(1).strip()
            item_id = None
            state = "meta"
            recorded_for_current = False
            fence_buf = []
            continue

        if state == "meta":
            id_match = ITEM_ID_RE.match(line)
            if id_match:
                item_id = int(id_match.group(1))
            if line.strip() == DECISION_MARKER:
                if item_id is None:
                    raise ProposalParseError(
                        heading, line_no, "missing '- Item ID: <int>' bullet before decision"
                    )
                state = "after_decision_marker"
            continue

        if state == "after_decision_marker":
            stripped = line.strip()
            if not stripped:
                continue
            if stripped == "TODO":
                push_skipped("still TODO")
                recorded_for_current = True
                state = "after_close"
                continue
            if stripped.startswith("```"):
                lang = stripped[3:].strip().lower()
                if lang not in FENCE_LANGS_ALLOWED:
                    raise ProposalParseError(
                        heading,
                        line_no,
                        f"unexpected fence language '{lang}'; expected ```yaml",
                    )
                fence_buf = []
                fence_start_line = line_no
                state = "in_fence"
                continue
            raise ProposalParseError(
                heading,
                line_no,
                "expected ```yaml fence or TODO under '### Claude decision'",
            )

        if state == "in_fence":
            if line.strip().startswith("```"):
                yaml_text = "\n".join(fence_buf)
                proposal = _build_proposal(heading, fence_start_line, yaml_text)
                proposals.append(
                    ParsedProposal(item_id=item_id, heading=heading or "", proposal=proposal)
                )
                recorded_for_current = True
                state = "after_close"
                continue
            fence_buf.append(line)
            continue

        # state == "after_close": ignore everything until next candidate or section

    if state == "in_fence":
        raise ProposalParseError(
            heading,
            fence_start_line,
            "unterminated YAML fence under '### Claude decision'",
        )
    if heading is not None and not recorded_for_current:
        push_skipped("missing '### Claude decision' section")
    return proposals


def _build_proposal(heading: str | None, line_no: int, yaml_text: str) -> DecisionProposal:
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise ProposalParseError(heading, line_no, f"malformed YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ProposalParseError(
            heading, line_no, "decision YAML must be a mapping with ring/reason/..."
        )
    try:
        return DecisionProposal.model_validate(data)
    except ValidationError as exc:
        raise ProposalParseError(heading, line_no, _format_validation_error(exc)) from exc


def _format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('msg')}")
    return "; ".join(parts) or str(exc)


def apply_proposals(
    session: Session,
    proposals: list[ParsedProposal],
    *,
    decided_by: str,
    dry_run: bool,
) -> ApplyReport:
    report = ApplyReport()
    for parsed in proposals:
        if parsed.proposal is None:
            report.skipped.append(parsed)
            continue
        if parsed.item_id is None:
            raise ProposalParseError(parsed.heading, 0, "missing item id for proposal")
        if has_prior_decision(session, parsed.item_id):
            report.warnings.append(
                f"item {parsed.item_id} already has a prior decision; appending a new row"
            )
        if dry_run:
            report.applied.append(parsed)
            continue
        try:
            record_decision(
                session,
                item_id=parsed.item_id,
                ring=parsed.proposal.ring,
                tracks=parsed.proposal.tracks,
                reason=parsed.proposal.reason,
                action=parsed.proposal.action,
                decided_by=decided_by,
                uncertain=parsed.proposal.uncertain,
            )
        except DecisionError as exc:
            raise ProposalParseError(parsed.heading, 0, str(exc)) from exc
        report.applied.append(parsed)
    return report


def parse_proposals_file(path: Path) -> list[ParsedProposal]:
    return parse_candidate_proposals(path.read_text(encoding="utf-8"))
