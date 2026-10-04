from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from openlatch.errors import PackError
from openlatch.types import QuestionType


class PackQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: QuestionType
    instructions: str
    criteria: dict[str, str] | None = None
    options: list[str] | None = None
    legend: dict[str, str] | None = None


class Pack(BaseModel):
    id: str
    version: int
    model: str
    bundle: Literal["all_must_accept", "per_question"] = "all_must_accept"
    questions: dict[str, PackQuestion]
    allow_unpinned: bool = False
    hash: str = Field(exclude=True)

    def wire_questions(self) -> dict[str, Any]:
        wired: dict[str, Any] = {}
        for question_id, question in self.questions.items():
            item: dict[str, Any] = {
                "type": question.type.value,
                "instructions": question.instructions,
            }
            if question.criteria:
                item["criteria"] = question.criteria
            if question.options:
                item["options"] = question.options
            if question.legend:
                item["legend"] = question.legend
            wired[question_id] = item
        return wired


def stringify_keys(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, inner in value.items():
            if isinstance(key, bool):
                named = "true" if key else "false"
            else:
                named = str(key) if not isinstance(key, str) else key
            out[named] = stringify_keys(inner)
        return out
    if isinstance(value, list):
        return [stringify_keys(item) for item in value]
    return value


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    return value


def canonical_dumps(value: Any) -> str:
    return json.dumps(
        _canonical(stringify_keys(value)),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def pack_hash(payload: Mapping[str, Any]) -> str:
    if "questions" in payload and "id" in payload:
        body = {
            "id": payload["id"],
            "version": payload["version"],
            "model": payload["model"],
            "bundle": payload.get("bundle", "all_must_accept"),
            "questions": stringify_keys(payload["questions"]),
        }
    else:
        body = stringify_keys(dict(payload))
    digest = hashlib.sha256(canonical_dumps(body).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def is_unpinned_model(model: str) -> bool:
    token = model.strip()
    if token.startswith("~"):
        token = token[1:]
    return token.endswith("jev-latest")


def load_pack(source: str | Path | Mapping[str, Any]) -> Pack:
    if isinstance(source, Mapping):
        data = stringify_keys(dict(source))
    else:
        try:
            loaded = yaml.safe_load(Path(source).read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            raise PackError(f"cannot read pack: {exc}") from exc
        if not isinstance(loaded, dict):
            raise PackError("pack must be a YAML mapping")
        data = stringify_keys(loaded)

    model = data.get("model")
    if not isinstance(model, str):
        raise PackError("pack.model is required")
    allow_unpinned = bool(data.get("allow_unpinned", False))
    if is_unpinned_model(model) and not allow_unpinned:
        raise PackError(f"unpinned model {model!r} requires allow_unpinned: true")

    try:
        questions = {
            question_id: PackQuestion.model_validate(spec)
            for question_id, spec in data["questions"].items()
        }
        pack = Pack(
            id=data["id"],
            version=data["version"],
            model=model,
            bundle=data.get("bundle", "all_must_accept"),
            questions=questions,
            allow_unpinned=allow_unpinned,
            hash=pack_hash(data),
        )
    except (KeyError, TypeError, ValidationError) as exc:
        raise PackError(f"illegal pack: {exc}") from exc
    return pack
