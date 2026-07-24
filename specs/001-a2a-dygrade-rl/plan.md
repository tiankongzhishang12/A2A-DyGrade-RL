# 实现计划：A2A-DyGrade-RL 实验流水线

**分支**：`001-a2a-dygrade-rl` | **日期**：2026-07-08 | **规格**：[spec.md](./spec.md)

**输入**：`docs/design/A2A-DyGrade-RL_实验设计方案.md`、`docs/design/实验计划.md`、`specs/001-a2a-dygrade-rl/spec.md`

## 摘要

本计划把 A2A-DyGrade-RL 的论文实验设计整理成可执行的离线研究流水线。核心目标不是构建新的单模型自动评分器，而是验证：在公开自动评分数据集上，通信感知的多 Agent 离线强化学习 Router 能否在保持评分质量的同时，降低试卷级阅卷成本、延迟和无效通信，并形成更优的 Cost-QWK Pareto Frontier。

流水线按“数据准备 -> Agent 缓存 -> 难度与能力建模 -> 离线轨迹构建 -> CAG-CQL 训练 -> baseline/消融/曲线评价 -> 论文材料生成”展开。所有阶段必须产出可复现、可审计、可重新计算的文件产物。

当前执行原则：先完成数据阶段的正式审计报告，再进入 Agent cache；Agent cache 先跑 fixture/smoke，再考虑全量真实模型调用。

## 实验设计蓝图

### 与实验设计方案的对齐范围

本计划必须覆盖 `docs/design/A2A-DyGrade-RL_实验设计方案.md` 的主要实验设计内容：

| 设计方案章节 | plan.md 承接位置 | 必须落地产物 |
|---|---|---|
| 2 数据集构建过程 | Phase 1：数据处理与审计 | `items_*.jsonl`、`papers_*.jsonl`、split/paper manifest、data audit |
| 3 Agent 设计与缓存机制 | Phase 2：Agent cache | 五类 Agent 输出缓存、成本/延迟/token 记录 |
| 4 题目难度建模 | Phase 2：difficulty labels | `difficulty_labels.jsonl` |
| 5 Agent 能力建模 | Phase 2：capability profiles | `agent_capability_table.csv` |
| 6 A2A 通信设计 | Phase 3/4：A2A message 与 history | `a2a_logs.jsonl`、A2A History Encoder 输入 |
| 7-12 离线强化学习、MDP、模型结构、Graph、Q 网络 | Phase 3/4：轨迹和 CAG-CQL | replay buffer、Q network、target network、Masked CQL |
| 13 奖励函数设计 | Phase 3/4：reward | step/final/paper reward |
| 14 离线轨迹构建 | Phase 3：trajectories | 基础轨迹、A2A 轨迹、边界轨迹、HBR |
| 15 Cost-QWK Curve | Phase 5：曲线实验 | `cost_qwk_curve.csv`、Pareto Frontier 图 |
| 16-17 Baseline 与消融 | Phase 5：评价 | 主实验表、消融表 |
| 18-20 评价指标、研究问题、实验表格 | Phase 5/6：报告 | `main_results.csv`、`ablation_results.csv`、论文图表 |
| 21-25 框架路径、实现顺序、创新点、方法一句话 | 全流程约束 | README、quickstart、论文材料 |

### 研究问题

| 编号 | 研究问题 | 需要的实验 |
|---|---|---|
| RQ1 | 动态路由是否优于 Cheap-only、Strong-only 和 Static Difficulty Router | 主实验表 |
| RQ2 | CAG-CQL Router 是否优于 CP-Router-Grade、SeqRoute-Grade 等路由 baseline | 主实验表和预算分组分析 |
| RQ3 | A2A 通信、预算状态、难度状态、Agent 能力画像和 HBR 是否有效 | 五组消融实验 |
| RQ4 | A2A-DyGrade-RL 是否形成更优 Cost-QWK Pareto Frontier | Cost-QWK 曲线和 Pareto Frontier |

### 数据集与实验作用

| 数据集 | 题型定位 | 实验作用 |
|---|---|---|
| DREsS | Rubric-based 作文评分 | 提供长答题、作文题和 rubric 约束场景 |
| ASAP-SAS | 经典短答案评分 | 提供短答评分经典基准，用于对齐自动短答评分文献 |
| SAS-Bench | 多学科短答案评分 | 提供更丰富的学科、题目和短答分布 |

数据处理先统一成 item-level 记录，再自动组合为 paper-level 伪试卷。每张 paper 默认包含 5 到 8 个 item，用于模拟真实试卷中的多题并行阅卷和预算分配。

统一 item-level 格式必须覆盖实验设计方案 2.2 节中的字段：`item_id`、`dataset`、`question_type`、`subject`、`prompt`、`student_answer`、`reference_answer`、`rubric`、`gold_score`、`score_min`、`score_max`、`metadata`。`metadata` 至少记录 prompt/answer/rubric 长度、是否有 reference answer、prompt group、split seed 和构造规则版本。

分数处理严格遵循 `docs/design/A2A-DyGrade-RL_实验设计方案.md` 第 2.3 节。由于不同数据集分值范围不同，实验不把所有原始分数替换成同一尺度，而是在保留原始 `gold_score`、`score_min` 和 `score_max` 的基础上，为后续 Agent 误差、难度建模、奖励和跨数据集误差比较统一计算归一化评分误差：

```text
R_i = score_max_i - score_min_i
E_i = abs(pred_score_i - gold_score_i) / R_i
```

其中 `pred_score_i` 是系统或 Agent 的预测分数，`gold_score_i` 是数据集提供的专家分数，`E_i` 是归一化评分误差。实验报告仍保留原始分数尺度下的 MAE，并使用 QWK 作为自动评分主指标。

paper-level 构造应尽量遵循实验设计方案 2.4 节的组合目标：每张 paper 包含 2-3 道 ASAP-SAS 短答案题、1-2 道 SAS-Bench 多学科短答案题、1 道 DREsS 作文题或长答题。当某个 split 因 prompt-level 防泄漏或样本分布导致无法满足该组合时，构造脚本可以退化为 5-8 个同 split item 的稳定重组，但必须在 `paper_manifest.csv` 和 `data_audit.md` 中记录实际 dataset mix 分布和偏离原因。

主实验 split 采用 **dataset-aware prompt-level split + paper-level regrouping**：

- 每个数据集内部按 prompt group 划分 `train/dev/test`，目标比例为 7:1:2。
- 同一 `item_id` 不得跨 split。
- 同一 prompt group 不得同时出现在训练相关 split 与 test split。
- paper 只能由同一 split 的 item 构成。
- split manifest 必须记录 `item_id`、dataset、prompt group、paper_id、split、seed、rule version 和 split scope。

### Agent 池

| Agent | 功能 | 预期用途 |
|---|---|---|
| CheapAgent | 低成本快速评分 | 简单题、低预算场景、成本下界 |
| MidAgent | 中等能力评分 | 中等难度题、质量与成本折中 |
| StrongAgent | 强推理评分 | 难题、长答题、高风险题、质量上界 |
| EvidenceAgent | 检查答案是否命中参考答案、rubric 或得分点 | 证据验证、降低无效升级 |
| ArbitratorAgent | 在多 Agent 分数冲突时仲裁 | 冲突解决和最终高置信评分 |

所有 Agent 输出必须缓存为统一 schema，至少包含 `item_id`、`agent_id`、predicted score、confidence、reasoning summary、evidence、cost、latency、token usage 和错误信息。Router 训练、baseline、消融和最终评价必须复用同一批 cache。

Agent 输出格式对齐实验设计方案 3.2 节，最小字段为 `item_id`、`agent_id`、`pred_score`、`confidence`、`justification`、`cost`、`latency`、`token_usage`、`gold_score`。缓存必须覆盖 CheapAgent、MidAgent、StrongAgent、EvidenceAgent 和 ArbitratorAgent，并写入 `outputs/runs/<run_id>/predictions/agent_cache/`，不得使用旧式 `outputs/agent_cache/` 平铺目录。

### 难度与能力建模

难度标签不引入人工标注，严格来自实验设计方案 4.1-4.3 节的两类信号：

- 静态复杂度：`question_type`、prompt length、answer length、rubric length、score range、has reference answer、dataset id。
- Agent 试评分表现：CheapAgent error、MidAgent error、StrongAgent error、Agent disagreement、confidence variance。

题目难度分数采用设计方案中的结构：

```text
D_i = alpha * Err_cheap + beta * Err_mid + gamma * Disagreement_i + delta * Complexity_i
```

其中 `Err_cheap` 和 `Err_mid` 必须使用归一化评分误差 `E_i`。难度分层为 Easy、Medium、Hard：Easy 表示 CheapAgent 误差低且分歧小；Medium 表示 CheapAgent 不稳定但 MidAgent 或 StrongAgent 明显改善；Hard 表示 CheapAgent 和 MidAgent 都不稳定且分歧高，通常需要 StrongAgent、A2A_ASK 或 ARBITRATE。

Agent capability profile 必须对齐实验设计方案第 5 节，按 Agent、question type 和 difficulty 统计 QWK、MAE、Cost、Latency、Calibration，并形成能力向量：

```text
c_a = [acc_a_type_d, mae_a_type_d, cost_a, latency_a, calibration_a, load_a]
```

能力画像拟合不得读取 test split。

### Router 与动作空间

A2A-DyGrade-RL 的核心 Router 是 **CAG-CQL：Communication-Aware Graph Conservative Q-Learning**。它把 paper-level 阅卷建模为预算约束下的离线 MDP。

状态至少包含：

- 当前 paper 内各 item 的题型、prompt、rubric/reference、分值范围和已知难度特征。
- 每个 item 已获得的 Agent 输出、分歧、置信度和证据状态。
- 当前剩余 cost、latency、Agent calls、A2A messages 等预算状态。
- Agent capability profile。
- A2A 通信历史。
- Agent-Item Routing Graph 编码结果。

动作至少包含：

| 动作 | 含义 |
|---|---|
| `ROUTE_CHEAP(i)` | 调用 CheapAgent 批改第 i 题 |
| `ROUTE_MID(i)` | 调用 MidAgent 批改第 i 题 |
| `ROUTE_STRONG(i)` | 调用 StrongAgent 批改第 i 题 |
| `VERIFY(i)` | 调用 EvidenceAgent 验证第 i 题证据或得分点 |
| `A2A_ASK(i)` | 请求另一个评分 Agent 给第 i 题第二意见 |
| `ARBITRATE(i)` | 调用 ArbitratorAgent 对第 i 题仲裁 |
| `STOP(i)` | 停止第 i 题评分并输出当前分数 |

必须实现 action mask，屏蔽预算不足、重复无意义调用、缺少仲裁前置条件和已完成 item 上的非法动作。

A2A 消息类型对齐实验设计方案第 6 节，必须支持 `VERIFY`、`A2A_ASK`、`CHALLENGE`、`JUSTIFICATION`、`ARBITRATE` 五类消息。Router 的显式动作至少包含 `VERIFY`、`A2A_ASK`、`ARBITRATE`；`CHALLENGE` 和 `JUSTIFICATION` 作为 A2A message schema 与 history encoder 的可记录消息类型，用于后续通信收益分析。

MDP 状态空间对齐实验设计方案第 8 节：

```text
s_t = [X_t, D_t, G_t, H_t, B_t]
```

其中 `X_t` 是所有题目的当前评分状态，`D_t` 是题目难度状态，`G_t` 是 Agent-Item 能力图状态，`H_t` 是 A2A 通信历史状态，`B_t` 是剩余预算状态。预算向量必须包含 remaining cost、remaining latency、remaining calls 和 remaining messages。

模型结构对齐实验设计方案第 9-12 节：Item Encoder、Agent Capability Encoder、Budget Encoder、Agent-Item Routing Graph Encoder、A2A History Encoder、Double Q Network、Target Network、Action Mask 和 Masked CQL Conservative Penalty 都必须作为 CAG-CQL 的组成部分落地。Agent-Item Routing Graph 需要包含 item nodes、agent nodes、budget node，以及 Item-Agent、Item-Budget、Agent-Budget、Item-Item 四类边。A2A History Encoder 至少支持 GRU 或 Transformer 中的一种实现，并保留消息序列供后续替换。

### 训练与奖励

离线轨迹从 Agent cache 自动构建，不在线探索真实模型。轨迹类型包括：

- 基础评分轨迹：`ROUTE_CHEAP -> STOP`、`ROUTE_MID -> STOP`、`ROUTE_STRONG -> STOP`。
- A2A 通信轨迹：覆盖 `ROUTE_CHEAP -> VERIFY -> STOP`、`ROUTE_CHEAP -> A2A_ASK -> STOP`、`ROUTE_CHEAP -> A2A_ASK -> ARBITRATE -> STOP`、`ROUTE_MID -> A2A_ASK -> ARBITRATE -> STOP`、`ROUTE_CHEAP -> VERIFY -> A2A_ASK -> ARBITRATE -> STOP` 等实验设计方案第 14.1 节列出的候选路径。
- 边界轨迹：Always-Cheap、Always-Strong 等成本和质量边界。
- Hindsight Budget Relabeling 轨迹：同一轨迹重标注多个预算版本。

奖励函数同时考虑评分质量、成本、延迟、预算违规和通信收益。主指标使用 QWK，辅助指标包括 MAE、RMSE、Within-1 Accuracy、Cost per Paper、Paper Latency、Token Usage、Agent Calls、A2A Messages、Useful Communication Rate、Disagreement Reduction、Arbitration Rate 和 Budget Violation Rate。

评分质量奖励中的误差项必须使用实验设计方案定义的归一化评分误差 `E_i`，以避免 DREsS、ASAP-SAS 和 SAS-Bench 的不同分值范围直接影响难度标签、Agent capability profiles、reward scale 和跨数据集比较。原始尺度 MAE 只用于报告和可解释分析，不用于替代归一化误差。

奖励函数按实验设计方案第 13 节分为单题质量奖励、步级奖励、终止奖励和试卷级奖励。单题质量奖励为 `Q_i = 1 - E_i`；步级奖励惩罚 cost、latency、A2A message 和无效通信，并奖励分歧下降；终止奖励惩罚 item 级成本、延迟、消息和预算违规；paper 级奖励汇总全卷质量、总成本、makespan、消息数和预算违规。所有 reward 计算都必须保存到 trajectory 或 audit 产物中，方便复算。

## 实验分组

### 主实验方法

| 方法 | 定位 | 说明 |
|---|---|---|
| Cheap-only | 成本下界 baseline | 所有 item 使用 CheapAgent |
| Strong-only | 质量上界 baseline | 所有 item 使用 StrongAgent |
| Static Difficulty Router | 静态难度 baseline | Easy -> Cheap，Medium -> Mid，Hard -> Strong |
| CP-Router-Grade | 不确定性升级 baseline | 基于置信度、分歧或 conformal-style 信号决定是否升级 |
| SeqRoute-Grade | 预算感知路由 baseline | 预算感知 CQL 路由，但不使用 A2A 通信和 Agent-Item Graph |
| A2A-DyGrade-RL | 本文方法 | 完整 CAG-CQL Router |

### 消融实验

| 消融版本 | 去掉内容 | 验证目的 |
|---|---|---|
| w/o A2A Communication | `VERIFY`、`A2A_ASK`、`ARBITRATE` | A2A 通信是否有效 |
| w/o Budget State | 剩余 cost、latency、calls、messages | 预算状态是否必要 |
| w/o Difficulty State | 题目难度特征 | 难度建模是否有效 |
| w/o Agent Capability State | Agent 能力画像 | Agent 能力建模是否有效 |
| w/o HBR | Hindsight Budget Relabeling | 预算重标注是否有效 |

第一版不进行 BC、Decision Transformer 或普通 CQL 的横向算法比较；实验设计方案明确只保留一个主算法：CAG-CQL。其他方法以自动阅卷路由 baseline 或消融形式出现。

### Cost-QWK 曲线

通过改变奖励函数中的成本惩罚系数生成多个成本点：

```text
beta = 0.05, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0
```

比较 Static Difficulty Router、CP-Router-Grade、SeqRoute-Grade 和 A2A-DyGrade-RL，输出 `cost_qwk_curve.csv`、曲线图和 Pareto Frontier 标记。

## 阶段计划与门禁

### Phase 1：数据处理与审计

**目标**：把 DREsS、ASAP-SAS、SAS-Bench 准备为统一 item-level 和 paper-level 数据，并证明 split 无泄漏。

**核心产物**：

- `data/processed/items_train.jsonl`
- `data/processed/items_dev.jsonl`
- `data/processed/items_test.jsonl`
- `data/processed/papers_train.jsonl`
- `data/processed/papers_dev.jsonl`
- `data/processed/papers_test.jsonl`
- `data/processed/split_manifest.csv`
- `data/processed/paper_manifest.csv`
- `outputs/runs/<run_id>/reports/data_audit.md`
- `outputs/runs/<run_id>/reports/data_distribution.csv`

**门禁**：

- 三个数据集均能进入 `train/dev/test`。
- item、prompt group、paper 均无跨 split 泄漏。
- score range 合法。
- 每条 item 保留原始 `gold_score`、`score_min`、`score_max`，并可据此计算 `R_i = score_max_i - score_min_i`。
- 审计报告必须验证 `R_i > 0`，并记录归一化评分误差公式 `E_i = abs(pred_score_i - gold_score_i) / R_i` 后续用于 Agent 误差、难度建模和奖励。
- paper 只引用同 split item。
- paper 构造报告必须统计每张 paper 的 dataset mix，并说明是否满足 2-3 ASAP-SAS、1-2 SAS-Bench、1 DREsS 的目标组合；不满足时必须解释原因。
- 空 prompt、空 answer、rubric/reference 缺失、重复 prompt-answer、DREsS 过滤数量都有审计记录。

**当前状态**：基础数据构建和第一版正式数据审计已完成。审计发现三项需在进入 Phase 2 前返修的数据隐患：exact prompt-answer 跨 split 重复键、主实验 paper dataset mix 大量偏离目标、`paper_manifest.csv` 中 `prompt_group` 为空。因此进入 Agent cache 前必须先完成数据修复 v2：

- split 逻辑必须把同一 prompt group 和同一 exact prompt-answer key 合并为同一防泄漏组件后再划分，避免同题面同答案跨 split。
- 主实验 `papers_train/dev/test.jsonl` 必须使用 strict mix：每张 paper 总数为 5，包含 2/3 个 ASAP-SAS、1/2 个 SAS-Bench、1 个 DREsS。
- 剩余 item 可在后续生成 `papers_relaxed_*.jsonl` 作为鲁棒性或附录实验，但不得混入主实验主表。
- `paper_manifest.csv` 必须补齐 `dataset`、`prompt_group`、`paper_dataset_mix`、`mix_status`、`deviation_reason` 等可审计字段。
- 数据审计必须将 exact prompt-answer 跨 split、strict paper mix 偏离和 manifest prompt group 为空升级为阻塞性错误。

### Phase 2：Agent cache、difficulty labels 与 capability profiles

**目标**：对 prepared items 运行或模拟五类 Agent，生成可复用缓存，并基于 train/dev 数据构建难度标签和 Agent 能力画像。

**核心产物**：

- `outputs/runs/<run_id>/predictions/agent_cache/*.jsonl`
- `data/processed/difficulty_labels.jsonl`
- `outputs/runs/<run_id>/reports/agent_cache_audit.md`
- `outputs/runs/<run_id>/reports/agent_capability_table.csv`

**门禁**：

- 先通过独立的 `fixture_smoke_<序号>` 运行；真实模型 pilot 使用 `real_pilot_<序号>`，正式缓存使用 `formal_agent_cache_<序号>`，三类 cache、checkpoint、阈值和 predictor 禁止跨模式续跑或复用。
- cache schema 必须记录 `run_id`、`execution_mode` 和 `is_fixture`，并校验它们与运行目录前缀一致。
- 每个被接受 item 至少拥有 Cheap/Mid/Strong 输出。
- EvidenceAgent 和 ArbitratorAgent 输出可用于轨迹构建。
- Agent 误差、difficulty labels 和 capability profiles 中的误差项必须使用 `E_i = abs(pred_score_i - gold_score_i) / (score_max_i - score_min_i)`。
- difficulty labels 必须输出 Easy、Medium、Hard 和难度分数 `D_i`；capability table 必须输出 QWK、MAE、Cost、Latency、Calibration。
- train gold 只用于构造 train difficulty supervision；Easy/Medium/Hard 阈值只从 train 分布冻结，dev 仅用于有限校验，test 只能使用推理时可见特征预测难度。
- 正式 difficulty predictor 固定为 `HistGradientBoostingRegressor`，`Ridge` 仅作诊断基线；fixture predictor 与正式 predictor 必须保存在不同运行目录，fixture/pilot predictor 不得进入正式 Router。
- capability profile 和 difficulty labels 不使用 test split 拟合。
- test cache 只允许 final evaluation 读取，不进入 replay buffer、调参和能力画像拟合。

### Phase 3：离线轨迹与 replay buffer

**目标**：从 Agent cache 和 paper splits 构建可训练的离线轨迹。

**核心产物**：

- `data/trajectories/train_trajectories.jsonl`
- `data/trajectories/dev_trajectories.jsonl`
- `data/trajectories/hbr_trajectories.jsonl`
- `outputs/runs/<run_id>/reports/trajectory_audit.md`

**门禁**：

- 轨迹状态、动作、奖励、下一状态和 action mask 完整。
- 轨迹必须覆盖基础轨迹、A2A 通信轨迹、Always-Cheap、Always-Strong 和 HBR 预算重标注。
- replay buffer 不包含 test split。
- 边界轨迹、A2A 轨迹和 HBR 轨迹可分别统计数量和覆盖率。

### Phase 4：CAG-CQL Router 训练

**目标**：训练完整 A2A-DyGrade-RL Router，并在 dev split 上选择配置。

**核心产物**：

- `outputs/runs/<run_id>/checkpoints/cag_cql/`
- `outputs/runs/<run_id>/logs/train.log`
- `outputs/runs/<run_id>/reports/dev_metrics.csv`

**门禁**：

- action mask 单元测试通过。
- loss、dev QWK、Cost、Budget Violation 可监控。
- CAG-CQL 训练必须包含 Double Q Network、Target Network、Masked Bellman Target 和 Masked CQL Conservative Penalty。
- 所有超参数、随机种子和配置快照进入 `outputs/runs/<run_id>/configs/`。

### Phase 5：主实验、baseline、消融与曲线

**目标**：在同一 test split、同一 Agent cache、同一 paper budgets 和同一评价脚本下比较所有方法。

**核心产物**：

- `outputs/runs/<run_id>/reports/main_results.csv`
- `outputs/runs/<run_id>/reports/ablation_results.csv`
- `outputs/runs/<run_id>/reports/cost_qwk_curve.csv`
- `outputs/runs/<run_id>/figures/cost_qwk_curve.*`
- `outputs/runs/<run_id>/figures/pareto_frontier.*`
- `outputs/runs/<run_id>/reports/case_study.md`

**门禁**：

- 主实验表包含所有方法和核心指标。
- 消融表包含五个消融版本。
- Cost-QWK 曲线覆盖所有 beta 点。
- 主实验表列必须对齐实验设计方案：Method、QWK、MAE、Cost、Paper Latency、A2A Msg、Budget Violation。
- 消融表列必须对齐实验设计方案：Method、QWK、MAE、Cost、Latency、Msg、Violation。
- predictions 和 router logs 能复算报告指标。

### Phase 6：论文材料与复现包

**目标**：把实验设置、指标定义、超参数、数据审计、结果表格、图和 case study 整理成论文可用材料。

**核心产物**：

- `outputs/runs/<run_id>/reports/experiment_readiness.md`
- `docs/paper/` 下的实验设置、指标说明、结果解读草稿
- README 或 quickstart 中的复现实验命令

**门禁**：

- 从保存的配置、predictions 和 logs 能重新计算主表。
- 所有路径符合 `AGENTS.md`。
- 无根目录散落实验产物。

## 技术上下文

**语言/版本**：Python 3.11+

**主要依赖**：PyTorch 用于路由模型和离线强化学习；pandas/numpy/scikit-learn 用于表格处理和指标；dataclasses 或 pydantic 用于 schema；PyYAML 用于配置；tqdm 用于批处理进度；matplotlib 用于绘图；pytest 用于验证。

**存储**：`data/` 保存原始数据、处理后数据和轨迹数据；`outputs/runs/<run_id>/` 保存每次运行的配置快照、日志、预测、checkpoint、报告和图。JSONL 存储记录和轨迹，CSV 存储统计和结果表，YAML 存储配置快照。

**测试**：pytest 单元测试和集成测试；smoke workflow 必须能在不调用实时模型的 fixture 数据上完成。

**目标平台**：Windows 或 Linux 本地研究工作站与可脚本化批处理环境。

**项目类型**：单体 Python 研究流水线，提供阶段化 CLI 脚本。

**性能目标**：完整实验复用 Agent cache，Router 训练和评价阶段不重复调用模型；全量实验前必须先通过 smoke run。

**约束**：不增加人工标签；主 split 必须防止 prompt-level leakage；所有报告必须能从保存的输入、配置、随机种子、predictions 和 logs 复现；实验输出不得散落在仓库根目录或旧式 `outputs/reports`、`outputs/logs` 等平铺目录。

**规模/范围**：三个公开数据集；每张合成 paper 5 到 8 个 item；五类 Agent 角色；六个主方法；五个消融版本；七个 Cost-QWK cost-penalty points。

## Constitution 检查

项目最高规则统一维护在仓库根目录 `AGENTS.md`，`.specify/memory/constitution.md` 只作为 spec-kit 指针。本计划应用以下门禁：

- 可复现性：每个主要阶段必须产生保存产物。
- 数据完整性：主测试评价中不得发生 item、prompt、paper、统计和缓存泄漏。
- 范围纪律：第一版是离线研究流水线，不是生产级阅卷服务。
- 评价公平性：所有方法必须共享相同 prepared data、paper budgets、Agent cache 和评价脚本。
- 文件管理：代码、文档、数据、运行日志和实验结果必须进入 `AGENTS.md` 规定的目录；每次运行必须写入 `outputs/runs/<run_id>/`。

门禁状态：通过。

## 项目结构

### 文档结构（本功能）

```text
specs/001-a2a-dygrade-rl/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── artifact-schemas.md
│   └── cli-contract.md
└── tasks.md
```

### 源代码结构（仓库根目录）

```text
configs/
├── dataset.yaml
├── agents.yaml
├── router.yaml
├── cag_cql.yaml
├── experiment.yaml
└── experiments/

data/
├── raw/
├── processed/
└── trajectories/

docs/
├── design/
├── paper/
└── logs/

prompts/
├── cheap_scorer.txt
├── mid_scorer.txt
├── strong_scorer.txt
├── evidence_agent.txt
└── arbitrator_agent.txt

src/
└── a2a_dygrade_rl/
    ├── datasets/
    ├── agents/
    ├── a2a/
    ├── graph/
    ├── router/
    ├── rl/
    ├── baselines/
    ├── evaluation/
    └── utils/

scripts/
├── 00_audit_prepared_data.py
├── 01_build_items.py
├── 02_build_papers.py
├── 03_run_agent_cache.py
├── 04_build_difficulty_labels.py
├── 05_build_trajectories.py
├── 06_train_cag_cql.py
├── 07_eval_baselines.py
├── 08_eval_ablation.py
└── 09_plot_cost_qwk_curve.py

outputs/
└── runs/
    └── <run_id>/
        ├── configs/
        ├── logs/
        ├── predictions/
        ├── checkpoints/
        ├── reports/
        └── figures/

tests/
├── unit/
├── integration/
└── fixtures/
```

**结构决策**：采用单体 Python 项目，使用 `src/a2a_dygrade_rl/` 包结构承载实验模块，使用 `scripts/` 做阶段编排，使用 `outputs/runs/<run_id>/` 隔离每次运行产物。这样可以独立实现数据层、Agent 缓存层、轨迹层、模型层和评价层，同时保持实验可从命令行复现，并避免代码、日志和实验结果放错位置。

## 当前执行状态与下一步

截至 2026-07-11，Phase 1 数据处理与正式数据审计已完成；Phase 2 的 `T031-T042A` 也已完成 Fixture 实施和 `fixture_smoke_001` 验证。该 smoke 使用 20 个 train items 生成 240 条合法 cache records、20 条 difficulty supervision/prediction 和 45 个 train-only capability profiles，0 failure，resume 前后 cache 哈希一致。下一步进入真实模型 Pilot 的方案与成本门禁；未获得单独批准前，不安装真实模型 SDK/权重、不调用付费 API，也不运行 `real_pilot` 或 `formal_experiment`。

## 复杂度跟踪

当前没有需要说明的 constitution 违规。由于旧版 `docs/design/实验计划.md` 中存在少量旧路径写法，例如 `outputs/reports/`，本计划统一修正为 `outputs/runs/<run_id>/reports/`，以 `AGENTS.md` 为准。
