# Agent Cache 阶段详细计划

**项目**：A2A-DyGrade-RL  
**阶段**：Agent cache、Difficulty Labels 与 Agent Capability Profiles  
**计划状态**：Fixture 实施与验证已完成  
**工作流**：`project-speckit-workflow` / `speckit-implement`  
**对应任务**：`T031-T042A`

## 1. 当前状态

数据阶段已经通过门禁，Agent cache 的 Fixture 实施与验证已完成：

- Prepared items 共 39,533 条。
- 数据审计结果为 PASS。
- Item、prompt、paper 和 exact prompt-answer 跨 split 泄漏均为 0。
- Strict paper mix 错误为 0。
- `T031-T042A` 共 13 项任务均已完成，并有代码、测试和运行产物支撑。
- 已实现统一 `AgentOutput` schema、五类 Agent wrappers、缓存写入器、CLI、difficulty labels、fixture predictor 和 capability profiles。
- `configs/agents.yaml` 中五类 Agent 当前均为 `fixture` 模式，不会连接真实模型、产生 API 费用或下载模型权重。
- `fixture_smoke_001` 使用 20 个 train items 生成 240 条 cache records，0 failure；resume 复用 240 条记录，5 个 Agent cache 文件哈希保持一致。
- Difficulty 分布为 Easy 7、Medium 6、Hard 7；生成 20 条预测和 45 个 train-only capability profiles。

## 2. 阶段目标

本阶段不是训练 Router，而是提前生成并冻结后续所有实验方法共同使用的 Agent 输出。

需要支持五类 Agent：

1. `CheapAgent`
2. `MidAgent`
3. `StrongAgent`
4. `EvidenceAgent`
5. `ArbitratorAgent`

Agent cache 将被以下阶段共同复用：

- Difficulty labels 构建。
- Agent capability profiles 构建。
- 离线轨迹和 replay buffer 构建。
- Baseline 与消融实验。
- CAG-CQL Router 训练。
- 最终 test split 评价。

后续阶段不得为相同 prepared data 重复调用模型，以保证公平性、成本可控性和实验可复现性。

## 3. Agent Cache 统一 Schema

每条 Agent cache record 至少包含：

```text
item_id
agent_id
run_id
execution_mode
is_fixture
pred_score
confidence
justification
evidence
cost
latency
token_usage
gold_score
split
model_id
prompt_version
prompt_hash
input_hash
context_hash
cache_key
cache_schema_version
status
error
metadata
```

### 3.1 基础校验

- `item_id` 必须能够关联到 prepared item。
- `agent_id` 必须属于配置中注册的 Agent。
- `pred_score` 必须位于该 item 的 `[score_min, score_max]` 范围内。
- `confidence` 必须位于 `[0, 1]`。
- `cost`、`latency` 和 `token_usage` 必须非负。
- 成功记录必须包含合法输出。
- 失败记录必须包含明确的 `status` 和 `error`，不得静默丢弃。
- 相同 active cache key 不得出现多条互相冲突的记录。

### 3.2 Gold Score 隔离

实验设计要求 cache schema 保留 `gold_score`，但必须使用以下流程避免泄漏：

1. 构建 Agent 请求时，从输入中移除 `gold_score`。
2. Agent 完成预测后，由 cache writer 从 prepared item 关联 `gold_score`。
3. `gold_score` 只能用于离线误差计算、难度监督、能力画像和最终评价。
4. test cache 必须与 train/dev cache 物理隔离。
5. 普通训练、调参、能力画像和 replay buffer 构建代码默认拒绝读取 test cache。
6. 只有显式启用 `final_evaluation` 模式时，评价程序才允许读取 test cache 和 test gold。

## 4. 第一阶段：Schema、校验与测试

**对应任务**：`T031`，以及 `T038` 的部分前置设计。

### 实现内容

- 完善 `src/a2a_dygrade_rl/utils/schemas.py` 中的 `AgentOutput`。
- 在 `src/a2a_dygrade_rl/utils/validation.py` 中实现 `validate_agent_output()`。
- 定义 Agent 成功、失败和跳过记录的统一格式。
- 定义 cache key 生成规则。
- 定义模型、prompt、输入和上下文版本字段。
- 扩充 `tests/fixtures/sample_agent_cache.jsonl`。
- 在 `tests/unit/test_agents.py` 中添加 schema 和 fixture-cache 测试。

### Cache Key

推荐 cache key 由以下内容的稳定 hash 构成：

```text
item_id
agent_id
split
model_id
model_revision
prompt_hash
generation_parameters
context_hash
cache_schema_version
```

相同输入和配置必须得到相同 cache key；模型、prompt、上下文或生成参数发生变化时必须得到新的 cache key。

### 验收标准

- 合法 fixture 记录通过校验。
- 分数越界、置信度越界、负成本和缺少必填字段的记录被拒绝。
- 单元测试确认 Agent 请求内容中不包含 `gold_score`。
- 相同输入重复生成的 cache key 完全一致。
- prompt、模型或上下文变化后 cache key 必须变化。

## 5. 第二阶段：五类 Agent 统一接口

**对应任务**：`T033-T037`。

### 5.1 BaseAgent

在 `src/a2a_dygrade_rl/agents/base_agent.py` 中定义统一接口：

```text
agent_id
role
build_request(item, context)
predict(item, context)
parse_response(raw_response)
validate_output(output, item)
estimate_cost(token_usage)
```

所有 Agent 必须经过同一个 client 抽象和 cache writer，不能各自直接写文件。

### 5.2 CheapAgent、MidAgent 与 StrongAgent

三个 scoring Agent 使用相同评分协议，但配置不同：

- 输入包含 prompt、student answer、rubric、reference answer 和合法分数范围。
- 输入不得包含 gold score。
- 输出包含 predicted score、confidence 和简短评分依据。
- 分数解析失败时生成失败记录，不能通过静默截断掩盖模型错误。
- 不同 Agent 可以使用不同模型、提示词、推理深度和成本配置。

| Agent | 作用 | 实验定位 |
|---|---|---|
| `CheapAgent` | 低成本快速评分 | 成本下界、简单题评分 |
| `MidAgent` | 中等能力评分 | 质量与成本折中 |
| `StrongAgent` | 强推理评分 | 难题评分、质量上界 |

### 5.3 EvidenceAgent

EvidenceAgent 负责检查学生答案是否命中 reference answer、rubric 或关键得分点。

输出至少包含：

- 已命中的得分点。
- 缺失的得分点。
- 支持当前分数的证据。
- 证据置信度。
- 是否建议升级到其他评分 Agent。

EvidenceAgent 的主要职责是证据验证，不应被当成普通 scorer。为了统一 cache schema，可以保留建议分数或使用可空评分字段，并在 metadata 中标记角色类型。

### 5.4 ArbitratorAgent

ArbitratorAgent 依赖已经获得的 Agent 意见，不能为每个 item 只缓存一条脱离上下文的仲裁结果。

推荐让其 cache key 包含：

```text
item_id
参与仲裁的 scorer 集合
已有 scorer 分数与置信度摘要
EvidenceAgent 是否参与
prompt_version
model_version
```

Fixture 和 pilot 阶段至少覆盖以下 canonical contexts：

```text
Cheap + Mid
Cheap + Strong
Mid + Strong
Cheap + Mid + Strong
Cheap + Mid + Evidence
Cheap + Strong + Evidence
Mid + Strong + Evidence
Cheap + Mid + Strong + Evidence
```

这样可以防止 Router 在只支付 CheapAgent 和 MidAgent 成本时，通过 Arbitrator cache 间接获取尚未调用的 StrongAgent 信息。

### 5.5 LLM Client 抽象

在 `src/a2a_dygrade_rl/utils/llm_client.py` 中首先实现：

- `FixtureClient`。
- 统一请求与响应类型。
- 超时和重试接口。
- token usage 与 cost 统计接口。
- provider-neutral 配置结构。
- 请求和响应的可审计 metadata。

Fixture 阶段不安装真实模型 SDK。真实模型依赖必须在 smoke 通过并获得用户批准后再安装。

## 6. 第三阶段：Cache Writer 与 CLI

**对应任务**：`T038-T039`。

### 6.1 运行模式与目录隔离

每次运行必须使用唯一 `run_id`，并且 `Fixture Smoke`、真实模型 Pilot 与正式实验必须使用不同的物理目录。三类运行统一位于 `outputs/runs/` 下，以继续满足项目宪法对运行产物目录的约束：

```text
outputs/runs/fixture_smoke_<序号>/
outputs/runs/real_pilot_<序号>/
outputs/runs/formal_agent_cache_<序号>/
```

静态 fixture 输入、预期输出和测试样本只允许放在：

```text
tests/fixtures/agent_cache/
```

运行模式与目录前缀必须一一对应：

| `execution_mode` | `is_fixture` | 目录前缀 | 用途 |
|---|---:|---|---|
| `fixture_smoke` | `true` | `fixture_smoke_` | 工程链路、schema、缓存和防泄漏验证 |
| `real_pilot` | `false` | `real_pilot_` | 真实模型小样本质量、费用和延迟审核 |
| `formal_experiment` | `false` | `formal_agent_cache_` | 冻结配置后的正式 Agent cache 与论文实验 |

三类目录不能互相续跑、导入 active cache 或复用 checkpoint。Fixture 产物不得进入真实模型 Pilot 或正式实验；Pilot 产物不得直接提升为正式 Agent cache。正式实验必须在模型、prompt 和参数冻结后重新生成 cache。

每个运行目录内部使用相同的可审计结构：

```text
outputs/runs/<run_id>/
├── configs/
│   ├── agents.resolved.yaml
│   ├── prompts_manifest.json
│   └── data_fingerprint.json
├── logs/
│   ├── agent_cache.log
│   └── failures.jsonl
├── predictions/
│   └── agent_cache/
│       ├── train/
│       ├── dev/
│       └── test/
└── reports/
    ├── agent_cache_audit.md
    ├── agent_cache_coverage.csv
    └── agent_cache_cost_summary.csv
```

每个 split 下按 Agent 分文件，并生成 `cache_manifest.csv`。

### 6.2 Cache Writer 行为

- 使用原子写入，避免进程中断后留下不完整 JSON。
- 支持断点续跑。
- 已存在合法 cache key 时直接复用，不重复调用。
- 输入、模型或 prompt 变化后生成新的 cache key。
- 默认禁止覆盖已有 run。
- 错误记录写入 `failures.jsonl`。
- 支持确定性的 item 抽样。
- 保存实际生效配置、prompt hash 和数据指纹。
- 生成覆盖率、成本、延迟和失败率报告。

- 校验 `execution_mode`、`is_fixture` 与 `run_id` 目录前缀一致。
- `fixture_smoke` 只能使用 `FixtureClient`；`real_pilot` 和 `formal_experiment` 必须拒绝 `FixtureClient`。
- 断点续跑只能读取同一 `run_id`、同一 `execution_mode`、同一模型和 prompt 指纹的 cache。
- capability profile、Router、replay buffer 和论文评价默认拒绝读取 `is_fixture=true` 的记录。
- 正式实验默认拒绝读取 `execution_mode=real_pilot` 的记录。

### 6.3 CLI 参数

`scripts/03_run_agent_cache.py` 至少支持：

```text
--config
--items
--split
--agents
--run-id
--sample-size
--seed
--fixture
--resume
--final-evaluation
--execution-mode
```

默认不允许覆盖有效缓存、读取未授权 test split、缺少 `run_id` 或 `execution_mode`、跨运行模式续跑，或把输出写入旧式平铺目录。

## 7. 第四阶段：Fixture Smoke Workflow

建议使用：

```text
run_id = fixture_smoke_001
```

### Smoke 样本

从 train split 中确定性抽取约 20 个 items，至少覆盖三个数据集、不同题型、不同分数范围、reference/rubric 可用性和多个 prompt groups。

### Fixture 行为

FixtureClient 根据 `item_id + agent_id + seed + context_hash` 确定性地产生模拟结果：

- `CheapAgent`：简单题误差较低，复杂题误差较高。
- `MidAgent`：总体比 CheapAgent 稳定。
- `StrongAgent`：总体误差最小，但不直接复制 gold score。
- `EvidenceAgent`：根据 rubric/reference 覆盖情况生成模拟证据。
- `ArbitratorAgent`：根据已有评分意见和证据生成确定性仲裁结果。

Fixture 只能用于工程验证，不能作为论文实验结果。

### Smoke 验证项

1. 五类 Agent fixture 均能生成合法输出。
2. 相同 seed 重跑结果完全一致。
3. 第二次运行命中缓存，不重复生成。
4. 非法记录能够被 validator 阻止。
5. 中断后能够断点续跑。
6. Agent 输入不包含 gold score。
7. 所有动态产物只能进入独立的 `outputs/runs/fixture_smoke_<序号>/`，静态 fixture 只能进入 `tests/fixtures/agent_cache/`。
8. Fixture smoke 不需要网络和新增依赖。
9. test split 不参与 difficulty/capability fitting。
10. Fixture cache、checkpoint 和阈值不能被真实模型 Pilot 或正式实验读取。

只有 fixture smoke 全部通过，才进入 difficulty 和 capability 实现。

## 8. 第五阶段：Difficulty Labels

**对应任务**：`T040`、`T042`、`T042A`。

训练难度监督分数严格使用实验设计公式：

```text
D_i =
alpha * Err_cheap
+ beta * Err_mid
+ gamma * Disagreement_i
+ delta * Complexity_i
```

Agent error 必须使用归一化评分误差：

```text
Err_agent =
abs(pred_score - gold_score)
/
(score_max - score_min)
```

原始尺度 MAE 只作为报告指标，不能替代归一化误差参与 difficulty scoring。

### 防泄漏难度方案

当前公式中的 `Err_cheap` 和 `Err_mid` 依赖 gold score，因此 test Router 不能直接使用按 test gold 计算的真实难度。

推荐拆成两层：

1. **Train Difficulty Supervision**
   - 只在 train split 使用 gold score 和归一化 Agent error 计算真实 `D_i`。
   - 只使用 train 分布确定 Easy、Medium、Hard 阈值。
   - 保存信号、公式版本、权重和阈值。

2. **Inference Difficulty**
   - 使用 train difficulty supervision 拟合 difficulty predictor。
   - 输入只能包含推理时已经可观测的特征。
   - dev 用于有限模型校验和参数选择。
   - test 只进行推断，不能使用 test gold 构造 Router 可见难度。
   - test gold 只能在 final evaluation 后用于诊断分析。

### Difficulty Predictor 模型选择

正式主模型固定为：

```text
sklearn.ensemble.HistGradientBoostingRegressor
```

模型预测目标为连续难度分数 `D_i`。选择该模型是因为它能够表达静态复杂度、Agent 置信度和评分分歧之间的非线性关系与特征交互，同时适合约 28,038 个 train items，可在 CPU 上训练，不需要 GPU 或额外模型权重，并且容易保存配置和复现实验。

同时保留以下诊断基线：

```text
sklearn.linear_model.Ridge
```

`Ridge` 只用于判断非线性 predictor 是否带来实际收益，不与主模型集成，也不参与正式 Router 推断。正式流水线只允许使用 dev 验证后冻结的一个 `HistGradientBoostingRegressor` checkpoint。

需要记录并冻结的参数至少包括：

- `loss`。
- `learning_rate`。
- `max_iter`。
- `max_leaf_nodes`。
- `min_samples_leaf`。
- `l2_regularization`。
- `early_stopping`。
- `random_state`。
- 特征 schema 与预处理版本。

Easy、Medium、Hard 阈值只能根据 train difficulty supervision 的分布确定并冻结。Dev 和 test 都必须使用同一组 train 阈值，不能根据各自 gold score 或各自难度分布重新计算。

### Predictor 输入可见性

允许的输入包括：

- prompt、answer、reference 和 rubric 的长度及静态结构特征。
- token 数、句子数、词汇多样性、数字、公式或代码等可确定性提取的复杂度特征。
- dataset、question type、score range 和 prompt group 等推理前可见元数据。
- 当前 Router 阶段已经实际调用并获得的 Agent confidence、score disagreement 和 confidence variance。

禁止输入 dev/test gold score、由 dev/test gold 计算的归一化 Agent error、test difficulty label，以及当前 Router 阶段尚未调用的 Agent 输出。离线 cache 中存在某个 Agent 结果，不等于在线决策时该结果可见；特征构建器必须按调用上下文执行可见性校验。

### Fixture 与正式 Predictor 隔离

- Fixture 数据可以验证 predictor 的特征提取、`fit/predict`、保存、加载和 schema，但生成的模型、阈值和预测结果只能留在 `outputs/runs/fixture_smoke_<序号>/`。
- Fixture predictor 不能晋升、复制或导入真实模型 Pilot 和正式实验。
- `real_pilot` 只用于验证真实 Agent 输出质量、特征可用性和资源预算，其小样本 cache 不得用于训练正式 predictor。
- 正式 predictor 必须使用 `formal_experiment` 模式下生成的真实 train cache 重新训练，并在 dev 上完成有限校验后冻结。
- 正式 predictor checkpoint、特征 schema、阈值和配置必须与正式 Agent cache 保存在同一 `formal_agent_cache_<序号>` 运行目录中。

`HistGradientBoostingRegressor` 和 `Ridge` 需要项目虚拟环境中的 `scikit-learn`。当前阶段只记录依赖选择；安装必须遵守项目宪法，在说明用途、D 盘 `.venv` 路径和影响并获得用户明确批准后执行。

建议产物：

```text
outputs/runs/<run_id>/configs/difficulty_predictor.resolved.yaml
outputs/runs/<run_id>/predictions/difficulty/train_supervision.jsonl
outputs/runs/<run_id>/predictions/difficulty/dev_predicted.jsonl
outputs/runs/<run_id>/predictions/difficulty/test_predicted.jsonl
outputs/runs/<run_id>/checkpoints/difficulty_predictor/model.joblib
outputs/runs/<run_id>/reports/difficulty_distribution.csv
outputs/runs/<run_id>/reports/difficulty_model_metrics.csv
outputs/runs/<run_id>/reports/difficulty_audit.md
```

## 9. 第六阶段：Agent Capability Profiles

**对应任务**：`T041-T042A`。

能力画像只允许使用 train cache 和 train gold 拟合。Dev 可以用于诊断，test 不得参与。

按 `agent_id`、dataset、question type 和 difficulty label 聚合：

- QWK。
- 原始尺度 MAE。
- 归一化 MAE。
- 平均 Cost。
- 平均 Latency。
- 平均 Token Usage。
- Calibration。
- Sample Count。
- Failure Rate。

能力向量：

```text
c_a = [
  accuracy_by_type_difficulty,
  normalized_mae,
  cost,
  latency,
  calibration,
  load
]
```

低样本组合必须标记 `low_support=true`。

产物：

```text
outputs/runs/<run_id>/reports/agent_capability_table.csv
outputs/runs/<run_id>/reports/agent_capability_audit.md
```

## 10. 第七阶段：集成测试与阶段审计

**对应任务**：`T032` 和 Phase 4 检查点。

集成测试必须检查：

- 每个接受的 item 是否拥有要求的 scorer cache。
- 是否存在非法分数、置信度或负成本。
- 是否存在重复 active cache key。
- prompt、model、config 和 context hash 是否完整。
- Difficulty 是否一条 item 对应一条有效记录。
- Capability profile 是否仅使用 train split。
- test cache 是否进入 difficulty fitting、capability fitting 或 replay buffer。
- 归一化误差是否与数据审计公式一致。
- 所有失败 item 是否有明确原因。
- 相同 cache 是否能被 baseline、消融和主方法共同读取。
- 重跑是否复用缓存并生成相同报告。

## 11. 第八阶段：真实模型 Pilot

本阶段必须在 fixture smoke 通过后，再获得用户明确批准。

开始前必须确定：

- 五类 Agent 分别使用什么模型。
- 使用本地模型还是在线 API。
- 模型权重、SDK 和缓存的 D 盘路径。
- API 费用上限。
- 并发数、重试次数和超时。
- 模型版本是否可以固定。
- token 单价和价格快照如何记录。

建议先运行约 100 个 train items：

```text
run_id = real_pilot_001
```

Pilot 重点检查 JSON 解析成功率、分数越界率、平均 token/cost/latency、Agent 能力差异、Evidence/Arbitrator 有效性以及全量费用和时间估算。

Prompt 一旦根据 train pilot 和 dev 验证冻结，才允许生成正式 test cache。不得根据 test 结果修改 prompt、模型、阈值或策略。

## 12. 第九阶段：全量 Agent Cache

正式全量 cache 必须创建新的正式运行目录，不得从 Pilot 目录续跑或复制 active cache。建议使用：

```text
run_id = formal_agent_cache_001
```

| Split | Items | 五个基础 Agent 输出下限 |
|---|---:|---:|
| Train | 28,038 | 140,190 |
| Dev | 3,244 | 16,220 |
| Test | 8,251 | 41,255 |
| 合计 | 39,533 | 197,665 |

`197,665` 是每个 item 每类 Agent 一条记录的理论下限。若 Arbitrator 按多个上下文变体缓存，实际记录和调用次数会更高，必须在真实 pilot 后重新估算费用。

推荐执行顺序：

1. 生成全量 train cache。
2. 运行 train cache audit。
3. 生成 train difficulty supervision。
4. 生成 Agent capability profiles。
5. 生成 dev cache。
6. 使用 dev 冻结 prompt、难度预测器、阈值和配置。
7. 封存训练配置和 prompt 版本。
8. 最后生成 test cache。
9. test cache 只允许 `final_evaluation` 模式读取。

## 13. 阶段完成标准

- `T031-T042A` 全部有代码、测试和产物支撑。
- Fixture smoke 全部通过。
- Fixture Smoke、真实模型 Pilot 和正式实验的目录、manifest、cache 与 checkpoint 已通过模式校验实现物理隔离。
- `HistGradientBoostingRegressor` 只使用正式真实模型 train cache 拟合，并在 dev 校验后冻结。
- `Ridge` 只作为诊断基线，不进入正式 Router 推断。
- Fixture 或 Pilot 生成的 difficulty predictor、阈值和预测结果未进入正式实验。
- 100% 被接受的 cache records 满足 schema。
- CheapAgent、MidAgent 和 StrongAgent 具有完整基础覆盖。
- EvidenceAgent 和 ArbitratorAgent 的输入上下文可追踪。
- test gold 从未进入 Agent 请求。
- test cache 未参与 difficulty fitting、capability fitting、调参或 replay buffer 构建。
- Difficulty 使用归一化评分误差。
- Capability profile 仅使用 train 数据拟合。
- 配置、prompt、模型、价格、数据指纹和随机种子可追溯。
- 下游可以完全离线复用相同 Agent cache。
- 所有运行产物均位于对应的 `outputs/runs/<run_id>/`，且 `run_id` 前缀与 `execution_mode` 一致。

## 14. 实施顺序与任务映射

| 顺序 | Tasks | 工作内容 | 门禁 |
|---:|---|---|---|
| 1 | `T031` | Agent schema、validator、fixture 单元测试 | Schema 测试通过 |
| 2 | `T033-T037` | BaseAgent、五类 wrappers、registry、FixtureClient | 五类 fixture 可调用 |
| 3 | `T038-T039` | Cache writer、manifest、CLI、断点续跑与三种运行模式隔离 | Cache smoke 通过且禁止跨模式复用 |
| 4 | `T040`、`T042A` | Train difficulty supervision、`HistGradientBoostingRegressor` 与防泄漏推断 | test gold 不可见，fixture/pilot 模型不可进入正式实验 |
| 5 | `T041`、`T042A` | Train-only capability profiles | 无统计泄漏 |
| 6 | `T032`、`T042` | 集成测试、CLI、审计报告 | Fixture 阶段验收 |
| 7 | 后续单独批准 | 真实模型 100-item pilot | 成本和质量审核 |
| 8 | 后续单独批准 | Train、dev、test 全量 cache | 正式 Agent cache 冻结 |

## 15. 待用户确认的设计决策

### 决策 1：Difficulty 防泄漏

推荐采用：

> Train gold 生成难度监督；正式主模型使用 `HistGradientBoostingRegressor`，`Ridge` 仅作诊断基线；dev/test 使用只依赖当前可观测特征的预测难度。

### 决策 2：Arbitrator Cache 上下文

推荐采用：

> ArbitratorAgent 按已经获得的 Agent 意见生成不同 context hash 和 cache key，而不是每个 item 只有一条无条件仲裁结果。

### 决策 3：真实模型门禁

推荐推进顺序：

```text
Fixture 单元测试
-> Fixture smoke
-> 约 100 个 train items 的真实模型 pilot
-> 审核质量、费用和延迟
-> 冻结模型与 prompt
-> 全量 Agent cache
```

真实模型、模型 SDK、API、模型权重和外部依赖的安装或下载，必须单独说明用途、D 盘路径和影响，并在获得用户明确批准后执行。


### 决策 4：Fixture、Pilot 与正式实验隔离

已确认采用：

> Fixture Smoke、真实模型 Pilot 和正式实验分别使用 `fixture_smoke_`、`real_pilot_` 和 `formal_agent_cache_` 前缀的独立运行目录；三类 cache、checkpoint、阈值和预测结果禁止跨模式续跑或复用。

该决策既通过物理目录隔离，也通过 `execution_mode`、`is_fixture`、manifest 校验和下游读取门禁强制执行。
## 16. 当前工作流门禁

用户已批准本计划，当前进入 `speckit-implement`。本轮先完成 fixture schema、五类 Agent、cache writer、difficulty/capability 和 smoke 验证；真实模型 SDK、API、权重、`scikit-learn` 安装及 `real_pilot`/`formal_experiment` 运行仍需遵守 `AGENTS.md` 的单独批准门禁。
