# 功能规格：面向模拟试卷级自动阅卷的质量约束多智能体动态路由实验流水线

**功能分支**：`001-a2a-dygrade-rl`
**创建日期**：2026-07-04
**最后修订**：2026-08-19
**状态**：V1.8 方案 A Official SSH Remote 控制面已完整验收；V1.6 本地准备 P1–P8、Dataset Semantic V2、internal audit、AutoDL 仓库同步、14B BF16 下载/完整性校验、冻结 5 Item 的 10 文件传输、远程 Codex CLI、进程级 Mihomo、双账号共享会话切换、远程 bootstrap Smoke、本机 Codex 官方 SSH Connection UI 与桌面只读 Smoke 均已完成；2026-08-19 已完成 T112A 14B 下载 Profile A 本地回传复核与 T115A Token/预算冻结，阶段 B 已收敛。GPU 当前关闭；推理环境、14B 真实 Smoke、3B/8B、真实 5 Item 和 30 Item 尚未完成。
**输入**：用户确认主研究对象是固定 Agent 环境中的动态路由增益，而不是先把基础阅卷器做到生产级准确率；DREsS 主实验采用无 Anchor 的 Content、Organization、Language 三维评分；ASAP-SAS 必须恢复官方 Prompt/Rubric 并使用 Score1 作为最终 Gold；SAS-Bench 必须从 Step Item 改为完整学生回答 Item；旧 100 Item Pilot 只保留为 cliproxy、模型身份、结构化输出、Token 与成本链路的工程证据，不得作为正式论文评分结果或 Formal cache。

---

## 1. 研究目标与范围

本文不训练、不微调任何评分 Agent，也不研究系统能够批改什么题。研究对象是在固定评分 Agent 池中，对一份包含多道真实学生作答的**模拟试卷评分 episode**进行质量约束的动态资源调度。

基础 Agent 的绝对准确率不需要先达到生产部署水平；主论文结论限定为：在语义有效、无 Anchor、所有方法共享相同 prepared data、Agent cache、预算和评价脚本的固定环境中，A2A-DyGrade-RL 是否改善评分质量与资源消耗的 Pareto Frontier。低绝对指标可以如实报告，但语义缺失、占位 Rubric、错误评分单位、常数输出或接近随机的退化环境不得用于支持算法结论。

在任何新的正式 Agent cache、Router 训练或最终评价前，三个数据集必须先完成 Dataset Semantic V2 整改并通过 fail-closed Semantic Readiness Gate；旧 prepared data 和旧 Pilot cache 不能被直接晋升为正式实验资产。

Router 每一步联合决定：

1. 下一步处理哪道作答；
2. 调用哪个评分 Agent；
3. 是否进行 Rubric 证据核验；
4. 是否请求独立第二意见；
5. 是否进行评分仲裁；
6. 是否满足安全停止条件；
7. 如何在多道作答之间分配剩余成本、累计延迟、调用次数和 A2A 通信资源。

统一原则为：

> **先通过相对于固定参考策略的零容忍配对统计准入门，再以准入候选中的 Quality Champion 作为质量保护基准；只有能够证明评分质量和严重错分风险均不劣于冠军的候选，才允许比较资源消耗。**

任何质量下降换取的资源下降均不得作为有效研究成果。

---

## 2. 术语和研究边界

### 2.1 模拟试卷

`Paper` 是由真实题目、真实学生作答、Rubric/参考答案和原数据集人工评分标签重组得到的多题评分 episode。它用于构造共享预算与序列决策环境，但不声称对应现实中的某个 `student_id + exam_id` 原始试卷。

代码字段 `paper_id` 可以继续保留；论文语义为 `simulated_paper_id` 或 `scoring_episode_id`。

### 2.2 冻结 Agent

冻结表示 Agent 的模型、模型版本、Prompt、生成参数、输出结构、解析规则、功能角色和成本定义在正式 cache 生成前确定，Router 训练期间不再改变。冻结不表示已知每道题的最优 Agent，也不等于能力画像。

### 2.3 Agent 能力画像

正式能力画像是由冻结 Agent 的 `train_fit` cache 自动统计得到的历史条件性能先验；如需 low-support 或置信校准边界，只能由 `train_calibration` 按预注册程序自动校准，且不得回流 Router 梯度训练。它不得使用 dev/test，不得直接输出具体 Item 的最优 Agent 标签，并必须作为可消融状态组件评价。

### 2.4 停止风险头

停止风险头是 Router 内部共享 CAG 编码器上的安全预测头，用于估计当前状态执行 `STOP` 后 `Gate Error > 0.25` 的风险。它不是新的评分模型，不输出学生分数，也不指定下一步调用哪个 Agent。`0.25` 是冻结指标阈值；`train_calibration` 只校准预测风险概率的决策边界。

### 2.5 共享资源约束

每份模拟试卷共享四维资源向量：

```text
max_cost
max_elapsed_time
max_agent_calls
max_a2a_exchanges
```

第一版 `max_elapsed_time` 表示串行 Agent 调用的累计延迟，不声称建模真实并发系统的 makespan。

### 2.6 正式质量指标协议

`Quality Metric Protocol` 是在真实 Pilot 与 Router 结果前冻结的机器可读协议，至少包含：Gate Error 与未完成处理、Severe/Extreme 阈值、Unsafe Stop 分母和零 STOP 处理、Macro-NMAE、固定11档 QWK、QWK readiness、Bootstrap 参数，以及 Dev 的固定参考准入、Quality Champion 质量词典序、候选对冠军保护门和资源词典序。

### 2.7 配对统计质量门

`Paired Bootstrap Gate` 在相同 split、Paper、Agent cache 和预算档位上，对候选与指定比较基准使用相同 Paper 重采样索引，执行5000次单侧95%配对 Cluster Bootstrap。固定参考策略用于第一层准入门，Quality Champion 用于第二层质量保护门；两层均采用零非劣效界，任一主指标未定义、置信区间跨0或未达到规定边界，均令对应质量门失败。

### 2.8 内部 Item Split

`Internal Item Split` 是在 Dataset Semantic V2 外部 train 内部进行的第二层拆分。它从通过 Semantic Readiness 的外部 train 主路由候选 Item 出发，以 dataset prompt group、source lineage 及 exact-answer/leakage component 的传递连通分量为不可拆分单元，目标约80%/20%分配到 `train_fit/train_calibration`。它不直接切分已有 `paper_train_*`，也不沿用旧 Item 数量。

### 2.9 内部重建 Paper

`Internal Rebuilt Paper` 是在 Item 原子分配冻结后，分别在 `train_fit` 和 `train_calibration` Item 池中重新构造的固定5题 strict episode。它使用新的 internal `paper_id`，原外部 train Paper 只作来源溯源，不作为内部 split 单元。

### 2.10 Calibration Package

`Calibration Package` 是某个冻结 Router checkpoint 加上该 checkpoint 自动校准的 STOP 安全概率边界、冻结质量参考、预算、support/catalog 与协议 hash 的完整候选方案。`train_calibration` 只生成这些候选 Package，不在它们之间选择最终冠军。

### 2.11 Quality Champion

`Quality Champion` 是 Dev 在全部通过固定参考策略准入门的候选 Router Policy Package 中，不使用任何资源指标，仅按跨预算最坏 Severe Error、跨预算最坏 Unsafe Stop、跨预算平均 Macro-NMAE、跨预算平均 Macro-QWK 和 Package ID 的固定质量词典序自动确定的唯一质量最优方案。固定参考、Baseline 和消融结果不参与冠军或最终 checkpoint 选择。

### 2.12 Quality Protection Gate

`Quality Protection Gate` 以 Quality Champion 为比较基准，对其他已准入候选在每个预算档位重新执行相同的四项 Paper 级配对 Bootstrap 零非劣效检验。只有在 Severe、Unsafe Stop、Macro-NMAE 和 Macro-QWK 四项均能证明不劣于冠军的候选，才允许进入资源词典序。

### 2.13 完整 Fixture Smoke

`Fixture Smoke` 是使用专用确定性测试资产、`FixtureClient` 和 fixture-only 候选 checkpoint 对正式核心流水线进行的小规模端到端验收。它必须复用 `src/a2a_dygrade_rl/` 中与正式实验相同的 split、Paper rebuild、cache、自动校准、质量门、Package 和 Dev selector 实现；只允许数据、配置和外部 Agent 边界使用 fixture。Fixture 输入位于 `tests/fixtures/quality_constrained_smoke/`，测试位于 `tests/integration/test_quality_constrained_smoke.py`，配置位于 `configs/experiments/fixture_smoke.yaml`，持久化验收产物只写入 `outputs/runs/fixture_smoke_<run_id>/`。所有 Fixture 产物必须标记或由完整 artifact inventory 绑定 `formal_eligible=false`，不得进入正式训练、能力画像、预算、参考、checkpoint 选择或论文结果汇总；正式入口拒绝必须由实际调用探针验证，候选进入 Dev/Test-like 时必须真正执行冻结 STOP 边界，预算不可行候选不得仅凭质量门通过而晋级。

### 2.14 Dataset Semantic V2

`Dataset Semantic V2` 是对 ASAP-SAS、DREsS 和 SAS-Bench 的正式语义整改版本。它不是对旧 JSONL 的局部覆盖，而是根据原始资料重新确定题目内容、评分单位、Gold 定义、分数范围、Prompt group、来源溯源和异常隔离规则，并重新生成 Item、split manifest、Paper、内部拆分和所有后续 cache。

### 2.15 Semantic Readiness Gate

`Semantic Readiness Gate` 是任何真实 Agent 调用前的 fail-closed 数据门禁。它同时执行全局完整性、数据集专用语义、评分范围、来源哈希、quarantine、split 泄漏、Paper 引用和模型可见输入 Gold 隔离检查。只有状态为 `PASS` 且 `formal_cache_eligible=true` 的 Dataset Semantic V2 资产可以进入真实 Agent Pilot 或 Formal cache。

### 2.16 无 Anchor 主实验协议

`anchor_mode=none` 表示主实验不向 Agent 提供从 `train_fit` 选择的低、中、高分作文示例，也不把完整已评分学生回答作为 Few-shot demonstration。数据集官方题目、参考答案、评分档描述和 Rubric 原文仍可作为任务定义使用；ASAP-SAS 的完整 Anchor Paper PDF、DREsS 的训练作文 Anchor 和 SAS-Bench 的 Gold Step 标签均不得进入模型可见输入。Anchor 如后续研究，只能作为独立配置、独立 Prompt hash、独立 cache 和独立报告的鲁棒性实验。

### 2.17 Scoring Unit

`Scoring Unit` 表示一个 Item 所对应的评分对象。ASAP-SAS 的单位是一条短答案，DREsS 的单位是一篇完整作文，SAS-Bench 的单位是一条完整学生回答而不是单个 Step。评分单位一旦改变，旧 Item ID、split、Paper 和 Agent cache 全部失效。

### 2.18 Quarantine Record

`Quarantine Record` 记录因缺失学生作答、结构损坏、分数越界、Gold 内部不一致、无法关联来源或缺少必要评分信息而不能进入正式数据的原始记录及原因。异常记录不得被静默跳过，也不得为追求 Item 数量而自动修补为猜测内容。

## 3. 用户场景与测试

### 用户故事 1：构建可审计的外部与内部模拟试卷数据（优先级：P1）

研究者可以将 DREsS、ASAP-SAS 和 SAS-Bench 规范化为统一 Item，保持外部 `train/dev/test` 防泄漏，并在外部 train 内先按题目组拆 Item、再分别重建 `train_fit/train_calibration` 模拟试卷，使参数训练和边界校准真正独立。

**优先级原因**：如果直接拆现有 train Paper，同一 prompt group 会跨两个内部 split；如果 prepared data、内部 Item 分配和重建 Paper 不可审计，后续 Agent cache、校准、轨迹和论文结果均不可信。

**独立测试**：运行 Dataset Semantic V2 资源审计、prepared data audit、实际 Agent request Gold 隔离检查与内部 split/rebuild audit，验证三个数据集的评分单位、Gold 定义、语义字段、quarantine、分值范围、Item/Prompt/Paper 泄漏、strict paper mix、leftover 和角色消费边界。

**验收场景**：

1. **给定** 三个原始数据集，**当** 运行数据准备流程，**则** 每条 Item 包含题目、作答、Rubric 或参考答案、gold score、分值范围、题型、来源和可审计 metadata。
2. **给定** 外部 split Item，**当** 构造模拟试卷，**则**主实验每份 Paper 固定5道题，并满足已配置的 strict dataset mix。
3. **给定** 外部 train/dev/test，**当** 运行审计，**则** Item、Prompt、Paper 和 exact prompt-answer 跨 split 泄漏均为0。
4. **给定** 已通过 Semantic Readiness Gate 的 Dataset Semantic V2 外部 train Item 池，**当** 构建内部 split，**则**程序以 prompt/leakage connected component 为不可拆分单元分配 `train_fit/train_calibration`，而不是分配现有 `paper_train_*`。
5. **给定** 内部 Item 分配，**当** 构造内部 Paper，**则**分别产生新的 `paper_train_fit_*` 和 `paper_train_calibration_*`，每份固定5题并满足 strict mix。
6. **给定** 目标80%/20%与大型 prompt group，**当** 精确比例和 group 完整性冲突，**则**保持 group 完整并记录实际比例、偏差和确定性选择依据，不拆 group。
7. **给定** 无法组成 strict Paper 的 Item，**当** 构建结束，**则**将其记录为 leftover 和原因，不跨内部 split 借题、不静默丢失。
8. **给定** internal manifests，**当** 运行审计，**则**内部 Item、prompt group、exact-answer component、Paper overlap、跨 split 引用和 strict mix 违规均为0。
9. **给定** ASAP-SAS 原始 TSV 与官方描述 ZIP，**当** 构建 Item，**则**每个 EssaySet 使用真实题目与官方 Rubric，`gold_score` 等于 `Score1`，`Score2` 只作评分者一致性 metadata，任何 ZIP/附件占位文本数量为0。
10. **给定** DREsS 主数据，**当** 构建 Item，**则**只使用非空完整作文，Gold 同时包含 Content、Organization、Language 三个维度，总分严格等于三维之和，主实验不提供 Anchor，DREsS_CASE 不进入主实验。
11. **给定** SAS-Bench 顶层学生回答，**当** 构建 Item，**则**一个顶层回答只生成一个完整回答 Item，`gold_score=manual_label`、`score_max=total`，有序 Step 仅用于重建完整回答和隐藏审计，不再把单个 Step 当作主实验 Item。
12. **给定** 任一语义字段缺失、评分范围不合法、Gold 内部不一致或来源无法确认的记录，**当** 构建结束，**则**生成带明确原因的 quarantine record，禁止静默跳过或进入正式 Paper。
13. **给定** Dataset Semantic V2 尚未通过全部门禁，**当** 尝试运行真实 Agent cache，**则**流程必须拒绝；给定旧 prepared data 或旧 Pilot cache，正式入口同样必须拒绝复用。

### 用户故事 2：冻结并缓存多 Agent 评分证据（优先级：P2）

研究者可以在不向 Agent 暴露 gold score 的前提下，对主路由范围中的 Item 运行或模拟五类 Agent，并缓存分数、置信度、证据、成本、累计延迟和上下文信息，供所有方法离线复用。

**优先级原因**：所有 baseline、消融和主方法只有共享完全相同的 Agent 输出，质量与资源比较才公平、可复现。

**独立测试**：使用 fixture 运行 Agent cache、能力画像和风险监督准备流程，验证 cache key、上下文隔离、断点续跑、gold 隔离和模式隔离。

**验收场景**：

1. **给定** 规范化 Item，**当** 调用 Cheap/Mid/Strong/Evidence/Arbitrator，**则** 输出写入统一 schema，并记录模型、Prompt、上下文和资源指纹。
2. **给定** Agent 请求，**当** 审计输入，**则** 请求中不包含 `gold_score`、test 误差或未调用 Agent 的结果。
3. **给定** Arbitrator 调用，**当** 生成上下文 cache，**则** 只包含 Router 已经实际获得的 Agent 意见。
4. **给定** `train_fit` cache，**当** 构建能力画像，**则** 画像由程序自动拟合；`train_calibration` 只允许自动校准支持度边界，dev/test 均不得参与，也不产生具体 Item 的最优 Agent 标签。
5. **给定** fixture、pilot 和 formal 三种模式，**当** 运行或续跑 cache，**则** 三种运行目录和 active records 物理隔离。
6. **给定** 已冻结 context support catalog，**当** 某动作不在 catalog 中或缺少合法 active record，**则** Action Mask 屏蔽该动作并记录原因，评价阶段不在线补算。
7. **给定** Dataset Semantic V2 internal manifests，**当** 生成 Formal cache，**则** train 侧 records 按新的 `train_fit/train_calibration` Item split 写入并校验；旧 `paper_train_*` 只作历史来源溯源，不决定 cache split。

---

### 用户故事 3：训练、校准并评价质量约束动态路由策略（优先级：P3）

研究者可以基于 `train_fit` 重建 Paper 和逐步暴露的 Agent cache 构建离线轨迹，训练带 Stop-Risk Head 的质量约束 Router；再在独立 `train_calibration` Paper 上为每个冻结 checkpoint 校准 STOP 安全边界，最后由 Dev 依次执行固定参考准入、Quality Champion 质量保护和资源选择，并与分类器、自动阈值、Bandit、knapsack 和固定多 Agent 工作流公平比较。

**优先级原因**：该故事提供论文核心证据，同时保证“参数学习、边界校准、最终 Router 选择”三件事使用不同数据职责，避免同一数据既调边界又宣称方案胜出。

**独立测试**：完成 `internal item split -> separate paper rebuild -> train_fit -> train_calibration package assembly -> Dev reference admission -> Quality Champion -> candidate-to-champion protection -> resource auto-select -> freeze -> test-like smoke`，验证 calibration 不训练参数、不排名 checkpoint，Dev 不移动边界，且资源更低但质量不能证明不劣于冠军的候选被淘汰。

**验收场景**：

1. **给定** Agent cache 和 `paper_train_fit_*`，**当** 构建轨迹，**则** Router 在每一步只能观察已经调用的 Agent 输出，未调用 cache 保持隐藏。
2. **给定** `train_fit`，**当** 训练 Router，**则** Routing Q Head、Stop-Risk Head、critics 和必要状态组件仅使用 train_fit 可见状态和标签学习，并生成预注册范围内候选 checkpoint。
3. **给定** 某个冻结 checkpoint 和 `train_calibration`，**当** 自动校准，**则**程序只产生该 checkpoint 的 STOP 安全概率边界或 calibration failure；Severe/Extreme 阈值、QWK 分档和 Bootstrap 参数保持冻结。
4. **给定** 多个 checkpoint，**当** 在 `train_calibration` 组装 Package，**则** calibration 不按质量或资源对 checkpoint 排名、不选择最终 Router，也不为 Mid/Strong/VERIFY/A2A/ARBITRATE 生成主方法升级阈值。
5. **给定** 预定义参考策略集合，**当** 自动产生质量参考，**则**程序对每个预算档位按冻结规则选择并记录 `budget_id -> reference_policy_id`，该环境定义不因某个 Router checkpoint 改变。
6. **给定** 候选和参考策略，**当** 执行质量门，**则**二者在同 split、同 Paper、同 cache、同预算上使用相同 Paper 重采样索引完成5000次单侧95%配对 Cluster Bootstrap。
7. **给定** 边界已冻结的多个预算条件 Policy Package，**当** 在 Dev 上选择，**则**程序先要求候选在 Tight/Medium/Loose 每档均通过相对于固定参考策略的质量准入门，再只按冻结质量词典序确定唯一 Quality Champion；其他候选只有在全部预算档位的 Severe、Unsafe Stop、Macro-NMAE 和 Macro-QWK 均能证明不劣于冠军时，才进入跨预算等权资源词典序，且 Dev 不重新拟合或移动边界。
8. **给定** 没有任何 checkpoint 通过质量门，**当** 结束 Dev 选择，**则**输出 `quality_constraint_unsatisfied` 或具体 readiness failure，保留全部失败记录，不降低质量门。
9. **给定** 已冻结策略包，**当** 运行 Test，**则**Test 只执行一次性 final evaluation，不参与任何学习、校准、预算、指标或 checkpoint 选择。
10. **给定** 主方法成本低于参考，**当** 任一配对统计质量边界未通过，**则**该结果标记为 `Quality Feasible = No`，不得宣称资源优化成功。
11. **给定** Deferral、预算耗尽后未安全完成或非法最终分数，**当** 计算质量指标，**则**`Gate Error = 1`，并进入 Severe Error 与 Macro-NMAE。
12. **给定** 某候选 `STOP count = 0`，**当** 计算 Unsafe Stop，**则**`UnsafeStopRisk = NA` 且 `Quality Feasible = No`，不能记为0。
13. **给定** 任一 dataset 有效完成 Item 少于100、gold 非空 bin 少于2或 expected weighted disagreement 不大于0，**当** 计算 QWK，**则**QWK 未定义并触发 readiness failure。
14. **给定** 任一非劣效置信区间跨0，**当** 生成质量门结论，**则**输出 `quality_noninferiority_inconclusive` 并令 `Quality Feasible = No`。
15. **给定** 完整 Fixture Smoke，**当** 创建测试输入、配置、cache、checkpoint 和运行产物，**则**它们分别位于专用 fixture/config/test/run 位置，均标记 `formal_eligible=false`，且正式 loader 必须拒绝读取。
16. **给定** Fixture Smoke 与正式实验共用核心算法，**当** 审核调用路径，**则** split、Paper rebuild、cache scope、参考/预算/支持度校准、STOP calibration、Package builder、Bootstrap 和 Dev selector 不得存在 smoke-only 业务旁路。
17. **给定** 某候选在任一预算档位固定参考准入失败，**当** Dev selector 运行，**则**整个 Package 被淘汰；给定另一候选资源更低但不能证明不劣于 Quality Champion，**则**它不得进入资源排序。
18. **给定** 相同 fixture、配置、候选集合和随机种子，**当**重复执行自动选择，**则**必须得到相同参考映射、STOP 边界、Quality Champion、质量保护集合和唯一 checkpoint。

## 4. 边界情况

- 源数据缺少 reference answer，但 Rubric 和作答足以评分时，Item 可以保留并记录 `has_reference_answer=false`；DREsS 开放式作文允许 reference 为空，但必须有冻结的三维评分定义。
- ASAP-SAS 官方描述中包含图片、地图、图表或实验数据时，不允许文本抽取后静默丢失；主实验可使用经过来源核验的结构化文本转录，并保留原始 asset hash，转录不得添加新标签或推断性答案。
- ASAP-SAS 的 `Score1` 与 `Score2` 不一致时，仍以官方最终分数字段 `Score1` 为 Gold，不得取平均值。
- DREsS 原始 `total` 缺失或与三个 Trait 之和不一致、但三个 Trait 和作文均合法时，以三个 Trait 之和构造 Gold total，并保留原始差异用于审计；作文为空时必须 quarantine。
- SAS-Bench 的空 Step 若带非零人工 Step 分数、完整人工分超过题目满分、Step 和完整分数不一致或中英文来源无法对齐时，整条完整回答必须 quarantine。
- 不同数据集使用不同分值范围时，保留原始分数，并按各 Item 分值范围计算 Gate Error 与11档 QWK 映射。
- 旧外部 train Paper 因共享 prompt group 形成大型连通分量时，不允许退化为随机切 Paper；必须回到 Dataset Semantic V2 Item/题目组层分配后重建。
- 目标80%/20%与完整 prompt group 冲突时，保持 group 完整，记录实际比例和偏差，不拆 group。
- 某个内部 split 无法覆盖三个数据集或无法构造 strict Paper 时，内部构建 readiness failure，不得跨 split 借 Item。
- strict mix 无法继续构造完整 Paper 时，剩余 Item 记录为 leftover，不得静默进入不合法 Paper。
- 原外部 train `paper_id` 只作来源溯源，不能直接成为 `train_fit/train_calibration` split 标签。
- Agent cache 缺失、失败、越界或上下文不完整时，下游拒绝该 active record并报告受影响 Item；最终无法安全完成时 Gate Error 记为1。
- 当前上下文不在已冻结 support catalog 中，或对应 active cache record 不存在时，Action Mask 必须屏蔽该动作，禁止评价阶段在线补算。
- 某动作会使任一资源预算为负时，Action Mask 必须屏蔽该动作。
- 没有合法分数时，`STOP` 必须非法；只有一个评分意见时，`ARBITRATE` 必须非法。
- `train_calibration` 若收到梯度训练、replay buffer 构建或跨 checkpoint 排名请求，流程必须拒绝并记录职责违规。
- 某 checkpoint 无法校准出可行 STOP 边界时，保留 calibration failure，不在 Dev 临时放宽边界。
- 预算耗尽而 Item 仍不满足安全完成条件时，记录 Deferral/Unresolved Failure，并以 `Gate Error = 1` 进入正式质量指标。
- 候选没有执行任何 `STOP` 时，Unsafe Stop 主指标为 `NA`，质量不可行，不能当作零风险。
- 任一 dataset 的有效完成 Item 少于100、gold bin 退化或 expected weighted disagreement 为0时，QWK 未定义并触发 readiness failure。
- 参考策略在某 split 或预算档位上自身不满足 STOP/QWK readiness 时，该档位整体 readiness failure，不得看到候选结果后临时更换参考。
- Paper 级配对 Bootstrap 的任一置信区间跨0或计算失败时，输出 `quality_noninferiority_inconclusive`，不得把“无显著差异”解释为不劣。
- Dev 上没有候选通过质量门时，自动选择结果为空，不允许人工挑选质量不合格 checkpoint。
- 多个候选均通过固定参考准入门时，资源更低但任一正式质量指标不能证明不劣于 Quality Champion 的候选必须被质量保护门淘汰；若只有冠军通过保护门，则直接冻结冠军。
- Test 上质量门失败时，如实报告，不允许返回 Dev 改边界、改指标或改 checkpoint 后重复使用同一 Test。

## 5. 功能需求

### 5.1 数据与模拟试卷

- **FR-001**：系统必须将 DREsS、ASAP-SAS 和 SAS-Bench 按 Dataset Semantic V2 的数据集专用评分语义规范化为统一且可审计的 Item schema，不得用统一字段掩盖不同数据集的真实评分单位。
- **FR-002**：系统必须保留 `item_id`、dataset、question type、prompt、student answer、Rubric/reference、gold score、score min/max、scoring unit、scoring mode、schema/version、来源指纹、formal eligibility 和 metadata；DREsS 还必须保留三个隐藏 Gold Trait。
- **FR-003**：系统必须在各 split 内构造固定5题的模拟 Paper，并保存 `paper_id`、Item 引用、strict mix、构造版本和共享资源配置。
- **FR-004**：系统必须生成 split manifest 和 paper manifest，并阻塞 Item、Prompt、Paper、source lineage、跨数据集 exact prompt-answer 和引用关系泄漏。
- **FR-005**：系统必须记录主路由范围 Item、quarantine Item 与未进入 Paper Item 的边界，主 Router 训练和评价只消费通过 Semantic Readiness 且被合法 Paper 引用的 Item。

### 5.2 Agent 冻结、Cache 与画像

- **FR-006**：系统必须支持 CheapAgent、MidAgent、StrongAgent、EvidenceAgent 和 ArbitratorAgent 的统一接口。
- **FR-007**：系统必须在 Agent 请求中隔离 gold score，并在响应返回后由 cache writer 关联 gold。
- **FR-008**：系统必须冻结并记录模型、Prompt、生成参数、解析规则、角色、成本和延迟定义。
- **FR-009**：系统必须按 Item、Agent、split、模型、Prompt、生成参数和 context hash 生成稳定 cache key。
- **FR-010**：系统必须隔离 fixture smoke、real pilot 和 formal experiment，禁止跨模式复用 active cache。
- **FR-011**：Arbitrator cache 必须绑定已获得意见的上下文，不得泄露未调用 Agent 输出。
- **FR-012**：系统必须仅使用 `train_fit` cache 拟合正式 Agent 能力画像，并保存样本支持度与不确定性；如需画像校准，只能使用 `train_calibration` 自动完成且不得读取 dev/test 或回流梯度训练。

### 5.3 内部数据重建与职责分离

- **FR-013**：系统必须从已通过 Semantic Readiness Gate 的 Dataset Semantic V2 外部 train 主路由 Item 池出发，以 dataset prompt group、source lineage 和 exact prompt-answer/leakage component 的传递连通分量为不可拆分单元，使用固定种子和预注册算法分配到 `train_fit/train_calibration`；目标约80%/20%，不得为了比例拆开 group，也不得沿用旧 Item 数量或旧 split assignment。
- **FR-014**：系统不得直接拆分现有 `paper_train_*`；必须在两个内部 Item 池中分别重建固定5题 strict Paper，生成新的 internal `paper_id`，记录 leftover、来源外部 Paper 和构造版本。
- **FR-015**：`train_fit` 只能用于训练 Router、Stop-Risk Head、quality/resource critics、其他可学习组件和正式能力画像主体，并生成预注册候选 checkpoint；不得读取 calibration/dev/test。
- **FR-016**：`train_calibration` 只能冻结质量参考、预算与支持度边界，并对每个固定 checkpoint 自动校准 STOP 安全概率边界、组装 Policy Package；不得更新模型参数、进入 replay buffer、比较不同 checkpoint 的最终排名、选择最终 Router 或为主方法升级动作生成阈值。
- **FR-017**：Dev 只能比较边界已经冻结的完整 Policy Package：先在所有预算档位执行相对于固定参考策略的 FR-047 准入门，再按 FR-048 自动确定 Quality Champion、执行候选对冠军的质量保护门，最后才在保护可行候选中按资源词典序选择唯一 Package/checkpoint；不得重新拟合、移动或试探边界。
- **FR-018**：完成 Dev 选择后，模型、Prompt、质量协议、STOP 边界、预算、参考映射、Bootstrap、internal manifest 与 checkpoint 必须冻结；Test 只能用于一次性 final evaluation，不得参与任何训练、校准、筛选或 replay buffer。

### 5.4 路由状态、动作和信息边界

- **FR-019**：Routing State 必须包含当前可见 Item 状态、已调用 Agent 结果、能力先验、通信历史和剩余四维资源。
- **FR-020**：系统必须支持 `ROUTE_CHEAP`、`ROUTE_MID`、`ROUTE_STRONG`、`VERIFY`、`A2A_ASK(target)`、`ARBITRATE` 和 `STOP`。
- **FR-021**：动作必须联合指定目标 Item 与操作，Router 必须能够在多个未完成 Item 之间调度。
- **FR-022**：未调用 Agent cache 必须对 Router 隐藏，只有执行对应动作后才能暴露输出。
- **FR-023**：Action Mask 必须同时执行结构合法性、剩余资源可行性和 Formal Context Support 检查。
- **FR-024**：Stop-Risk Head 只允许估计当前 `STOP` 后 `Gate Error > 0.25` 的风险，不得直接指定下一步 Agent、改变 Severe 阈值或读取不可见信息。

### 5.5 质量参考、约束学习和失败保留

- **FR-025**：系统必须从预定义参考策略集合中，对每个预算档位按冻结的质量优先顺序自动选择并冻结质量参考，保存全部候选、readiness、排序键和 `budget_id -> reference_policy_id` 映射；不允许研究者手工选择较弱参考。
- **FR-026**：候选与参考必须在同一 split、Paper、Agent cache 和预算档位上配对比较，使用 FR-046 和 FR-047 的统计质量门；资源指标不得补偿质量不合格。
- **FR-027**：主方法必须使用质量约束的离线序列学习，不以 `QWK - beta*Cost` 作为唯一优化与模型选择依据。
- **FR-028**：系统必须保存所有候选 checkpoint、校准边界、质量协议 hash、readiness、相对于固定参考的准入 Bootstrap、Quality Champion 及其质量选择键、候选对冠军的保护 Bootstrap、Dev 资源排序、淘汰原因和失败状态。
- **FR-029**：没有候选通过固定参考准入门时，系统必须返回失败状态而不是放宽阈值、改指标或更换参考；有准入候选但没有其他候选通过 Quality Champion 保护门时，系统必须保留并选择冠军，不得为获得资源收益放宽保护门。
- **FR-030**：Test 质量门失败时，系统必须保留结果并禁止使用同一 Test 重新调参。

### 5.6 预算、Baseline、评价与复现

- **FR-031**：每份模拟 Paper 必须共享 `max_cost`、`max_elapsed_time`、`max_agent_calls` 和 `max_a2a_exchanges`。
- **FR-032**：第一版 elapsed time 必须按串行调用累计；不得将其表述为真实并行 makespan。
- **FR-033**：真实 Pilot 只能用于资源可行性估算；正式 Tight/Medium/Loose 预算档位必须使用重建后的 `train_calibration` strict Paper、冻结 Agent cache 和预注册固定 behavior/reference policies 自动生成，并保存 calibration manifest；不得用 Pilot 分位数或 Dev/Test 结果调整预算。
- **FR-034**：所有方法必须共享外部 prepared data、相同 internal item/paper manifests、Agent cache、预算、成本/延迟定义、随机种子集合和评价脚本。
- **FR-035**：Baseline 至少包含 Always-Cheap、Always-Mid、Always-Strong、自动校准阈值、静态分类器、完整多 Agent、Contextual Bandit 和 Top-k/knapsack；不再纳入 Fixed Cascade、Per-item Myopic Router 和 Greedy Marginal Utility。
- **FR-036**：消融至少覆盖无 A2A、无预算状态、无能力画像、无 Stop-Risk Head、无 CAG 图编码和无自动风险校准。
- **FR-037**：系统必须报告 Reference Admission Feasible、Quality Champion、Quality Protection Feasible、Gate Error 处理、Severe/Extreme Error、Unsafe Stop、Stop Coverage、Deferral、dataset QWK、Macro-QWK、Macro/Micro-NMAE、QWK readiness、参考准入与冠军保护 Bootstrap 边界、资源、通信、预算耗尽和失败状态。
- **FR-038**：每次运行必须使用唯一 `run_id`，保存配置、external/internal split 与 paper manifest 指纹、日志、predictions、checkpoints、reports 和 figures。
- **FR-039**：所有正式表格和图必须能够从保存的 predictions、logs、config 和统计重采样产物重新计算。
- **FR-040**：正式离线 cache 必须以 Dataset Semantic V2 internal manifests 作为 train 侧 split 来源，并冻结有限的 context/action support catalog；不在 catalog 中或缺少合法 active record 的动作必须被屏蔽并记录，所有方法共享同一 catalog，评价阶段不得在线补算。

### 5.7 继承的 V1.3 正式质量指标与统计门

- **FR-041**：合法最终分数必须使用 `abs(pred-gold)/(score_max-score_min)` 计算 Gate Error；Deferral、预算耗尽后未安全完成、最终分数缺失/越界/不可解析或无合法 active cache 结果必须统一令 `Gate Error = 1`。
- **FR-042**：Severe Error 必须固定为 `Gate Error > 0.25`；Extreme Error 必须固定为 `Gate Error >= 0.50` 且只作补充敏感性分析；两个阈值不得在 calibration 学习。
- **FR-043**：Unsafe Stop 主指标必须为“STOP 后发生 Severe Error 数量 / 全部 STOP 数量”，并同时报告 `Unsafe Stop / All Items`、`Stop Coverage` 和 `Deferral Rate`；`STOP count = 0` 时主指标为 `NA` 且质量不可行。
- **FR-044**：主 NMAE 必须分别基于 Gate Error 计算三个 dataset NMAE，再不加权平均为 `Macro-NMAE`；`Micro-NMAE` 只作补充。
- **FR-045**：gold 与合法预测必须按 Item 分值范围归一化后使用 `floor(10*z + 0.5)` 并 clip 到 `[0,10]`；QWK 必须使用完整 label set `0..10`，分别计算三个 dataset QWK 后宏平均。每个 dataset 必须至少100个有效完成 Item、至少2个非空 gold bin 且 expected weighted disagreement 大于0，否则 QWK 未定义并触发 readiness failure。
- **FR-046**：参考准入门和 Quality Champion 保护门都必须使用 Paper 为 cluster、候选/比较基准配对、5000次、单侧95%、零非劣效界、固定种子 `20260729` 的 Bootstrap；同一重采样中候选与固定参考或 Quality Champion 必须共享 Paper 索引。
- **FR-047**：`Quality Feasible = Yes` 必须同时满足 `UCB95(max_dataset_delta_severe) <= 0`、`UCB95(max_dataset_delta_unsafe_stop) <= 0`、`UCB95(delta_macro_nmae) <= 0` 和 `LCB95(delta_macro_qwk) >= 0`；任一指标未定义、置信区间跨0或未通过时必须输出 `quality_noninferiority_inconclusive` 或具体 readiness failure，并令质量不可行。
- **FR-048**：同一个预算条件 Policy Package 必须先在所有预注册预算档位分别通过相对于固定参考策略的 FR-047，才具备 Package 级参考准入资格。Dev 随后必须在全部准入候选中，不使用资源指标，按“跨预算最坏 Severe -> 跨预算最坏 Unsafe Stop -> 跨预算平均 Macro-NMAE -> 跨预算平均 Macro-QWK -> Policy Package ID”自动确定唯一 Quality Champion；其他候选必须在所有预算档位再次以冠军为基准通过 FR-047，才具备质量保护资格。最终只能在质量保护可行候选中按三个预算档位等权平均的 `Cost/Paper -> Elapsed Time/Paper -> Agent Calls/Paper -> A2A Exchanges/Paper` 排序，并保留原质量指标和 Package ID 作为资源并列规则；不得结果后改变冠军、聚合或顺序。

### 5.8 V1.4 内部拆分与职责审计

- **FR-049**：旧外部 train Paper 只能作为历史来源溯源证据，不得定义 Dataset Semantic V2 的主 Item 范围；内部训练、校准、Pilot 和 trajectory 脚本必须默认拒绝把旧 `paper_train_*` 直接当作 `train_fit/train_calibration` episode。
- **FR-050**：系统必须生成 `internal_item_split_manifest.csv`、`papers_train_fit.jsonl`、`papers_train_calibration.jsonl`、`internal_paper_manifest.csv`、`leftover_items.csv` 和 `internal_split_audit.md`，并阻塞内部 Item、prompt group、exact-answer/leakage component、Paper overlap、跨 split 引用、5题数量和 strict mix 任一违规。
- **FR-051**：主方法 calibration 只允许改变 STOP 安全概率边界；Mid/Strong/VERIFY/A2A/ARBITRATE 和下一 Item 由 Router 学习。阈值 baseline 可自动校准其自身边界，但必须与主方法共享 calibration split 和冻结门禁。
- **FR-052**：系统必须记录 calibration 对每个 checkpoint 的边界与 failure，但 calibration 输出中不得出现跨 checkpoint 最终排名或 `selected_final_router=true`；唯一最终选择只能由 Dev selector 产生。
- **FR-053**：完整 Fixture Smoke 的静态输入必须位于 `tests/fixtures/quality_constrained_smoke/`，测试代码位于 `tests/`，fixture 配置位于 `configs/experiments/`，持久化产物位于唯一 `outputs/runs/fixture_smoke_<run_id>/`；`run_id` 必须是单一安全路径组件，仓库内 `output_root` 只能位于 `outputs/runs/`；不得通过路径遍历或自定义输出目录写入正式 `data/processed/`、Formal cache、正式 checkpoint 或论文结果目录。
- **FR-054**：Fixture Smoke 必须标记 `execution_mode=fixture_smoke`、`is_fixture=true`、`formal_eligible=false`、`online_agent_calls=0`，并复用正式核心模块；任何 Formal loader、训练、画像、校准、选择或报告汇总收到 Fixture 资产时必须 fail closed。
- **FR-055**：完整 Fixture Smoke 必须生成可审计 run manifest、source-path isolation audit、formal loader rejection probes、context support catalog、internal split/rebuild audit、capability support manifest、quality reference manifest、budget calibration manifest、per-checkpoint calibration records、Calibration/Policy Package、Dev gate/selection/freeze、test-like one-shot 报告和覆盖全部运行文件的 fixture artifact inventory；并记录所有禁止行为计数、STOP 边界实际应用/升级次数以及完整确定性检查。；run manifest 还必须记录完整实验源码树的逐文件 SHA-256 与聚合 `source_tree_hash`，使验收结果可与当次代码精确绑定。

### 5.9 Dataset Semantic V2 数据整改

- **FR-056**：Dataset Semantic V2 必须作为新的不可变 prepared data 版本生成，不得原地覆盖旧 Item、split、Paper 或 cache；构建 manifest 必须记录原始文件 SHA-256、转换规则版本、配置指纹、代码版本、接受数量、quarantine 数量和原因分布。
- **FR-057**：ASAP-SAS 必须直接从官方数据描述资源恢复10个 EssaySet 的完整题目、必要 source context、官方 Rubric、分数范围和资源指纹；全部正式 Item 中指向 ZIP、附件或外部材料的占位文本数量必须为0。
- **FR-058**：ASAP-SAS 的正式 `gold_score` 必须等于 `Score1`；`Score2` 只能作为 inter-rater reliability metadata，禁止平均、校准或进入 Agent 请求、Router 状态和主质量指标。
- **FR-059**：ASAP-SAS 主实验不得使用完整 Anchor Paper PDF 或从 `train_fit` 选择的已评分回答示例；官方 Rubric 原文可以保留。题目必要图片必须作为带原始哈希、MIME、来源 URI 和稳定相对路径的 source asset 保存；结构化转录只能作为可选辅助字段，不能替代或修改原始图片，且所有方法共享相同资产。
- **FR-060**：DREsS 主实验只使用 DREsS_Std 和 DREsS_New 的合法非空作文；DREsS_CASE 不得进入主 train/dev/test，也不得以同源增强样本形式跨 split 出现。
- **FR-061**：DREsS 主实验必须固定 `anchor_mode=none`，使用 Content、Organization、Language 三维任务定义，每维合法范围为 `[0,5]`，总分范围为 `[0,15]`；所有 baseline、消融和主方法共享完全相同的无 Anchor Prompt 和 Agent cache。
- **FR-062**：DREsS 必须以三个 Trait Gold 的和构造 `gold_score`；原始 `total` 缺失或不一致不得覆盖合法 Trait，也不得静默丢弃合法作文，但必须记录差异。作文为空、Trait 缺失、越界或不可解析的记录必须 quarantine。
- **FR-063**：DREsS 评分 Agent 必须输出三个可校验 Trait 分数以及严格等于三者之和的 `pred_score`；正式报告除总分 NMAE/QWK 外，还必须报告三个 Trait 的误差、偏差和 Trait-Macro 指标，防止总分误差抵消掩盖维度错误。
- **FR-064**：SAS-Bench 主实验必须以一条顶层学生完整回答作为一个 Item，按原始 Step 顺序重建模型可见完整回答；不得把单个 Step 继续作为主实验 Item，也不得使用完整题目的总分范围评价单个 Step。
- **FR-065**：SAS-Bench 必须使用 `manual_label` 作为完整回答 Gold、使用 `total` 作为该 Item 满分，并对中英文来源、问题 ID、Step 数量/顺序和数字标签执行一一对应审计；`analysis` 与 `reference` 至少一个必须可用于评分。
- **FR-066**：SAS-Bench 的 Step label、Step error 和其他 Gold annotation 只能作为隐藏审计或补充评价字段，不得进入 Agent 请求；空 Step 带非零标签、`manual_label > total`、完整分与 Step 和不一致、来源无法对齐或必要语义同时缺失的记录必须 quarantine。
- **FR-067**：系统必须生成 Dataset Semantic V2 的数据集专用 Semantic Readiness 报告；任一全局或数据集专用检查失败时，`formal_cache_eligible=false`，真实 Agent cache、能力画像、Router 训练和 final evaluation 入口必须 fail closed。
- **FR-068**：Dataset Semantic V2 必须重新生成 Item ID、prompt group、split manifest、Paper 和内部 split；ASAP-SAS 按 EssaySet 分组，DREsS 按来源与完整规范化 Prompt 分组，SAS-Bench 按来源问题 ID 分组。分配算法不得使用 test Gold 调整比例或事后修订。
- **FR-069**：旧 100 Item Pilot 只允许作为 cliproxy 连通性、模型身份、结构化输出、Token 和成本账本的工程证据；其 predictions、Agent 能力结论和 cache records 不得进入 Dataset Semantic V2 的能力画像、Router 训练、Baseline、Formal cache 或论文主结果。
- **FR-070**：Dataset Semantic V2 通过离线审计后，真实 Agent 验证必须按“1份5题 checkpoint，仅 Cheap/Mid/Strong，共15次调用”再到“30 Item Pilot，仅 Cheap/Mid/Strong，共90次调用”的顺序执行；两个阶段均不得调用 Evidence/Arbitrator，未通过前不得启动新的100 Item Formal Pilot或1,000 Item耐久测试。
- **FR-071**：模型可见 Item 必须采用显式白名单投影；白名单可包含经过校验的 `source_assets`，但实际序列化请求中出现 `gold_score`、DREsS Gold Trait、ASAP `Score1/Score2`、SAS `manual_label/Step label/Step error` 或等价字段的次数必须为0。
- **FR-072**：Dataset Semantic V2 数据构建必须与具体本地模型、Tokenizer、视觉 Processor、GPU 和推理引擎解耦；数据阶段不得预先计算模型专用 Token、执行模型专用缩放或把某一模型的图像表示写入正式 Item。
- **FR-073**：自托管多模态 Agent 在 cache 阶段必须从 Item 的稳定 source asset 解析图片，并记录实际模型/Processor产生的文本 Token、视觉 Token、缩放参数和输入 hash；这些运行时字段不得反向修改 prepared data。
- **FR-074**：从 API 调用改为租用服务器自托管只允许改变 Agent 执行与成本来源，不得改变三个数据集的 Gold、Scoring Unit、无 Anchor 协议、split、Paper 或 Semantic Readiness 标准。

### 5.9 V1.6 自托管 Ministral 3 Pilot 本地准备（P1–P8）

- **FR-075**：P1–P8 必须全部在本地完成，只允许修改代码、配置、Prompt、测试、文档和本地 Mock/Fixture 产物；在线模型调用、模型权重下载、服务器租用、CUDA/PyTorch/vLLM/SGLang 安装和真实 GPU 推理次数必须均为0。
- **FR-076**：自托管真实客户端必须使用 OpenAI-compatible `POST /v1/chat/completions` 契约，支持文本与 base64 图像块、严格 JSON 输出、模型身份校验、有效 `usage` 校验、硬预算、有限重试和可注入传输层；不得把 CLIProxy `Responses` 客户端伪装成自托管实现。
- **FR-077**：候选 Agent 池必须冻结为同一 Ministral 3 Instruct 家族：Cheap=`mistralai/Ministral-3-3B-Instruct-2512-BF16`、Mid=`mistralai/Ministral-3-8B-Instruct-2512-BF16`、Strong=`mistralai/Ministral-3-14B-Instruct-2512-BF16`；三者使用同一 Prompt、同一 JSON Schema、`temperature=0`、非 Thinking 和相同输出上限；模型可见请求中不得包含 Cheap/Mid/Strong 的角色名或能力暗示，除 `model` 外的请求语义 hash 必须一致。权重 revision 在服务器下载后再冻结，P1–P8 不得编造 revision。
- **FR-078**：自托管请求必须从 Dataset Semantic V2 prepared root 解析 `source_assets`，校验相对路径不越界、字节数、SHA-256 和 MIME；JPEG 保持原字节，TIFF 必须确定性无损转码为 PNG，记录源/发送尺寸、源/发送 MIME、转换方式和发送字节 hash，且不得修改 prepared data。
- **FR-079**：模型可见 HTTP 请求体必须通过显式白名单构建，递归出现 Gold、隐藏 Trait、Score1/Score2、manual label、Step label/error、raw/derived total 或等价键的次数必须为0；本地 Mock 必须捕获并审计实际序列化 body，而不是只审计内存中的 Item。
- **FR-080**：自托管评分输出必须支持通用分数、置信度、理由和证据；DREsS 必须额外返回 Content、Organization、Language 三维分数，三维均在0–5且总分与三维和一致；非 DREsS 的 trait scores 必须为空。
- **FR-081**：Token 账本必须优先采用推理服务实际返回的 `prompt_tokens`、`completion_tokens` 和 `total_tokens`；三者缺失、为负或不自洽时请求失败。多模态 Item 在正式 checkpoint 中还必须具有服务器/Processor 提供的文本与视觉 Token 分解，否则门禁失败，不得用字符数估算冒充正式 Token。
- **FR-082**：每次成功调用必须记录 `official_api_equivalent_token_cost`。该指标按冻结的 Mistral 输入/输出 Token 价格计算，是 Router 预算与跨 Agent 公平比较的唯一主成本，不是实际 API 账单。AutoDL 服务器租金、GPU 空闲、模型下载、模型加载、环境安装和人工等待不属于论文实验成本，不进入 Router、Baseline、Cost-QWK、Pareto Frontier 或论文结果表格；本实验的 `server_hourly_price_usd` 与 `actual_server_allocated_cost_usd` 保持为 `null`。
- **FR-083**：每个 `Item × Agent` 必须具有稳定 `logical_call_id`。正式 canonical cost 只统计一条最终成功调用；每次 HTTP 尝试必须产生独立 attempt audit，失败重试、超时、OOM 和服务重启产生的额外 Token 成本进入 `operational_retry_overhead`，不得重复计入 canonical experiment cost；进程重启必须从 attempt 账本恢复已发生调用数与 Token 成本。服务器成本相关兼容字段在本实验中必须保持 `null`，不得生成或累计 `operational_retry_server_overhead`。
- **FR-084**：本地必须确定性生成一份5题 checkpoint：来自 `train_fit` 的一份 strict Paper，恰含5个唯一 Item，覆盖 ASAP-SAS、DREsS、SAS-Bench，且至少一个 ASAP-SAS Item 带必要图片；样本选择不得读取 Gold，清单生成后按源文件 hash、种子和选择规则冻结。
- **FR-085**：真实 checkpoint 只允许 Cheap/Mid/Strong，共15个 canonical 调用；Evidence/Arbitrator、Dev/Test、30/100/1000 Item 入口在 checkpoint PASS 前必须为0。门禁至少检查身份、结构、范围、DREsS三维和、SAS whole-response、图片审计、Gold隔离、Token、成本、attempt/canonical唯一性和 resume 幂等性。
- **FR-086**：本地必须提供无需真实模型的 Fake OpenAI-compatible 服务或可注入 transport，覆盖正常、JPEG/TIFF图片、非JSON、模型替换、usage缺失/不自洽、分数/trait非法、HTTP可重试/不可重试、断点恢复、跨进程预算恢复、单模型分阶段合并和预算硬门；Mock 输出只能标记 `formal_eligible=false`，不得进入能力画像、Router、Baseline或论文结果。
- **FR-087**：服务器交接材料必须冻结代码提交、数据传输 manifest、模型审批项、环境与磁盘路径、费用/时长/调用上限、部署命令模板、5 Item runbook 和返回产物清单；不得包含密钥、模型权重、本地虚拟环境或未批准下载命令的实际执行。
- **FR-088**：P1–P8 完成前必须运行新增单元/集成测试、完整测试套件、仓库结构检查、规格—计划—任务一致性分析、实现后 verify、任务真实性检查和代码/测试/错误处理审查；发现高风险缺口必须修复后重跑，不得仅以测试“没有失败”代替逐项验收。
- **FR-089**：真实模型 Smoke 和 5 Item 前，必须按冻结的 `data-transfer-manifest.json` 将恰好 10 个最小 Semantic V2/checkpoint 文件传输到远程服务器，逐文件验证 size 与 SHA-256；Dev/Test 和非 checkpoint train 文件传输数必须为 0。
- **FR-090**：真实模型调用前必须冻结 canonical 调用数、最大 attempt 数、并发、超时、`max_model_len`、输出上限、`temperature` 和 Thinking 模式；超出任一硬门时必须 fail closed。该预算不包含服务器租金。
- **FR-091**：每个真实 download、per-model Smoke、5 Item 和 30 Item run 都必须生成全文件 SHA-256 清单并回传本地相同 `run_id` 目录；本地必须重新验证 hash 和可重算报告。模型权重、下载缓存、虚拟环境和认证凭据不得回传。
- **FR-092**：30 Item Pilot 必须输出每个数据集的 QWK readiness。若任一数据集不满足正式 QWK 最小样本、Gold bin 或 expected disagreement 条件，正式 dataset QWK 与 `Macro-QWK` 必须为 `NA`；探索性 QWK 必须标记 `exploratory_not_formal=true`，不得进入正式质量门或 Formal 解锁结论。


## 6. 关键实体

- **Dataset Semantic V2 Item**：按数据集真实 Scoring Unit 构造的单条学生作答；包含模型可见题目、作答、Rubric/reference、分值范围，以及模型不可见 Gold、评分模式、来源指纹和正式资格 metadata。
- **Dataset Resource Catalog**：从原始官方资料恢复并冻结的题目、source context、Rubric、分数范围、图像资产和资源 hash 目录。
- **Model-Visible Item View**：从 Item 白名单投影得到的真实 Agent 请求输入，禁止包含任何 Gold、隐藏 Trait、Step label/error 或只供审计的来源字段。
- **Quarantine Record**：未进入正式 Item 的原始记录、来源标识、失败原因和转换版本，不包含自动猜测的替代内容。
- **Semantic Readiness Report**：证明 Dataset Semantic V2 在全局完整性、数据集语义、范围、来源、泄漏、Paper 和 Gold 隔离上是否具备 Formal cache 资格的门禁报告。
- **External Simulated Paper**：prepared data 阶段构造的固定5题 episode；外部 train Paper 在 V1.4 只作来源溯源，Dev/Test Paper 保持正式评价用途。
- **Internal Item Split Manifest**：将外部 train 主路由 Item 的 prompt/leakage connected component 分配到 `train_fit/train_calibration` 的冻结记录。
- **Internal Rebuilt Paper**：在单个内部 Item split 内重新构造的固定5题 strict episode，使用 `paper_train_fit_*` 或 `paper_train_calibration_*` 新 ID。
- **Internal Paper Manifest**：新 Paper、Item 引用、strict mix、source paper、种子和规则版本的审计记录。
- **Leftover Item Record**：已分入某个内部 split 但无法组成合法 strict Paper 的 Item、原因和来源记录；不得跨 split 借题消除。
- **Paper Budget**：`max_cost`、`max_elapsed_time`、`max_agent_calls`、`max_a2a_exchanges`。
- **Frozen Agent Definition**：模型、Prompt、参数、角色、解析与资源定义的不可变快照。
- **Agent Output**：冻结 Agent 在特定 Item/上下文下的分数、置信度、证据和资源记录。
- **Agent Capability Profile**：仅用 train_fit cache 拟合的条件性能先验；支持度边界可在 calibration 自动冻结。
- **A2A Exchange**：一次完整请求—响应通信；第一版仅 `A2A_ASK` 计入 exchange。
- **Routing State**：当前可见 Item、Agent、历史、风险和剩余预算快照。
- **Routing Action**：目标 Item 与评分、核验、二评、仲裁或停止操作的组合。
- **Stop-Risk Head**：在 train_fit 训练、对固定 checkpoint 在 calibration 校准 STOP 概率边界的安全头。
- **Quality Metric Protocol**：Gate Error、Severe/Extreme、Unsafe Stop、Macro-NMAE、固定11档 QWK、readiness、Bootstrap 和 Dev 排序的冻结机器可读定义。
- **QWK Readiness Record**：dataset 有效完成数、gold bin 数、expected disagreement、QWK defined 状态和失败原因。
- **Quality Reference Manifest**：在 calibration 冻结的每预算参考策略候选、readiness、固定排序、选择结果和协议/数据指纹记录。
- **Calibration Package**：一个固定 checkpoint、其 STOP 安全概率边界、参考映射、预算和全部 hash 的候选完整方案；无跨 checkpoint 最终排名。
- **Quality Champion**：Dev 在全部参考准入候选中只按固定质量词典序自动确定的唯一质量保护基准。
- **Quality Protection Gate Result**：候选—Quality Champion 指标差值、Paper 重采样配置、单侧置信边界、四项通过状态和失败原因。
- **Paired Bootstrap Gate Result**：候选与固定参考或 Quality Champion 的指标差值、Paper 重采样配置、单侧置信边界、四项通过状态和失败原因。
- **Budget Calibration Manifest**：使用重建 calibration Paper 自动生成预算档位的数据、分位数、结果和指纹记录。
- **Formal Context Support Catalog**：正式离线评价允许使用的 Agent、上下文模板、前置可见意见集合和 context hash 规则的冻结清单。
- **Policy Package**：通过 calibration 组装并在 Dev 比较的单一预算条件 Router checkpoint、风险头、STOP 边界、质量协议 hash、质量参考映射、预算配置和版本指纹组合。
- **Trajectory**：只由 train_fit rebuilt Paper 产生的逐步暴露状态、动作、资源、质量监督和结果序列。
- **Experiment Report**：质量可行性、统计边界、资源、消融、失败记录、曲线和 case study 的可复现报告。

## 7. 成功标准

- **SC-001**：Prepared data audit 为 PASS，Item、Prompt、Paper 和 exact prompt-answer 跨 split 泄漏均为0。
- **SC-002**：100% 主实验 Paper 满足固定5题和 strict mix 规则；Paper 引用不存在或跨 split Item 的数量为0。
- **SC-003**：100% 接受的正式 Agent cache records 满足 Dataset Semantic V2 schema、Gold 隔离、模式隔离、context 可追踪和新 internal split 一致性要求。
- **SC-004**：Router 在任何决策步骤都无法读取未调用 Agent 输出，相关阻塞性集成测试全部通过。
- **SC-005**：质量指标协议、质量参考、STOP 安全概率边界、预算档位、Quality Champion、质量保护门和策略包选择均由预注册程序产生或冻结；calibration 与 Dev 各自生成职责独立的可审计 manifest。
- **SC-006**：Dev 不含人工操作；相同输入、种子和候选集合的两次运行，必须输出相同参考准入状态、同一个 Quality Champion、相同候选对冠军保护状态、相同跨预算资源排序和唯一预算条件 Policy Package/checkpoint。
- **SC-007**：Test 在所有组件冻结后只执行一次 final evaluation，test cache 不进入训练、校准、画像或 replay buffer。
- **SC-008**：所有主方法和 baseline 在相同 Paper、Agent cache、预算档位、质量协议和评价脚本上评价。
- **SC-009**：在同一 split、Paper、Agent cache 和预算档位上，无论比较基准是固定参考还是 Quality Champion，候选都只能在 `UCB95(max_dataset_delta_severe) <= 0`、`UCB95(max_dataset_delta_unsafe_stop) <= 0`、`UCB95(delta_macro_nmae) <= 0` 和 `LCB95(delta_macro_qwk) >= 0` 四项同时成立时通过对应质量门。
- **SC-010**：若不存在参考准入可行策略，系统输出明确失败状态；若只有 Quality Champion 通过质量保护门，则选择冠军。两种情况都必须保留全部候选、readiness、参考准入边界、冠军选择和保护边界，不修改质量门。
- **SC-011**：主报告完整包含 Always-Cheap、Always-Mid、Always-Strong、自动阈值、静态分类器、Contextual Bandit、Top-k/knapsack、完整多 Agent 和质量约束 CAG-CQL，不包含 Fixed Cascade、Per-item Myopic Router 和 Greedy Marginal Utility。
- **SC-012**：至少完成无 Stop-Risk Head 等关键消融，能够区分安全头与强化学习 Router 的贡献。
- **SC-013**：最终实验包能够从保存的配置、predictions、logs、checkpoints 和 Bootstrap 产物重算所有论文表格与图。
- **SC-014**：Fixture smoke 在不调用真实模型的情况下完成 data-to-report 流程；真实模型 Pilot 和正式实验须另行批准。
- **SC-015**：正式评价中100%的已执行动作均命中冻结 support catalog 和合法 active cache record；在线补算次数为0，所有方法的 catalog 指纹一致。
- **SC-016**：Deferral、预算耗尽后未安全完成及非法/缺失最终分数100%被赋予 `Gate Error = 1`；Severe 固定为 `> 0.25`，Extreme 固定为 `>= 0.50`；`STOP count = 0` 的候选100%被标记为 Unsafe Stop `NA` 且质量不可行。
- **SC-017**：正式 QWK 100%使用固定 label set `0..10` 和 half-up 映射；每个 dataset 均输出有效完成数、gold bin 数和 expected disagreement，任一 readiness 条件失败时 Macro-QWK 不进入质量门且候选不可行。
- **SC-018**：Paper 级配对 Bootstrap 固定执行5000次、单侧95%、零非劣效界和种子 `20260729`；同一输入重复运行的置信边界与通过状态完全一致，置信区间跨0时状态为 `quality_noninferiority_inconclusive`。
- **SC-019**：候选必须先在 Tight/Medium/Loose 全部通过固定参考准入门；Dev 随后只按固定质量词典序产生唯一 Quality Champion。其他候选只有在全部预算档位四项质量均证明不劣于冠军时，才进入跨预算等权平均的 `Cost/Paper -> Elapsed Time/Paper -> Agent Calls/Paper -> A2A Exchanges/Paper` 排序；最终只冻结一个预算条件 Policy Package/checkpoint，资源节省声明只出现在质量保护可行结果上。
- **SC-020**：内部拆分实现对现有 `paper_train_*` 的直接分配次数为0；`train_fit/train_calibration` Item、prompt group、exact-answer/leakage component、Paper 和跨 split 引用 overlap 均为0。
- **SC-021**：`papers_train_fit.jsonl` 与 `papers_train_calibration.jsonl` 100%使用本 split Item、固定5题并满足 strict mix；目标80%/20%的实际比例、偏差、leftover 和确定性 group 分配可完整审计。
- **SC-022**：`train_calibration` 被梯度训练、能力画像主体拟合或 replay buffer 消费的记录为0；calibration 输出中的跨 checkpoint 最终排名和最终 Router 选择字段为0；每个 checkpoint 只得到 STOP 边界或明确 calibration failure。
- **SC-023**：Dev 输入的所有 Package 边界在进入 Dev 前已冻结；Dev 边界修改次数为0，Quality Champion 人工替换次数为0，并且相同候选、种子和 manifests 两次运行输出相同冠军、质量保护集合和唯一最终 Package/checkpoint。
- **SC-024**：完整 Fixture Smoke 的正式数据读取、正式入口误接受、在线 Agent 调用、跨模式 cache 复用、calibration 梯度、calibration replay、calibration checkpoint ranking、Dev 边界更新、Quality Champion 资源字段参与、人工替换和 test-like 训练读取计数全部为0；其中正式数据读取必须由路径白名单阻塞，正式入口误接受必须由实际 fail-closed 探针计算，不得仅写死为0。；`quality_champion_resource_reads=0` 必须由冠军排序阶段的资源字段结构性隔离与读取守卫证明，不得只写常量0。
- **SC-025**：Fixture Smoke 产物100%内嵌 `formal_eligible=false` 或被 `fixture_artifact_manifest.json` 逐文件哈希覆盖并绑定 `formal_eligible=false`，未纳入 inventory 的运行文件数为0，正式实验入口对这些产物的接受次数为0；Smoke 通过只证明流水线契约成立，不得作为真实 Agent 质量或论文效果证据。
- **SC-026**：ASAP-SAS 的10个 EssaySet 资源均成功恢复；正式 Item 中 ZIP/附件占位数量为0，17,043条源作答全部使用 `Score1` 作为 Gold，`Score1/Score2` 平均值作为 Gold 的记录数为0。
- **SC-027**：DREsS 正式 Item 100%包含合法 Content、Organization、Language Gold，`gold_score` 与三维和不一致的记录数为0；空作文全部进入 quarantine，DREsS_CASE 和主实验 Anchor 的接受数均为0。
- **SC-028**：SAS-Bench 每个接受的顶层完整回答恰好生成一个 Item，单 Step 主实验 Item 数为0；`gold_score=manual_label`、`score_max=total`、Gold 范围合法和 Step 顺序完整四项通过率均为100%。
- **SC-029**：所有被排除的 ASAP-SAS、DREsS 和 SAS-Bench 原始记录均能在 quarantine manifest 中找到唯一来源和至少一个明确 reason code；静默跳过记录数为0。
- **SC-030**：Dataset Semantic V2 的 Semantic Readiness 状态为 PASS 且 `formal_cache_eligible=true`；Item、Prompt、source lineage、Paper 和 exact prompt-answer 跨 split 泄漏均为0。
- **SC-031**：随机抽查和自动扫描的实际 Agent 序列化请求中，Gold、隐藏 Trait、Score1/Score2、manual_label、Step label/error 或等价信息的出现次数为0。
- **SC-032**：旧 prepared data、旧 Item/Paper ID 和旧 100 Item Pilot cache 被 Dataset Semantic V2 正式入口接受或复用的次数为0；旧 Pilot 在论文主评分表、能力画像和 Router replay buffer 中的记录数为0。
- **SC-033**：Dataset Semantic V2 的5 Item checkpoint 在15次 Cheap/Mid/Strong 调用中完成模型身份、结构化输出、范围、DREsS 三维求和、SAS 完整回答和单次成本记账验收；未通过时30 Item Pilot调用数为0。
- **SC-034**：只有5 Item checkpoint 通过后才允许完成30 Item、90次 Cheap/Mid/Strong Pilot，并产出分数据集质量、输出退化、Agent 分歧、Best-fixed 与 Item Oracle headroom 诊断；在该报告审批前新的100 Item Formal Pilot和1,000 Item耐久测试调用数均为0。
- **SC-035**：ASAP-SAS 官方描述中的全部图片资产均保留原始字节哈希、MIME、来源 URI 和可解析相对路径；必要图片被静默丢失、仅保留人工转录或写入模型专用视觉表示的数量均为0。
- **SC-036**：Dataset Semantic V2 Item 与资源目录不包含任何具体模型 Tokenizer、视觉 Processor、GPU 或推理引擎生成的 Token/embedding；模型专用图像处理只出现在后续 Agent cache 运行产物。
- **SC-037**：相同 Dataset Semantic V2 资产可由本地自托管 Agent 或另行批准的 API Agent 消费，二者使用完全相同的 Gold、split、Paper 和模型可见语义字段。
- **SC-038**：P1–P8 的 `online_agent_calls`、`model_downloads`、`dependency_installs`、`server_rental_actions`、`cuda_runtime_installs` 和 `prepared_data_writes` 均为0；所有本地运行产物均具有唯一 `run_id` 且 `formal_eligible=false`。
- **SC-039**：Cheap/Mid/Strong 三个配置的模型家族、Prompt hash、Schema hash、temperature、Thinking模式、输出上限和图片策略除模型ID外完全一致；Evidence/Arbitrator 不在 checkpoint support catalog 中。
- **SC-040**：4个 ASAP-SAS 正式 source asset 均通过路径、大小、SHA-256、MIME和可解码性检查；2个TIFF均可确定性转为相同尺寸PNG，原始prepared文件修改数为0。
- **SC-041**：Fake服务捕获的每一个序列化请求体均无禁用Gold键；文本、JPEG、TIFF和无图片四类请求均通过Chat Completions契约测试；同一Item的三档请求除模型ID外语义hash完全相同。
- **SC-042**：正常Mock的Token/价格/attempt/canonical账本逐字段可重算；usage缺失或不自洽、模型替换、非法JSON、越界分数和DREsS三维不一致均被fail-closed拒绝。
- **SC-043**：5 Item checkpoint manifest 恰含1份strict Paper、5个唯一train_fit Item、3个数据集且至少1个图像Item，选择过程Gold读取次数为0；预期canonical调用数固定为15；服务器传输manifest只包含该checkpoint、必要lineage/Readiness和实际引用资产，不传Dev/Test。
- **SC-044**：本地checkpoint workflow在Fake服务上完成15条成功canonical记录，resume再次执行产生的新HTTP请求数为0；失败attempt保留但canonical成本不重复累计。
- **SC-045**：服务器交接包包含模型/环境/数据/费用/runbook/返回产物六类材料且不含密钥、权重、C盘实验路径或实际服务器操作；P1–P8完成报告逐项给出证据路径与测试命令。
- **SC-046**：新增测试与全仓测试全部通过，spec/plan/tasks中的V1.6要求都有已完成任务和实现证据，任务真实性、verify和专项review不存在未解决的CRITICAL/HIGH问题。
- **SC-047**：远程数据接收 manifest 显示 `expected_file_count=10`、`received_file_count=10`、`hash_mismatch_count=0`、`dev_test_file_count=0` 和 `non_checkpoint_train_file_count=0`。
- **SC-048**：真实配置中的 `server_hourly_price_usd=null`；论文主成本 100% 由冻结 Token 价格和服务端 usage 重算，服务器租金不进入正式报告。
- **SC-049**：远程与本地 run 的 artifact hash 完全一致，本地重新运行 validator 得到与远程相同的 PASS/FAIL。
- **SC-050**：30 Item 不满足正式 QWK readiness 时，`formal_macro_qwk=NA` 且 `exploratory_not_formal=true`。


## 8. 非目标

- 不训练或微调 Cheap/Mid/Strong/Evidence/Arbitrator Agent。
- 不构建任意题目、任意考试的通用评分系统。
- 不研究 student_id、exam_id、学生能力、学生总分或学生级公平性。
- 不恢复真实学生原始试卷。
- 不把现有外部 train Paper 直接随机拆成 `train_fit/train_calibration`。
- 不让 `train_calibration` 承担最终 Router/checkpoint 选择。
- 不在第一版建模真实异步并发 makespan。
- 不把 HumanAgent 作为核心动作，除非后续单独设计并批准。
- 不在主实验中使用从 `train_fit` 选择的 Anchor、DREsS_CASE 或 SAS-Bench 单 Step Item；这些方向如后续研究必须独立审批和报告。
- 不把官方数据中不存在的 Rubric、参考答案、Step 满分或人工标签凭空补写进正式数据。
- 不要求基础 Agent 的绝对准确率先达到生产部署标准，但不允许使用语义缺失、评分单位错误、常数输出或接近随机的退化环境支持算法结论。
- 不为了获得资源收益而放宽评分质量或严重错分要求。
- 不根据 test 结果修改 Prompt、阈值、预算、参考策略或 checkpoint。
- 不建设生产级 Web、教师端、学生端、账号或权限系统。

---

## 9. 假设

- 第一版是离线论文实验流水线，Agent cache 用于公平复用和反事实轨迹构建。
- 三个现有数据集继续使用，不引入额外人工评分标签；因评分单位修正、空作答和结构异常 quarantine，Dataset Semantic V2 的 Item 数量允许与旧 prepared data 不同，并以冻结 build manifest 为准。
- ASAP-SAS 的原始图片资产必须保留；来源核验转录只作为可选辅助信息，不视为新增人工标签，也不得替代原图。任何无法恢复或校验的必要图片都应导致对应 EssaySet readiness failure。
- DREsS 主实验默认无 Anchor；所有方法共享相同无 Anchor Prompt、数据和 cache。绝对指标可以不高，但至少必须通过语义有效性、输出非退化和可利用路由空间诊断，论文结论只声称动态路由相对改进，不声称达到生产级阅卷准确率。
- Gold 仅用于 train_fit 监督、train_calibration 自动校准、Dev 选择和最终离线评价，不进入 Agent 请求或 Router 在线状态。
- 旧外部 Paper、旧 Item ID、旧 split manifest 和旧 cache 在 Dataset Semantic V2 中只作历史溯源；内部 Item 分配和 Paper 重建将在实现前按固定算法完成并冻结新 manifests。
- 内部拆分以约80%/20%为目标，但 prompt/leakage component 完整性、strict Paper 可构造性和可审计性优先于精确比例。
- 正式 Agent 模型、Prompt、真实费用和延迟必须先通过 Dataset Semantic V2 的1份5题 checkpoint 和30 Item Pilot；是否进入新的100 Item Formal Pilot由30 Item报告审批决定，1,000 Item耐久性验证不在当前批准范围。
- 当前 fixture 预算仅用于工程 smoke；Pilot 只估算可行性，正式预算由冻结 cache 上重建的 `train_calibration` Paper 和固定 behavior/reference policies 自动生成。
- `train_calibration` 不产生最终 checkpoint 排名；每个 checkpoint 只得到 STOP 边界或 calibration failure，最终选择仅由 Dev selector 产生。
- V1.3 的 Gate Error、Severe/Extreme 阈值、Unsafe Stop 分母、Macro-NMAE、11档 QWK、readiness、Bootstrap 参数和 Dev 排序继续冻结，V1.4 不改变这些定义。
- 每个预注册预算档位独立执行参考选择与固定参考准入门；Dev 在全部档位均准入的候选中只按质量确定 Quality Champion，再对其他候选执行冠军保护门，并仅在质量保护可行候选中按跨预算等权资源聚合自动选择并冻结唯一预算条件 Policy Package/checkpoint。
- 项目最高规则以仓库根目录 `AGENTS.md` 为准。
