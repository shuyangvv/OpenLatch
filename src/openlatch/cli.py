from __future__ import annotations

import json
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

import typer

from openlatch.decide import decide
from openlatch.errors import OpenLatchError
from openlatch.fit import fit
from openlatch.log import JsonlStore
from openlatch.pack import load_pack
from openlatch.policy import load_policy
from openlatch.replay import replay

F = TypeVar("F", bound=Callable[..., Any])

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _catch_config(func: F) -> F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except OpenLatchError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(2) from exc

    return wrapper  # type: ignore[return-value]


@app.command("hash")
@_catch_config
def hash_cmd(pack: Path = typer.Option(..., "--pack")) -> None:
    typer.echo(load_pack(pack).hash)


@app.command("decide")
@_catch_config
def decide_cmd(
    pack: Path = typer.Option(..., "--pack"),
    policy: Path = typer.Option(..., "--policy"),
    answers: Path = typer.Option(..., "--answers"),
) -> None:
    loaded_pack = load_pack(pack)
    loaded_policy = load_policy(policy, pack=loaded_pack)
    payload = json.loads(answers.read_text(encoding="utf-8"))
    decision = decide(payload, loaded_pack, loaded_policy)
    typer.echo(decision.model_dump_json())


@app.command("replay")
@_catch_config
def replay_cmd(
    log: Path = typer.Option(..., "--log"),
    pack: Path = typer.Option(..., "--pack"),
    policy: Path = typer.Option(..., "--policy"),
    assert_unchanged: bool = typer.Option(False, "--assert-unchanged"),
) -> None:
    loaded_pack = load_pack(pack)
    loaded_policy = load_policy(policy)
    report = replay(list(JsonlStore(log).read()), loaded_policy, loaded_pack)
    for item in report.records:
        if item.old.overall != item.new.overall:
            typer.echo(
                f"{item.id}: {item.old.overall.value} -> {item.new.overall.value}",
                err=True,
            )
        for question_id, old_item in item.old.items.items():
            new_item = item.new.items.get(question_id)
            if new_item is None or old_item.model_dump() == new_item.model_dump():
                continue
            typer.echo(
                f"{item.id}.{question_id}: {old_item.reason.value} -> {new_item.reason.value}",
                err=True,
            )
    typer.echo(report.model_dump_json())
    if assert_unchanged and (
        report.flipped_to_escalate or report.flipped_to_accept
    ):
        raise typer.Exit(1)


@app.command("fit")
@_catch_config
def fit_cmd(
    log: Path = typer.Option(..., "--log"),
    pack: Path = typer.Option(..., "--pack"),
    out: Path = typer.Option(..., "--out"),
    min_n: int = typer.Option(50, "--min-n"),
) -> None:
    loaded_pack = load_pack(pack)
    policy = fit(list(JsonlStore(log).read()), loaded_pack, min_n=min_n)
    out.write_text(policy.model_dump_json(indent=2) + "\n", encoding="utf-8")


def main() -> None:
    app()
