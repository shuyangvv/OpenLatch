from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from openlatch.errors import AnswerError
from openlatch.pack import Pack, PackQuestion
from openlatch.policy import Policy
from openlatch.signals import signal
from openlatch.types import (
    Answer,
    ChoiceAnswer,
    Decision,
    LogRecord,
    NoulAnswer,
    NoulRule,
    QuestionDecision,
    QuestionType,
    Reason,
    Resolution,
    ScoreAnswer,
    TauRule,
)


def model_matches(pinned: str, observed: str) -> bool:
    return observed == pinned or observed.startswith(f"{pinned}-")


def parse_answer(raw: Any) -> Answer | None:
    if not isinstance(raw, dict):
        return None
    kind = raw.get("type")
    try:
        if kind == "noul":
            return NoulAnswer.model_validate(raw)
        if kind == "choice":
            return ChoiceAnswer.model_validate(raw)
        if kind == "score":
            return ScoreAnswer.model_validate(raw)
    except ValidationError:
        return None
    return None


def label_matches(accepted: Any, label: Any, question_type: QuestionType) -> bool:
    if question_type is QuestionType.NOUL:
        return _as_noul_label(accepted) == _as_noul_label(label)
    if question_type is QuestionType.SCORE:
        try:
            return float(accepted) == float(label)
        except (TypeError, ValueError):
            return False
    return str(accepted) == str(label)


def _as_noul_label(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "yes", "y"}:
        return True
    if text in {"false", "no", "n"}:
        return False
    return None


def decide(
    answers: dict[str, Any],
    pack: Pack,
    policy: Policy,
    *,
    model: str | None = None,
    record: LogRecord | None = None,
) -> Decision:
    del record
    reported_model = model or policy.model
    if policy.pack_hash != pack.hash:
        return _closed(pack, reported_model, Reason.PACK_MISMATCH)
    if model is not None and not model_matches(policy.model, model):
        return _closed(pack, reported_model, Reason.MODEL_MISMATCH)
    if _backend_failure(answers):
        return _closed(pack, reported_model, Reason.BACKEND_FAILURE)
    if policy.escalate_all:
        return _closed(pack, reported_model, Reason.ESCALATE_ALL)

    items = {
        question_id: _decide_one(
            question_id,
            question,
            answers.get(question_id),
            policy,
        )
        for question_id, question in pack.questions.items()
    }
    return _finish(pack, reported_model, items)


def _backend_failure(answers: dict[str, Any] | None) -> bool:
    if not answers:
        return True
    return "__error__" in answers


def _closed(pack: Pack, model: str, reason: Reason) -> Decision:
    items = {
        question_id: QuestionDecision(
            question_id=question_id,
            resolution=Resolution.ESCALATE,
            reason=reason,
        )
        for question_id in pack.questions
    }
    return _finish(pack, model, items)


def _finish(pack: Pack, model: str, items: dict[str, QuestionDecision]) -> Decision:
    accepted = all(item.resolution is Resolution.ACCEPT for item in items.values())
    return Decision(
        pack_id=pack.id,
        pack_hash=pack.hash,
        model=model,
        items=items,
        overall=Resolution.ACCEPT if accepted else Resolution.ESCALATE,
    )


def _decide_one(
    question_id: str,
    question: PackQuestion,
    raw: Any,
    policy: Policy,
) -> QuestionDecision:
    if raw is None:
        return QuestionDecision(
            question_id=question_id,
            resolution=Resolution.ESCALATE,
            reason=Reason.MISSING_ANSWER,
        )
    parsed = parse_answer(raw)
    if parsed is None or parsed.type != question.type.value:
        return QuestionDecision(
            question_id=question_id,
            resolution=Resolution.ESCALATE,
            reason=Reason.TYPE_MISMATCH,
        )
    try:
        value = signal(parsed, question)
    except AnswerError:
        return QuestionDecision(
            question_id=question_id,
            resolution=Resolution.ESCALATE,
            reason=Reason.TYPE_MISMATCH,
        )
    rule = policy.rules.get(question_id)
    if rule is None or rule.type != question.type.value:
        return QuestionDecision(
            question_id=question_id,
            resolution=Resolution.ESCALATE,
            reason=Reason.TYPE_MISMATCH,
            signal=value,
        )
    if question.type is QuestionType.NOUL:
        assert isinstance(rule, NoulRule)
        thresholds = {"tau_yes": rule.tau_yes, "tau_no": rule.tau_no}
        if value >= rule.tau_yes:
            return QuestionDecision(
                question_id=question_id,
                resolution=Resolution.ACCEPT,
                signal=value,
                thresholds=thresholds,
                reason=Reason.ACCEPTED,
                accepted_value=True,
            )
        if value <= rule.tau_no:
            return QuestionDecision(
                question_id=question_id,
                resolution=Resolution.ACCEPT,
                signal=value,
                thresholds=thresholds,
                reason=Reason.ACCEPTED,
                accepted_value=False,
            )
        return QuestionDecision(
            question_id=question_id,
            resolution=Resolution.ESCALATE,
            signal=value,
            thresholds=thresholds,
            reason=Reason.NOUL_BAND,
        )
    assert isinstance(rule, TauRule)
    accepted_value: Any = None
    if isinstance(parsed, ChoiceAnswer):
        accepted_value = parsed.choice
    elif isinstance(parsed, ScoreAnswer):
        accepted_value = parsed.score
    if value >= rule.tau:
        return QuestionDecision(
            question_id=question_id,
            resolution=Resolution.ACCEPT,
            signal=value,
            threshold=rule.tau,
            reason=Reason.ACCEPTED,
            accepted_value=accepted_value,
        )
    return QuestionDecision(
        question_id=question_id,
        resolution=Resolution.ESCALATE,
        signal=value,
        threshold=rule.tau,
        reason=Reason.BELOW_TAU,
    )
