# 面向模拟试卷级自动阅卷的质量约束多智能体动态路由实验设计方案

> 方法名称：**A2A-DyGrade-RL**
> 英文题目：**Quality-Constrained Multi-Agent Dynamic Routing for Simulated Paper-Level Automated Scoring**
> 版本：2.3（同步 V1.4 职责、内部拆分与质量保护正式稿）
> 修订日期：2026-07-29
> 状态：V1.4 质量保护与精简 Baseline 正式设计稿（等待实现）
> 最高规则：`AGENTS.md`

---

## 0. 本次修订的硬性原则

本方案统一执行以下六项正式决定：

1. 论文方向正式确定为：**面向模拟试卷级自动阅卷的质量约束多智能体动态路由方法研究**。
2. 评分准确性和严重错分风险是最高优先级；必须先通过固定参考准入门，再通过 Quality Champion 质量保护门，资源下降不得补偿相对于参考或冠军的质量失败。
3. 主方法的下一 Item、升级、核验、二评和仲裁由 Router 学习；只对 STOP 安全概率边界进行独立自动校准，禁止研究者根据结果手工调边界。
4. 正式质量协议固定为 Gate Error、Severe/Extreme Error、Unsafe Stop、Macro-NMAE、固定11档 Macro-QWK 和 Paper 级配对 Cluster Bootstrap。
5. `train_fit` 只训练参数，`train_calibration` 只校准每个冻结 checkpoint 的 STOP 安全边界并组装 Package，Dev 才在完整 Package 之间选择唯一 Router；三者职责不得混用。
6. 不直接拆现有 train Paper；必须先把原 train 主路由 Item 按不可拆分题目组划入 `train_fit/train_calibration`，再分别重建固定5题 strict Paper。

统一实验流程：

```text
外部train主路由Item
→ 按prompt/exact-answer/leakage传递连通分量确定性拆分
→ 分别重建train_fit/train_calibration strict Paper
→ train_fit：学习Router和风险模型参数
→ train_calibration：只校准STOP安全边界并冻结参考/预算/Package
→ dev：先执行固定参考准入门，再确定Quality Champion并执行质量保护门，最后按资源词典序选择唯一checkpoint
→ freeze：锁定模型、Prompt、指标协议、边界、预算、质量门和checkpoint
→ test：一次性最终评价；质量门不通过即如实保留失败
```

统一选择原则：

> **先证明评分质量相对参考策略不劣，再在质量可行策略中最小化 Cost、Elapsed Time、Agent Calls 和 A2A Exchanges。**

## 1. 研究方向定位

本文不训练、不微调评分 Agent，不以提升某个评分模型的 QWK 为贡献，也不研究系统能够批改什么题。Cheap/Mid/Strong/Evidence/Arbitrator 的评分能力由冻结模型、Prompt 和输入上下文决定；Router 的研究任务是在这些评分能力已经存在的条件下，对多道待评分作答进行质量约束的序列调度。

本文的研究对象是一份**模拟试卷级评分 episode**。Router 每一步需要联合决定：

- 下一步处理哪道作答；
- 调用哪个评分 Agent；
- 是否进行 Rubric 证据核验；
- 是否请求独立第二意见；
- 是否进行仲裁；
- 是否能够安全停止；
- 如何在多道作答之间分配剩余资源。

核心问题是：

> 在未调用 Agent 输出不可见、评分信息逐步产生、多道任务共享成本与调用资源的条件下，质量约束的离线强化学习 Router 能否在评分质量和严重错分风险不劣于自动参考策略的前提下，减少达到可靠评分所需的资源？

核心表述为：

> **我们固定的是评分 Agent，不固定的是评分过程。**

---

## 2. 研究范围与非目标

### 2.1 本文研究

- 模拟试卷中的多题共享预算；
- 多 Agent 可变长度评分路径；
- 逐步评分、证据、分歧和通信状态；
- Router 对下一任务和下一操作的联合选择；
- 自动质量参考、自动风险校准和自动 checkpoint 选择；
- 质量可行条件下的资源优化；
- 强分类器、Bandit、knapsack 与 RL 的公平比较。

### 2.2 本文不研究

- 评分 Agent 训练或微调；
- 专用评分模型构建；
- 任意题目、任意考试的通用评分；
- Agent 评分覆盖范围扩展；
- `student_id`、`exam_id`、学生能力或整卷总分建模；
- 真实学生原始试卷恢复；
- 生产级在线阅卷平台；
- 第一版真实并发 makespan；
- 未正式建模的人工复核收益。

---

## 3. 模拟试卷与数据定义

### 3.1 单道评分任务

每道作答表示为：

\[
x_i=(prompt_i,answer_i,rubric_i,reference_i,scale_i,type_i)
\]

其中：

- `prompt`：题目；
- `answer`：学生作答；
- `rubric`：评分标准；
- `reference`：参考答案或得分点；
- `scale`：分值范围；
- `type`：题型、学科和语言等属性。

Agent 和 Router 均不需要真实 `student_id`。真实系统中的 `exam_id` 可以用于检索 Rubric 和归档成绩，但不作为大模型评分证据。

### 3.2 模拟试卷

一份模拟试卷表示为：

\[
P=\{x_1,x_2,\ldots,x_n\}
\]

当前主实验固定：

```text
n = 5
2～3条 ASAP-SAS
1～2条 SAS-Bench
1条 DREsS
```

模拟试卷中的：

| 内容 | 性质 |
|---|---|
| 原始题目 | 真实数据 |
| 学生答案 | 真实学生作答 |
| Rubric/参考答案 | 原数据集信息 |
| Gold score | 原数据集人工评分 |
| 多条作答组合关系 | 模拟构造 |
| 共享资源 | 实验设定 |
| Agent 调用路径 | Cache replay/模拟环境 |

因此本文使用：

> **基于真实学生作答重组的模拟试卷。**

不声称它是某名真实学生在某场真实考试中的原始试卷。

### 3.3 代码字段

代码中继续保留 `paper_id`，但论文和报告语义为：

```text
simulated_paper_id
scoring_episode_id
```

---

## 4. 数据集与当前数据状态

继续使用：

| 数据集 | 类型 | 作用 |
|---|---|---|
| DREsS | Rubric-based 英语作文 | 长文本、Rubric 和证据风险 |
| ASAP-SAS | 短答案 | 经典离散评分任务 |
| SAS-Bench | 多学科简答 | 多学科、分步得分和错误异构性 |

当前 prepared data：

| Split | Item | Paper | Paper引用Item |
|---|---:|---:|---:|
| Train | 28,038 | 5,475 | 27,375 |
| Dev | 3,244 | 196 | 980 |
| Test | 8,251 | 1,566 | 7,830 |
| 合计 | 39,533 | 7,237 | 36,185 |

审计状态：

```text
Prepared Data Audit = PASS
Item leakage = 0
Prompt leakage = 0
Paper leakage = 0
Paper reference error = 0
Strict mix deviation = 0
```

主 Router、轨迹和主评价只使用 `paper_manifest.csv` 引用的36,185条 Item。未进入 Paper 的 Item 可用于独立 Agent QA，不进入主路由训练和主结果。

---

## 5. 数据划分、内部 Paper 重建与防泄漏

### 5.1 外部划分保持不变

现有 prompt-aware `train/dev/test`、prepared Item 和外部 Paper 继续保持。原始 Dev 只用于完整 Policy Package 的统计质量门与自动选择，原始 Test 只用于冻结后的最终评价。

外部 train 中：

```text
Prepared Item：28,038
现有train Paper：5,475
现有train Paper引用Item：27,375
```

内部拆分只使用当前27,375条主路由候选 Item，不把另外663条未入 Paper Item 擅自扩入主实验；后者继续用于独立 Agent QA。

### 5.2 禁止直接切分现有 train Paper

不能将现有 `paper_train_*` 随机或按比例直接分到 `train_fit/train_calibration`。本地审计显示：

```text
现有train Paper：5,475
prompt group：2,903
按共享prompt group连接后的Paper连通分量：1
最大连通分量：5,475（100%）
```

原因是不同 Paper 反复共享大型 prompt group。直接切 Paper 会使同一题目组跨内部 split；若强制 Paper 与 prompt group 同时完整，则5,475份 Paper 无法拆成两个非空独立部分。

因此，现有外部 `papers_train.jsonl` 和 `paper_manifest.csv` 只保留为 prepared data 来源、Item 范围和审计证据，不能直接作为内部训练 episode manifest。

### 5.3 先按题目组拆分原 train Item

从当前27,375条 train 主路由 Item 建立不可拆分内部单元。原子关系包括：

- 相同 `dataset + prompt_group`；
- 相同 exact prompt-answer/leakage component；
- 上述关系传递连接形成的 connected component。

以固定随机种子和预注册确定性算法把完整内部单元分配到：

```text
train_fit
train_calibration
```

目标比例为约80%/20%，但优先级固定为：

1. prompt、exact answer 和 component 完整性；
2. 两个 split 都能覆盖三个数据集并构造 strict Paper；
3. 最大化可构造的合法5题 Paper 总数；
4. 在上述条件下最小化与80%/20%目标的偏差；
5. 使用稳定 group hash/固定种子解决并列。

不得为了凑精确比例拆开题目组，也不得根据 Router 或 Agent 实验结果重新分配 group。

### 5.4 在两个内部 split 中分别重建 Paper

Item 分配冻结后，分别运行 strict Paper builder：

```text
train_fit Item pool
→ papers_train_fit.jsonl
→ paper_train_fit_*

train_calibration Item pool
→ papers_train_calibration.jsonl
→ paper_train_calibration_*
```

每份内部 Paper 继续固定5题，并满足同一 strict dataset mix。硬约束：

- Paper 只能引用本 split Item；
- 一个 Item 不得跨 split 或在同一内部实验范围重复引用；
- 不得从另一 split 借 Item 完成 Paper；
- 不能组成 strict Paper 的 leftover Item 单独记录，不静默丢失；
- 新 `paper_id` 与原 `paper_train_*` 无语义继承关系，但保存来源 Item 与构造版本。

### 5.5 四个数据阶段的最终职责

| 数据 | 唯一用途 | 禁止事项 |
|---|---|---|
| `train_fit` | 训练 Router、Stop-Risk Head、critics 和其他可学习状态组件；拟合正式能力画像 | 读取 calibration/dev/test；在其结果反馈后继续改参数 |
| `train_calibration` | 为每个冻结 checkpoint 自动校准 STOP 安全概率边界；冻结质量参考、预算和画像支持度边界；组装完整候选 Policy Package | 更新模型参数、进入 replay buffer、比较不同 checkpoint 的最终资源排名或选冠军 |
| `dev` | 对边界已冻结的 Package 运行各预算质量门，并跨预算资源排序选择唯一 Package/checkpoint | 重新拟合、移动或试探边界 |
| `test` | 所有组件冻结后一次性最终评价 | 任何训练、校准、筛选或返回调参 |

主 Router 的 Mid/Strong、VERIFY、A2A、ARBITRATE 和跨 Item 调度由 Routing Q Head 学习；`train_calibration` 不为这些动作生成一套升级阈值。阈值 baseline 可以在 calibration 上自动校准自身阈值，但 Dev 同样不得修改。

### 5.6 必须生成的内部产物与审计

```text
internal_item_split_manifest.csv
papers_train_fit.jsonl
papers_train_calibration.jsonl
internal_paper_manifest.csv
internal_split_audit.md
```

manifest 至少记录：

- `item_id`、dataset、prompt group、leakage component；
- internal split；
- source external paper ID（仅溯源）；
- new internal paper ID；
- strict mix、构造规则版本、随机种子；
- leftover reason。

阻塞性审计必须满足：

```text
Internal item overlap = 0
Internal prompt-group overlap = 0
Internal exact-answer/component overlap = 0
Internal paper overlap = 0
Cross-split paper reference error = 0
Strict five-item paper violation = 0
Strict dataset-mix violation = 0
Calibration gradient/replay consumption = 0
```

### 5.7 Test 红线

Test 不参与：

```text
Agent Prompt修改
模型选择
风险模型训练
STOP边界校准
质量参考选择
能力画像
预算档位生成
指标协议修改
reward调整
checkpoint选择
replay buffer
```

Test 结果不理想时，不能返回 Dev 改边界、改指标或改 checkpoint 后重复把同一 Test 当作最终测试。

## 6. 正式质量误差、NMAE 与 QWK 协议

### 6.1 Gate Error

对存在合法 active cache 结果、最终分数可解析且位于题目分值范围内的 Item，定义：

\[
R_i=score_{max,i}-score_{min,i}
\]

\[
E_i^{gate}=\frac{|\hat y_i-y_i|}{R_i}
\]

以下情况统一赋予最坏损失：

\[
E_i^{gate}=1
\]

- Deferral；
- Budget Exhaustion 后仍未安全完成；
- 最终分数缺失、越界或不可解析；
- 无合法 active cache 结果。

该规则防止方法通过放弃困难 Item 人为降低错误率。`train_fit` 可使用 `1-E_i^{gate}` 构造质量监督或 counterfactual 标签；正式 NMAE 与 Severe Error 必须直接基于 `E_i^{gate}`。

### 6.2 Severe Error 与 Extreme Error

\[
Severe_i=\mathbf{1}[E_i^{gate}>0.25]
\]

\[
Extreme_i=\mathbf{1}[E_i^{gate}\ge 0.50]
\]

`Severe Error` 进入主质量门；`Extreme Error` 只作补充敏感性分析。两个阈值均属于冻结指标协议，不在 `train_calibration` 学习，也不得根据实验结果调整。

### 6.3 Unsafe Stop

主指标定义为：

\[
UnsafeStopRisk=\frac{\#\{STOP\land Severe\}}{\#\{STOP\}}
\]

同时报告：

- `Unsafe Stop / All Items`；
- `Stop Coverage = STOP count / All Items`；
- `Deferral Rate`。

若 `STOP count = 0`，则 `UnsafeStopRisk = NA` 且 `Quality Feasible = No`，不能记为0，也不能通过从不停止规避不安全停止风险。

### 6.4 Macro-NMAE

对每个数据集分别计算：

\[
NMAE_g=\frac{1}{|I_g|}\sum_{i\in I_g}E_i^{gate}
\]

主指标为：

\[
MacroNMAE=\frac{NMAE_{DREsS}+NMAE_{ASAP-SAS}+NMAE_{SAS-Bench}}{3}
\]

三个数据集不加权平均，以避免样本量较大的数据集支配主结论。全部 Item 直接平均的 `Micro-NMAE` 只作补充。

### 6.5 固定11档 Macro-QWK

对 gold 和合法预测分数分别按题目分值范围归一化：

\[
z_i=\frac{score_i-score_{min,i}}{R_i}
\]

再使用 half-up 规则固定映射到0～10共11档：

\[
b_i=\min\left(10,\max\left(0,\left\lfloor 10z_i+0.5\right\rfloor\right)\right)
\]

正式 QWK 必须：

1. 使用完整固定 label set `0..10`；
2. 不得使用当前样本实际出现标签的 union；
3. 分别计算 `QWK_DREsS`、`QWK_ASAP-SAS`、`QWK_SAS-Bench`；
4. 对三个 dataset QWK 做不加权算术平均得到 `Macro-QWK`；
5. 每个 dataset 至少包含100个有效完成 Item、至少2个非空 gold bin，且 expected weighted disagreement 大于0。

任一 dataset 不满足第5项时，QWK 未定义并触发 `qwk_readiness_failure`；对应候选不得通过质量门。Deferral 或非法最终分数不进入 QWK 混淆矩阵，但已经通过 `Gate Error = 1` 进入 Severe Error 与 Macro-NMAE，不能因此获得质量优势。

### 6.6 使用边界

- QWK 是 dataset-level 统计指标，不能作为单条 Item 的即时 reward；
- Severe/Extreme 阈值、11档映射、完整 label set 和 readiness 条件在任何真实 Pilot 与 Router 结果前冻结；
- Dev/Test 使用完全相同的指标实现与协议 hash；
- 补充 MAE、RMSE、Within-1 Accuracy 不替代主质量门。

## 7. Agent 设计与冻结

### 7.1 Agent 池

| Agent | 角色 | 主要输出 |
|---|---|---|
| `CheapAgent` | 高吞吐基础评分 | score、confidence、依据 |
| `MidAgent` | 常规评分 | score、confidence、依据 |
| `StrongAgent` | 深度评分 | score、confidence、关键证据 |
| `EvidenceAgent` | Rubric/参考答案核验 | matched/missing points、coverage、建议 |
| `ArbitratorAgent` | 已获得意见的仲裁 | final score、confidence、仲裁理由 |

`A2A_ASK(target)` 是路由操作，不是第六个独立 Agent。

### 7.2 冻结内容

Formal cache 前固定：

```text
model_id/model_revision
Prompt文本/version/hash
temperature/max_tokens
请求上下文schema
响应JSON schema
解析规则
Agent角色
成本与延迟记录规则
价格快照
```

冻结 Agent 不等于能力画像，也不等于预先知道每题最优 Agent。

### 7.3 Gold 隔离

Agent 请求中禁止包含：

```text
gold_score
test误差
最优Agent标签
未调用Agent输出
```

Gold 只能在 Agent 返回后由 cache writer 关联，用于训练范围监督和最终评价。

---

## 8. Agent Cache 与信息权限

### 8.1 Cache schema

每条记录至少包含：

```text
item_id
agent_id
split
pred_score
confidence
justification
evidence
cost
latency
token_usage
model_id
prompt_version
prompt_hash
context_hash
cache_key
execution_mode
status/error
```

### 8.2 模式隔离

```text
fixture_smoke_<run_id>
real_pilot_<run_id>
formal_agent_cache_<run_id>
```

Fixture、Pilot 和 Formal active cache 不得互相复制、续跑或晋升。

### 8.3 主 Cache 范围

Formal 主路由 cache 只覆盖 Paper 引用 Item：

```text
Train 27,375
Dev 980
Test 7,830
```

实际范围必须写入 cache manifest 和数据指纹。

### 8.4 Arbitrator 上下文

Arbitrator 只能看到已经实际调用的意见。Cache key 必须包含：

```text
参与Agent集合
已有score/confidence
已有Evidence
context_hash
```

不得通过 Arbitrator 间接获得尚未调用的 StrongAgent 等输出。

### 8.5 Formal Context Support Catalog

为避免离线 cache 对任意上下文组合无限展开，正式 cache 前必须预注册有限的 `context_support_catalog.json`，列出允许的 Agent、上下文模板、前置可见意见集合、`context_template_id` 和版本指纹。

离线 Router 只能选择“结构合法、预算可行且当前 context 存在有效 active cache record”的动作；不在 catalog 中或缺少合法记录的动作必须被 Action Mask 屏蔽并记录 `unsupported_context/cache_missing`，不得在评价时临时调用在线模型补齐。所有 baseline、消融和主方法共享同一 catalog。

---

## 9. Agent 能力画像

能力画像在 Agent 定义已冻结且 `train_fit` Formal cache 通过审计后自动生成。用于 Router 训练和推断的画像统计参数只允许由 `train_fit` 拟合；若存在 low-support 或置信校准边界，只允许在 `train_calibration` 按预注册程序自动校准，不得将 calibration 样本回流梯度训练。建议包含：

```text
Agent
可观察任务属性
NMAE
严重错分率
confidence calibration
cost
elapsed time
sample count
uncertainty/low_support
```

能力画像只提供历史先验，不能：

- 直接指定某道题的最优 Agent；
- 使用 Test；
- 按照 Test 结果手工修改；
- 替代当前评分、证据和分歧状态。

必须设置 `without capability profile` 消融。

现有静态 difficulty 工程产物可作为诊断或初始特征，但正式论文状态统一改为：

> **动态未解决评分风险（unresolved scoring risk）**。

---

## 10. 模拟试卷级共享资源

### 10.1 资源向量

\[
B_P=[C_{max},T_{max},N_{max},M_{max}]
\]

对应：

```text
max_cost
max_elapsed_time
max_agent_calls
max_a2a_exchanges
```

### 10.2 累计定义

\[
C(\tau)=\sum_t c(a_t)
\]

\[
T(\tau)=\sum_t \ell(a_t)
\]

\[
N(\tau)=\sum_t\mathbf 1[a_t\text{调用Agent}]
\]

\[
M(\tau)=\sum_t\mathbf 1[a_t=A2A\_ASK]
\]

第一版 `T` 是串行累计调用延迟，不称为真实并行 makespan。

### 10.3 动作消耗

| 动作 | Calls | A2A Exchanges |
|---|---:|---:|
| `ROUTE_CHEAP/MID/STRONG` | 1 | 0 |
| `VERIFY` | 1 | 0 |
| `A2A_ASK(target)` | 1 | 1 |
| `ARBITRATE` | 1 | 0 |
| `STOP` | 0 | 0 |

### 10.4 预算自动产生

当前已实现 fixture 仍使用以下 legacy 字段，仅用于 smoke 兼容：

```yaml
max_cost: 0.20
max_latency: 30.0
max_agent_calls: 12
max_a2a_messages: 6
```

其中 `max_latency` 与 `max_a2a_messages` 分别映射到正式语义 `max_elapsed_time` 与 `max_a2a_exchanges`。V1.3 实现阶段必须将 Formal schema 和新产物统一为正式字段；legacy 字段只能作为旧 fixture 的显式兼容输入，并在 manifest 中记录迁移，不得出现在正式论文预算产物中。

上述数值只用于 smoke，不直接作为正式论文预算。

真实 Agent Pilot 只用于估算调用质量、费用和可行性。Formal Tight/Medium/Loose 必须在冻结 Agent cache 后，使用 `train_fit/train_calibration` 中完整5题 Paper 上的预注册固定 behavior/reference policies 产生 paper-level cost、elapsed time、calls 和 exchanges 分布，再按预注册分位数（例如25/50/75）自动生成。预算生成后保存 manifest，不根据主方法结果移动档位。

### 10.5 预算耗尽

预算耗尽而任务未安全完成时：

```text
budget_exhausted = true
unfinished/deferral = true
```

不得强制 `STOP` 或虚构人工复核。

---

## 11. MDP/CMDP 定义

### 11.1 状态

\[
s_t=[S_t^{item},S_t^{agent},S_t^{history},B_t^{remain}]
\]

Item 状态：

```text
题型和可观察文本特征
当前候选分数
已获得confidence/evidence/disagreement
已调用Agent集合
完成状态
动态未解决风险
```

Agent 状态：

```text
角色
能力画像先验
成本/延迟
是否已调用
当前是否合法
```

History 状态：

```text
评分调用
A2A exchange
Evidence
仲裁
```

Budget 状态：

```text
remaining_cost
remaining_elapsed_time
remaining_calls
remaining_exchanges
```

状态中禁止包含 gold 和未调用 Agent 输出。

### 11.2 动作

\[
a_t=(i_t,o_t)
\]

```text
ROUTE_CHEAP
ROUTE_MID
ROUTE_STRONG
VERIFY
A2A_ASK(target_agent)
ARBITRATE
STOP
```

### 11.3 转移

执行动作后：

1. 环境查询对应隐藏 cache；
2. 暴露本次 Agent 输出；
3. 更新当前分数、证据和分歧；
4. 扣除资源；
5. 更新风险、历史和动作掩码；
6. Router 选择下一步。

---

## 12. Cache 逐步暴露硬约束

Agent cache 只能作为隐藏环境查询表。

正确流程：

```text
Router选择动作
→ 环境查询对应cache
→ 只暴露该动作的输出
→ 更新状态
→ Router继续决策
```

严禁：

```text
初始状态同时提供Cheap/Mid/Strong/Evidence/Arbitrator全部结果
```

否则问题退化为预知结果后的分类或组合优化。

隐藏 cache 必须有单元和集成测试，任何未调用输出进入状态均为阻塞性错误。

---

## 13. 动作掩码

### 13.1 结构掩码

- 无合法评分时不能 `STOP`；
- 只有一个评分意见时不能 `ARBITRATE`；
- 没有 Evidence 上下文时不能执行依赖 Evidence 的仲裁；
- 已完成 Item 不再调用 Agent；
- 同一 context 不重复仲裁；
- Agent 输入权限不满足时屏蔽动作。

### 13.2 资源掩码

动作会使 cost/time/calls/exchanges 任一资源为负时屏蔽。

### 13.3 质量安全约束

结构合法不等于质量安全。`STOP` 还需经过 Stop-Risk Head 的自动校准风险约束。

---

## 14. CAG-CQL Router 架构

### 14.1 最小正式架构

```text
CAG Shared Encoder
├── Routing Q Head
├── Stop-Risk / Safety Head
└── Resource Critic
```

### 14.2 CAG Shared Encoder

节点包括：

- Item；
- Agent；
- Budget/Episode；
- 可选消息或评分意见。

边只表示已经发生的调用、证据和通信。未调用 Agent 不得带预测输出边。

### 14.3 Routing Q Head

学习任务—操作的长期价值，保留：

- Double Q；
- Target Network；
- Action Mask；
- CQL conservative penalty；
- 预算条件状态。

### 14.4 Resource Critic

预测候选动作未来累计 cost、elapsed time、calls 和 exchanges，帮助在质量可行动作中选择资源更低的长期路径。

### 14.5 方法属性

加入 Stop-Risk Head 后，方法仍属于强化学习，更准确地称为：

> **带学习型安全约束的离线强化学习路由方法。**

如果风险头直接决定全部升级路径、Router 只执行固定规则，则会退化成分类器；因此风险头仅能约束 `STOP`。

---

## 15. Stop-Risk Head

### 15.1 作用

\[
r_\psi(s_{i,t})=P\left(E_{i,t}^{gate}>0.25\mid s_{i,t}, STOP\right)
\]

它只回答：

> 当前对该 Item 执行 `STOP` 是否存在严重错分风险？

它不能回答：

- 下一步调用哪个 Agent；
- 下一步处理哪道题；
- 是否必须调用 Evidence 或 Strong；
- 其他任务如何分配预算。

### 15.2 训练标签

在 `train_fit`，对每个结构上可停止的可见状态计算当前候选分数的 `Gate Error`，自动生成：

\[
y_{stop-risk}=\mathbf{1}[E_{i,t}^{gate}>0.25]
\]

其中 `0.25` 是冻结的 Severe Error 指标阈值，不由 Stop-Risk Head 学习，不在 calibration 调整。Deferral、无合法最终分数等状态按 `Gate Error = 1` 产生严重风险标签。

### 15.3 自动校准

`train_calibration` 学习的是“对当前冻结 checkpoint，预测风险概率达到什么边界时允许 STOP”，不是学习 Severe Error 的定义，也不是选择最终 Router。

固定流程：

1. checkpoint 的 Router 与 Stop-Risk Head 参数先冻结；
2. 只在该 checkpoint 的 calibration Paper 上收集可停止状态风险与 Severe 标签；
3. 由预注册算法自动产生一个 STOP 安全概率边界或 calibration failure；
4. 保存边界、覆盖率、质量约束、失败原因和 hash；
5. 与质量参考、预算、特征 schema 等组装为该 checkpoint 的 Policy Package；
6. calibration 不比较不同 checkpoint 的 Cost/Time/Calls/Exchanges，也不选择最终 Package；
7. Dev 只能比较这些已冻结 Package，不能移动边界。

`0.25` Severe 阈值、QWK 分档和 Bootstrap 规则均不参与校准。主 Router 的升级、核验、二评和仲裁仍由 Routing Q Head 决定；不得由 calibration 额外生成 `risk < x -> Strong` 等固定规则。

校准失败、无可行边界或 STOP 覆盖为0时必须保留失败状态，不能把风险记为0。

### 15.4 推断

Router 提议 `STOP` 时：

```text
结构合法
+ 预算合法
+ 已存在合法候选分数
+ 学习风险满足自动校准边界
→ STOP进入质量可行动作集合
```

若 `STOP` 被屏蔽，下一步具体操作仍由 Routing Q Head 在其他合法动作中决定。

### 15.5 消融

必须比较：

```text
CAG-CQL + Stop-Risk Head
CAG-CQL without Stop-Risk Head
Risk Classifier + Fixed Upgrade
Risk Classifier + Greedy
```

以区分“停止安全预测”与“跨 Item、多动作、长期资源分配”的强化学习贡献。

## 16. 质量参考策略自动产生

### 16.1 候选集合

在正式实验前固定候选定义与执行语义：

```text
Always-Cheap
Always-Mid
Always-Strong
Fixed Full Multi-Agent Workflow
```

### 16.2 自动选择

在 `train_calibration` 上对每个预注册预算档位分别执行 readiness 检查，并按以下固定质量优先顺序选择该档位的参考策略。该步骤只在预定义 reference policies 之间建立质量门锚点，不比较或选择 Router checkpoint：

```text
Quality Metrics Defined = Yes
→ Worst-Dataset Severe Error（低）
→ Worst-Dataset Unsafe Stop（低）
→ Macro-NMAE（低）
→ Macro-QWK（高）
→ Cost/Paper（低，仅质量完全并列时）
→ Elapsed Time/Paper（低）
→ Agent Calls/Paper（低）
→ A2A Exchanges/Paper（低）
→ Reference Policy ID（确定性并列规则）
```

输出 `quality_reference_manifest.json`，记录 `budget_id -> reference_policy_id`、全部候选指标、readiness、排序键、淘汰原因、协议 hash 和数据/cache 指纹。研究者不能为使主方法容易通过而手工选择较弱参考。

冻结的是参考策略的 ID、定义、预算对应关系和选择程序，不是把 `train_calibration` 上的数值指标直接搬到 Dev/Test。进入 Dev 或 Test 时，冻结参考策略与候选策略必须在同一 split、同一 Paper、同一 Agent cache 和同一预算档位上配对评价。

若某预算档位没有任何参考候选满足 STOP 与 QWK readiness，则该档位状态为 `quality_reference_readiness_failure`，不得进入 Router 成功声明，也不得在看到 Dev/Test 后更换候选集合。

### 16.3 Paper 级配对统计质量门

对候选策略 \(\pi\) 与对应参考策略 \(\pi_{ref}\)，定义所有差值为“候选减参考”。固定使用 Paper 级配对 Cluster Bootstrap：

```yaml
unit: paper
paired: true
replicates: 5000
confidence_level: 0.95
sidedness: one_sided
noninferiority_margin: 0
seed: 20260729
```

每次重采样使用同一组 Paper 索引同时计算候选和参考指标，并保留 Paper 内5道题的相关性。候选仅在以下条件全部成立时标记为 `Quality Feasible = Yes`：

\[
UCB_{95}\left(\max_g\Delta Severe_g\right)\le 0
\]

\[
UCB_{95}\left(\max_g\Delta UnsafeStop_g\right)\le 0
\]

\[
UCB_{95}\left(\Delta MacroNMAE\right)\le 0
\]

\[
LCB_{95}\left(\Delta MacroQWK\right)\ge 0
\]

其中 \(g\in\{DREsS, ASAP\text{-}SAS, SAS\text{-}Bench\}\)。若候选或参考任一主指标未定义、`STOP count = 0`、QWK readiness 失败、Bootstrap 失败、置信区间跨0或未达到边界，统一输出 `quality_noninferiority_inconclusive` 或更具体 readiness failure，并令 `Quality Feasible = No`。

零非劣效界表示本研究不预先允许任何质量下降；资源收益不能补偿统计质量门失败。第17节和第18节会复用同一 Bootstrap 程序，将比较基准从固定参考替换为 Quality Champion，以执行第二层质量保护门。

## 17. 质量绝对优先的优化目标

不使用：

\[
\max_\pi\left(QWK-\beta Cost\right)
\]

作为主模型选择原则，因为手工或结果后调整 \(\beta\) 会把质量损失转化为可接受的资源收益。

正式目标分三层：

1. **固定参考策略准入门**：同一个预算条件 Policy Package 必须在 Tight/Medium/Loose 每个预注册档位上分别通过第16.3节相对于冻结参考策略的零容忍配对统计质量门；
2. **质量冠军保护门**：在所有预算档位均准入的候选中，先只按质量指标自动确定唯一 Quality Champion；其余候选必须在每个预算档位证明四项正式质量指标均不劣于该冠军；
3. **Package 资源优化**：只有通过质量冠军保护门的候选，才允许最小化跨预算等权聚合的每 Paper 资源消耗。

Quality Champion 只在候选 Router Policy Package 中确定；固定参考、Baseline 和消融只用于评价报告，不具备冠军或最终 checkpoint 资格。其固定选择键不包含任何资源指标：

```text
Worst-(Budget,Dataset) Severe Error（低）
→ Worst-(Budget,Dataset) Unsafe Stop（低）
→ Mean-Budget Macro-NMAE（低）
→ Mean-Budget Macro-QWK（高）
→ Policy Package ID（升序）
```

对每个准入候选 \(\pi\) 与 Quality Champion \(\pi^*\)，在相同 Dev Paper、cache、预算与重采样索引上重新计算“候选减冠军”的四项配对 Bootstrap 边界。只有 Tight/Medium/Loose 每档均满足：

```text
UCB95(max_dataset_delta_severe) <= 0
UCB95(max_dataset_delta_unsafe_stop) <= 0
UCB95(delta_macro_nmae) <= 0
LCB95(delta_macro_qwk) >= 0
```

才令 `Quality Protection Feasible = Yes`。Quality Champion 与自身比较时自动通过；资源更低但严重错分、Unsafe Stop、NMAE 或 QWK 不能证明不劣于冠军的候选不得进入资源排序。

设正式预算集合为 \(\mathcal B\)，定义：

\[
\overline{C}=\frac{1}{|\mathcal B|}\sum_{b\in\mathcal B}CostPerPaper_b
\]

Elapsed Time、Agent Calls 和 A2A Exchanges 使用相同的不加权平均。Dev 最终固定词典序为：

```text
Package Reference Admission Feasible = Yes
→ Quality Protection Feasible = Yes
→ Mean-Budget Cost/Paper（低）
→ Mean-Budget Elapsed Time/Paper（低）
→ Mean-Budget Agent Calls/Paper（低）
→ Mean-Budget A2A Exchanges/Paper（低）
→ Worst-(Budget,Dataset) Severe Error（低，仅资源并列时）
→ Worst-(Budget,Dataset) Unsafe Stop（低）
→ Mean-Budget Macro-NMAE（低）
→ Mean-Budget Macro-QWK（高）
→ Policy Package ID（升序，确定性最终并列规则）
```

训练实现可使用 separate critics、Lagrangian/primal-dual 或 constrained CQL，但质量与资源不得压成由研究者结果后调节的单一手工权重。最终只冻结一个能够以剩余预算为状态输入的 Policy Package/checkpoint，不得按预算档位人工挑选不同模型。

## 18. 参数训练、边界校准和最终 Router 选择

### 18.1 Train Fit：只训练参数

`train_fit` 使用重建后的 `paper_train_fit_*`，训练：

```text
CAG encoder
Routing Q Head
Stop-Risk Head
Resource Critic
必要状态组件
```

同时生成预注册范围内的候选 checkpoint。Router 将剩余预算作为状态输入，同一个 checkpoint 适配 Tight/Medium/Loose。

`train_fit` 不读取 `train_calibration/dev/test`，能力画像主体也只由 train_fit formal cache 拟合。Severe/Extreme 指标阈值、QWK 分档、Bootstrap 和 Dev 排序不是可学习参数。

### 18.2 Train Calibration：只固定每个方案的使用边界

`train_calibration` 使用独立重建的 `paper_train_calibration_*`，先冻结环境侧定义：

- 每个预算档位的质量参考映射；
- Tight/Medium/Loose 预算；
- 能力画像 low-support/uncertainty 边界；
- quality protocol 和 support catalog hash。

然后对每个固定 checkpoint 独立执行：

1. 校准该 checkpoint 的 STOP 安全概率边界；
2. 检查 calibration coverage 和 failure；
3. 将单一 Router checkpoint、Stop-Risk Head、STOP 边界、参考映射、预算和全部 hash 组装为 Policy Package。

calibration 明确禁止：

- 更新 Router/Stop-Risk/critic 参数；
- 将 calibration trajectory 放入 replay buffer；
- 在不同 checkpoint 之间按资源或质量排名；
- 选择最终 Router；
- 为 Mid/Strong/VERIFY/A2A/ARBITRATE 生成主方法升级阈值。

因此它的输出是“一组边界已固定的候选 Package”，不是最终冠军。

### 18.3 Dev Auto-Select：参考准入、质量保护后再选择资源

Dev 对每个候选 Policy Package 执行以下不可更改流程：

1. 读取冻结的预算—参考映射、STOP 边界、指标协议和候选 Package；
2. 在 Tight/Medium/Loose 每个预算档位分别运行候选对固定参考策略的 Paper 级配对 Bootstrap 准入门；
3. 任一档位准入失败或 readiness failure，则淘汰整个 Package；
4. 在全部预算档位均准入的候选中，按 `Worst-(Budget,Dataset) Severe -> Worst-(Budget,Dataset) Unsafe Stop -> Mean-Budget Macro-NMAE -> Mean-Budget Macro-QWK -> Policy Package ID` 自动确定唯一 Quality Champion，禁止使用资源指标；
5. 以 Quality Champion 为质量保护基准，对其余准入候选在每个预算档位重新执行候选减冠军的四项零边界配对 Bootstrap；
6. 任一质量维度或任一预算档位不能证明不劣于 Quality Champion，候选即标记 `Quality Protection Feasible = No`，即使资源更低也不得进入最终排序；
7. 只在质量保护可行候选中，按 `Mean-Budget Cost/Paper -> Mean-Budget Elapsed Time/Paper -> Mean-Budget Agent Calls/Paper -> Mean-Budget A2A Exchanges/Paper -> 原质量并列键 -> Policy Package ID` 自动选择唯一 Package；
8. 保存每个档位的参考准入边界、Quality Champion 选择键、候选对冠军的质量保护边界、资源聚合键、淘汰原因和最终选择。

Dev 不重新训练、不重新校准、不移动阈值、不更换指标定义，也不人工更换 Quality Champion 或按预算档位挑不同 checkpoint。

### 18.4 Freeze

生成 `policy_freeze_manifest.json`，锁定：

```text
唯一 Router checkpoint / Policy Package
模型与Prompt
STOP安全概率边界
指标协议与代码hash
预算档位
质量参考映射
Bootstrap配置
各预算档位质量门结果
跨预算资源排序键
internal item/paper manifest hash
Agent cache/data/code指纹
```

### 18.5 Test

Test 只执行一次性 final evaluation。唯一冻结 Package 在每个预算档位上分别与对应参考重算 Test 指标与配对置信区间；只有全部正式预算档位通过时，Package 级 `Quality Feasible = Yes`。任一档位失败或结果未定义，保留失败并如实报告，不返回调参。

## 19. 离线轨迹构建

### 19.1 Behavior Policies

使用固定且预注册的 behavior policies：

```text
固定Agent
自动阈值
A2A/仲裁
多预算探索
```

### 19.2 轨迹字段

```text
visible_state
valid_action_mask
action
revealed_output
resource_delta
next_visible_state
stop_risk_label（train only）
done
failure_reason
```

### 19.3 Replay Buffer

只使用 `train_fit` 轨迹。Calibration、Dev、Test 不进入梯度训练。

### 19.4 HBR

Hindsight Budget Relabeling 可保留，但：

- 不改变质量标签；
- 不读取 Test；
- 必须消融；
- 不用于人为制造某个预算档位优势。

---

## 20. Baseline 设计

### 20.1 固定方法

- Always-Cheap；
- Always-Mid；
- Always-Strong；
- Fixed Full Multi-Agent Workflow。

### 20.2 自动校准和监督方法

- Single Agent + Automatically Calibrated Confidence Routing；
- Static Feature Classifier。

### 20.3 非 RL 动态方法

- Contextual Bandit；
- Top-k/Knapsack Allocation。

### 20.4 主方法

- Quality-Constrained CAG-CQL + Stop-Risk Head。

所有方法共享：

```text
prepared data
simulated papers
hidden Agent cache
budget tiers
cost/elapsed definitions
random seeds
evaluation code
```

如简单方法达到相同质量—资源前沿，应收缩 RL 必要性结论。

---

## 21. 消融实验

至少包括：

| 消融 | 验证内容 |
|---|---|
| Without Stop-Risk Head | 安全头是否降低严重错分和不安全停止 |
| Without Automatic Risk Calibration | 自动校准是否必要 |
| Without A2A | 通信是否有增益 |
| Without Budget State | 全局机会成本是否被利用 |
| Without Capability Profile | 历史能力先验是否有效 |
| Without CAG | 图结构是否必要 |
| Without HBR | 预算重标记是否有效 |
| Risk Classifier + Fixed Upgrade | 是否分类器已经足够 |

“提前暴露全部 cache”只能作为非法 oracle 诊断上界，不能作为正式可比较方法。

---

## 22. 评价指标与统计报告

### 22.1 主质量与安全指标

| 指标 | 正式定义 | 主/辅 |
|---|---|---|
| `Quality Feasible` | 第16.3节四个单侧95%配对 Bootstrap 边界全部通过 | 主 |
| `Severe Error Rate` | `Gate Error > 0.25`，分别按 dataset 报告并取最坏数据集 | 主 |
| `UnsafeStopRisk` | `STOP` 后发生 Severe Error的数量 / 全部 `STOP` 数量 | 主 |
| `Macro-NMAE` | 三个 dataset NMAE 的不加权平均，NMAE 使用 Gate Error | 主 |
| `Macro-QWK` | 固定11档 dataset QWK 的不加权平均 | 主 |
| `Extreme Error Rate` | `Gate Error >= 0.50` | 补充敏感性 |
| `Micro-NMAE` | 全部 Item Gate Error 的直接平均 | 补充 |
| `Unsafe Stop / All Items` | 不安全 STOP 数量 / 全部 Item | 补充 |
| `Stop Coverage` | STOP 数量 / 全部 Item | 必报诊断 |
| `Deferral Rate` | Deferral 数量 / 全部 Item | 必报诊断 |
| MAE/RMSE/Within-1 | 原始尺度补充指标 | 补充 |

Deferral、预算耗尽后未安全完成、非法或缺失最终分数均以 `Gate Error = 1` 进入 Severe Error 和 NMAE。`STOP count = 0` 时 `UnsafeStopRisk = NA` 且质量不可行。

### 22.2 QWK Readiness

每个 dataset 的 QWK 报告必须同时给出：

```text
valid_completed_n
gold_nonempty_bin_count
expected_weighted_disagreement
fixed_label_set = 0..10
qwk_defined
readiness_failure_reason
```

要求 `valid_completed_n >= 100`、`gold_nonempty_bin_count >= 2`、expected weighted disagreement > 0。任一数据集 QWK 未定义时，不计算可用于质量门的 Macro-QWK，候选状态为 readiness failure。

### 22.3 资源指标

- Cost per Paper/Item；
- Cumulative Elapsed Time per Paper；
- Token Usage；
- Agent Calls per Paper/Item；
- Strong/Evidence/Arbitrator Call Rate；
- A2A Exchanges per Paper/Item；
- Budget Violation；
- Budget Exhaustion。

Dev 自动选择使用 `Cost/Paper`、`Elapsed Time/Paper`、`Agent Calls/Paper`、`A2A Exchanges/Paper` 的确定性点估计，且只在质量可行候选中比较。

### 22.4 路由过程指标

- 平均路径长度；
- 路径类型分布；
- 有效通信率；
- 分歧降低率；
- 追加调用边际收益；
- 不同预算下质量可行率；
- 各动作、各 Agent 和各 Item 的预算分配分布。

### 22.5 Paper 级配对 Bootstrap 报告

固定参数：

```yaml
unit: paper
paired: true
replicates: 5000
confidence_level: 0.95
sidedness: one_sided
noninferiority_margin: 0
seed: 20260729
```

对每个 `split × budget_id × candidate × reference` 必须保存点估计、5000次重采样差值、单侧边界、readiness 和最终状态。正式四项门为：

```text
UCB95(max_dataset_delta_severe) <= 0
UCB95(max_dataset_delta_unsafe_stop) <= 0
UCB95(delta_macro_nmae) <= 0
LCB95(delta_macro_qwk) >= 0
```

置信区间跨0、任一指标未定义或 Bootstrap 无法完成时，统一不得通过质量门；不得用“差异不显著”代替“证明不劣”。

## 23. 预算档位与质量—资源前沿

正式实验使用自动生成的：

```text
Tight
Medium
Loose
```

每个档位同时包含四维资源上限。所有方法在相同档位比较。

仍可绘制 Cost-QWK、Cost-NMAE 等曲线，但其作用是描述不同方法的表现，不能通过手工改变 \(\beta\) 选择主模型。

图中应：

- 分别标记 `Reference Admission Feasible` 与 `Quality Protection Feasible`；
- 将参考准入失败或冠军保护失败点显示为不可行；
- 只对 Quality Champion 保护可行点计算资源节省；
- 同时报告 Severe Error 和 Unsafe Stop。

更准确名称为：

> **质量保护资源前沿（Quality-Protected Resource Frontier）**。

---

## 24. 研究问题

### RQ1：通过固定参考准入和 Quality Champion 保护后能否节约资源？

在不降低 QWK、不增加 NMAE、严重错分和不安全停止的前提下，主方法能否降低成本、累计延迟、调用和通信？

### RQ2：为什么需要强化学习？

在相同 hidden cache 和预算下，CAG-CQL 是否优于分类器、自动阈值、Bandit 和 knapsack？

### RQ3：Stop-Risk Head 是否必要？

风险头是否降低不安全停止和严重错分，同时保留 Router 对后续动作和任务顺序的决策价值？

### RQ4：CAG、能力画像、预算状态和 A2A 是否有效？

各组件对质量可行率、资源和路径行为有什么独立贡献？

### RQ5：自动校准和失败保留是否提高可信度？

重复运行是否得到同一参考、预算、阈值和 checkpoint；失败时是否能返回明确失败而不是人为放宽规则？

---

## 25. 实验表格

### 25.1 质量门与资源主表

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

主表先展示预算档位参考准入、Package 级全预算准入、Quality Champion、候选对冠军的质量保护状态和统计边界，再展示资源。主方法只有在 `Quality Protection Feasible = Yes` 时才允许进入资源比较并形成总体资源优化结论；分预算资源差异仍完整报告。

### 25.2 分数据集质量与 Readiness 表

```text
Method
Budget ID
Dataset
N All Items
N Valid Completed
Severe Error
Extreme Error
Unsafe Stop
Unsafe Stop / All Items
Stop Coverage
Deferral Rate
NMAE
QWK
Gold Nonempty Bins
Expected Weighted Disagreement
QWK Defined
Readiness Failure Reason
```

### 25.3 消融表

```text
Variant
Budget ID
Quality Feasible
Quality Gate Status
Worst-Dataset Severe Error
Worst-Dataset Unsafe Stop
Macro-NMAE
Macro-QWK
Cost/Paper
Elapsed Time/Paper
Agent Calls/Paper
A2A Exchanges/Paper
```

### 25.4 Dev 自动选择审计表

```text
Policy Package ID
All-Budgets Reference Admission Feasible
Tight Reference Gate Status
Medium Reference Gate Status
Loose Reference Gate Status
Quality Champion
Quality Champion Selection Key
All-Budgets Quality Protection Feasible
Tight Champion Gate Status
Medium Champion Gate Status
Loose Champion Gate Status
Mean-Budget Cost/Paper
Mean-Budget Elapsed Time/Paper
Mean-Budget Agent Calls/Paper
Mean-Budget A2A Exchanges/Paper
Worst-(Budget,Dataset) Severe Error
Worst-(Budget,Dataset) Unsafe Stop
Mean-Budget Macro-NMAE
Mean-Budget Macro-QWK
Dev Rank
Selected
Rejection Reason
Quality Protocol Hash
Config Hash
```

### 25.5 配对 Bootstrap 明细表

```text
Split
Budget ID
Candidate
Reference
Metric
Point Delta
One-Sided Bound Type
One-Sided 95% Bound
Pass
Replicates
Seed
Readiness Status
Failure Reason
```

### 25.6 失败注册表

```text
run_id
stage
split
budget_id
failure_type
policy/checkpoint
reason
quality_metrics
confidence_bounds
resource_metrics
protocol_hash
retained_artifact
```

## 26. 运行与复现

每次运行必须使用唯一 `run_id`：

```text
outputs/runs/<run_id>/
├── configs/
├── logs/
├── predictions/
├── checkpoints/
├── reports/
└── figures/
```

内部重建数据的规范文件按仓库规则写入 `data/processed/`；每个正式 run 必须在自身目录保存对应配置快照、manifest/hash 和审计报告，使本次训练、校准、Dev 选择与 Test 评价能够准确回放。

必须保存或快照：

- resolved config，以及 Prompt/model/cache/data/code hashes；
- 外部 split/paper manifest 指纹；
- `internal_item_split_manifest.csv`；
- `papers_train_fit.jsonl` 与 `papers_train_calibration.jsonl`；
- `internal_paper_manifest.csv`、`leftover_items.csv` 与 `internal_split_audit.md`；
- `quality_protocol.yaml` 的冻结快照与 `quality_protocol_manifest.json`；
- `agent_capability_manifest.json`、`quality_reference_manifest.json` 与 `budget_calibration_manifest.json`；
- `qwk_readiness.csv`、`risk_calibration_report.csv` 与 `calibration_package_manifest.jsonl`；
- `quality_gate_bootstrap.csv`、`checkpoint_selection.csv` 与 `policy_freeze_manifest.json`；
- `failure_registry.jsonl` 和 Test final-evaluation record。

`calibration_package_manifest.jsonl` 每行只对应一个冻结 checkpoint，记录其 STOP 边界或 calibration failure 以及相关环境 hash，不得包含跨 checkpoint 最终排名；`checkpoint_selection.csv` 只能由 Dev selector 产生。

`quality_protocol_manifest.json` 至少记录 Gate Error 规则、Severe/Extreme 阈值、Unsafe Stop 分母、QWK 分档与固定 labels、QWK readiness、Bootstrap 参数、固定参考准入门、Quality Champion 质量选择键、候选对冠军保护门、资源词典序以及实现代码 hash。

所有论文表格和图必须能够从保存的 predictions、logs、configs、external/internal manifests、Calibration Package 和 Bootstrap 产物重新计算；不得只保存最终均值或手工整理后的表格。

## 27. 实施阶段

### 阶段1：External Prepared Data（已完成）

现有三个数据集、外部 `train/dev/test`、prepared Item、外部 Paper 与审计继续保持，不替换数据集，也不扩展当前主路由 Item 范围。

### 阶段2：Agent Fixture Cache（已完成）

Agent/cache 工程链路和 fixture smoke 已完成，但 fixture 不能进入论文正式结果。

### 阶段3：V1.4 Internal Split、Paper Rebuild 与协议基础

必须先完成以下顺序，之后才允许进入真实 Pilot：

```text
27,375条train主路由Item
→ prompt/exact-answer/leakage connected-component原子分配
→ train_fit/train_calibration两个Item池
→ 两边分别重建固定5题strict Paper
→ internal manifests、leftover与阻塞性audit
→ quality protocol、QWK readiness与paired Bootstrap
→ calibration/Dev职责隔离fixture smoke
```

门禁要求旧 `paper_train_*` 直接分配次数为0，内部 Item/Prompt/Component/Paper 泄漏和 strict mix 违规均为0。

### 阶段4：真实 Agent Pilot

经用户批准后，只从重建后的完整 strict `train_fit` Paper 中抽取约100个 Item（约20份5题 Paper）运行 Pilot，同时审核 Item 级质量/互补性和 Paper 级 cost、elapsed time、calls、exchanges。Pilot 只决定是否允许进入 Formal cache，不改变内部 split、正式质量协议或正式预算规则。

### 阶段5：Formal Cache 与全局校准产物

Pilot 门禁通过后冻结 Formal Agent、Prompt、解析、成本定义和 context support catalog，再按 internal Item manifest 生成独立 `train_fit/train_calibration` cache，按外部 manifest 生成 Dev cache。仅用 `train_fit` 拟合能力画像主体；仅用重建后的 `train_calibration` Paper/cache 冻结画像支持度边界、质量参考和正式预算。此阶段尚无 Router checkpoint，因此不得提前宣称已完成 per-checkpoint STOP 校准。Test cache 继续推迟。

### 阶段6：Hidden Environment、轨迹与 Router 参数训练

只使用重建后的 `train_fit` Paper 和 train_fit formal cache，实现 Action、Mask、State、A2A、hidden cache、trajectory、CAG-CQL、Stop-Risk Head 和 critics，构建 replay buffer 并训练预注册候选 checkpoint。`train_calibration/dev/test` 不进入梯度、target、early stopping 或 replay。

### 阶段7：Per-Checkpoint Calibration 与 Dev 最终选择

对阶段6产生的每个冻结 checkpoint，使用同一预注册程序在 `train_calibration` 上自动产生唯一 STOP 安全概率边界或 calibration failure，并组装 Calibration Package；calibration 不进行跨 checkpoint 排名。随后 Dev 只比较边界已冻结的完整 Package：先在 Tight/Medium/Loose 各档执行相对于固定参考策略的准入门，再从全部准入候选中自动确定 Quality Champion，并淘汰任何不能在四项质量指标上证明不劣于冠军的候选；最后仅在质量保护可行候选中按跨预算等权资源词典序选择唯一 checkpoint，并生成 freeze manifest。

### 阶段8：Test Final Evaluation

所有组件冻结后才生成隔离 Test cache 并运行一次性最终评价。指标未定义、readiness 失败、置信区间跨0或质量门失败均如实保留并报告，不得返回 calibration 或 Dev 调整边界、指标或 checkpoint。

## 28. 当前尚未冻结的决策

以下工程细节必须在对应实现或真实 Pilot 前预注册，但不能根据 Dev/Test 结果决定：

1. 真实 Cheap/Mid/Strong/Evidence/Arbitrator 模型与版本；
2. 正式 Prompt、生成参数、解析规则和输出 JSON；
3. connected-component 分配求解器、strict Paper builder 的确定性实现及并列处理细节；这些实现不得改变“component完整性优先、目标约80%/20%、两边分别重建”的冻结原则；
4. Stop-Risk 概率校准算法、候选边界生成和覆盖率约束的具体实现；
5. Formal calibration Paper 资源分位数与 Tight/Medium/Loose 预算生成的固定规则；
6. 完整多 Agent 工作流等保留参考候选的精确动作语义；
7. 最小三头架构是否增加独立 Quality Critic；
8. 资源指标数值精度、排序序列化和同值比较的工程实现。

以下内容已由 V1.4 正式冻结，不再属于未决项：

- 继续使用已有三个数据集和当前27,375条 train 主路由 Item，不把另外663条未入 Paper Item扩入主实验；
- 现有5,475份 train Paper不得直接拆为两个内部 split；
- 先按 prompt/exact-answer/leakage传递连通分量拆 Item，再在 `train_fit/train_calibration` 内分别重建固定5题 strict Paper；
- 内部拆分目标约80%/20%，但 component完整性、三数据集覆盖和 strict Paper可构造性优先于精确比例；
- `train_fit` 训练参数、`train_calibration` 固定每个 checkpoint 的 STOP 边界和环境 Package、Dev 选择唯一 Package、Test 一次性评价；
- `Gate Error` 与 Deferral/非法结果赋值为1；
- `Severe Error > 0.25` 与 `Extreme Error >= 0.50`；
- Unsafe Stop 主分母及 `STOP count = 0` 处理；
- Macro-NMAE；
- 固定0～10共11档 Macro-QWK 与 readiness 条件；
- Paper 级配对 Bootstrap 的5000次、单侧95%、零非劣效界和种子 `20260729`；
- 四项零边界质量门、Quality Champion 的固定质量词典序、候选对冠军质量保护门，以及质量保护可行后 Dev 跨预算资源词典序。

所有尚未冻结内容必须写入配置、任务和 manifest，不能人工依据主实验结果调整。内部拆分实际比例、Paper数量和leftover数量属于确定性构建结果，不是看到 Router 结果后可以重新选择的超参数。

## 29. 预期创新点

### 创新点1：质量绝对优先的模拟试卷级共享资源调度

将多题自动阅卷建模为质量不可被资源补偿的约束序列决策。

### 创新点2：逐步证据驱动的可变长度多 Agent 路径

Router 在看不到未调用 Agent 输出的条件下，自主学习评分、核验、二评、仲裁和跨 Item 停止路径。

### 创新点3：学习型 STOP 风险与职责隔离的自动校准

Stop-Risk Head 在 `train_fit` 学习不安全停止风险，每个冻结 checkpoint 只在独立 `train_calibration` Paper 上自动固定 STOP 安全概率边界；Dev 只选择完整固定 Package。Mid/Strong、核验、A2A、仲裁和下一 Item 仍由 Router 学习，不退化为人工阈值级联。

### 创新点4：CAG、通信、能力和预算的联合状态表示

通过 CAG 编码已发生的 Item-Agent-Message 关系、能力先验和共享资源状态，并通过消融检验各组件贡献。

### 创新点5：不可手调且可审计的四阶段实验协议

数据先按题目组 component 拆 Item并分别重建 Paper；参数学习、边界校准、Dev 选择和 Test 评价严格分离。质量参考、风险边界、预算档位和 checkpoint 均由预注册程序自动产生或选择，所有失败结果完整保留。

## 30. 最终论文方法一句话

> **本文提出 A2A-DyGrade-RL，一种面向模拟试卷级自动阅卷的质量约束多智能体动态路由方法。现有 train 主路由作答先按 prompt/exact-answer/leakage 传递连通分量确定性划分为 `train_fit` 与 `train_calibration`，再在两个内部 split 中分别重建固定5题 strict 模拟试卷，禁止直接切分已有 train Paper。系统冻结评分 Agent，不训练评分模型；CAG-CQL Router 仅在 `train_fit` 学习下一 Item、评分、核验、二评、A2A、仲裁和停止等长期序列决策，每个冻结 checkpoint 只在 `train_calibration` 自动固定 STOP 安全概率边界并组装完整 Package，Dev 才对边界冻结 Package 先执行相对于固定参考策略的全预算零容忍准入门，再自动确定 Quality Champion，并要求其他候选证明四项质量均不劣于冠军；只有通过质量保护门的候选才按跨预算等权资源消耗选择唯一 checkpoint。完成选择后，模型、Prompt、边界、预算、质量门和 checkpoint 全部冻结，Test 仅用于一次性最终评价。**
