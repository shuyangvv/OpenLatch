from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal

from openlatch.decide import decide
from openlatch.log import JsonlStore, build_record
from openlatch.pack import Pack
from openlatch.policy import Policy


def latch_update(
    state: Mapping[str, Any],
    pack: Pack,
    policy: Policy,
    *,
    answers_key: str = "answers",
    model_key: str = "model",
    decision_key: str = "decision",
    route_key: str = "route",
    store: JsonlStore | None = None,
) -> dict[str, Any]:
    answers = state[answers_key]
    model = state.get(model_key)
    decision = decide(answers, pack, policy, model=model)
    if store is not None:
        store.append(build_record(decision, answers))
    return {decision_key: decision, route_key: decision.overall.value}


def make_latch_node(
    pack: Pack,
    policy: Policy,
    **kwargs: Any,
) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    def node(state: Mapping[str, Any]) -> dict[str, Any]:
        return latch_update(state, pack, policy, **kwargs)

    return node


def route_latch(
    state: Mapping[str, Any],
    *,
    route_key: str = "route",
) -> Literal["accept", "escalate"]:
    return state[route_key]
