from __future__ import annotations

from pathlib import Path

from openlatch.decide import decide
from openlatch.log import build_record
from openlatch.pack import load_pack
from openlatch.replay import replay
from openlatch.types import NoulRule, Resolution
from tests.conftest import policy_for


def _records(pack, policy, noul_values: list[float]):
    records = []
    for noul in noul_values:
        decision = decide({"sufficient": {"type": "noul", "noul": noul}}, pack, policy)
        records.append(
            build_record(
                decision,
                {"sufficient": {"type": "noul", "noul": noul}},
                model=pack.model,
                usage={"input_tokens": 10, "cost": 0.0001},
                label={"sufficient": noul >= 0.5},
            )
        )
    return records


def test_replay_of_the_same_policy_matches_stored_decision_fieldwise(
    rag_pack_path: Path,
) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(
        pack,
        rules={"sufficient": NoulRule(type="noul", tau_yes=0.95, tau_no=0.05)},
    )
    records = _records(pack, policy, [0.96, 0.50, 0.02])
    report = replay(records, policy, pack)
    assert report.n == 3
    for item in report.records:
        assert item.new.model_dump() == item.old.model_dump()
        assert item.new.items["sufficient"] == item.old.items["sufficient"]


def test_raising_tau_flips_accepts_to_escalate_without_network(
    rag_pack_path: Path,
) -> None:
    pack = load_pack(rag_pack_path)
    loose = policy_for(
        pack,
        rules={"sufficient": NoulRule(type="noul", tau_yes=0.80, tau_no=0.20)},
    )
    tight = policy_for(
        pack,
        rules={"sufficient": NoulRule(type="noul", tau_yes=0.99, tau_no=0.01)},
    )
    records = _records(pack, loose, [0.96, 0.96, 0.96])
    report = replay(records, tight, pack)
    assert report.flipped_to_escalate == 3
    assert report.flipped_to_accept == 0
    assert report.accept_rate_old == 1.0
    assert report.accept_rate_new == 0.0
    assert report.estimated_cost_if_refit is None
    assert all(item.new.overall is Resolution.ESCALATE for item in report.records)


def test_estimated_cost_sums_usage_only_for_new_accepts(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(
        pack,
        rules={"sufficient": NoulRule(type="noul", tau_yes=0.95, tau_no=0.05)},
    )
    records = _records(pack, policy, [0.96, 0.50])
    report = replay(records, policy, pack)
    assert report.estimated_cost_if_refit == 0.0001
