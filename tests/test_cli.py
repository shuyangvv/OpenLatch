from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from openlatch.cli import app
from openlatch.decide import decide
from openlatch.log import JsonlStore, build_record
from openlatch.pack import load_pack
from openlatch.types import NoulRule
from tests.conftest import policy_for, rag_pack_yaml, write_yaml

runner = CliRunner()


def test_hash_prints_pack_hash(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    result = runner.invoke(app, ["hash", "--pack", str(rag_pack_path)])
    assert result.exit_code == 0
    assert result.stdout.strip() == pack.hash


def test_decide_cli_prints_accept(rag_pack_path: Path, rag_ok_path: Path, tmp_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        policy_for(
            pack,
            rules={"sufficient": NoulRule(type="noul", tau_yes=0.95, tau_no=0.05)},
        ).model_dump_json(),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        [
            "decide",
            "--pack",
            str(rag_pack_path),
            "--policy",
            str(policy_path),
            "--answers",
            str(rag_ok_path),
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["overall"] == "accept"


def test_latest_pack_cli_exits_2(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "latest.yaml", rag_pack_yaml(model="jev-latest"))
    result = runner.invoke(app, ["hash", "--pack", str(path)])
    assert result.exit_code == 2


def test_fit_cli_exits_2_when_labels_are_short(rag_pack_path: Path, tmp_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    policy = policy_for(pack)
    store = JsonlStore(tmp_path / "log.jsonl")
    store.append(
        build_record(
            decide({"sufficient": {"type": "noul", "noul": 0.96}}, pack, policy),
            {"sufficient": {"type": "noul", "noul": 0.96}},
            label={"sufficient": True},
        )
    )
    result = runner.invoke(
        app,
        [
            "fit",
            "--log",
            str(store.path),
            "--pack",
            str(rag_pack_path),
            "--out",
            str(tmp_path / "out.json"),
            "--min-n",
            "50",
        ],
    )
    assert result.exit_code == 2


def test_replay_assert_unchanged_exits_1_on_flip(
    rag_pack_path: Path, tmp_path: Path
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
    log_path = tmp_path / "log.jsonl"
    store = JsonlStore(log_path)
    store.append(
        build_record(
            decide({"sufficient": {"type": "noul", "noul": 0.96}}, pack, loose),
            {"sufficient": {"type": "noul", "noul": 0.96}},
        )
    )
    policy_path = tmp_path / "tight.json"
    policy_path.write_text(tight.model_dump_json(), encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "replay",
            "--log",
            str(log_path),
            "--pack",
            str(rag_pack_path),
            "--policy",
            str(policy_path),
            "--assert-unchanged",
        ],
    )
    assert result.exit_code == 1
    default = runner.invoke(
        app,
        [
            "replay",
            "--log",
            str(log_path),
            "--pack",
            str(rag_pack_path),
            "--policy",
            str(policy_path),
        ],
    )
    assert default.exit_code == 0
