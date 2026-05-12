from __future__ import annotations

from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvalLabel(StrEnum):
    RELEVANT = "relevant"
    BORDERLINE = "borderline"
    NOISE = "noise"


class LabeledItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    label: EvalLabel
    false_positive_class: str | None = None
    note: str = ""

    @model_validator(mode="after")
    def class_only_for_noise(self) -> LabeledItem:
        if self.label != EvalLabel.NOISE and self.false_positive_class is not None:
            msg = "false_positive_class is only valid when label='noise'"
            raise ValueError(msg)
        return self


class LabeledSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LabeledItem]

    @model_validator(mode="after")
    def external_ids_unique(self) -> LabeledSet:
        ids = [item.external_id for item in self.items]
        if len(ids) != len(set(ids)):
            msg = "labeled item external_ids must be unique"
            raise ValueError(msg)
        return self

    def by_external_id(self) -> dict[str, LabeledItem]:
        return {item.external_id: item for item in self.items}


def load_labeled_items(path: Path) -> LabeledSet:
    if not path.exists():
        msg = f"labeled set not found: {path}"
        raise FileNotFoundError(msg)
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        msg = f"labeled set must be a YAML mapping: {path}"
        raise ValueError(msg)
    return LabeledSet.model_validate(payload)
