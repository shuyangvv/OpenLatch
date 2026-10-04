from __future__ import annotations

import json
from pathlib import Path

from openlatch.graph import latch_update, make_latch_node, route_latch
from openlatch.log import JsonlStore
from openlatch.pack import load_pack
from openlatch.types import Reason, Resolution
from tests.conftest import policy_for


def test_latch_update_accepts_fixture_answers(
    rag_pack_path: Path, rag_ok_path: Path
) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    answers = json.loads(rag_ok_path.read_text(encoding="utf-8"))
    update = latch_update(
        {"answers": answers, "model": "typesafe/jev-1.13-20260917"},
        pack,
        policy,
    )
    assert update["route"] == "accept"
    assert update["decision"].overall is Resolution.ACCEPT
    assert update["decision"].items["sufficient"].accepted_value is True
    assert route_latch(update) == "accept"


def test_latch_update_escalates_noul_band(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    update = latch_update(
        {"answers": {"sufficient": {"type": "noul", "noul": 0.50}}},
        pack,
        policy,
    )
    assert update["route"] == "escalate"
    assert update["decision"].overall is Resolution.ESCALATE
    assert update["decision"].items["sufficient"].reason is Reason.NOUL_BAND
    assert route_latch(update) == "escalate"


def test_latch_update_pack_mismatch_escalates_every_question(
    rag_pack_path: Path,
) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    policy.pack_hash = "sha256:" + ("00" * 32)
    update = latch_update(
        {"answers": {"sufficient": {"type": "noul", "noul": 0.99}}},
        pack,
        policy,
    )
    assert update["route"] == "escalate"
    assert update["decision"].items["sufficient"].reason is Reason.PACK_MISMATCH
    for item in update["decision"].items.values():
        assert item.resolution is Resolution.ESCALATE
        assert item.reason is Reason.PACK_MISMATCH


def test_optional_store_appends_one_record(
    rag_pack_path: Path, rag_ok_path: Path, tmp_path: Path
) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    answers = json.loads(rag_ok_path.read_text(encoding="utf-8"))
    store = JsonlStore(tmp_path / "decisions.jsonl")
    before = set(tmp_path.iterdir())
    latch_update({"answers": answers}, pack, policy)
    assert set(tmp_path.iterdir()) == before
    update = latch_update({"answers": answers}, pack, policy, store=store)
    rows = list(store.read())
    assert len(rows) == 1
    assert rows[0].decision.overall is update["decision"].overall
    assert rows[0].answers == answers


def test_make_latch_node_closes_over_pack_and_policy(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    node = make_latch_node(pack, policy, store=None)
    update = node({"answers": {"sufficient": {"type": "noul", "noul": 0.96}}})
    assert update["route"] == "accept"
    assert route_latch(update) == "accept"
