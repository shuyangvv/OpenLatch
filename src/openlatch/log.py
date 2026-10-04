from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openlatch.errors import OpenLatchError
from openlatch.pack import canonical_dumps
from openlatch.types import Decision, LogRecord, Usage

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    millis = int(time.time() * 1000)
    entropy = int.from_bytes(os.urandom(10), "big")
    value = (millis << 80) | entropy
    chars = ["0"] * 26
    for index in range(25, -1, -1):
        chars[index] = _CROCKFORD[value & 31]
        value >>= 5
    return "".join(chars)


def digest_state(state: Any) -> str:
    payload = hashlib.sha256(canonical_dumps(state).encode("utf-8")).hexdigest()
    return f"sha256:{payload}"


def build_record(
    decision: Decision,
    answers: dict[str, Any],
    *,
    state: Any = None,
    store_state: bool = False,
    usage: Usage | dict[str, Any] | None = None,
    label: dict[str, Any] | None = None,
    model: str | None = None,
    answers_reversed: dict[str, Any] | None = None,
) -> LogRecord:
    usage_obj = None
    if usage is not None:
        usage_obj = usage if isinstance(usage, Usage) else Usage.model_validate(usage)
    return LogRecord(
        id=new_ulid(),
        ts=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        pack_id=decision.pack_id,
        pack_hash=decision.pack_hash,
        model=model or decision.model,
        state_digest=digest_state(state) if state is not None else None,
        state=state if store_state else None,
        answers=answers,
        answers_reversed=answers_reversed,
        decision=decision,
        label=label,
        usage=usage_obj,
    )


class JsonlStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, record: LogRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json(exclude_none=True) + "\n")

    def read(self) -> Iterator[LogRecord]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if text:
                    yield LogRecord.model_validate_json(text)

    def attach_label(self, id: str, label: dict[str, Any]) -> None:
        records = list(self.read())
        found = False
        for record in records:
            if record.id == id:
                record.label = label
                found = True
                break
        if not found:
            raise OpenLatchError(f"unknown log id: {id}")
        tmp = self.path.with_name(self.path.name + ".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(record.model_dump_json(exclude_none=True) + "\n")
        tmp.replace(self.path)
