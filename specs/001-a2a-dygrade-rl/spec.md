# 功能规格：A2A-DyGrade-RL 实验流水线

**功能分支**：`001-a2a-dygrade-rl`

**创建日期**：2026-07-04

**状态**：草案

**输入**：用户描述：“使用 spec-kit 将 A2A-DyGrade-RL 实验设计方案和实验计划转化为规格、实现计划和可执行任务清单。”

## 用户场景与测试 *(必填)*

### 用户故事 1：构建可比较的实验数据（优先级：P1）

研究者可以将公开自动评分数据集整理为统一的 item-level 和 paper-level 格式，使所有路由方法都在相同输入、分数范围、预算和数据划分上进行评价。

**优先级原因**：如果没有可靠的统一数据层，后续 Agent 缓存、路由策略和实验结果比较都不可信。

**独立测试**：使用每个目标数据集的小样本运行数据准备流程，确认生成的 item 文件、paper 文件和 split 文件字段完整，并且不存在 prompt 泄漏。

**验收场景**：

1. **给定** 原始公开评分数据可用，**当** 运行数据准备流程，**则** 每个 item 都包含 prompt、answer、rubric 或 reference、gold score、score range、question type、source dataset 和 metadata。
2. **给定** 已生成 item 文件，**当** 运行 paper 构造流程，**则** 每张 paper 包含 5 到 8 个 item 引用，并包含完整 paper budget。
3. **给定** train、dev、test 划分已经创建，**当** 比较不同 split 中的 prompt 标识，**则** 同一原始题目的 prompt 不会同时出现在训练集和测试集中。

---

### 用户故事 2：缓存多 Agent 阅卷证据（优先级：P2）

研究者可以对每个 item 一次性运行或模拟五类评分相关 Agent，缓存其输出，并在离线轨迹构建、baseline 评价和成本分析中复用这些输出。

**优先级原因**：项目依赖可复现的离线强化学习轨迹；如果反复实时调用模型，成本、延迟和复现性都难以控制。

**独立测试**：对小样本 split 缓存 Agent 输出，确认每个 item 都有合法评分输出、置信度、成本、延迟、token 使用量，以及可选证据或仲裁记录。

**验收场景**：

1. **给定** 规范化 item 文件存在，**当** 运行 Agent 缓存流程，**则** CheapAgent、MidAgent、StrongAgent、EvidenceAgent 和 ArbitratorAgent 输出被写入统一 schema。
2. **给定** 一个 Agent 输出已缓存，**当** 检查该记录，**则** 它包含预测分数、置信度、成本、延迟、token 使用量和来源 item 标识。
3. **给定** Agent 缓存存在，**当** 计算难度与能力摘要，**则** 能够在不增加人工标注的情况下得到 item difficulty labels 和 Agent capability profiles。

---

### 用户故事 3：训练并评价路由策略（优先级：P3）

研究者可以构建离线路由轨迹，训练 A2A-DyGrade-RL Router，并在同一评价协议下与固定模型、静态难度、不确定性升级和预算感知路由 baseline 比较。

**优先级原因**：该故事产出核心研究证据，即通信感知动态路由是否改善 cost-quality tradeoff。

**独立测试**：在小 paper 集合上运行 smoke experiment，确认主实验结果、消融结果、预算指标、通信指标和 Cost-QWK 曲线数据均可生成。

**验收场景**：

1. **给定** Agent cache 和 paper splits 存在，**当** 构建轨迹，**则** 生成基础轨迹、A2A 轨迹、边界轨迹和 hindsight-budget-relabelled 轨迹。
2. **给定** 轨迹存在，**当** 训练 Router，**则** 生成 checkpoint 和训练日志，并记录 dev 集质量、成本和预算违规指标。
3. **给定** 已训练策略和 baseline 策略可用，**当** 运行评价，**则** 从相同 test split 生成主实验比较、消融比较和 Cost-QWK 曲线报告。

---

### 边界情况

- 源数据集缺少 reference answer；当 rubric 和 answer 足以支持评分时，该 item 仍然有效。
- 源数据集使用非零起点或非统一分数范围；归一化误差使用每个 item 自己的分数范围，同时报告保留原始尺度 MAE。
- 某个 split 太小，无法满足目标 dataset mix；流程必须报告样本不足并跳过非法 paper 构造，而不是静默生成畸形 paper。
- Agent cache 记录缺失、格式错误或分数越界；下游轨迹构建必须拒绝该记录并报告受影响 item。
- 某个路由动作会超过 cost、call、latency 或 message budget；有效动作集合必须屏蔽该动作，或在评价时记录预算违规。
- A2A 通信没有降低分歧；该事件必须计为无效通信，用于后续分析。

## 需求 *(必填)*

### 功能需求

- **FR-001**：系统必须将 DREsS、ASAP-SAS 和 SAS-Bench 记录规范化为统一 item-level schema。
- **FR-002**：系统必须保留每个 item 的 source dataset、question type、prompt、student answer、gold score、score minimum、score maximum，以及难度估计所需 metadata。
- **FR-003**：系统必须构造 paper-level 样本，每个样本包含 5 到 8 个 item 引用，并显式包含 cost、latency、Agent calls 和 A2A messages 预算。
- **FR-004**：系统必须支持 train、dev、test 划分，并防止训练与测试评价之间发生 prompt 泄漏。
- **FR-005**：系统必须用可复用 schema 缓存 CheapAgent、MidAgent、StrongAgent、EvidenceAgent 和 ArbitratorAgent 输出。
- **FR-006**：系统必须为每个缓存 Agent 输出记录 predicted score、confidence、cost、latency、token usage、source item 和 Agent identity。
- **FR-007**：系统必须使用静态复杂度、Agent error、Agent disagreement 和 confidence dispersion 信号推导 item difficulty labels。
- **FR-008**：系统必须按 question type 和 difficulty 推导 Agent capability profile，包含质量、成本、延迟和校准相关摘要。
- **FR-009**：系统必须用 item status、difficulty status、Agent capability status、A2A history 和 remaining budget 表示路由状态。
- **FR-010**：系统必须支持 CheapAgent、MidAgent、StrongAgent、evidence verification、second opinion、arbitration 和 stop item 等路由动作。
- **FR-011**：系统必须根据 item completion、missing initial scores、insufficient budget、missing disagreement、exhausted message budget 或 repeated arbitration 拒绝非法路由动作。
- **FR-012**：系统必须构建覆盖 basic routing、A2A communication、arbitration、always-cheap、always-strong 和 hindsight budget relabeling 的离线轨迹。
- **FR-013**：系统必须使用离线轨迹和预算感知奖励信号训练并评价 A2A-DyGrade-RL 路由策略。
- **FR-014**：系统必须在相同 prepared test papers 上评价 Cheap-only、Strong-only、Static Difficulty Router、CP-Router-Grade、SeqRoute-Grade 和 A2A-DyGrade-RL。
- **FR-015**：系统必须评价五个消融版本：without A2A communication、without budget state、without difficulty state、without Agent capability state 和 without hindsight budget relabeling。
- **FR-016**：系统必须生成 main results、ablation results、Cost-QWK curve data、routing logs、A2A logs、budget logs 和 case studies。
- **FR-017**：系统必须报告 QWK、MAE、RMSE、Within-1 Accuracy、Cost per Paper、Paper Latency、Token Usage、Agent Calls、A2A Messages、Useful Communication Rate、Disagreement Reduction、Arbitration Rate 和 Budget Violation Rate。
- **FR-018**：系统必须保证每个主要实验阶段可从保存的输入、配置、随机种子和中间产物复现。

### 关键实体 *(涉及数据时必填)*

- **Item**：单个学生作答，包含 prompt、answer、rubric 或 reference answer、score range、gold score、question type、dataset source 和 metadata。
- **Paper**：合成试卷级样本，包含多个 item identifiers 和 paper-level budget。
- **Agent Output**：某个 Agent 对某个 item 的缓存结果，包含 score、confidence、cost、latency、token usage，以及可用时的 explanation 或 evidence。
- **Difficulty Label**：基于复杂度和 Agent 行为推导的 item 难度标签和数值分数。
- **Agent Capability Profile**：某个 Agent 在不同题型和难度上的聚合表现与成本画像。
- **A2A Message**：验证、第二意见、质疑、解释或仲裁等通信事件。
- **Routing State**：Router 在动作选择前看到的 item progress、difficulty、Agent capability、A2A history 和 remaining budget 快照。
- **Routing Action**：对某个 item 选择的合法操作，包括 route、verify、ask、arbitrate 或 stop。
- **Trajectory**：用于训练或评价路由行为的离线 state、action、reward、mask 和 outcome 序列。
- **Experiment Report**：一次完整评价产生的结果表、曲线、日志或 case study。

## 成功标准 *(必填)*

### 可衡量结果

- **SC-001**：100% 被接受的 prepared items 包含必需的 identity、scoring、source 和 metadata 字段。
- **SC-002**：训练 prompt 与测试 prompt 之间的 test split prompt leakage rate 为 0。
- **SC-003**：在 split 样本量足够时，至少 95% 构造出的 papers 满足配置的 item-count 和 dataset-mix 规则。
- **SC-004**：100% 被接受的 Agent cache records 包含合法 score、confidence、cost、latency、token usage、item identity 和 Agent identity 字段。
- **SC-005**：六个主实验比较方法均在相同 test papers 上评价，并产出 QWK、MAE、Cost per Paper、Paper Latency、A2A Messages 和 Budget Violation Rate。
- **SC-006**：五个消融版本均在 ablation report 中产出完整结果行。
- **SC-007**：Cost-QWK curve data 对每个曲线比较方法均包含七个配置好的 cost-penalty points。
- **SC-008**：最终实验包保存足够产物，使每个报告表都能从 stored predictions 和 logs 复现。
- **SC-009**：在提供 raw data 和必要凭据后，smoke run 能够无需人工干预完成完整 data-to-report 流程。

## 假设

- 第一版实现目标是离线研究流水线，不是生产级阅卷服务。
- 公开数据集除确定性规范化、划分和 paper-level 重组外，不进行额外修改。
- 不引入额外人工标签。
- Agent 输出可以来自实时模型调用，也可以在 smoke test 中来自确定性 fixtures，但二者必须使用相同 cache schema。
- 主实验默认使用 prompt-level 和 paper-level split。
- 第一里程碑优先保证可复现实验产物，而不是实时用户交互。
- 项目最高规则以仓库根目录 `AGENTS.md` 为准，`.specify/memory/constitution.md` 仅作为 spec-kit 入口指针；本规格必须遵守 `AGENTS.md` 中关于简体中文、离线论文实验、可复现性、数据划分、防泄漏、公平评价、运行产物和目录职责的约束。
