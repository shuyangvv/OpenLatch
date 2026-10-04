from __future__ import annotations

from pathlib import Path

import pytest

from openlatch.errors import PolicyError
from openlatch.pack import load_pack
from openlatch.policy import load_policy
from tests.conftest import policy_for


def test_on_failure_must_be_escalate(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(
        '{"pack_id":"x","pack_version":1,"pack_hash":"sha256:aa",'
        '"model":"typesafe/jev-1.13","on_failure":"accept",'
        '"rules":{"sufficient":{"type":"noul","tau_yes":0.9,"tau_no":0.1}}}',
        encoding="utf-8",
    )
    with pytest.raises(PolicyError):
        load_policy(path)


def test_noul_requires_ordered_tau_pair() -> None:
    with pytest.raises(PolicyError):
        load_policy(
            {
                "pack_id": "rag-sufficiency",
                "pack_version": 1,
                "pack_hash": "sha256:aa",
                "model": "typesafe/jev-1.13",
                "on_failure": "escalate",
                "rules": {
                    "sufficient": {"type": "noul", "tau_yes": 0.2, "tau_no": 0.8}
                },
            }
        )


def test_handwritten_policy_without_fit_is_legal(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    loaded = load_policy(policy.model_dump(mode="json"), pack=pack)
    assert loaded.fit is None
    assert loaded.pack_hash == pack.hash


def test_binding_to_the_wrong_pack_hash_raises(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    payload = policy_for(pack).model_dump(mode="json")
    payload["pack_hash"] = "sha256:" + ("ab" * 32)
    with pytest.raises(PolicyError):
        load_policy(payload, pack=pack)
