# 实现计划：面向模拟试卷级自动阅卷的质量约束多智能体动态路由实验流水线

**分支**：`001-a2a-dygrade-rl`
**日期**：2026-07-29
**规格**：[spec.md](./spec.md)
**依据**：`docs/design/研究定义与实验约束同步方案.md` V1.4、`docs/design/A2A-DyGrade-RL_实验设计方案.md` 2.3、`AGENTS.md` 1.4.0

---

## 1. 摘要

本计划继续研究“面向模拟试卷级自动阅卷的质量约束多智能体动态路由方法”，继承 V1.3 正式质量协议，并执行 V1.4 四项已确认决定：

1. **最终职责分离**：`train_fit` 只训练参数；`train_calibration` 只为每个冻结 checkpoint 校准 STOP 安全概率边界、冻结参考/预算并组装候选 Package；Dev 才比较完整 Package 并选择唯一 Router；Test 只最终评价。
2. **内部 Paper 重建**：不直接拆现有5,475份 train Paper；从当前27,375条 train 主路由 Item 出发，先按 prompt/leakage connected component 分配到 `train_fit/train_calibration`，再分别重建固定5题 strict Paper。
3. **Quality Champion 保护**：Dev 先执行固定参考准入门，再只按质量确定冠军，其他候选证明不劣于冠军后才能比较资源。
4. **Baseline 精简**：删除 Fixed Cascade、Per-item Myopic Router 和 Greedy Marginal Utility，保留固定 Agent、完整多 Agent、自动阈值、静态分类器、Contextual Bandit 和 Top-k/Knapsack。

核心流程：

```text
external train Item scope
→ prompt/exact-answer/leakage connected-component internal split（目标约80/20）
→ separate train_fit/train_calibration strict Paper rebuild
→ train_fit parameter learning
→ train_calibration per-checkpoint STOP boundary + environment/package freeze
→ Dev fixed-reference admission + Quality Champion protection + cross-budget resource selection
→ unique Policy Package freeze
→ one-shot Test
```

主方法的 Mid/Strong、VERIFY、A2A、ARBITRATE 和下一 Item 选择由 Router 学习，不在 calibration 额外配置一组升级阈值。任何 calibration 梯度训练、replay consumption、跨 checkpoint 最终排名，或 Dev 边界移动都属于阻塞性违规。

V1.3 的 Gate Error、Severe/Extreme、Unsafe Stop、Macro-NMAE、固定11档 Macro-QWK、QWK readiness 和 Paper 级配对 Bootstrap 保持不变；Dev 选择改为“固定参考准入门 -> Quality Champion 质量保护门 -> 资源词典序”。

## 2. 当前执行状态

### 2.1 已完成

- 三个数据集已下载并规范化。
- Prepared Item 共39,533条：train 28,038、dev 3,244、test 8,251。
- 外部 Strict Paper 共7,237份：train 5,475、dev 196、test 1,566，每份固定5题。
- 外部 prepared data audit 为 PASS，Item、Prompt、Paper、exact prompt-answer 跨 split 泄漏均为0。
- 外部主 Paper 共引用36,185条 Item：train 27,375、dev 980、test 7,830。
- 已完成 train Paper—prompt group 图审计：5,475份 train Paper 形成1个覆盖100%的连通分量，证明不能直接按 Paper 拆 `train_fit/train_calibration`。
- Agent cache schema、五类 Agent wrapper、FixtureClient、cache writer、断点续跑、模式隔离、difficulty/capability fixture 流程已实现。
- 历史 `fixture_smoke_001` 已通过；V1.4 完整 Fixture Smoke 最新权威 run 为 `fixture_smoke_v14_20260729_005`，已通过路径隔离、Formal 拒绝探针、STOP 边界应用、预算硬门、A2A 计数、完整确定性与逐文件 inventory 门禁；最终全量命令为 `135 passed in 191.29s`，后续仍以当次命令输出为准。
- V1.3 质量协议和 V1.4 最终职责/内部重建决定已在设计、规格、计划与任务层确定。

### 2.2 尚未完成

- 正式真实 Agent 模型与 Prompt 尚未冻结；重建 train_fit Paper 上约100 Item/20 Paper Pilot 尚未运行。
- CLIProxy 已暴露 `gpt-5.6-luna/terra/sol` 模型目录；身份探针中 Luna/Terra 已通过，Sol 先后出现 `HTTP 408 stream closed` 与 `HTTP 503 auth_unavailable`，因此100 Item调用按门禁暂停，待 Sol 上游认证/配额恢复后重跑 T052B0。
- Formal `train_fit/train_calibration/dev/test` Agent cache 尚未生成。
- 隐藏 cache 环境、train_fit-only 轨迹/replay、质量约束 Router、强 baseline、消融和正式一次性 Test 门禁尚未实现。
- Fixture Smoke 已实现的质量协议、参考/预算/支持度/STOP 校准、Package 与 Dev selector 只证明职责链和测试契约连通，不能替代正式 Router 候选与真实 Agent 评价。

### 2.3 当前门禁

进入真实 Agent Pilot 前，必须先完成：

1. prompt/leakage component 原子分配的确定性算法与目标约80%/20%配置；
2. 两个内部 split 的 strict Paper 重建、leftover 记录和阻塞性 audit；
3. schema/config/contracts 对 internal manifests 和职责字段的支持；
4. V1.4 fixture smoke，证明 calibration 不训练参数、不排名 checkpoint，Dev 不移动边界；
5. 五类 Agent 的真实模型、Prompt、JSON、D盘依赖路径、Pilot 费用上限、并发、重试和超时审批。

V1.3 正式质量指标、统计门和跨预算 Dev 排序仍冻结，不允许因内部拆分结果或 Pilot 修改。未获得用户单独批准前，不安装或下载真实模型依赖，不调用付费 API。

## 3. 研究问题与证据链

| 编号 | 研究问题 | 主要证据 |
|---|---|---|
| RQ1 | 在通过固定参考准入门且不劣于 Quality Champion 的前提下，动态路由能否减少资源？ | 两层四项配对 Bootstrap 边界、质量保护主表、Tight/Medium/Loose 资源结果 |
| RQ2 | 共享预算和多步反馈是否使强化学习优于分类器、Bandit 和 knapsack？ | 强 baseline 对照、路径与机会成本分析 |
| RQ3 | Stop-Risk Head、CAG、能力画像、预算状态和 A2A 是否有独立贡献？ | 消融、Severe/Unsafe Stop、Macro-NMAE/QWK、通信收益 |
| RQ4 | 参数训练、STOP边界校准和最终 Router 选择分离后，是否能避免边界过拟合和手工调参？ | calibration 不训练/不排名审计、Dev 边界冻结、重复运行一致性 |
| RQ5 | 在 readiness 或 Test 质量门失败时，系统是否能够如实返回失败而不修改协议？ | QWK/STOP readiness、freeze manifest、失败注册表和一次性 final report |

## 4. 核心设计决策

### 4.1 模拟试卷语义

`Paper` 是共享资源的多题评分 episode，不声称恢复真实 `student_id + exam_id`。单条题目、作答和人工标签来自真实数据，组合关系和预算是实验构造。

代码继续使用 `paper_id`，文档和报告中同时标注 `simulated paper/scoring episode`。

### 4.2 质量不可与资源交换

不使用 `QWK - beta*Cost` 作为唯一训练、调参和结果选择规则。正式决策分三层，并保持一个预算条件策略适配全部正式预算档位：

1. 候选 Policy Package 必须在 Tight/Medium/Loose 每个预注册预算档位上分别通过相对于固定参考策略的 Paper 级配对 Bootstrap 零容忍质量准入门；
2. 在全部预算档位均准入的候选 Router Policy Package 中，只按 `Worst-(Budget,Dataset) Severe -> Worst-(Budget,Dataset) Unsafe Stop -> Mean-Budget Macro-NMAE -> Mean-Budget Macro-QWK -> Package ID` 自动确定唯一 Quality Champion；固定参考、Baseline 和消融不参与冠军或最终 checkpoint 选择；
3. 其他候选必须在每个预算档位用相同四项零边界 Bootstrap 证明不劣于 Quality Champion，只有质量保护可行候选才进入跨预算资源词典序。

设预算集合为 \(\mathcal B\)，Cost/Paper 的 Dev 选择值为各档位不加权平均，其他资源同理。最终固定顺序：

```text
Package Reference Admission Feasible = Yes
→ Quality Protection Feasible = Yes
→ Mean-Budget Cost/Paper
→ Mean-Budget Elapsed Time/Paper
→ Mean-Budget Agent Calls/Paper
→ Mean-Budget A2A Exchanges/Paper
→ Worst-(Budget,Dataset) Severe Error
→ Worst-(Budget,Dataset) Unsafe Stop
→ Mean-Budget Macro-NMAE
→ Mean-Budget Macro-QWK
→ Policy Package ID
```

资源指标不能帮助候选通过参考准入门或 Quality Champion 保护门。若更便宜的候选严重错分率或其他质量指标不能证明不劣于冠军，它必须在资源排序前被淘汰。

### 4.3 禁止人工调边界

正式流程固定为：

```text
train_fit：学习模型参数和动作策略
→ train_calibration：对每个冻结checkpoint只校准STOP安全概率边界并组装Package
→ dev：不改边界，依次执行固定参考准入、Quality Champion 保护和跨预算资源选择
→ freeze：锁定唯一Package及全部协议
→ test：一次性最终评价
```

主方法的升级、核验、二评、仲裁和下一 Item 选择由 Routing Q Head 学习，不在 calibration 生成固定升级阈值。Severe/Extreme、QWK 分档、Bootstrap 参数和 Dev 顺序不属于自动校准对象。所有候选、边界、readiness、重采样结果、排序和失败原因保存为机器可读产物。

### 4.4 Stop-Risk Head 属于 Router

停止风险头共享 CAG 编码器，只估计当前 `STOP` 的严重错分风险。它不输出分数、不选择下一 Agent，也不能读取未调用 cache。核心多任务多动作选择仍由离线 RL 的 Routing Q Head 完成。

方法准确命名为：

> **带学习型安全约束的质量约束 CAG-CQL 离线强化学习路由方法。**

### 4.5 Cache 逐步暴露

Agent cache 是隐藏环境查询表。每次动作执行后只暴露该动作对应输出；未调用 Agent 输出不得进入状态、风险头、能力画像的 Item 级输入或仲裁上下文。

### 4.6 主路由 Item 范围

外部主范围仍为 `paper_manifest.csv` 当前引用的36,185条 Item：train 27,375、dev 980、test 7,830。未进入外部 Paper 的 Item 可用于单独 Agent QA，但不因 V1.4 内部重建擅自扩入主路由结果。

### 4.7 内部 split 不继承外部 train Paper

本地审计证明5,475份现有 train Paper 通过共享 prompt group 构成一个连通分量。因此内部流程必须：

```text
27,375 train main Items
→ prompt/leakage connected-component allocation
→ train_fit/train_calibration Item pools
→ separate strict Paper rebuild
```

外部 `paper_train_*` 只作为 Item 来源和溯源字段，不作为内部 split 单元。目标约80%/20%，但 group 完整性和 strict Paper 可构造性是硬约束。

### 4.8 Calibration 与 Dev 不重复

`train_calibration` 对每个 checkpoint 只产生 STOP 边界或 failure，不输出跨 checkpoint 最终排名；Dev 输入边界固定的 Package，才执行最终质量筛选和资源排名。任何 calibration 梯度/replay 消费、calibration 选最终 Router 或 Dev 改边界均为阻塞性违规。

### 4.9 Fixture Smoke 隔离但不分叉核心代码

完整 Fixture Smoke 采用“四类资产隔离、核心实现复用”的结构：

- 静态 fixture 与蓝图：`tests/fixtures/quality_constrained_smoke/`；
- 集成契约：`tests/integration/test_quality_constrained_smoke.py`；
- fixture-only 配置：`configs/experiments/fixture_smoke.yaml` 与专用 Agent 配置；
- 持久化验收产物：`outputs/runs/fixture_smoke_<run_id>/`。

Smoke 不写入 `data/processed/`，不读取27,375条正式主路由 Item，不调用真实 Agent，不向正式能力画像、预算、参考、replay、checkpoint 或论文结果汇总提供输入。`run_manifest.json` 必须固定 `execution_mode=fixture_smoke`、`is_fixture=true`、`formal_eligible=false`、`online_agent_calls=0`。蓝图/config/protocol 路径必须先经过白名单审计；正式入口读取到上述标记时必须 fail closed，并由实际 run manifest、cache scope、capability loader 探针验证拒绝。成功 run 最后生成逐文件哈希的 `fixture_artifact_manifest.json`，未覆盖文件数必须为0。

隔离的只是数据、配置、cache、checkpoint fixture 和运行产物；`internal_split`、`build_internal_papers`、`cache`、`capability`、`quality_reference`、`budget_calibration`、`calibration`、`policy_package`、`paired_bootstrap` 与 `checkpoint_selector` 必须使用正式模块，禁止为 Smoke 复制一套简化选择逻辑。Router candidate 进入 Dev/Test-like 后必须实际读取冻结 STOP 边界，超过边界先执行验证动作并计入资源；`budget_feasible=false` 必须在参考准入前淘汰，Arbitrator 暴露意见必须进入 A2A Exchanges。

## 5. 数据、内部 Paper 重建与正式质量协议

### 5.1 外部 split 与主 Item 池

继续使用现有 prompt-aware `train/dev/test`。外部 train 28,038 Item 中，V1.4 内部构建只使用当前 `paper_manifest.csv` 引用的27,375条主路由 Item；Dev 980与Test 7,830条 Paper 引用 Item及其现有 Paper 保持不变。

### 5.2 题目组原子分配

禁止把现有5,475份 `paper_train_*` 直接拆分。建立内部原子单元：

```text
same dataset + prompt_group
OR same exact-answer/leakage component
→ transitive connected component
```

使用固定种子和预注册算法分配到 `train_fit/train_calibration`，目标约80%/20%。硬约束优先级：

1. component 不跨 split；
2. 两个 split 覆盖三个数据集并能构造 strict Paper；
3. 最大化合法5题 Paper 总数；
4. 最小化与80%/20%目标偏差；
5. 稳定 hash 解决并列。

### 5.3 分别重建内部 Paper

在两个 Item 池中独立运行 strict builder：

```text
papers_train_fit.jsonl / paper_train_fit_*
papers_train_calibration.jsonl / paper_train_calibration_*
```

每份固定5题并满足 strict dataset mix。禁止跨 split 借 Item、重复引用或继承原外部 `paper_id` 语义；leftover 必须记录。生成 `internal_item_split_manifest.csv`、`internal_paper_manifest.csv` 和 `internal_split_audit.md`。

### 5.4 数据职责

| Split | 允许用途 | 禁止用途 |
|---|---|---|
| `train_fit` | 参数训练、能力画像主体、轨迹/replay、候选 checkpoint | 读取其他 split |
| `train_calibration` | 质量参考、预算、支持度边界、per-checkpoint STOP 边界、Package 组装 | 梯度、replay、跨 checkpoint 最终排名/选择 |
| Dev | 固定 Package 质量门与最终选择 | 重新校准边界 |
| Test | 一次性最终评价 | 训练、校准、筛选 |

### 5.5 Gate Error 与未完成处理

合法最终分数：

\[
E_i^{gate}=\frac{|\hat y_i-y_i|}{score_{max,i}-score_{min,i}}
\]

Deferral、预算耗尽后未安全完成、最终分数缺失/越界/不可解析或无合法 active cache 结果统一令 `E_i^{gate}=1`，防止放弃困难 Item 改善质量指标。

### 5.6 Severe/Extreme 与 Unsafe Stop

\[
Severe_i=\mathbf{1}[E_i^{gate}>0.25],\qquad Extreme_i=\mathbf{1}[E_i^{gate}\ge0.50]
\]

Severe 进入主质量门，Extreme 只作补充。`UnsafeStopRisk = STOP后Severe数量 / 全部STOP数量`；同时报告全 Item 发生率、Stop Coverage 和 Deferral Rate。`STOP count = 0` 时为 `NA` 且质量不可行。

### 5.7 Macro-NMAE

分别对 DREsS、ASAP-SAS、SAS-Bench 使用 Gate Error 计算 NMAE，`Macro-NMAE` 为三个 dataset NMAE 的不加权平均；Micro-NMAE 仅作补充。

### 5.8 固定11档 Macro-QWK

对 gold 和合法预测按各 Item 分值范围归一化到 `[0,1]`，使用：

\[
b_i=\min\left(10,\max\left(0,\left\lfloor10z_i+0.5\right\rfloor\right)\right)
\]

固定映射到 `0..10`。每个 dataset 至少100个有效完成 Item、至少2个非空 gold bin，且 expected weighted disagreement 大于0；否则 QWK 未定义并触发 readiness failure。

### 5.9 协议冻结

`configs/quality_protocol.yaml` 固定保存 Gate Error、Severe/Extreme、Unsafe Stop、Macro-NMAE、11档 QWK、readiness、Paper paired Bootstrap（5000次、单侧95%、零界、种子20260729）和 Dev 跨预算排序。Pilot、calibration、Dev 和 Test 均不得改变该协议。

## 6. Agent 池与正式 Cache 计划

### 6.1 Agent 角色

| Agent | 角色 | 是否直接评分 |
|---|---|---:|
| CheapAgent | 高吞吐基础评分 | 是 |
| MidAgent | 常规评分 | 是 |
| StrongAgent | 深度评分 | 是 |
| EvidenceAgent | Rubric/参考答案证据核验 | 辅助，可提供建议分数 |
| ArbitratorAgent | 基于已获得意见仲裁 | 是 |

### 6.2 冻结内容

Formal cache 前冻结：

- model id/revision；
- Prompt 文本、版本和 hash；
- generation parameters；
- 请求上下文 schema；
- 响应 JSON schema 和解析规则；
- 单价快照、token 计费和 latency 记录规则；
- Agent 角色和允许看到的信息；
- 有限 context/action support catalog 的模板、版本和 hash 规则。

### 6.3 Pilot

从 V1.4 重建后的完整 strict `paper_train_fit_*` 中抽取约100个 Item（约20份5题 Paper）运行 `real_pilot_<run_id>`，检查：

- JSON 成功率、越界率和失败率；
- Cheap/Mid/Strong 是否存在非平凡互补性；
- Evidence 是否提供增量证据；
- Arbitrator 是否仅使用已获得上下文并降低分歧；
- confidence/risk 可校准性；
- 实际 token、cost 和 elapsed time；
- Paper 级 calls/exchanges 与资源分布的可行性估计；
- Formal cache 及 support catalog 的规模、费用和时间估计。

Pilot 产物不能晋升为 Formal cache，Pilot 资源分位数也不能直接充当正式预算档位。

#### 6.3.1 CLIProxy GPT-5.6 Pilot 已批准执行方案

真实 Pilot 的候选接入为本机 CLIProxy/CC Switch Responses-compatible 网关。候选模型与角色固定为：Cheap=`gpt-5.6-luna`、Mid/Evidence=`gpt-5.6-terra`、Strong/Arbitrator=`gpt-5.6-sol`。运行前必须以代理模型目录和响应实际 `model` 字段证明三个型号均可用；任一模型发生静默替换、usage 缺失或认证不可用时停止，不得自动回退到其他模型。

100 Item 样本只从 `papers_train_fit.jsonl` 确定性抽取20份固定5题 strict Paper，固定 seed=42，不按 gold 或 Agent 误差选择。当前8种 Arbitrator context 全部是候选 arms，必须在相同100 Item上完整运行后再比较；5 Item与20 Item检查点只执行协议、模型身份、usage、成本、配额和稳定性停止门，不得提前按质量删除 context。完整候选规模为4个基础Agent加8种仲裁上下文，即1,200条成功记录；最多120次重试、总调用硬门1,320、按冻结官方 Standard API 价格计算的成本硬门75 USD。

成本必须由实际上游 usage 的普通输入、缓存读取、缓存写入、输出与 reasoning 明细结合运行目录内冻结的 `pricing_manifest` 重算；reasoning tokens 作为 output 明细不得重复收费。Pilot 结束后按协议资格、安全/严重错误、增量质量、累计成本/延迟/calls/exchanges及可达状态内 Pareto 支配关系生成 context 保留建议，只有用户审批后的子集才能成为 Formal `context_support_catalog.json`。本阶段不执行1,000 Item耐久测试；100 Item报告完成后停止，由用户决定是否补充规模验证或进入 Formal cache。

### 6.4 Formal cache 顺序

```text
freeze internal item/paper manifests
→ freeze context support catalog
→ train_fit cache（按internal split）
→ train_fit audit / capability fit / train trajectories
→ train_calibration cache（按internal split）
→ reference + budget + support-boundary freeze
→ per-checkpoint STOP boundary calibration / Package assembly
→ dev cache
→ fixed-Package quality gate + unique Dev selection + freeze
→ test cache
→ final evaluation only
```

Formal cache writer 必须以 internal item split 为 train 侧 split 来源，拒绝直接用旧 `paper_train_*` 推断 `train_fit/train_calibration`。Test cache 可生成，但只能由 final evaluation 读取。

### 6.5 能力画像

正式能力画像只使用 `train_fit` cache 拟合；若需要 low-support 或置信校准边界，只允许在 `train_calibration` 通过预注册程序自动校准，且 calibration 样本不得回流 Router 梯度训练。建议包含：

- dataset/question type/observable risk bin；
- NMAE、严重错分率、calibration；
- cost、elapsed time、样本数；
- uncertainty/low_support。

不得使用 dev/test，不得给出具体 Item 的 oracle 最优 Agent 标签。画像及校准结果在 Dev 前冻结，并设置 `without capability profile` 消融。

### 6.6 Formal Context Support

正式离线 cache 不枚举任意自由上下文。Formal cache 前冻结 `context_support_catalog.json`，定义允许的 Agent、上下文模板、前置意见集合、`context_template_id` 与 hash 规则。

环境只对同时满足结构合法、预算可行和 cache support 可用的动作开放；缺失或 catalog 外动作被屏蔽并记录，不能在 Dev/Test 在线补算。所有方法共享相同 catalog 与 active records。

---

## 7. 共享资源模型

### 7.1 四维资源向量

每个 Paper：

\[
B_P=[C_{max},T_{max},N_{max},M_{max}]
\]

其中：

- `max_cost`：累计货币或归一化计算成本；
- `max_elapsed_time`：串行 Agent 调用累计延迟；
- `max_agent_calls`：所有 Agent 调用总数；
- `max_a2a_exchanges`：完整 A2A 请求—响应交换次数。

### 7.2 动作资源消耗

| 动作 | Calls | Exchanges | Cost/Time |
|---|---:|---:|---|
| ROUTE_CHEAP/MID/STRONG | 1 | 0 | 对应 Agent 实际记录 |
| VERIFY | 1 | 0 | EvidenceAgent 实际记录 |
| A2A_ASK(target) | 1 | 1 | 目标 Agent 实际记录 |
| ARBITRATE | 1 | 0 | Arbitrator 实际记录 |
| STOP | 0 | 0 | 0 |

动作若使任一剩余资源为负，则被 Action Mask 屏蔽。

### 7.3 正式预算自动产生

当前 fixture 数值只用于 smoke。真实 Pilot 只估算费用和可行性，不直接提供正式预算。

Formal Agent/cache 冻结后，在重建的完整 `paper_train_calibration_*` 上运行预注册固定 behavior/reference policies，统计每 Paper 的 cost、elapsed time、calls 和 exchanges，并按实现前冻结的分位数规则自动生成 Tight/Medium/Loose。输出 `budget_calibration_manifest.json`，记录 internal paper manifest hash、policy ID、分位数、实际结果和配置指纹。

预算环境定义在候选 checkpoint 比较前冻结，不因某个 Router 的 Dev 表现改变。

### 7.4 预算耗尽

预算耗尽且存在未安全完成 Item 时：

- 记录 `budget_exhausted=true`；
- 记录 unfinished/deferral；
- 不强制 STOP；
- 不虚构 HumanAgent；
- 纳入失败和可行性指标。

---

## 8. MDP/CMDP 定义

### 8.1 状态

\[
s_t=[S_t^{item},S_t^{agent},S_t^{history},B_t^{remain}]
\]

仅含当前可见信息：

- Item 静态属性和当前候选分数；
- 已调用 Agent 分数、置信度、证据和分歧；
- 能力画像历史先验；
- A2A/仲裁历史；
- 已完成状态；
- 剩余 cost/time/calls/exchanges；
- 当前学习到的 unresolved scoring risk。

不得包含：

- gold score；
- test 误差；
- 未调用 Agent 输出；
- Item 级 oracle 最优动作。

### 8.2 动作

\[
a_t=(i_t,o_t)
\]

操作集合：

```text
ROUTE_CHEAP
ROUTE_MID
ROUTE_STRONG
VERIFY
A2A_ASK(target_agent)
ARBITRATE
STOP
```

### 8.3 状态转移

环境根据动作查询对应 cache，暴露结果，更新：

- Item 当前分数/证据/分歧；
- 历史；
- 剩余资源；
- 合法动作；
- 未解决风险；
- 完成状态。

### 8.4 约束

CMDP 以资源最小化为目标，同时满足：

```text
SevereError <= reference
UnsafeStop <= reference
NMAE <= reference
MacroQWK >= reference
```

质量不可由资源收益补偿。

---

## 9. CAG 与 Router 架构

### 9.1 共享 CAG 编码器

图节点：

- Item 节点；
- Agent 节点；
- Budget/episode 节点；
- 可选消息/意见节点。

图边只表示已经发生的调用、证据和通信，不为未调用 Agent 添加带输出的边。

### 9.2 最小正式架构

```text
CAG Shared Encoder
├── Routing Q Head
├── Stop-Risk / Safety Head
└── Resource Critic
```

`Quality Critic` 可在不增加不可控复杂度的前提下加入，但必须有独立消融或清晰理由。

### 9.3 Routing Q Head

通过离线 CQL/TD 学习长期任务—操作价值，保留 Double Q、Target Network、Action Mask 和 conservative penalty。

### 9.4 Stop-Risk Head

估计：

\[
r_\psi(s_{i,t})=P(\text{当前STOP导致严重错分}\mid s_{i,t})
\]

训练标签由 `train_fit` 中当前候选分数与 gold 自动生成；风险边界在 `train_calibration` 自动校准。该头只约束 `STOP`，不能指定升级 Agent。

### 9.5 Resource Critic

估计候选动作未来累计 cost/time/calls/exchanges，支持在质量可行动作中选择长期资源更低的动作。

### 9.6 动作选择

1. 结构/预算/cache-support Action Mask 屏蔽非法或无有效 cache 支持的动作；
2. Stop-Risk Head 对 `STOP` 进行质量安全约束；
3. Routing Q Head 在剩余动作中执行长期序列选择；
4. 质量可行性优先于资源排序。

---

## 10. 质量参考与配对统计门

### 10.1 候选集合

预先固定精确动作定义：

```text
Always-Cheap
Always-Mid
Always-Strong
Fixed Full Multi-Agent Workflow
```

### 10.2 自动选择

在 `train_calibration` 对每个预算档位先做 STOP/QWK readiness，再按固定顺序选择 reference policy。该步骤只确定质量门锚点，不比较 Router checkpoint：

```text
Quality Metrics Defined = Yes
→ Worst-Dataset Severe Error（低）
→ Worst-Dataset Unsafe Stop（低）
→ Macro-NMAE（低）
→ Macro-QWK（高）
→ Cost/Paper（低）
→ Elapsed Time/Paper（低）
→ Agent Calls/Paper（低）
→ A2A Exchanges/Paper（低）
→ Reference Policy ID（升序）
```

输出 `quality_reference_manifest.json`，记录全部候选和 `budget_id -> reference_policy_id` 映射，在 dev/test 前冻结。没有候选满足 readiness 时，该预算档位直接 readiness failure。

### 10.3 配对质量门

冻结的是参考策略、预算映射、指标协议和选择程序，而不是 `train_calibration` 数值。Dev 的第一层准入门和 Test 最终评价都让候选与对应固定参考在同一 split、Paper、Agent cache 与预算档位上配对；Dev 的第二层质量保护门复用同一程序，但将比较基准替换为自动确定的 Quality Champion。Test 不重新选择冠军。

固定 Bootstrap：

```yaml
unit: paper
paired: true
replicates: 5000
confidence_level: 0.95
sidedness: one_sided
noninferiority_margin: 0
seed: 20260729
```

候选减参考的四项通过条件：

```text
UCB95(max_dataset_delta_severe) <= 0
UCB95(max_dataset_delta_unsafe_stop) <= 0
UCB95(delta_macro_nmae) <= 0
LCB95(delta_macro_qwk) >= 0
```

同一重采样必须复用 Paper 索引，保留 Paper 内 Item 的依赖。任一主指标未定义、STOP/QWK readiness 失败、Bootstrap 失败、置信区间跨0或未达到边界时，输出 `quality_noninferiority_inconclusive` 或具体 readiness failure，并令 `Quality Feasible = No`。不得把“差异不显著”当作“已经证明不劣”。

## 11. 参数训练、边界校准与最终 checkpoint 选择

### 11.1 Train Fit：参数学习

仅使用 `paper_train_fit_*` 和 train_fit formal cache：

- 训练 CAG encoder、Routing Q Head、Stop-Risk Head、Resource Critic；
- 拟合能力画像主体；
- 构建 behavior trajectories 与 replay buffer；
- 生成预注册范围内候选 checkpoint。

Router 以剩余四维预算为状态输入，同一个 checkpoint 适配 Tight/Medium/Loose。`train_calibration/dev/test` 不得进入梯度、target、early stopping 或 replay。

### 11.2 Train Calibration：每个 checkpoint 独立固定边界

仅使用 `paper_train_calibration_*` 和 calibration formal cache，先冻结：

- 每预算质量参考映射；
- Tight/Medium/Loose 预算；
- 能力画像 low-support/uncertainty 边界；
- quality protocol、support catalog 和 internal manifest hash。

然后对每个候选 checkpoint：

1. 保持所有模型参数不变；
2. 自动校准唯一 STOP 安全概率边界；
3. 输出边界、coverage、quality constraint、failure reason；
4. 组装 Calibration/Policy Package。

calibration 不允许：

- 训练任何 Router/Head/Critic 参数；
- 构建或写入 replay buffer；
- 比较不同 checkpoint 的 Cost/Time/Calls/Exchanges；
- 输出最终 checkpoint 排名或最终选择；
- 为主方法的 Mid/Strong/VERIFY/A2A/ARBITRATE 生成升级阈值。

### 11.3 Dev Auto-Select：参考准入、质量保护后比较资源

Dev 对每个候选 Package：

1. 验证 calibration manifest、STOP 边界和全部 hash 已冻结；
2. 在每个预算档位计算正式指标与 readiness；
3. 在每个预算档位执行候选对固定参考策略的5000次 Paper 级配对 Cluster Bootstrap；
4. 任一预算档位参考准入失败即淘汰整个 Package；
5. 在全预算准入候选中，不使用资源指标，按冻结质量词典序确定唯一 Quality Champion；
6. 对其余准入候选，在每个预算档位执行候选对 Quality Champion 的四项零边界配对 Bootstrap；
7. 任一预算或任一质量维度不能证明不劣于冠军即淘汰，资源更低不能豁免；
8. 对质量保护可行 Package 计算跨预算等权 Cost/Paper、Elapsed Time/Paper、Agent Calls/Paper、A2A Exchanges/Paper；
9. 按冻结资源词典序自动输出唯一预算条件 Policy Package/checkpoint。

Dev 边界修改次数和 Quality Champion 人工替换次数必须均为0。相同输入、种子和 manifests 必须输出相同冠军、保护集合和最终结果。

### 11.4 Freeze

生成 `policy_freeze_manifest.json`，记录唯一 checkpoint、STOP 边界、质量协议、预算、参考映射、各预算参考准入门、Quality Champion 及选择键、候选对冠军质量保护门、跨预算资源键、internal manifests、Agent cache 和代码指纹。

### 11.5 Test

Test 只读取唯一冻结 Package 和隔离 test cache，一次性运行 final evaluation。任一预算档位 readiness、指标或置信区间失败均如实输出，不返回 calibration 或 Dev 更换边界/策略。

## 12. 离线轨迹与训练数据

### 12.1 轨迹来源

仅在 V1.4 重建的 `paper_train_fit_*` 和 train_fit hidden cache 环境中，使用固定 behavior policies 生成：

- 固定 Agent 轨迹；
- 自动阈值轨迹；
- A2A/仲裁轨迹；
- 多预算探索轨迹。

### 12.2 每步记录

```text
state_visible
valid_action_mask
action
revealed_agent_output
resource_delta
next_state_visible
stop_counterfactual_label(train only)
done/failure reason
```

不得把未调用 Agent 输出写入可见 state。

### 12.3 Hindsight Budget Relabeling

HBR 可保留，但必须：

- 不改变质量标签；
- 不从 train_calibration、Dev 或 Test 生成训练轨迹；
- 作为可消融组件；
- 不用于人为制造特定预算优势。

### 12.4 Replay Buffer 隔离

Replay buffer 只允许 train_fit 轨迹；train_calibration、dev 和 test 均不得进入梯度训练。

---

## 13. Baseline 计划

### 13.1 固定方法

- Always-Cheap；
- Always-Mid；
- Always-Strong；
- Fixed Full Multi-Agent Workflow。

### 13.2 自动校准与监督方法

- Single Agent + Automatically Calibrated Confidence Routing；
- Static Feature Classifier。

阈值和分类器只使用 train_fit/train_calibration，并遵守相同 Dev 自动选择门禁。

### 13.3 非 RL 动态方法

- Contextual Bandit；
- Top-k/Knapsack Allocation。

### 13.4 主方法

- Quality-Constrained CAG-CQL + Stop-Risk Head。

如简单方法达到相同质量—资源前沿，论文必须收缩 RL 必要性结论。

---

## 14. 消融计划

至少包括：

1. `without Stop-Risk Head`；
2. `without automatic risk calibration`；
3. `without A2A communication`；
4. `without budget state`；
5. `without Agent capability profile`；
6. `without CAG graph encoder`；
7. `without HBR`（若正式使用）；
8. `without hidden-cache enforcement` 只可作为诊断上界，不得作为合法方法。

主要比较：Severe Error、Unsafe Stop、NMAE、Macro-QWK、Quality Feasible、Cost、Calls 和 Budget Exhaustion。

---

## 15. 评价指标与报告规则

### 15.1 主质量与安全指标

- Quality Feasible；
- Dataset Severe Error 与 Worst-Dataset Severe Error；
- Dataset Unsafe Stop 与 Worst-Dataset Unsafe Stop；
- Unsafe Stop / All Items；
- Stop Coverage；
- Deferral Rate；
- Dataset NMAE、Macro-NMAE 和补充 Micro-NMAE；
- Dataset QWK 与 Macro-QWK；
- 补充 Extreme Error、MAE/RMSE、Within-1 Accuracy。

Deferral、预算耗尽后未安全完成、非法或缺失最终分数以 `Gate Error = 1` 进入 Severe 与 NMAE。`STOP count = 0` 时 Unsafe Stop 为 `NA`，质量不可行。

### 15.2 QWK Readiness

每个 dataset 必须报告：

```text
valid_completed_n >= 100
gold_nonempty_bin_count >= 2
expected_weighted_disagreement > 0
fixed_label_set = 0..10
qwk_defined
readiness_failure_reason
```

任一 dataset QWK 未定义时，Macro-QWK 不得进入质量门，候选直接 readiness failure。

### 15.3 配对统计质量门

对每个 `split × budget_id × candidate × reference` 保存：

- 指标点估计；
- candidate-reference delta；
- 5000次配对 Paper 重采样结果；
- 单侧95% UCB/LCB；
- 四项 pass flag；
- readiness 与最终状态。

正式条件：

```text
UCB95(max_dataset_delta_severe) <= 0
UCB95(max_dataset_delta_unsafe_stop) <= 0
UCB95(delta_macro_nmae) <= 0
LCB95(delta_macro_qwk) >= 0
```

置信区间跨0不是通过，必须标记 `quality_noninferiority_inconclusive`。

### 15.4 资源与路由指标

- Cost per Paper/Item；
- Cumulative Elapsed Time per Paper；
- Agent Calls per Paper/Item；
- Strong/Evidence/Arbitrator Call Rate；
- A2A Exchanges per Paper/Item；
- Token Usage；
- Budget Violation/Exhaustion；
- 平均路径长度、路径类型、有效通信、分歧降低和追加调用边际收益。

### 15.5 主表与选择顺序

主表列顺序：

```text
Method
Budget ID
Budget Reference Admission Feasible
Package Reference Admission Feasible
Quality Champion
Quality Protection Feasible
Quality Gate Status
Worst-Dataset Severe Error
UCB95(max_dataset_delta_severe)
Worst-Dataset Unsafe Stop
UCB95(max_dataset_delta_unsafe_stop)
Macro-NMAE
UCB95(delta_macro_nmae)
Macro-QWK
LCB95(delta_macro_qwk)
Stop Coverage
Deferral Rate
Cost/Paper
Elapsed Time/Paper
Agent Calls/Paper
A2A Exchanges/Paper
Budget Exhaustion
```

Dev 先报告相对于固定参考的准入状态，再报告 Quality Champion 和候选对冠军的质量保护状态。只有 `Quality Protection Feasible = Yes` 的 Package 才进入跨预算资源四项优先排序并形成总体资源节省声明；每个预算档位的完整结果仍保留。

### 15.6 失败保留

保存所有：

- run 与 checkpoint；
- Dev 指标与 QWK/STOP readiness；
- Bootstrap 置信边界；
- 自动资源排序；
- 淘汰原因；
- 校准失败；
- `quality_noninferiority_inconclusive`；
- Test 失败；
- 与简单 baseline 无差异的结果。

失败记录必须包含 quality protocol hash、split、budget、candidate/reference 和可追溯产物。

## 16. 阶段计划与门禁

### Phase 1：External Prepared Data（已完成）

现有 Item、外部 Paper、split/paper manifests 和 data audit 保持不变。门禁：外部 train/dev/test 泄漏为0。

### Phase 2：Agent Cache 工程 Fixture（已完成）

统一 Agent、cache、difficulty/capability fixture 和断点续跑已完成。门禁：Fixture smoke 通过，不代表正式论文 Agent 质量。

### Phase 3：V1.4 Internal Split、Paper Rebuild、协议基础与完整 Fixture Smoke（已完成）

1. 新增 internal split/rebuild schema 与配置；
2. 从27,375条 train 主路由 Item 构造 prompt/leakage connected components；
3. 按确定性约80%/20%目标分配 Item；
4. 分别重建 `papers_train_fit.jsonl` 与 `papers_train_calibration.jsonl`；
5. 生成 internal manifests、leftover 和阻塞性 audit；
6. 实现 V1.3 quality protocol、QWK readiness 和 Paper paired Bootstrap；
7. 实现 calibration 不训练/不排名与 Dev 不改边界的职责测试；
8. 在专用 fixture/config/test/run 位置完成 `item component split -> separate paper rebuild -> fixture cache -> train_fit fixture checkpoint -> train_calibration reference/budget/support/STOP calibration -> Package -> Dev three-layer selection -> freeze -> test-like one-shot`；
9. 审核测试契约与实现，使用预算不可行候选、NaN/重复 STOP 证据、失败 cache 续跑、正式路径/loader、STOP 边界应用、A2A 计数、完整确定性和 artifact inventory 反例，确认不存在 smoke-only 质量/选择旁路、Fixture/Formal 资产混用和人工阈值。

门禁：内部 Item/Prompt/Component/Paper 泄漏与 strict mix 违规全部为0；旧 `paper_train_*` 直接拆分次数为0；Fixture formal acceptance/online calls/cross-mode reuse 为0；calibration gradient/replay/ranking、Dev boundary update、Quality Champion resource read/manual override、test-like training read 均为0。

### Phase 4：真实 Agent Pilot 与 Formal Cache（下一阶段，需用户单独批准）

1. 从重建后的完整 `paper_train_fit_*` 抽取约100 Item/20 Paper Pilot；
2. 用户批准后运行，审核质量互补性、Evidence/Arbitrator 增益和费用；
3. Pilot 通过后冻结 Formal Agent/Prompt/解析/成本与 context support catalog；
4. 按 internal Item split 依次生成 train_fit、train_calibration、Dev formal cache；
5. 仅用 train_fit 拟合能力画像主体；
6. 使用 calibration 冻结支持度、质量参考和正式预算。

门禁：Pilot 不改变 internal split 或 V1.3质量协议；所有 Formal cache records 与 internal manifests 一致；Test 未参与。

### Phase 5：隐藏环境、轨迹、Router 参数训练与 Calibration Package

1. 只用 `paper_train_fit_*` 构建 hidden environment、behavior trajectories 和 replay buffer；
2. 训练 CAG shared encoder、Routing Q Head、Stop-Risk Head、Resource Critic 和质量约束 CQL；
3. 生成预注册候选 checkpoint；
4. 对每个冻结 checkpoint 只在 `paper_train_calibration_*` 上校准 STOP 边界；
5. 组装候选 Package，保留 calibration failure。

门禁：calibration 不更新参数、不进入 replay、不跨 checkpoint 排名；主方法升级动作仍由 Router 学习。

### Phase 6：Dev 固定参考准入、Quality Champion 保护、最终选择与 Baseline/消融

1. 对所有边界已冻结 Package 和保留 baseline 计算正式指标与 readiness；
2. 在每个预算档位执行对应固定参考的 paired Paper Bootstrap 准入门；
3. 淘汰任一预算档位准入失败的 Package，并只按冻结质量词典序确定唯一 Quality Champion；
4. 对其余准入候选执行候选对冠军的质量保护门，淘汰任何不能证明质量不劣于冠军的 Package；
5. 只在质量保护可行候选中按跨预算资源词典序自动选择唯一 Package/checkpoint；
6. 生成 freeze manifest，完成保留 baseline、消融和预算分析。

门禁：Dev 边界修改次数和 Quality Champion 人工替换次数均为0；没有全预算参考准入 Package 时记录失败，不返回 calibration 改边界；只有冠军通过质量保护门时直接选择冠军。

### Phase 7：Test Final Evaluation

验证 internal/external manifests、quality protocol、Package、边界、参考、预算、cache 和代码 hash 后，只运行一次 Test final evaluation，输出质量门、资源、失败状态、case study 和复现包。Test 后不再调参。

## 17. 运行产物

内部重建后的规范数据文件写入 `data/processed/`：

```text
data/processed/
├── internal_item_split_manifest.csv
├── papers_train_fit.jsonl
├── papers_train_calibration.jsonl
├── internal_paper_manifest.csv
└── leftover_items.csv
```

每次实验仍进入唯一 `outputs/runs/<run_id>/`，并保存上述规范数据的路径、大小和内容 hash，而不是在多个 run 中生成彼此不一致的内部 split。关键运行产物：

```text
outputs/runs/<run_id>/
├── configs/
│   ├── resolved configs
│   ├── quality_protocol.yaml
│   ├── external_data_manifest.json
│   ├── internal_data_snapshot_manifest.json
│   ├── quality_reference_manifest.json
│   ├── budget_calibration_manifest.json
│   └── policy_freeze_manifest.json
├── predictions/
│   ├── agent_cache/
│   ├── calibration_package_manifest.jsonl
│   └── policy_evaluations/
├── checkpoints/
├── logs/
├── reports/
│   ├── internal_split_audit.md
│   ├── internal_split_distribution.csv
│   ├── agent_cache_audit.*.md
│   ├── qwk_readiness.csv
│   ├── risk_calibration_report.csv
│   ├── quality_gate_bootstrap.csv
│   ├── checkpoint_selection.csv
│   ├── main_results.csv
│   ├── dataset_quality_results.csv
│   ├── ablation_results.csv
│   ├── failure_registry.jsonl
│   └── case_study.md
└── figures/
```

`calibration_package_manifest.jsonl` 每行对应一个固定 checkpoint，只记录 STOP 边界、coverage、failure、参考/预算和 hash，不允许包含跨 checkpoint Dev rank 或最终选择。`checkpoint_selection.csv` 只能由 Dev selector 生成。

所有主表必须能从 predictions、external/internal manifests、协议快照、calibration packages 和统计产物重新生成。

## 18. 技术上下文

**语言**：Python 3.11+。
**核心依赖**：PyTorch、PyTorch Geometric、NumPy、pandas、scikit-learn、PyYAML、matplotlib、pytest；真实模型 SDK/权重须另行批准。
**存储**：JSONL/CSV/YAML/checkpoint；所有运行产物进入 `outputs/runs/<run_id>/`。
**测试**：external/internal split audit、strict Paper rebuild、unit、integration、fixture smoke、quality protocol、paired Bootstrap、formal artifact audit。
**数据**：外部三个数据集与36,185条主 Item 范围不变；train 27,375条 Item 内部重分配并重建 Paper。
**Agent**：五类冻结角色。
**主方法**：单一预算条件 Quality-Constrained CAG-CQL + Stop-Risk Head checkpoint。
**职责**：train_fit 参数学习；train_calibration per-checkpoint STOP boundary/package；Dev final selection；Test one-shot。

---

## 19. Constitution 检查

- **简体中文**：通过。
- **论文实验优先**：通过；内部重建只服务实验可信度，不建设生产系统。
- **可复现性**：group allocation、Paper rebuild、calibration、Dev 选择和失败均保存 manifest/hash。
- **数据完整性**：外部 split 不变；内部先按 component 拆 Item、后重建 Paper；calibration/dev/test 不训练。
- **公平评价**：所有方法共享 internal papers、cache、预算、质量协议、参考和评价脚本。
- **Smoke first**：internal rebuild/audit 和职责隔离 smoke 位于 Pilot/Router 前。
- **依赖安装**：真实 SDK/权重/API 必须另行获得用户批准并优先使用 D 盘。
- **运行目录**：全部进入唯一 `outputs/runs/<run_id>/`。

门禁状态：V1.4 设计层通过；具体 component allocation 实现、实际 internal Paper 数量/比例、Stop-Risk 校准算法、参考动作语义和正式预算分位数必须在实现前通过配置与 fixture 固定，不得根据 Dev/Test 改动。

---

## 20. 项目结构

新增或扩展：

```text
configs/
├── dataset.yaml
├── quality_protocol.yaml
└── experiments/
    ├── fixture_smoke.yaml
    └── fixture_smoke_agents.yaml

src/a2a_dygrade_rl/
├── datasets/
│   ├── internal_split.py
│   ├── build_internal_papers.py
│   └── audit_internal_split.py
├── agents/
│   ├── capability.py
│   └── cache.py
├── router/
│   ├── action.py
│   ├── action_mask.py
│   ├── state.py
│   ├── stop_risk_head.py
│   ├── resource_critic.py
│   └── cag_cql_policy.py
├── rl/
│   ├── hidden_cache_env.py
│   ├── trajectory_builder.py
│   ├── replay_buffer.py
│   ├── quality_reference.py
│   ├── budget_calibration.py
│   ├── calibration.py
│   ├── policy_package.py
│   ├── checkpoint_selector.py
│   ├── train_cag_cql.py
│   └── evaluate_policy.py
└── evaluation/
    ├── quality_protocol.py
    ├── metrics_quality.py
    ├── metrics_safety.py
    ├── qwk_readiness.py
    ├── paired_bootstrap.py
    ├── statistical_gate.py
    ├── report_tables.py
    └── failure_registry.py

scripts/
├── 04a_build_internal_split.py
├── 04c_build_internal_papers.py
└── 04d_run_quality_constrained_fixture_smoke.py

tests/
├── fixtures/quality_constrained_smoke/
└── integration/test_quality_constrained_smoke.py
```

CLI 只做流程编排，业务逻辑留在 `src/`。具体任务见 `tasks.md`。

---

## 21. 复杂度与风险跟踪

| 风险 | 控制措施 |
|---|---|
| 直接拆现有 Paper 导致 prompt 泄漏 | 明确禁止；先按 Item component 分配，再分别重建 Paper；审计直接拆分次数为0 |
| 大型 prompt group 使80/20无法精确 | group 完整性优先；确定性优化实际比例；记录偏差和leftover，不结果后重拆 |
| 重建后 strict Paper 数量下降 | 在无泄漏和三数据集覆盖前提下最大化合法 Paper；报告利用率和数据量学习曲线 |
| Calibration 与 Dev 功能重复 | calibration只校准每个checkpoint STOP边界且无跨checkpoint排名；Dev只选择固定Package |
| Calibration 退化成固定级联 | 主方法只校准 STOP；升级、核验、仲裁和下一 Item 由 Router 学习；阈值方法仅作baseline |
| Calibration 数据回流训练 | schema/loader 默认拒绝；gradient/replay consumption审计为0 |
| Dev 过拟合 | 边界在calibration冻结；Dev只执行质量门与单一固定排序；保留全部候选 |
| Stop-Risk Head 使方法退化为分类器 | 风险头只约束STOP，Routing Q仍决定多任务多动作 |
| 质量参考过强导致无可行 Router | 如实输出失败，不降低参考或非劣效门 |
| Deferral 改善表面质量 | Deferral、未安全完成和非法结果统一Gate Error=1 |
| QWK异构尺度/退化 | 固定0..10 labels和readiness；未定义直接失败 |
| Test 被重复使用 | freeze manifest、one-shot记录和失败封存 |
| Formal cache 成本过高 | 先在重建train_fit Paper做用户批准Pilot；有限support catalog；Pilot不晋升Formal |

---

## 22. 下一步

依据 `tasks.md`，实现顺序固定为：

1. V1.4 internal component split、两个 strict Paper rebuild 和 audit；
2. internal manifests/schema/config 与 fixture tests；
3. V1.3 quality protocol、QWK readiness、paired Bootstrap；
4. train_fit-only 参数/轨迹边界与 calibration no-gradient/no-ranking 门禁；
5. per-checkpoint STOP calibration、Calibration Package，以及 Dev 的固定参考准入、Quality Champion 保护与资源 selector smoke；
6. 向用户提交基于重建 train_fit Paper 的真实 Agent Pilot 模型、费用、support catalog 和依赖审批方案。

完整 Fixture Smoke 已实现、审核并通过；下一步只准备 T052A 的真实 Agent Pilot 候选配置和审批材料，不联网、不下载依赖、不调用真实模型，直到用户单独批准。

