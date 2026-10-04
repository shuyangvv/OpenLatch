from __future__ import annotations

from collections.abc import Iterable

from openlatch.decide import decide, label_matches
from openlatch.pack import Pack
from openlatch.policy import Policy
from openlatch.types import LogRecord, ReplayItem, ReplayReport, Resolution


def replay(records: Iterable[LogRecord], policy: Policy, pack: Pack) -> ReplayReport:
    items: list[ReplayItem] = []
    old_accepts = 0
    new_accepts = 0
    flipped_to_escalate = 0
    flipped_to_accept = 0
    label_conflicts_new = 0
    cost = 0.0
    saw_cost = False
    count = 0

    for record in records:
        count += 1
        new_decision = decide(record.answers, pack, policy, model=record.model)
        items.append(ReplayItem(id=record.id, old=record.decision, new=new_decision))
        if record.decision.overall is Resolution.ACCEPT:
            old_accepts += 1
        if new_decision.overall is Resolution.ACCEPT:
            new_accepts += 1
            if record.usage is not None and record.usage.cost is not None:
                cost += record.usage.cost
                saw_cost = True
        if (
            record.decision.overall is Resolution.ACCEPT
            and new_decision.overall is Resolution.ESCALATE
        ):
            flipped_to_escalate += 1
        if (
            record.decision.overall is Resolution.ESCALATE
            and new_decision.overall is Resolution.ACCEPT
        ):
            flipped_to_accept += 1
        if record.label:
            for question_id, item in new_decision.items.items():
                if item.resolution is not Resolution.ACCEPT:
                    continue
                if question_id not in record.label:
                    continue
                question = pack.questions[question_id]
                if not label_matches(
                    item.accepted_value, record.label[question_id], question.type
                ):
                    label_conflicts_new += 1

    return ReplayReport(
        n=count,
        accept_rate_old=(old_accepts / count) if count else 0.0,
        accept_rate_new=(new_accepts / count) if count else 0.0,
        flipped_to_escalate=flipped_to_escalate,
        flipped_to_accept=flipped_to_accept,
        label_conflicts_new=label_conflicts_new,
        estimated_cost_if_refit=round(cost, 10) if saw_cost else None,
        records=items,
    )
