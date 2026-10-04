from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Resolution(str, Enum):
    ACCEPT = "accept"
    ESCALATE = "escalate"


class Reason(str, Enum):
    ACCEPTED = "accepted"
    BELOW_TAU = "below_tau"
    NOUL_BAND = "noul_band"
    TYPE_MISMATCH = "type_mismatch"
    MISSING_ANSWER = "missing_answer"
    PACK_MISMATCH = "pack_mismatch"
    MODEL_MISMATCH = "model_mismatch"
    BACKEND_FAILURE = "backend_failure"
    ESCALATE_ALL = "escalate_all"


class QuestionType(str, Enum):
    CHOICE = "choice"
    SCORE = "score"
    NOUL = "noul"


class _IgnoreExtra(BaseModel):
    model_config = ConfigDict(extra="ignore")


class NoulAnswer(_IgnoreExtra):
    type: Literal["noul"] = "noul"
    noul: float


class ChoiceAnswer(_IgnoreExtra):
    type: Literal["choice"] = "choice"
    choice: str
    confidence: float | None = None
    probabilities: dict[str, float] | None = None


class ScoreAnswer(_IgnoreExtra):
    type: Literal["score"] = "score"
    score: float
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    legend: dict[str, str] | None = None


Answer = NoulAnswer | ChoiceAnswer | ScoreAnswer


class QuestionDecision(BaseModel):
    question_id: str
    resolution: Resolution
    signal: float | None = None
    threshold: float | None = None
    thresholds: dict[str, float] | None = None
    reason: Reason
    accepted_value: Any = None


class Decision(BaseModel):
    pack_id: str
    pack_hash: str
    model: str
    items: dict[str, QuestionDecision]
    overall: Resolution


class Usage(_IgnoreExtra):
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None


class LogRecord(BaseModel):
    id: str
    ts: str
    pack_id: str
    pack_hash: str
    model: str
    state_digest: str | None = None
    state: Any = None
    answers: dict[str, Any]
    answers_reversed: dict[str, Any] | None = None
    decision: Decision
    label: dict[str, Any] | None = None
    usage: Usage | None = None


class FitMeta(BaseModel):
    n: int
    rule: str
    grid: list[float]
    qualified: bool
    fitted_at: str
    order: Literal["single", "bilateral"] | None = None


class NoulRule(BaseModel):
    type: Literal["noul"]
    tau_yes: float
    tau_no: float

    @model_validator(mode="after")
    def _ordered(self) -> NoulRule:
        if self.tau_no >= self.tau_yes:
            raise ValueError("tau_no must be < tau_yes")
        return self


class TauRule(BaseModel):
    type: Literal["choice", "score"]
    tau: float


Rule = Annotated[Union[NoulRule, TauRule], Field(discriminator="type")]


class ReplayItem(BaseModel):
    id: str
    old: Decision
    new: Decision


class ReplayReport(BaseModel):
    n: int
    accept_rate_old: float
    accept_rate_new: float
    flipped_to_escalate: int
    flipped_to_accept: int
    label_conflicts_new: int
    estimated_cost_if_refit: float | None = None
    records: list[ReplayItem] = Field(default_factory=list)
