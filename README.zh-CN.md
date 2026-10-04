# OpenLatch

<p align="center">
  <a href="./README.md">English</a> · <strong>简体中文</strong>
</p>

**System One 的失败即关闭决议层。** 带类型的模型给出概率，OpenLatch 给出 `accept` 或 `escalate`。量规、模型钉死值和阈值写成可提交的政策。改门闩只需回放旧日志，不必重新推理。

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-45%20passed-2ea44f)](tests/)

</div>

OpenLatch 不是 Jev 客户端，也不会发起网络连接。调用方用官方 SDK 取得 `answers`，再询问 OpenLatch 自动路径是否可以继续。缺少政策、哈希不一致、类型错误、未解锁的 `jev-latest`，或后端失败，都会使整单升级。没有默认阈值。

```text
官方 SDK ── answers ──► openlatch.decide ──► accept   ──► 自动路径
                         │                  escalate ──► 人审 / 调用方回退
                         ▼
                      JSONL 日志 ── attach_label
                         │
              fit ──► Policy ── replay ──► 覆盖率 / 冲突报告
```

## 安装

```bash
python -m pip install openlatch
```

需要 Python 3.10 或更高版本。运行时只依赖 `pydantic>=2` 和 `PyYAML`。可选 extra：`openlatch[cli]`（`openlatch` 命令）、`openlatch[dev]`（pytest 与 CLI）。本库不依赖 `httpx`、`typesafe-sdk`、`openai`、`langchain` 或 `fastapi`。持续集成不需要 API key。

若使用 [uv](https://docs.astral.sh/uv/)，在 uv 项目中执行 `uv add openlatch`，或在虚拟环境中执行 `uv pip install openlatch`。源码安装与各平台命令见 [安装细节](#安装细节)。

## 快速开始

公开 fixture 量规询问一段文本是否直接回答了查询（`noul`）。加载该 Pack，把一份手写政策绑定到它的哈希，再对已录制的 answers 做判定。过程中不会发出 HTTP 请求。

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

`pack.wire_questions()` 把 YAML 中的问题转成官方 SDK 需要的字典，不会发请求。生产代码通常如下：

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

召回过滤、不确定分支路由、译文充分性门闩应共用这一次 `decide`。这些服务里不应再手写 `if confidence > 0.8`。

在仓库克隆中运行已录制的 fixture：

```bash
python examples/rag_filter.py
```

## 对象

| 对象 | 格式 | 作用 |
|---|---|---|
| Pack | YAML | 钉死的量规：`id`、`version`、`model` 与问题 |
| Policy | JSON | 钉死的阈值。必须引用 Pack 的 `pack_hash` |
| Log | JSONL | 审计日志。默认只写 `state_digest`，不保存 state 原文 |

`pack_hash` 是 `{id, version, model, bundle, questions}` 按 RFC 8785 风格规范 JSON 编码后的 SHA-256，写成 `sha256:<hex>`。YAML 注释不进入哈希。若 Pack 的模型为 `jev-latest`（或 `~typesafe/jev-latest`），除非显式设置 `allow_unpinned: true`，否则加载时抛出 `PackError`。即使 Pack 未钉死版本，`fit` 写出的政策仍会写入日志里的具体模型字符串。

`on_failure` 只能是 `"escalate"`。没有 `fit` 块的手写政策合法，`decide` 不要求该块。`fit` 总会写入该块。

除非调用方在 `build_record` 中传入 `store_state=True`，否则日志行不保存原始 `state`。标签稍后用 `JsonlStore.attach_label(id, {question_id: value})` 补上。v1 的实现会读入整个文件、改一行并以原子方式替换。记录量大时应等到 v1.1 的 sidecar；第二个存储引擎不在范围内。

## 判定

`decide` 是纯函数，不写磁盘。由调用方或 `JsonlStore.append` 负责落盘。`replay` 必须调用同一函数；测试禁止再实现一套阈值逻辑。

判定顺序，短路径在前：

1. `policy.pack_hash != pack.hash` — 每个问题记为 `pack_mismatch`，整单升级。
2. 传入的 `model` 与政策钉死前缀不一致 — `model_mismatch`。允许日期后缀：`typesafe/jev-1.13-20260917` 匹配 `typesafe/jev-1.13`。
3. 缺问记为 `missing_answer`。类型错误、越界 noul、缺少 confidence，或概率键与 Pack 对不上，记为 `type_mismatch`。OpenLatch 不会夹紧数值，也不会填上 `0.0`。
4. 否则将该问的信号与规则比较：
   - choice / score：`signal >= tau` 则接受，否则 `below_tau`。
   - noul：`>= tau_yes` 接受为 yes，`<= tau_no` 接受为 no，否则 `noul_band`。
5. 空的 `answers` 或含 `__error__` 的载荷记为 `backend_failure`。

`bundle: all_must_accept`（默认）在任一问题升级时升级整单。`bundle: per_question` 仍把该摘要写在 `overall` 上；按问消费的调用方应读取 `decision.items`。

政策若带 `escalate_all: true`，规则仍保留，但 `decide` 会以原因 `escalate_all` 升级每一问。OpenLatch 不调用第二个模型，也不指定升级去向。由调用方人审，或自行提供回退。

## 回放与拟合

`replay(records, policy, pack)` 对每条已存 `answers` 再跑 `decide`，并与磁盘上的旧决议比较。

| 字段 | 含义 |
|---|---|
| `n` | 回放条数 |
| `accept_rate_old` / `accept_rate_new` | `overall` 为 `accept` 的比例 |
| `flipped_to_escalate` / `flipped_to_accept` | `overall` 发生变化的条数 |
| `label_conflicts_new` | 存在人标、新决议为接受、且接受值与标不一致 |
| `estimated_cost_if_refit` | 新政策仍接受的记录上 `usage.cost` 之和；没有 usage 时为 `None`。不估计升级代价 |

不变量：用当初产出日志的政策回放，每一问必须逐字段一致。提高 τ 只需要 `replay`。持续集成不需要模型 key。

`fit` 从带标签的记录中选阈。人标是强裁判。级联接受且与人标一致，或任意升级，相对该裁判都算正确。级联接受但与人标不一致则算错误。这些残差均值的单侧 95% 下界必须至少为 `lcb_margin`（默认 `-0.02`）。在合格阈值中，`fit` 保留接受条数最多的 τ；并列时取更大的 τ。若无一合格，政策设置 `escalate_all: true`。

noul 按公开网格扫描成对 `(1 - τ, τ)`。Pack 中每一问独立拟合，再组成一份政策。标签少于 `min_n`（默认 50）时抛出 `NotEnoughLabels`。若记录含 `answers_reversed`，`fit` 先平均两个信号再选阈，并报告 `order="bilateral"`。否则报告 `order="single"`，不假装做过双边协议。

## 命令行

`openlatch[cli]` 会安装 `openlatch` 命令，供本地检查。生产调用应使用 Python API。

```bash
openlatch hash --pack packs/rag.yaml
openlatch decide --pack p.yaml --policy pol.json --answers a.json
openlatch replay --log logs.jsonl --pack p.yaml --policy pol.json
openlatch fit --log logs.jsonl --pack p.yaml --out pol.json --min-n 50
```

配置错误和 `NotEnoughLabels` 的退出码为 2。当新政策与已存决议不一致时，`replay` 会打印 diff，但仍退出 0，因为这是改 τ 的预期结果。加上 `--assert-unchanged` 会在出现 flip 时退出 1；该标志供持续集成使用。

## 安装细节

需要 Python 3.10 或更高版本。若已有虚拟环境，用该环境的解释器安装当前检出：

```bash
python -m pip install -e ".[dev]"
python -I -c "import openlatch; print(openlatch.__version__)"
```

`-I` 会把当前目录排除在导入路径之外，避免本地源码树掩盖未安装成功的包。

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

**使用 uv 安装**

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"
```

若应用本身是 uv 项目：

```bash
uv add openlatch
uv run python -I -c "import openlatch; print(openlatch.__version__)"
```

**从 GitHub 安装**

```bash
python -m pip install "git+https://github.com/shuyangvv/OpenLatch.git"
```

**排错**

- **`ModuleNotFoundError: No module named 'openlatch'`：** 安装与运行脚本须使用同一虚拟环境中的 Python。编辑器也要选中该解释器。
- **遇到 `jev-latest` 时抛出 `PackError`：** 钉死带日期的模型，或在 Pack 中设置 `allow_unpinned: true`。OpenLatch 不会静默接受未钉死的别名。
- **加载时抛出 `PolicyError`：** `on_failure` 不是 `"escalate"`、noul 阈值顺序不合法，或政策绑定的 Pack 哈希不一致。
- **`NotEnoughLabels`：** `fit` 收到的带标签行数少于 `--min-n` / `min_n`。

## 可复现的拟合与回放

公开 fixture 为 `tests/fixtures/packs/rag_sufficiency.v1.yaml`，以及 `tests/fixtures/logs/labeled.jsonl` 中的五十条带标签记录。磁盘上的决议由手写政策 `tau_yes=0.95` / `tau_no=0.05` 产生。在仓库根目录执行：

```bash
python examples/fit_from_log.py
```

稳定数字（只有 `fitted_at` 会变）：

| 字段 | 值 |
|---|---|
| `pack_hash` | `sha256:01cade1c40c5cabe1e0f8406b47fc20026307d5cb4816e6ddaeb0b3db9ad92de` |
| 拟合 `tau_yes` / `tau_no` | `0.80` / `0.20` |
| `fit.n` | `50` |
| `fit.rule` | `lcb-0.02` |
| `fit.qualified` | `true` |
| `fit.order` | `single` |
| `accept_rate_old` → `accept_rate_new` | `0.9` → `1.0` |
| `flipped_to_escalate` / `flipped_to_accept` | `0` / `5` |
| `label_conflicts_new` | `0` |
| `estimated_cost_if_refit` | `0.00085` |

`tests/test_fit.py` 锁住这些数字。改 fixture、哈希或 LCB 规则都会使该测试失败。

## 范围

v1 包含库、JSONL 存储和 CLI。

明确不做：

- HTTP、重试或限流（属于官方 SDK）
- 内置强裁判、解释生成或调用 GPT
- MCP 服务、LangGraph 节点、FastAPI 中间件或仪表盘
- Postgres、多租户或第二套存储引擎
- 默认阈值，或静默放行 `jev-latest`
- 代码评审或客服路由的预设置量规（那是量规包，不是本库）

v1.1 可能把双边 `answers_reversed` 做成一等路径、增加 sidecar 标签存储，以及可选的 `resolve(fallback=...)` 辅助函数。该辅助函数已存在于 `openlatch.extras.resolve`，不属于核心导出列表。

## 许可证

[MIT](LICENSE)
