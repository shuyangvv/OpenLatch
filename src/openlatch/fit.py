from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from openlatch.decide import decide, label_matches
from openlatch.errors import NotEnoughLabels
from openlatch.pack import Pack, PackQuestion
from openlatch.policy import Policy
from openlatch.types import (
    FitMeta,
    LogRecord,
    NoulRule,
    QuestionType,
    Resolution,
    Rule,
    TauRule,
)

DEFAULT_GRID: tuple[float, ...] = (0.80, 0.85, 0.90, 0.95, 0.99)
LabeledRecord = LogRecord


def fit(
    records: Sequence[LabeledRecord],
    pack: Pack,
    *,
    grid: Sequence[float] = DEFAULT_GRID,
    min_n: int = 50,
    lcb_margin: float = -0.02,
) -> Policy:
    labeled = [record for record in records if record.label]
    n = len(labeled)
    if n < min_n:
        raise NotEnoughLabels(n, min_n)

    order = (
        "bilateral"
        if any(record.answers_reversed for record in labeled)
        else "single"
    )
    rules: dict[str, Rule] = {}
    qualified_all = True
    for question_id, question in pack.questions.items():
        rule, qualified = _fit_question(
            question_id, question, labeled, pack, grid, lcb_margin
        )
        rules[question_id] = rule
        qualified_all = qualified_all and qualified

    return Policy(
        pack_id=pack.id,
        pack_version=pack.version,
        pack_hash=pack.hash,
        model=_fitted_model(pack, labeled),
        rules=rules,
        escalate_all=not qualified_all,
        fit=FitMeta(
            n=n,
            rule=f"lcb{lcb_margin}",
            grid=list(grid),
            qualified=qualified_all,
            fitted_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            order=order,
        ),
    )


def _fitted_model(pack: Pack, records: Sequence[LogRecord]) -> str:
    if not pack.allow_unpinned:
        return pack.model
    counts: dict[str, int] = {}
    for record in records:
        counts[record.model] = counts.get(record.model, 0) + 1
    return max(counts, key=lambda name: (counts[name], name))


def _fit_question(
    question_id: str,
    question: PackQuestion,
    records: Sequence[LogRecord],
    pack: Pack,
    grid: Sequence[float],
    lcb_margin: float,
) -> tuple[Rule, bool]:
    scored: list[tuple[Rule, int, bool]] = []
    for candidate in _candidates(question, grid):
        accepts, deltas = _score_candidate(question_id, question, records, pack, candidate)
        scored.append((candidate, accepts, _lcb(deltas) >= lcb_margin))
    qualified = [row for row in scored if row[2]]
    pool = qualified or scored
    best = max(pool, key=lambda row: (row[1], _tau_key(row[0])))
    return best[0], bool(qualified)


def _candidates(question: PackQuestion, grid: Sequence[float]) -> list[Rule]:
    if question.type is QuestionType.NOUL:
        return [
            NoulRule(type="noul", tau_yes=tau, tau_no=round(1.0 - tau, 2))
            for tau in grid
        ]
    return [TauRule(type=question.type.value, tau=tau) for tau in grid]


def _tau_key(rule: Rule) -> float:
    if isinstance(rule, NoulRule):
        return rule.tau_yes
    return rule.tau


def _score_candidate(
    question_id: str,
    question: PackQuestion,
    records: Sequence[LogRecord],
    pack: Pack,
    rule: Rule,
) -> tuple[int, list[float]]:
    policy = Policy(
        pack_id=pack.id,
        pack_version=pack.version,
        pack_hash=pack.hash,
        model=pack.model,
        rules={question_id: rule},
        escalate_all=False,
    )
    accepts = 0
    deltas: list[float] = []
    for record in records:
        decision = decide(_answers_for_fit(record), pack, policy)
        item = decision.items[question_id]
        if item.resolution is Resolution.ACCEPT:
            accepts += 1
            label = (record.label or {}).get(question_id)
            matched = label is not None and label_matches(
                item.accepted_value, label, question.type
            )
            deltas.append(-1.0 if not matched else 0.0)
        else:
            deltas.append(0.0)
    return accepts, deltas


def _answers_for_fit(record: LogRecord) -> dict[str, Any]:
    if not record.answers_reversed:
        return record.answers
    return _average_answers(record.answers, record.answers_reversed)


def _average_answers(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for key, raw in left.items():
        other = right.get(key)
        if not isinstance(raw, dict) or not isinstance(other, dict):
            merged[key] = raw
            continue
        item = dict(raw)
        if "noul" in raw and "noul" in other:
            item["noul"] = (float(raw["noul"]) + float(other["noul"])) / 2.0
        if "confidence" in raw and "confidence" in other:
            item["confidence"] = (
                float(raw["confidence"]) + float(other["confidence"])
            ) / 2.0
        merged[key] = item
    return merged


def _lcb(values: Sequence[float]) -> float:
    n = len(values)
    if n == 0:
        return float("-inf")
    mean = statistics.fmean(values)
    spread = statistics.stdev(values) if n >= 2 else 0.0
    return mean - 1.645 * spread / math.sqrt(n)
