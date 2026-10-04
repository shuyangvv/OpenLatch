from __future__ import annotations

import json
from pathlib import Path

from openlatch.decide import decide
from openlatch.pack import load_pack
from openlatch.types import NoulRule, Reason, Resolution, TauRule
from tests.conftest import policy_for


def _choice_pack() -> dict:
    return {
        "id": "choice-pack",
        "version": 1,
        "model": "typesafe/jev-1.13",
        "bundle": "all_must_accept",
        "questions": {
            "label": {
                "type": "choice",
                "instructions": "Is the claim supported?",
                "options": ["yes", "no"],
            }
        },
    }


def test_pack_hash_mismatch_escalates_every_question(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    policy.pack_hash = "sha256:" + ("00" * 32)
    decision = decide({"sufficient": {"type": "noul", "noul": 0.99}}, pack, policy)
    assert decision.overall is Resolution.ESCALATE
    assert decision.items["sufficient"].reason is Reason.PACK_MISMATCH
    assert decision.items["sufficient"].resolution is Resolution.ESCALATE


def test_missing_question_escalates_and_fails_the_bundle(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    decision = decide({"other": {"type": "noul", "noul": 0.99}}, pack, policy)
    assert decision.items["sufficient"].reason is Reason.MISSING_ANSWER
    assert decision.overall is Resolution.ESCALATE


def test_type_mismatch_escalates_the_question(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    decision = decide(
        {"sufficient": {"type": "choice", "choice": "yes", "confidence": 0.99}},
        pack,
        policy,
    )
    assert decision.items["sufficient"].reason is Reason.TYPE_MISMATCH
    assert decision.overall is Resolution.ESCALATE


def test_choice_just_below_tau_is_below_tau() -> None:
    pack = load_pack(_choice_pack())
    policy = policy_for(
        pack,
        rules={"label": TauRule(type="choice", tau=0.95)},
    )
    decision = decide(
        {
            "label": {
                "type": "choice",
                "choice": "yes",
                "confidence": 0.94,
                "probabilities": {"yes": 0.94, "no": 0.06},
            }
        },
        pack,
        policy,
    )
    item = decision.items["label"]
    assert item.reason is Reason.BELOW_TAU
    assert item.resolution is Resolution.ESCALATE
    assert item.signal == 0.94
    assert item.threshold == 0.95
    assert item.accepted_value is None


def test_noul_in_the_band_escalates(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(
        pack,
        rules={"sufficient": NoulRule(type="noul", tau_yes=0.95, tau_no=0.05)},
    )
    decision = decide({"sufficient": {"type": "noul", "noul": 0.50}}, pack, policy)
    item = decision.items["sufficient"]
    assert item.reason is Reason.NOUL_BAND
    assert item.resolution is Resolution.ESCALATE
    assert item.thresholds == {"tau_yes": 0.95, "tau_no": 0.05}


def test_noul_accepts_yes_and_no(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(
        pack,
        rules={"sufficient": NoulRule(type="noul", tau_yes=0.95, tau_no=0.05)},
    )
    yes = decide({"sufficient": {"type": "noul", "noul": 0.96}}, pack, policy)
    no = decide({"sufficient": {"type": "noul", "noul": 0.02}}, pack, policy)
    assert yes.overall is Resolution.ACCEPT
    assert yes.items["sufficient"].accepted_value is True
    assert yes.items["sufficient"].reason is Reason.ACCEPTED
    assert no.overall is Resolution.ACCEPT
    assert no.items["sufficient"].accepted_value is False
    assert no.items["sufficient"].reason is Reason.ACCEPTED


def test_dated_model_suffix_matches_pinned_prefix(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack, model="typesafe/jev-1.13")
    decision = decide(
        {"sufficient": {"type": "noul", "noul": 0.96}},
        pack,
        policy,
        model="typesafe/jev-1.13-20260917",
    )
    assert decision.overall is Resolution.ACCEPT


def test_unrelated_model_is_a_mismatch(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack, model="typesafe/jev-1.13")
    decision = decide(
        {"sufficient": {"type": "noul", "noul": 0.96}},
        pack,
        policy,
        model="typesafe/jev-1.14",
    )
    assert decision.items["sufficient"].reason is Reason.MODEL_MISMATCH
    assert decision.overall is Resolution.ESCALATE


def test_backend_failure_from_empty_or_error_payload(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    empty = decide({}, pack, policy)
    errored = decide({"__error__": "timeout"}, pack, policy)
    assert empty.items["sufficient"].reason is Reason.BACKEND_FAILURE
    assert errored.items["sufficient"].reason is Reason.BACKEND_FAILURE
    assert empty.overall is Resolution.ESCALATE


def test_escalate_all_policy_does_not_accept(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack, escalate_all=True)
    decision = decide({"sufficient": {"type": "noul", "noul": 0.99}}, pack, policy)
    assert decision.items["sufficient"].reason is Reason.ESCALATE_ALL
    assert decision.overall is Resolution.ESCALATE


def test_extra_answer_fields_are_ignored(rag_ok_path: Path, rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(
        pack,
        rules={"sufficient": NoulRule(type="noul", tau_yes=0.95, tau_no=0.05)},
    )
    answers = json.loads(rag_ok_path.read_text(encoding="utf-8"))
    decision = decide(answers, pack, policy)
    assert decision.overall is Resolution.ACCEPT


def test_decide_does_not_write_disk(rag_pack_path: Path, tmp_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    before = set(tmp_path.iterdir())
    decide({"sufficient": {"type": "noul", "noul": 0.96}}, pack, policy)
    assert set(tmp_path.iterdir()) == before
