from __future__ import annotations

from openlatch.errors import AnswerError
from openlatch.pack import PackQuestion
from openlatch.types import Answer, ChoiceAnswer, NoulAnswer, ScoreAnswer


def signal(answer: Answer, question: PackQuestion | None = None) -> float:
    if isinstance(answer, NoulAnswer):
        if not 0.0 <= answer.noul <= 1.0:
            raise AnswerError("noul out of range")
        return answer.noul
    if answer.confidence is None:
        raise AnswerError("missing confidence")
    if not 0.0 <= answer.confidence <= 1.0:
        raise AnswerError("confidence out of range")
    if isinstance(answer, ChoiceAnswer):
        _check_choice(answer, question)
    elif isinstance(answer, ScoreAnswer):
        _check_score(answer, question)
    return answer.confidence


def _check_choice(answer: ChoiceAnswer, question: PackQuestion | None) -> None:
    if answer.probabilities is None:
        raise AnswerError("missing probabilities")
    keys = set(answer.probabilities)
    if answer.choice not in keys:
        raise AnswerError("choice is not a probabilities key")
    if question is not None and question.options is not None:
        if keys != set(question.options):
            raise AnswerError("probability keys do not match pack options")


def _check_score(answer: ScoreAnswer, question: PackQuestion | None) -> None:
    if answer.probabilities is None:
        return
    expected: set[str] | None = None
    if answer.legend is not None:
        expected = set(answer.legend)
    elif question is not None and question.legend is not None:
        expected = set(question.legend)
    if expected is not None and set(answer.probabilities) != expected:
        raise AnswerError("probability keys do not match legend")
