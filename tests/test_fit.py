from __future__ import annotations

from pathlib import Path

import pytest

from openlatch.decide import decide
from openlatch.errors import NotEnoughLabels
from openlatch.fit import fit
from openlatch.log import JsonlStore, build_record
from openlatch.pack import load_pack
from openlatch.replay import replay
from openlatch.types import NoulRule, TauRule
from tests.conftest import policy_for


def _noul_labeled(pack, pairs: list[tuple[float, bool]]):
    policy = policy_for(
        pack,
        rules={"sufficient": NoulRule(type="noul", tau_yes=0.95, tau_no=0.05)},
    )
    records = []
    for noul, yes in pairs:
        answers = {"sufficient": {"type": "noul", "noul": noul}}
        records.append(
            build_record(
                decide(answers, pack, policy),
                answers,
                model=pack.model,
                label={"sufficient": yes},
            )
        )
    return records


def _choice_labeled(pack, rows: list[tuple[float, str, str]]):
    policy = policy_for(pack, rules={"label": TauRule(type="choice", tau=0.0)})
    records = []
    for confidence, choice, label in rows:
        answers = {
            "label": {
                "type": "choice",
                "choice": choice,
                "confidence": confidence,
                "probabilities": {
                    choice: confidence,
                    ("no" if choice == "yes" else "yes"): round(1.0 - confidence, 4),
                },
            }
        }
        records.append(
            build_record(
                decide(answers, pack, policy),
                answers,
                model=pack.model,
                label={"label": label},
            )
        )
    return records


def _choice_pack() -> dict:
    return {
        "id": "choice-pack",
        "version": 1,
        "model": "typesafe/jev-1.13",
        "bundle": "all_must_accept",
        "questions": {
            "label": {
                "type": "choice",
                "instructions": "supported?",
                "options": ["yes", "no"],
            }
        },
    }


def test_fit_rejects_fewer_than_min_n_labels(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    records = _noul_labeled(pack, [(0.99, True)] * 20)
    with pytest.raises(NotEnoughLabels) as exc:
        fit(records, pack, min_n=50)
    assert exc.value.n == 20
    assert exc.value.min_n == 50


def test_fit_picks_loosest_qualified_tau_when_high_confidence_is_correct() -> None:
    pack = load_pack(_choice_pack())
    rows = [(0.99, "yes", "yes")] * 35 + [(0.82, "yes", "yes")] * 15
    policy = fit(_choice_labeled(pack, rows), pack, min_n=50)
    rule = policy.rules["label"]
    assert rule.type == "choice"
    assert rule.tau == 0.80
    assert policy.escalate_all is False
    assert policy.fit is not None
    assert policy.fit.qualified is True
    assert policy.fit.n == 50
    assert policy.fit.rule == "lcb-0.02"
    assert policy.fit.order == "single"


def test_fit_escalates_all_when_high_confidence_is_usually_wrong() -> None:
    pack = load_pack(_choice_pack())
    rows = [(0.99, "yes", "no")] * 50
    policy = fit(_choice_labeled(pack, rows), pack, min_n=50)
    assert policy.escalate_all is True
    assert policy.fit is not None
    assert policy.fit.qualified is False
    assert "label" in policy.rules


README_PACK_HASH = (
    "sha256:01cade1c40c5cabe1e0f8406b47fc20026307d5cb4816e6ddaeb0b3db9ad92de"
)


def test_public_fixture_fit_replay_matches_readme_numbers() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    pack = load_pack(fixtures / "packs" / "rag_sufficiency.v1.yaml")
    records = list(JsonlStore(fixtures / "logs" / "labeled.jsonl").read())
    policy = fit(records, pack, min_n=50)
    report = replay(records, policy, pack)
    assert pack.hash == README_PACK_HASH
    assert policy.rules["sufficient"].tau_yes == 0.80
    assert policy.rules["sufficient"].tau_no == 0.20
    assert policy.fit is not None
    assert policy.fit.n == 50
    assert policy.fit.rule == "lcb-0.02"
    assert policy.fit.qualified is True
    assert policy.fit.order == "single"
    assert report.n == 50
    assert report.accept_rate_old == 0.9
    assert report.accept_rate_new == 1.0
    assert report.flipped_to_escalate == 0
    assert report.flipped_to_accept == 5
    assert report.label_conflicts_new == 0


def test_fit_writes_concrete_model_when_pack_is_unpinned() -> None:
    pack = load_pack(
        {
            "id": "rag-sufficiency",
            "version": 1,
            "model": "typesafe/jev-latest",
            "allow_unpinned": True,
            "bundle": "all_must_accept",
            "questions": {
                "sufficient": {
                    "type": "noul",
                    "instructions": "answered?",
                    "criteria": {"true": "yes", "false": "no"},
                }
            },
        }
    )
    records = _noul_labeled(
        pack, [(0.97, True)] * 40 + [(0.82, True)] * 5 + [(0.03, False)] * 5
    )
    for record in records:
        record.model = "typesafe/jev-1.13-20260917"
    policy = fit(records, pack, min_n=50)
    assert policy.model == "typesafe/jev-1.13-20260917"
    assert policy.rules["sufficient"].tau_yes == 0.80
    assert policy.rules["sufficient"].tau_no == 0.20
