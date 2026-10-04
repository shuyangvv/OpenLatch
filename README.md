# OpenLatch

<p align="center">
  <strong>English</strong> · <a href="./README.zh-CN.md">简体中文</a>
</p>

**Fail-closed decision layer for System One.** A typed model returns probabilities; OpenLatch returns `accept` or `escalate`. Rubrics, model pins, and thresholds are committed policy. Changing a gate replays old logs with no new inference.

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-50%20passed-2ea44f)](tests/)

</div>

OpenLatch is not a Jev client and does not open a network connection. The caller obtains `answers` from an official SDK, then asks OpenLatch whether the automatic path may proceed. A missing policy, a hash mismatch, a type error, an unpinned `jev-latest` model, or a backend failure escalates the whole bundle. There is no default threshold.

```text
official SDK ── answers ──► openlatch.decide ──► accept   ──► automatic path
                             │                  escalate ──► human / caller fallback
                             ▼
                          JSONL log ── attach_label
                             │
                  fit ──► Policy ── replay ──► coverage / conflict report
```

## Installation

```bash
python -m pip install openlatch
```

Python 3.10 or newer. The runtime depends only on `pydantic>=2` and `PyYAML`. Optional extras: `openlatch[cli]` (the `openlatch` command), `openlatch[dev]` (pytest and the CLI), `openlatch[langgraph]` (the `examples/langgraph_router.py` demo). The library does not depend on `httpx`, `typesafe-sdk`, `openai`, `langchain`, or `fastapi`. Continuous integration does not need an API key.

With [uv](https://docs.astral.sh/uv/), run `uv add openlatch` in a uv project or `uv pip install openlatch` in a virtual environment. A source checkout and platform-specific commands are in [Installation details](#installation-details).

## Quickstart

The public fixture pack asks whether a passage answers a query (`noul`). Load that pack, bind a handwritten policy to its hash, and decide on recorded answers. No HTTP leaves the process.

```python
import json
from pathlib import Path

from openlatch import decide, load_pack, load_policy

root = Path("tests/fixtures")
pack = load_pack(root / "packs" / "rag_sufficiency.v1.yaml")
policy = load_policy(
    {
        "pack_id": pack.id,
        "pack_version": pack.version,
        "pack_hash": pack.hash,
        "model": pack.model,
        "on_failure": "escalate",
        "rules": {"sufficient": {"type": "noul", "tau_yes": 0.95, "tau_no": 0.05}},
    },
    pack=pack,
)
answers = json.loads((root / "answers" / "rag_ok.json").read_text())
decision = decide(answers, pack, policy, model="typesafe/jev-1.13-20260917")
print(decision.overall.value)  # accept
print(decision.items["sufficient"].accepted_value)  # True
```

`pack.wire_questions()` converts the YAML questions into the dict an official SDK expects. It does not send a request. Production code looks like this:

```python
from typesafe_sdk import TypeSafeClient
from openlatch import decide, load_pack, load_policy
from openlatch.log import JsonlStore, build_record
from openlatch.types import Resolution

pack = load_pack("packs/rag_sufficiency.v1.yaml")
policy = load_policy("policies/rag_sufficiency.v1.json", pack=pack)
raw = client.system_one(model=pack.model, state=state, questions=pack.wire_questions())
decision = decide(raw.answers, pack, policy, model=raw.model)
store = JsonlStore("logs/decisions.jsonl")
store.append(build_record(decision, raw.answers, usage=raw.usage))
if decision.overall is Resolution.ACCEPT:
    use(raw.answers)
else:
    review_queue.push(decision)
```

The same `decide` call is what recall filters, uncertain-branch routers, and translation-adequacy gates should share. Hand-written `if confidence > 0.8` checks do not belong in those services. `openlatch.graph` exposes that call as a node: the caller puts `answers` on graph state, `make_latch_node` writes `decision` and `route`, and `route_latch` branches `accept` vs `escalate`. The node does not call a model and does not open a network connection.

```python
from openlatch.graph import make_latch_node, route_latch
from langgraph.graph import END, START, StateGraph

graph = StateGraph(dict)
graph.add_node("latch", make_latch_node(pack, policy))
graph.add_edge(START, "latch")
graph.add_conditional_edges(
    "latch",
    route_latch,
    {"accept": "use_passage", "escalate": "review"},
)
```

Run the recorded fixture from a clone:

```bash
python examples/rag_filter.py
python examples/langgraph_router.py  # needs openlatch[langgraph]
```

## Objects

| Object | Format | Role |
|---|---|---|
| Pack | YAML | Pinned rubric: `id`, `version`, `model`, and questions |
| Policy | JSON | Pinned thresholds. Must cite the pack's `pack_hash` |
| Log | JSONL | Audit trail. Stores a `state_digest` by default, not the raw state |

`pack_hash` is SHA-256 of `{id, version, model, bundle, questions}` encoded as RFC 8785-style canonical JSON, written `sha256:<hex>`. YAML comments are not hashed. Loading a pack whose model is `jev-latest` (or `~typesafe/jev-latest`) raises `PackError` unless the pack sets `allow_unpinned: true`. A policy produced by `fit` still records the concrete model string from the log, even when the pack was unpinned.

`on_failure` may only be `"escalate"`. A handwritten policy without a `fit` block is valid; `decide` does not require one. `fit` always writes that block.

A log line does not keep the original `state` unless the caller passes `store_state=True` to `build_record`. Labels are attached later with `JsonlStore.attach_label(id, {question_id: value})`. In v1 that rewrite reads the whole file, updates one row, and replaces the file atomically. Large stores should wait for a sidecar in v1.1; a second storage engine is out of scope.

## Decision

`decide` is a pure function. It does not write to disk. Callers or `JsonlStore.append` persist the result. `replay` must call this same function; the suite forbids a second copy of the threshold logic.

Evaluation order, shortest path first:

1. `policy.pack_hash != pack.hash` — every question is `pack_mismatch`; the bundle escalates.
2. A `model` argument that does not match the policy pin — `model_mismatch`. A dated suffix is allowed: `typesafe/jev-1.13-20260917` matches `typesafe/jev-1.13`.
3. A missing question is `missing_answer`. A type error, an out-of-range noul, a missing confidence, or probability keys that do not match the pack is `type_mismatch`. OpenLatch does not clamp or invent `0.0`.
4. Otherwise the question signal is compared to its rule:
   - choice / score: accept when `signal >= tau`, otherwise `below_tau`.
   - noul: accept yes when `>= tau_yes`, accept no when `<= tau_no`, otherwise `noul_band`.
5. An empty `answers` dict or a payload containing `__error__` is `backend_failure`.

`bundle: all_must_accept` (the default) escalates the whole decision if any question escalates. `bundle: per_question` still reports that summary on `overall`; callers that want per-question consumption should read `decision.items`.

A policy with `escalate_all: true` keeps its rules but `decide` escalates every question with reason `escalate_all`. OpenLatch does not call a second model and does not choose where escalations go. The caller reviews the item or supplies its own fallback.

## Replay and fit

`replay(records, policy, pack)` runs `decide` on each stored `answers` object and compares the new decision to the one on disk.

| Field | Meaning |
|---|---|
| `n` | Records replayed |
| `accept_rate_old` / `accept_rate_new` | Fraction of records whose `overall` is `accept` |
| `flipped_to_escalate` / `flipped_to_accept` | Records whose `overall` changed |
| `label_conflicts_new` | Human label present, new decision accepts, accepted value disagrees |
| `estimated_cost_if_refit` | Sum of `usage.cost` on records the new policy still accepts; `None` if no usage is present. Escalation cost is not estimated |

The invariant: replaying a log under the policy that produced it yields a field-for-field match on every question. Raising τ only needs `replay`. Continuous integration does not need a model key.

`fit` selects thresholds from labeled records. The human label is the strong referee. A cascade accept that matches the label, or any escalate, counts as correct relative to that referee. A cascade accept that disagrees is an error. The one-sided 95% lower confidence bound on the mean of those residuals must be at least `lcb_margin` (default `-0.02`). Among qualified thresholds, `fit` keeps the one with the most accepts; ties take the larger τ. If none qualify, the policy sets `escalate_all: true`.

noul scans the published grid as pairs `(1 - τ, τ)`. Each question in a pack is fitted independently, then composed into one policy. Fewer than `min_n` labels (default 50) raises `NotEnoughLabels`. If a record includes `answers_reversed`, `fit` averages the two signals before selecting τ and reports `order="bilateral"`. Otherwise it reports `order="single"` and does not pretend to have run a two-sided protocol.

## Command line

`openlatch[cli]` installs an `openlatch` command for local checks. Production callers should use the Python API.

```bash
openlatch hash --pack packs/rag.yaml
openlatch decide --pack p.yaml --policy pol.json --answers a.json
openlatch replay --log logs.jsonl --pack p.yaml --policy pol.json
openlatch fit --log logs.jsonl --pack p.yaml --out pol.json --min-n 50
```

Configuration errors and `NotEnoughLabels` exit 2. `replay` prints diffs when a new policy disagrees with a stored decision and still exits 0, because that is the expected result of changing τ. Pass `--assert-unchanged` to exit 1 on any flip; that flag is the continuous-integration gate.

## Installation details

Python 3.10 or newer. If you already have a virtual environment, install the checkout with that environment's interpreter:

```bash
python -m pip install -e ".[dev]"
python -I -c "import openlatch; print(openlatch.__version__)"
```

`-I` excludes the current directory from the import path, so a local source tree cannot mask a missing installation.

**macOS / Linux**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -I -c "import openlatch; print(openlatch.__version__)"
```

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -I -c "import openlatch; print(openlatch.__version__)"
```

**Install with uv**

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
```

If the application is a uv project:

```bash
uv add openlatch
uv run python -I -c "import openlatch; print(openlatch.__version__)"
```

**From GitHub**

```bash
python -m pip install "git+https://github.com/shuyangvv/OpenLatch.git"
```

**Troubleshooting**

- **`ModuleNotFoundError: No module named 'openlatch'`:** run install and the script with the same virtual environment's Python executable. Select that interpreter in the editor as well.
- **`PackError` on `jev-latest`:** pin a dated model, or set `allow_unpinned: true` on the pack. OpenLatch will not silently accept an unpinned alias.
- **`PolicyError` on load:** `on_failure` is not `"escalate"`, noul thresholds are unordered, or the policy was bound to a pack whose hash does not match.
- **`NotEnoughLabels`:** `fit` received fewer labeled rows than `--min-n` / `min_n`.

## Reproducible fit and replay

The public fixtures are `tests/fixtures/packs/rag_sufficiency.v1.yaml` and fifty labeled rows in `tests/fixtures/logs/labeled.jsonl`. The stored decisions were produced by a handwritten policy at `tau_yes=0.95` / `tau_no=0.05`. From the repository root:

```bash
python examples/fit_from_log.py
```

Stable figures (`fitted_at` is the only field that changes):

| Field | Value |
|---|---|
| `pack_hash` | `sha256:01cade1c40c5cabe1e0f8406b47fc20026307d5cb4816e6ddaeb0b3db9ad92de` |
| fitted `tau_yes` / `tau_no` | `0.80` / `0.20` |
| `fit.n` | `50` |
| `fit.rule` | `lcb-0.02` |
| `fit.qualified` | `true` |
| `fit.order` | `single` |
| `accept_rate_old` → `accept_rate_new` | `0.9` → `1.0` |
| `flipped_to_escalate` / `flipped_to_accept` | `0` / `5` |
| `label_conflicts_new` | `0` |
| `estimated_cost_if_refit` | `0.00085` |

`tests/test_fit.py` holds these numbers. A change to the fixture, the hash, or the LCB rule fails that test.

## Scope

v1 is a library, a JSONL store, a CLI, and an optional LangGraph node contract (`openlatch.graph`, not in the core export list). The node still calls `decide`; it is not a second copy of the threshold logic.

Out of scope:

- HTTP, retries, or rate limits (those belong to the official SDK)
- A built-in strong referee, explanation generator, or call to GPT
- MCP servers, FastAPI middleware, or dashboards
- Postgres, multi-tenancy, or a second storage engine
- A default threshold, or silent acceptance of `jev-latest`
- Preset packs for code review or support routing (those are rubrics, not this library)

v1.1 may add bilateral `answers_reversed` as a first-class path, a sidecar label store, and an optional `resolve(fallback=...)` helper. The helper already exists as `openlatch.extras.resolve` and is not part of the core export list.

## License

[MIT](LICENSE)
