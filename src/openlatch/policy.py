from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from openlatch.errors import PolicyError
from openlatch.pack import Pack
from openlatch.types import FitMeta, Rule


class Policy(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pack_id: str
    pack_version: int
    pack_hash: str
    model: str
    on_failure: Literal["escalate"] = "escalate"
    rules: dict[str, Rule]
    fit: FitMeta | None = None
    escalate_all: bool = False


def load_policy(
    source: str | Path | Mapping[str, Any],
    pack: Pack | None = None,
) -> Policy:
    if isinstance(source, Mapping):
        data = dict(source)
    else:
        try:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PolicyError(f"cannot read policy: {exc}") from exc
    if not isinstance(data, dict):
        raise PolicyError("policy must be a JSON object")
    if data.get("on_failure", "escalate") != "escalate":
        raise PolicyError("on_failure must be 'escalate'")
    try:
        policy = Policy.model_validate(data)
    except ValidationError as exc:
        raise PolicyError(f"illegal policy: {exc}") from exc
    if pack is not None:
        if policy.pack_hash != pack.hash:
            raise PolicyError("policy pack_hash does not match pack")
        for question_id, question in pack.questions.items():
            rule = policy.rules.get(question_id)
            if rule is None:
                raise PolicyError(f"missing rule for {question_id}")
            if rule.type != question.type.value:
                raise PolicyError(f"rule type for {question_id} does not match pack")
    return policy
