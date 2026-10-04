from __future__ import annotations

import socket
from pathlib import Path

import pytest
import yaml

from openlatch.pack import Pack
from openlatch.policy import Policy
from openlatch.types import FitMeta, NoulRule, TauRule

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("OpenLatch tests must not use the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def rag_pack_path() -> Path:
    return FIXTURES / "packs" / "rag_sufficiency.v1.yaml"


@pytest.fixture
def rag_ok_path() -> Path:
    return FIXTURES / "answers" / "rag_ok.json"


def write_yaml(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def pack_from_mapping(data: dict) -> Pack:
    from openlatch.pack import load_pack

    return load_pack(data)


def policy_for(
    pack: Pack,
    *,
    rules: dict | None = None,
    model: str | None = None,
    escalate_all: bool = False,
    fit: FitMeta | None = None,
) -> Policy:
    if rules is None:
        rules = {}
        for qid, question in pack.questions.items():
            if question.type.value == "noul":
                rules[qid] = NoulRule(type="noul", tau_yes=0.95, tau_no=0.05)
            else:
                rules[qid] = TauRule(type=question.type.value, tau=0.95)
    return Policy(
        pack_id=pack.id,
        pack_version=pack.version,
        pack_hash=pack.hash,
        model=model or pack.model,
        on_failure="escalate",
        rules=rules,
        fit=fit,
        escalate_all=escalate_all,
    )


def rag_pack_yaml(
    *,
    instructions: str = "Does the passage directly answer the query?",
    comment: str | None = "# RAG sufficiency gate. Comments must not enter pack_hash.",
    model: str = "typesafe/jev-1.13",
    allow_unpinned: bool | None = None,
) -> str:
    header = f"{comment}\n" if comment else ""
    unlock = ""
    if allow_unpinned is not None:
        unlock = f"allow_unpinned: {'true' if allow_unpinned else 'false'}\n"
    return (
        f"{header}"
        "id: rag-sufficiency\n"
        "version: 1\n"
        f"model: {model}\n"
        f"{unlock}"
        "bundle: all_must_accept\n"
        "questions:\n"
        "  sufficient:\n"
        "    type: noul\n"
        f"    instructions: {yaml.dump(instructions, default_style='\"').strip()}\n"
        "    criteria:\n"
        '      true: "The passage contains a direct answer."\n'
        '      false: "The passage is related but does not answer."\n'
    )
