"""Fake Jev answers through openlatch.decide. No HTTP leaves this process."""

from __future__ import annotations

import json
from pathlib import Path

from openlatch import decide, load_pack, load_policy
from openlatch.types import Resolution

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "tests/fixtures/packs/rag_sufficiency.v1.yaml"
ANSWERS = ROOT / "tests/fixtures/answers/rag_ok.json"


def main() -> None:
    pack = load_pack(PACK)
    policy = load_policy(
        {
            "pack_id": pack.id,
            "pack_version": pack.version,
            "pack_hash": pack.hash,
            "model": pack.model,
            "on_failure": "escalate",
            "rules": {
                "sufficient": {"type": "noul", "tau_yes": 0.95, "tau_no": 0.05}
            },
        },
        pack=pack,
    )
    answers = json.loads(ANSWERS.read_text(encoding="utf-8"))
    # Caller would do: raw = client.system_one(..., questions=pack.wire_questions())
    decision = decide(answers, pack, policy, model="typesafe/jev-1.13-20260917")
    print(decision.model_dump_json(indent=2))
    if decision.overall is Resolution.ACCEPT:
        print("auto path: use the passage")
    else:
        print("closed: escalate to a human")


if __name__ == "__main__":
    main()
