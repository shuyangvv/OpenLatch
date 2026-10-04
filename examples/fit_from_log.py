"""Reproduce the README numbers: fit a Policy from labeled JSONL, then replay."""

from __future__ import annotations

from pathlib import Path

from openlatch import fit, load_pack, replay
from openlatch.log import JsonlStore

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "tests/fixtures/packs/rag_sufficiency.v1.yaml"
LOG = ROOT / "tests/fixtures/logs/labeled.jsonl"


def main() -> None:
    pack = load_pack(PACK)
    records = list(JsonlStore(LOG).read())
    policy = fit(records, pack, min_n=50)
    report = replay(records, policy, pack)
    print(policy.model_dump_json(indent=2))
    print(
        report.model_dump_json(
            indent=2,
            exclude={"records"},
        )
    )


if __name__ == "__main__":
    main()
