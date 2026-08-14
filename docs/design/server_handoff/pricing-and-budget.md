# Token价格与实验调用预算

> 本文件只定义论文实验的Token等价成本和调用硬门。AutoDL服务器租金、GPU空闲、模型下载、模型加载、环境安装和远程Codex操作不属于论文实验成本。

## 论文主成本：Official API-Equivalent Token Cost

```text
input_tokens / 1,000,000 × official_input_price
+
output_tokens / 1,000,000 × official_output_price
```

该指标用于Router预算与跨Agent公平比较，不是实际API账单。价格快照固定在：

```text
configs/pricing/ministral3_official_api_equivalent_20260812.yaml
```

| Agent | 模型 | Input / M Token | Output / M Token |
|---|---|---:|---:|
| CheapAgent | Ministral 3 3B | USD 0.10 | USD 0.10 |
| MidAgent | Ministral 3 8B | USD 0.15 | USD 0.15 |
| StrongAgent | Ministral 3 14B | USD 0.20 | USD 0.20 |

三者官方上下文均为262,144 Token；首轮实验人为批准的运行上限固定为32,768。

## Cache Token约定

官方模型页未单列 cached input 或 cache-write 价格。本项目对这两类Token使用普通输入价，作为显式、保守且可复算的论文代理定义，不宣称这是Mistral实际缓存账单。服务未返回某类usage时必须按冻结schema记为0或NA，不得用字符数估算正式Token。

## 不属于论文实验成本的内容

以下内容不进入Router、Baseline、Cost-QWK、Pareto Frontier或论文结果表格：

- AutoDL服务器租金；
- GPU空闲和平台计费等待；
- 模型下载、校验与模型加载时间；
- 环境安装与依赖构建时间；
- 远程Codex、VS Code和Mihomo运行时间；
- 人工等待与运维操作。

真实配置固定：

```yaml
server_hourly_price_usd: null
actual_server_allocated_cost_usd: null
operational_retry_server_overhead_usd: null
```

代码和冻结配置中的 `actual_server_cost_allocation` 等兼容元数据可以保留；当 `server_hourly_price_usd=null` 时该逻辑必须保持禁用，实际成本字段为 `null`，不得作为必填字段、预算门或论文指标。

## Canonical与重试

- 每个 `Item × Agent` 只有一条最终成功canonical成本。
- 所有HTTP attempt写入 `logs/call_attempts.jsonl`。
- 失败attempt产生的Token进入 `operational_retry_overhead`，不重复进入canonical experiment cost。
- `--resume`只补缺失canonical记录，不能重复累计已成功Item。
- `max_attempts_per_logical_call`限制单个逻辑调用；`max_total_calls`限制整个run的全部HTTP attempt，两道门必须同时满足。
- 达到调用、Token等价费用、上下文、输出或超时硬门时立即fail closed，不能临时扩大预算继续。

## Per-Model Smoke调用预算

3B、8B和14B分别使用同一套3个canonical探针：通用文本、DREsS三维文本、多模态图片。每个模型单独运行、单独记账，不把额外身份探针混入canonical账本。

```yaml
stage: per_model_smoke
canonical_probe_calls: 3
max_attempts_per_logical_call: 2
max_total_calls: 6
concurrency: 1
timeout_seconds: 180
max_model_len: 32768
max_output_tokens: 768
temperature: 0.0
enable_thinking: false
max_cost_usd_per_model: 0.05
server_hourly_price_usd: null
```

## 真实5 Item调用预算

```yaml
stage: real_five_item_checkpoint
items: 5
agents: [CheapAgent, MidAgent, StrongAgent]
canonical_calls: 15
max_attempts_per_logical_call: 2
max_total_calls: 18
concurrency: 1
timeout_seconds: 180
max_model_len: 32768
max_output_tokens: 768
temperature: 0.0
enable_thinking: false
max_cost_usd: 0.10
server_hourly_price_usd: null
```

15条canonical之外只允许最多3次额外attempt。失败attempt保留Token overhead，但不得产生第二条canonical成本。

## 30 Item调用预算

```yaml
stage: real_thirty_item_pilot
items: 30
agents: [CheapAgent, MidAgent, StrongAgent]
canonical_calls: 90
max_attempts_per_logical_call: 2
max_total_calls: 108
concurrency: 1
timeout_seconds: 180
max_model_len: 32768
max_output_tokens: 768
temperature: 0.0
enable_thinking: false
max_cost_usd: 1.00
server_hourly_price_usd: null
```

90条canonical之外只允许最多18次额外attempt。30 Item只有在真实5 Item远程与本地validator均PASS且用户批准、30 Item输入传输receipt PASS后执行。达到任一硬门、连续错误或阻塞性质量/语义失败时必须停止，不能通过增加重试预算继续。

## 配置一致性门

执行真实run前必须逐项核对本文件与resolved config：

- `max_total_calls`、`max_cost_usd`、`timeout_seconds`；
- `max_model_len`、`max_output_tokens`、`temperature`、`enable_thinking`；
- `server_hourly_price_usd=null`；
- Agent集合、canonical调用数和并发；
- 价格manifest路径与SHA-256。

任一字段不一致时不得启动模型调用，并在run的 `reports/budget-gate.json` 中记录FAIL。