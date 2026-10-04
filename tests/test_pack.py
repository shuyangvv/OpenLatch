from __future__ import annotations

from pathlib import Path

import pytest

from openlatch.errors import PackError
from openlatch.pack import load_pack
from tests.conftest import rag_pack_yaml, write_yaml


def test_hash_changes_when_only_instruction_whitespace_changes(tmp_path: Path) -> None:
    a = load_pack(write_yaml(tmp_path / "a.yaml", rag_pack_yaml(instructions="hello")))
    b = load_pack(write_yaml(tmp_path / "b.yaml", rag_pack_yaml(instructions="hello ")))
    assert a.hash != b.hash
    assert a.hash.startswith("sha256:")
    assert len(a.hash) == len("sha256:") + 64


def test_hash_ignores_yaml_comments(tmp_path: Path) -> None:
    with_comment = load_pack(
        write_yaml(tmp_path / "a.yaml", rag_pack_yaml(comment="# changed comment"))
    )
    without_comment = load_pack(
        write_yaml(tmp_path / "b.yaml", rag_pack_yaml(comment=None))
    )
    assert with_comment.hash == without_comment.hash


def test_latest_model_is_rejected_unless_unlocked(tmp_path: Path) -> None:
    locked = write_yaml(
        tmp_path / "latest.yaml",
        rag_pack_yaml(model="typesafe/jev-latest"),
    )
    with pytest.raises(PackError):
        load_pack(locked)

    tilde = write_yaml(
        tmp_path / "tilde.yaml",
        rag_pack_yaml(model="~typesafe/jev-latest"),
    )
    with pytest.raises(PackError):
        load_pack(tilde)


def test_latest_model_loads_when_allow_unpinned(tmp_path: Path) -> None:
    path = write_yaml(
        tmp_path / "unlocked.yaml",
        rag_pack_yaml(model="typesafe/jev-latest", allow_unpinned=True),
    )
    pack = load_pack(path)
    assert pack.model == "typesafe/jev-latest"
    assert pack.allow_unpinned is True


def test_wire_questions_is_sdk_dict_not_a_request(rag_pack_path: Path) -> None:
    pack = load_pack(rag_pack_path)
    wired = pack.wire_questions()
    assert wired == {
        "sufficient": {
            "type": "noul",
            "instructions": "Does the passage directly answer the query?",
            "criteria": {
                "true": "The passage contains a direct answer.",
                "false": "The passage is related but does not answer.",
            },
        }
    }


def test_allow_unpinned_is_not_part_of_the_hash(tmp_path: Path) -> None:
    pinned = load_pack(write_yaml(tmp_path / "a.yaml", rag_pack_yaml()))
    flagged = load_pack(
        write_yaml(tmp_path / "b.yaml", rag_pack_yaml(allow_unpinned=False))
    )
    assert pinned.hash == flagged.hash
