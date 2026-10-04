from __future__ import annotations

import pytest

from openlatch.errors import AnswerError
from openlatch.pack import PackQuestion
from openlatch.signals import signal
from openlatch.types import ChoiceAnswer, NoulAnswer, QuestionType, ScoreAnswer


def test_noul_signal_is_the_noul_value() -> None:
    assert signal(NoulAnswer(noul=0.96)) == 0.96


def test_choice_signal_is_confidence() -> None:
    answer = ChoiceAnswer(
        choice="yes",
        confidence=0.94,
        probabilities={"yes": 0.94, "no": 0.06},
    )
    assert signal(answer) == 0.94


def test_score_signal_is_confidence() -> None:
    answer = ScoreAnswer(
        score=4.0,
        confidence=0.91,
        probabilities={"3": 0.09, "4": 0.91},
    )
    assert signal(answer) == 0.91


def test_missing_choice_confidence_raises_instead_of_pretending_zero() -> None:
    answer = ChoiceAnswer(choice="yes", confidence=None, probabilities={"yes": 1.0})
    with pytest.raises(AnswerError):
        signal(answer)


def test_noul_out_of_range_raises_instead_of_clamping() -> None:
    with pytest.raises(AnswerError):
        signal(NoulAnswer(noul=1.4))


def test_choice_probability_keys_must_match_pack_options() -> None:
    question = PackQuestion(
        type=QuestionType.CHOICE,
        instructions="pick",
        options=["yes", "no"],
    )
    answer = ChoiceAnswer(
        choice="yes",
        confidence=0.9,
        probabilities={"yes": 0.9, "maybe": 0.1},
    )
    with pytest.raises(AnswerError):
        signal(answer, question)
