# OpenLatch

System One 的决议层，不是 Jev 客户端。

Jev 给出 typed 概率。OpenLatch 给出 `accept` 或 `escalate`。Pack、模型版本和阈值打成可提交的政策；改门闩对旧日志零推理回放。超时、类型不对、政策和量规对不上：整单升级，不放行。

过线才锁上自动路径。失败时门是关的。

```text
官方 SDK ── answers ──► openlatch.decide ──► accept   ──► 业务自动路径
                         │                  escalate ──► 人 / 调用方强裁判
                         ▼
                      JSONL Log ── attach_label
                         │
              fit ──► 新 Policy ── replay ──► 覆盖率 / 冲突报告
```

## 安装

```bash
pip install openlatch
pip install 'openlatch[cli]'   # 可选：openlatch 命令
```

硬依赖只有 `pydantic>=2` 和 `PyYAML`。库内零 HTTP，不依赖 `httpx`、`typesafe-sdk`、`openai`、`langchain`、`fastapi`。CI 不需要 key。

## 8 行接入

```python
from typesafe_sdk import TypeSafeClient
from openlatch import load_pack, load_policy, decide
from openlatch.log import JsonlStore
from openlatch.types import Resolution

pack = load_pack("packs/rag_sufficiency.v1.yaml")
policy = load_policy("policies/rag_sufficiency.v1.json")
raw = client.system_one(model=pack.model, state=state, questions=pack.wire_questions())
decision = decide(raw.answers, pack, policy, model=raw.model)
store.append(...)
if decision.overall is Resolution.ACCEPT:
    use(raw.answers)
else:
    review_queue.push(...)
```

`pack.wire_questions()` 只把 YAML 转成 SDK 要的 dict，不发请求。PPT 的召回过滤、AIOB 的不确定分支、trans 的 adequacy 门共用这一套决议代码。

没有 Policy 就不能 `decide`。没有默认 0.9。`on_failure` 只能是 `escalate`。

## 三个对象

| 对象 | 格式 | 作用 |
|---|---|---|
| Pack | YAML | 钉死的量规：`id` / `version` / `model` / 问题 |
| Policy | JSON | 钉死的阈值，必须引用 Pack 的 `pack_hash` |
| Log | JSONL | 决议审计。默认只写 `state_digest`，不落业务原文 |

`pack_hash` 是 `{id, version, model, bundle, questions}` 按 RFC 8785 风格键序 JSON 的 SHA-256，写成 `sha256:<hex>`。YAML 注释不进哈希。加载时拒绝 `jev-latest`，除非 Pack 里显式 `allow_unpinned: true`。

## 判定

`decide` 是纯函数，不写磁盘。短路径在前：

1. `policy.pack_hash != pack.hash` → 整单 `pack_mismatch`
2. 传入的 `model` 与政策钉死前缀不一致 → `model_mismatch`（允许 `jev-1.13-20260917` 匹配 `typesafe/jev-1.13`）
3. 缺问 / 类型不对 / 概率不合法 → 该问 mismatch
4. choice/score：`confidence >= tau` 才 accept；noul：`>= tau_yes` 为 yes，`<= tau_no` 为 no，中间带升级
5. 空 answers 或 `{"__error__": "..."}` → `backend_failure`

`replay` 对每条旧日志调用**同一套** `decide`。改 τ 只跑 replay，不打模型。

`fit` 按论文 LCB：自动接受集合上的错误率，单侧 95% 下界相对人标不差过 2 个百分点。合格里取 accept 最多的 τ，并列取更大的 τ。都不合格则 `escalate_all: true`。`n < min_n` 抛 `NotEnoughLabels`。v1 不在库内打第二次 Jev；没有 `answers_reversed` 时 `order="single"`。

## CLI

```text
openlatch hash --pack packs/rag.yaml
openlatch decide --pack p.yaml --policy pol.json --answers a.json
openlatch replay --log logs.jsonl --pack p.yaml --policy pol.json
openlatch fit --log logs.jsonl --pack p.yaml --out pol.json --min-n 50
```

配置错误和样本不足退出码 2。`replay` 发现 flip 默认仍退出 0；`--assert-unchanged` 才在有 flip 时退出 1，给 CI 用。

`JsonlStore.attach_label` 会读全文件、改一行、原子替换。记录量大时这是 v1 的已知上限，v1.1 再加 sidecar。不要引入第二个存储故事。

## 可复现的 fit → replay

公开 fixture：`tests/fixtures/packs/rag_sufficiency.v1.yaml` 与 50 条带人标的 `tests/fixtures/logs/labeled.jsonl`。旧政策是手写的 `tau_yes=0.95` / `tau_no=0.05`。在仓库根目录：

```bash
python examples/fit_from_log.py
```

稳定数字（`fitted_at` 除外）：

```text
pack_hash          sha256:01cade1c40c5cabe1e0f8406b47fc20026307d5cb4816e6ddaeb0b3db9ad92de
fitted tau_yes     0.80
fitted tau_no      0.20
fit.n              50
fit.rule           lcb-0.02
fit.qualified      true
fit.order          single
accept_rate_old    0.9
accept_rate_new    1.0
flipped_to_escalate 0
flipped_to_accept   5
label_conflicts_new 0
```

伪 answers 走一遍 `decide`：

```bash
python examples/rag_filter.py
```

## v1 明确不做

- 任何 HTTP / 重试 / 限流
- 库内强裁判或生成解释（escalate 的去向由调用方接）
- MCP、LangGraph、FastAPI 中间件、仪表盘
- Postgres、多租户、默认阈值、静默放行 `jev-latest`

许可证：MIT。
