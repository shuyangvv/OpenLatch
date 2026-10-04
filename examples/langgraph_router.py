"""Route accept vs escalate with openlatch.graph. Requires `pip install langgraph`. No HTTP leaves this process."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

from openlatch.graph import make_latch_node, route_latch
from openlatch.pack import load_pack
from openlatch.policy import load_policy

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:
    raise SystemExit(
        "install openlatch[langgraph] (or pip install langgraph) to run this example"
    ) from exc

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "tests/fixtures/packs/rag_sufficiency.v1.yaml"
ANSWERS = ROOT / "tests/fixtures/answers/rag_ok.json"
BAND = {"sufficient": {"type": "noul", "noul": 0.50}}


class LatchState(TypedDict, total=False):
    answers: dict[str, Any]
    model: str
    decision: Any
    route: str
    path: str


def use_passage(state: LatchState) -> dict[str, str]:
    return {"path": "auto path: use the passage"}


def review(state: LatchState) -> dict[str, str]:
    return {"path": "closed: escalate to a human"}


def main() -> None:
    pack = load_pack(PACK)
    policy = load_policy(
        {
            "pack_id": pack.id,
            "pack_version": pack.version,
            "pack_hash": pack.hash,
            "model": pack.model,
            "on_failure": "escalate",
            "rules": {
                "sufficient": {"type": "noul", "tau_yes": 0.95, "tau_no": 0.05}
            },
        },
        pack=pack,
    )
    graph = StateGraph(LatchState)
    graph.add_node("latch", make_latch_node(pack, policy))
    graph.add_node("use_passage", use_passage)
    graph.add_node("review", review)
    graph.add_edge(START, "latch")
    graph.add_conditional_edges(
        "latch",
        route_latch,
        {"accept": "use_passage", "escalate": "review"},
    )
    graph.add_edge("use_passage", END)
    graph.add_edge("review", END)
    app = graph.compile()

    accepted = json.loads(ANSWERS.read_text(encoding="utf-8"))
    for label, answers in (("accept", accepted), ("escalate", BAND)):
        result = app.invoke(
            {"answers": answers, "model": "typesafe/jev-1.13-20260917"}
        )
        print(label, result["route"], result["path"])
        print(result["decision"].model_dump_json(indent=2))


if __name__ == "__main__":
    main()
