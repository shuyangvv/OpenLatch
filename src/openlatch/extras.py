from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openlatch.types import Decision, Resolution


def resolve(
    decision: Decision,
    fallback: Callable[[], Any] | None = None,
) -> Any:
    if decision.overall is Resolution.ACCEPT:
        return decision
    if fallback is None:
        return decision
    return fallback()
