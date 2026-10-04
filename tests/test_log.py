from __future__ import annotations

from pathlib import Path

from openlatch.decide import decide
from openlatch.log import JsonlStore, build_record
from openlatch.pack import load_pack
from openlatch.types import NoulRule
from tests.conftest import policy_for


def test_append_read_roundtrip_without_storing_state(rag_pack_path: Path, tmp_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(
        pack,
        rules={"sufficient": NoulRule(type="noul", tau_yes=0.95, tau_no=0.05)},
    )
    answers = {"sufficient": {"type": "noul", "noul": 0.96}}
    decision = decide(answers, pack, policy)
    record = build_record(
        decision,
        answers,
        state={"query": "secret business text", "passage": "..."},
        usage={"input_tokens": 412, "cost": 0.000017},
    )
    assert record.state is None
    assert record.state_digest is not None
    assert record.state_digest.startswith("sha256:")

    store = JsonlStore(tmp_path / "log.jsonl")
    store.append(record)
    loaded = list(store.read())
    assert len(loaded) == 1
    assert loaded[0].id == record.id
    assert loaded[0].decision.overall == decision.overall
    assert loaded[0].state is None


def test_store_state_opt_in_keeps_the_raw_state(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    decision = decide({"sufficient": {"type": "noul", "noul": 0.96}}, pack, policy)
    state = {"query": "keep me"}
    record = build_record(decision, {"sufficient": {"type": "noul", "noul": 0.96}}, state=state, store_state=True)
    assert record.state == state


def test_attach_label_rewrites_one_row(rag_pack_path: Path, tmp_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    first = build_record(
        decide({"sufficient": {"type": "noul", "noul": 0.96}}, pack, policy),
        {"sufficient": {"type": "noul", "noul": 0.96}},
    )
    second = build_record(
        decide({"sufficient": {"type": "noul", "noul": 0.02}}, pack, policy),
        {"sufficient": {"type": "noul", "noul": 0.02}},
    )
    store = JsonlStore(tmp_path / "log.jsonl")
    store.append(first)
    store.append(second)
    store.attach_label(first.id, {"sufficient": True})
    rows = list(store.read())
    assert rows[0].label == {"sufficient": True}
    assert rows[1].label is None
    assert rows[1].id == second.id
