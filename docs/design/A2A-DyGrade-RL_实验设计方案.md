# A2A-DyGrade-RL 实验设计方案

## 0. 研究方向定位

本文拟研究一种面向自动阅卷的通信感知多智能体动态路由方法，暂命名为 **A2A-DyGrade-RL**。该方法不以构建新的单模型自动评分器为核心，而是关注在一份已经切分好的试卷中，如何根据题目难度、题型、学生答案长度、Rubric 或标准答案、Agent 能力、剩余预算、通信历史和当前评分风险，动态决定每道题应由哪个 Agent 批改，是否需要证据验证、A2A 第二意见、仲裁或停止。

与第一版综述中的 RBAR 方向相比，本方案保留 Rubric 约束、证据验证、动作选择和预算控制等思想，但论文主线从“边界样本证据决策”转向“试卷级多智能体动态路由与并行阅卷效率优化”。第一版综述已经指出，Rubric 约束自动评分不应仅被看作一次性分数预测，而应被建模为围绕评分项、证据状态和风险展开的动态决策过程；本方案进一步将该思想扩展到试卷级多 Agent 动态路由场景。fileciteturn0file0

本文的核心问题是：

> 在公开自动评分数据集上，能否通过离线强化学习 Router 学会在不同题目、不同 Agent、不同预算和不同通信状态之间进行动态决策，从而在保证评分质量的同时降低平均阅卷成本和试卷级完成时间？

---

## 1. 实验总体目标

### 1.1 任务定义

给定一份已经切分好的试卷：

\[
P=\{q_1,q_2,\ldots,q_n\}
\]

其中每道题 \(q_i\) 包含：

\[
q_i = (prompt_i, answer_i, rubric_i, reference_i, type_i)
\]

系统拥有一个异构 Agent 池：

\[
\mathcal{A}=\{CheapAgent, MidAgent, StrongAgent, EvidenceAgent, ArbitratorAgent\}
\]

系统需要在预算约束下完成整张试卷评分：

\[
B = [B_{cost}, B_{latency}, B_{calls}, B_{messages}]
\]

其中：

- \(B_{cost}\)：模型调用成本预算；
- \(B_{latency}\)：试卷级最大完成时间；
- \(B_{calls}\)：最大 Agent 调用次数；
- \(B_{messages}\)：最大 A2A 通信次数。

目标是在保证评分质量的同时，最小化成本、延迟和无效通信。

---

### 1.2 研究目标

本文实验要验证以下问题：

1. **动态路由是否优于固定模型批改？**
2. **离线强化学习 Router 是否优于静态难度路由和不确定性升级路由？**
3. **A2A 通信、Agent 能力图、预算状态、难度状态是否真的有贡献？**
4. **A2A-DyGrade-RL 是否能形成更优的 Cost-QWK Pareto Frontier？**

---

## 2. 数据集构建过程

### 2.1 数据集选择原则

本实验只使用现成公开数据集，不进行额外人工标注。数据集数量最多 3 个，避免实验范围过大、数据清洗成本过高和论文主线发散。

最终选择：

| 数据集 | 类型 | 用途 |
|---|---|---|
| DREsS | Rubric-based 作文评分 | 作文题 / 长答题 |
| ASAP-SAS | 短答案评分 | 经典短答题 |
| SAS-Bench | LLM 短答案评分基准 | 多学科短答题 |

DREsS 是面向 EFL 写作教育的 rubric-based essay scoring 数据集，包含真实课堂作文、专家评分以及基于 Rubric 的评分信息，适合作为作文类主观题评分实验数据。([arxiv.org](https://arxiv.org/abs/2402.16733?utm_source=chatgpt.com)) ASAP-SAS 是短答案自动评分领域常用公开数据集，已有自动短答案评分工作将其作为主要评测数据集。([arxiv.org](https://arxiv.org/abs/2012.11243?utm_source=chatgpt.com)) SAS-Bench 是 2025 年提出的短答案评分基准，包含真实学科考试题、学生回答、专家评分和细粒度评分信息，适合补充多学科短答题场景。([arxiv.org](https://arxiv.org/abs/2505.07247?utm_source=chatgpt.com))

---

### 2.2 原始数据统一格式

不同数据集字段不同，因此第一步是统一成 item-level 格式。

统一后的 `items.jsonl` 示例：

```json
{
  "item_id": "dress_000001",
  "dataset": "DREsS",
  "question_type": "essay",
  "subject": "english",
  "prompt": "作文题目",
  "student_answer": "学生作答内容",
  "reference_answer": null,
  "rubric": "评分量表",
  "gold_score": 4,
  "score_min": 0,
  "score_max": 6,
  "metadata": {
    "prompt_len": 128,
    "answer_len": 512,
    "rubric_len": 420,
    "has_reference_answer": false
  }
}
```

短答案数据统一为：

```json
{
  "item_id": "asap_sas_000001",
  "dataset": "ASAP-SAS",
  "question_type": "short_answer",
  "subject": "science",
  "prompt": "题目文本",
  "student_answer": "学生作答",
  "reference_answer": "标准答案",
  "rubric": "评分规则或评分说明",
  "gold_score": 2,
  "score_min": 0,
  "score_max": 3,
  "metadata": {
    "prompt_len": 64,
    "answer_len": 38,
    "rubric_len": 120,
    "has_reference_answer": true
  }
}
```

---

### 2.3 分数归一化

由于不同数据集分值范围不同，需要统一计算归一化误差。

对第 \(i\) 道题：

\[
R_i = score\_max_i - score\_min_i
\]

\[
E_i = \frac{|\hat{y}_i-y_i|}{R_i}
\]

其中：

- \(\hat{y}_i\)：系统预测分数；
- \(y_i\)：数据集 gold score；
- \(E_i\)：归一化评分误差。

实验报告仍保留原始分数尺度下的 MAE，同时使用 QWK 作为自动评分主指标。

---

### 2.4 自动构造试卷级样本

公开数据集通常是单题或单作文样本，而本文研究的是试卷级多题并行阅卷。因此需要将 item 自动组合成 paper-level 样本。

注意：该过程不涉及人工标注，只是自动重组公开数据。

每张伪试卷包含 5–8 道题，组合规则如下：

```text
每张试卷包含：
- 2–3 道 ASAP-SAS 短答案题；
- 1–2 道 SAS-Bench 多学科短答案题；
- 1 道 DREsS 作文题或长答题。
```

`papers.jsonl` 示例：

```json
{
  "paper_id": "paper_000001",
  "items": [
    "asap_sas_000023",
    "asap_sas_000105",
    "sasbench_000081",
    "sasbench_000304",
    "dress_000092"
  ],
  "paper_budget": {
    "max_cost": 1.0,
    "max_latency": 30.0,
    "max_agent_calls": 10,
    "max_a2a_messages": 6
  }
}
```

这种 paper-level 构造用于模拟真实试卷中的多题并行评分场景，使实验能够评估：

- 试卷级平均完成时间；
- 多 Agent 并行调度效率；
- 不同题目之间的预算竞争；
- A2A 通信是否值得；
- 动态路由是否比静态路由更优。

---

### 2.5 数据划分

采用三种划分方式：

```text
Split A：Item-level random split
Split B：Prompt-level split
Split C：Paper-level split
```

主实验使用 **Prompt-level split + Paper-level split**。这样可以避免同一题目 prompt 同时出现在训练集和测试集，减少数据泄漏风险。

最终数据文件：

```text
data/processed/
├── items_train.jsonl
├── items_dev.jsonl
├── items_test.jsonl
├── papers_train.jsonl
├── papers_dev.jsonl
└── papers_test.jsonl
```

---

## 3. Agent 设计与缓存机制

### 3.1 Agent 类型

系统包含 5 类 Agent：

| Agent | 功能 |
|---|---|
| CheapAgent | 低成本快速评分，适合简单题 |
| MidAgent | 中等能力评分，适合中等难度题 |
| StrongAgent | 强推理评分，适合难题和长答题 |
| EvidenceAgent | 检查答案是否命中标准答案、Rubric 或得分点 |
| ArbitratorAgent | 当多个 Agent 分数冲突时进行仲裁 |

不同 Agent 可以通过不同模型、不同提示词、不同推理深度或不同上下文长度实现。

---

### 3.2 Agent 输出格式

所有 Agent 输出统一为：

```json
{
  "item_id": "asap_sas_000001",
  "agent_id": "cheap_agent",
  "pred_score": 2,
  "confidence": 0.78,
  "justification": "答案包含关键概念，但解释不完整。",
  "cost": 0.01,
  "latency": 0.8,
  "token_usage": 320,
  "gold_score": 2
}
```

---

### 3.3 Agent 输出缓存

为构建离线 RL 轨迹，需要先对训练集、验证集和测试集缓存所有 Agent 输出。

缓存对象包括：

```text
CheapAgent
MidAgent
StrongAgent
EvidenceAgent
ArbitratorAgent
```

缓存文件：

```text
outputs/agent_cache/
├── cheap_agent_outputs.jsonl
├── mid_agent_outputs.jsonl
├── strong_agent_outputs.jsonl
├── evidence_agent_outputs.jsonl
└── arbitrator_agent_outputs.jsonl
```

这样做的好处是：

1. 离线 RL 训练不需要反复调用大模型；
2. 轨迹构建可以完全复现；
3. 可以精确记录 cost、latency、token usage；
4. 能够自动计算 Agent 能力画像。

---

## 4. 题目难度建模

### 4.1 难度来源

难度标签不进行人工标注，而是自动生成。难度由两类信息组成：

第一类是静态复杂度：

```text
question_type
prompt_len
answer_len
rubric_len
score_range
has_reference_answer
dataset_id
```

第二类是 Agent 试评分表现：

```text
CheapAgent error
MidAgent error
StrongAgent error
Agent disagreement
confidence variance
```

---

### 4.2 难度分数

定义题目难度分数：

\[
D_i =
\alpha Err_{cheap}
+
\beta Err_{mid}
+
\gamma Disagreement_i
+
\delta Complexity_i
\]

其中：

- \(Err_{cheap}\)：CheapAgent 与 gold score 的归一化误差；
- \(Err_{mid}\)：MidAgent 与 gold score 的归一化误差；
- \(Disagreement_i\)：多个 Agent 分数方差；
- \(Complexity_i\)：题目静态复杂度。

---

### 4.3 自动难度分层

根据 \(D_i\) 自动划分：

```text
Easy:
CheapAgent 误差低，Agent 分歧小。

Medium:
CheapAgent 不稳定，但 MidAgent 或 StrongAgent 能明显改善。

Hard:
CheapAgent 和 MidAgent 都不稳定，Agent 分歧高，通常需要 StrongAgent、A2A_ASK 或 ARBITRATE。
```

难度文件：

```text
data/processed/difficulty_labels.jsonl
```

---

## 5. Agent 能力建模

### 5.1 Agent Capability Table

每个 Agent 在不同题型和难度上的表现被记录为能力画像。

示例：

| Agent | Question Type | Difficulty | QWK | MAE | Cost | Latency | Calibration |
|---|---|---|---:|---:|---:|---:|---:|
| CheapAgent | short_answer | easy | 0.86 | 0.21 | 0.01 | 0.8 | 0.74 |
| CheapAgent | essay | hard | 0.42 | 0.91 | 0.02 | 1.3 | 0.51 |
| StrongAgent | essay | hard | 0.78 | 0.39 | 0.12 | 6.8 | 0.73 |
| ArbitratorAgent | conflict | hard | 0.81 | 0.34 | 0.10 | 5.9 | 0.76 |

---

### 5.2 Agent 能力向量

定义 Agent 能力向量：

\[
c_a =
[
acc_{a,type,d},
mae_{a,type,d},
cost_a,
latency_a,
calibration_a,
load_a
]
\]

其中：

- \(acc_{a,type,d}\)：Agent 在某题型、某难度上的历史准确性；
- \(mae_{a,type,d}\)：历史平均误差；
- \(cost_a\)：平均调用成本；
- \(latency_a\)：平均延迟；
- \(calibration_a\)：置信度校准程度；
- \(load_a\)：当前负载。

能力画像文件：

```text
outputs/profiles/agent_capability_table.csv
```

---

## 6. A2A 通信设计

### 6.1 A2A 消息类型

本实验保留 5 类核心消息：

| 消息类型 | 作用 |
|---|---|
| VERIFY | 请求 EvidenceAgent 验证证据或得分点 |
| A2A_ASK | 请求另一个评分 Agent 给第二意见 |
| CHALLENGE | 一个 Agent 质疑另一个 Agent 的评分 |
| JUSTIFICATION | Agent 解释自己的评分依据 |
| ARBITRATE | 请求 ArbitratorAgent 进行最终仲裁 |

A2A 本身不作为论文创新点，创新点在于：**Router 将 A2A 通信显式建模为可选择的路由动作，并学习何时通信、和谁通信、何时仲裁、何时停止。**

---

### 6.2 消息格式

```json
{
  "message_id": "msg_000001",
  "paper_id": "paper_000001",
  "item_id": "asap_sas_000001",
  "message_type": "A2A_ASK",
  "sender": "Router",
  "receiver": "MidAgent",
  "payload": {
    "current_score": 2,
    "current_confidence": 0.62,
    "request": "请给出第二评分意见。"
  },
  "response": {
    "pred_score": 3,
    "confidence": 0.71,
    "justification": "答案包含关键概念，但表达不完整。"
  },
  "cost": 0.03,
  "latency": 1.5
}
```

---

## 7. 离线强化学习建模

本文核心 Router 为：

# CAG-CQL：Communication-Aware Graph Conservative Q-Learning

中文名：

> 通信感知图结构保守 Q 学习路由算法

CAG-CQL 是 A2A-DyGrade-RL 的核心。它不是普通 CQL 的直接套用，而是在自动阅卷场景中引入：

```text
1. Agent-Item Routing Graph Encoder
2. GRU / Transformer A2A History Encoder
3. Budget-aware State Encoding
4. Action Masked Double Q Network
5. Target Network
6. Masked CQL Conservative Penalty
7. Hindsight Budget Relabeling
```

CQL 适合本任务的原因是：离线强化学习需要从静态轨迹数据中学习策略，而不能进行高成本在线探索；CQL 通过保守 Q 函数降低离线数据外动作被过度高估的风险。([arxiv.org](https://arxiv.org/abs/2006.04779?utm_source=chatgpt.com)) 近年的 SeqRoute 已经将 LLM routing 建模为有限时域 MDP，并使用 CQL 和 Hindsight Budget Relabeling 学习预算感知的顺序路由策略，这为本文将 CQL 扩展到试卷级自动阅卷路由提供了直接方法依据。([arxiv.org](https://arxiv.org/abs/2605.25424?utm_source=chatgpt.com))

---

## 8. MDP 定义

### 8.1 状态空间

对一张试卷 \(P=\{q_1,q_2,\ldots,q_n\}\)，第 \(t\) 步状态定义为：

\[
s_t = [X_t, D_t, G_t, H_t, B_t]
\]

其中：

| 符号 | 含义 |
|---|---|
| \(X_t\) | 所有题目的当前评分状态 |
| \(D_t\) | 题目难度状态 |
| \(G_t\) | Agent-Item 能力图状态 |
| \(H_t\) | A2A 通信历史状态 |
| \(B_t\) | 剩余预算状态 |

每道题 \(q_i\) 的状态为：

\[
x_i^t =
[
type_i,
len_i,
rubric\_len_i,
score\_range_i,
d_i,
\hat{y}_i^t,
u_i^t,
conflict_i^t,
done_i^t
]
\]

预算状态为：

\[
B_t =
[
remaining\_cost,
remaining\_latency,
remaining\_calls,
remaining\_messages
]
\]

---

### 8.2 动作空间

动作定义为：

\[
a_t=(i,o)
\]

其中：

- \(i\)：选择第几道题；
- \(o\)：对该题执行的操作。

动作集合为：

| 动作 | 含义 |
|---|---|
| `ROUTE_CHEAP(i)` | 调用 CheapAgent 批改第 \(i\) 题 |
| `ROUTE_MID(i)` | 调用 MidAgent 批改第 \(i\) 题 |
| `ROUTE_STRONG(i)` | 调用 StrongAgent 批改第 \(i\) 题 |
| `VERIFY(i)` | 调用 EvidenceAgent 验证证据或得分点 |
| `A2A_ASK(i)` | 请求另一个评分 Agent 给第二意见 |
| `ARBITRATE(i)` | 调用 ArbitratorAgent 仲裁 |
| `STOP(i)` | 停止第 \(i\) 题评分并输出当前分数 |

---

### 8.3 动作掩码

采用动作掩码，保证 Router 不会选择非法动作。

设合法动作集合为：

\[
\mathcal{A}_{valid}(s_t)
\]

对非法动作：

\[
Q(s_t,a)=-\infty,\quad a\notin \mathcal{A}_{valid}(s_t)
\]

动作掩码规则：

| 条件 | 屏蔽动作 |
|---|---|
| 题目已经完成 | 屏蔽所有非必要动作 |
| 题目没有初评分 | 屏蔽 `VERIFY`、`A2A_ASK`、`ARBITRATE`、`STOP` |
| 只有一个 Agent 给过分 | 屏蔽 `ARBITRATE` |
| 剩余 cost 不足 | 屏蔽 `ROUTE_STRONG`、`ARBITRATE` |
| 剩余 message budget 为 0 | 屏蔽 `VERIFY`、`A2A_ASK` |
| 题目已经仲裁 | 屏蔽再次 `ARBITRATE` |

动作掩码用于：

```text
1. 训练时 target Q 的 max 操作；
2. 推理时 action selection；
3. CQL conservative penalty 的 logsumexp 动作集合。
```

---

## 9. 模型结构设计

### 9.1 总体结构

```text
Item Encoder
      ↓
Agent Capability Encoder
      ↓
Budget Encoder
      ↓
Agent-Item Routing Graph Encoder
      ↓
A2A History Encoder
      ↓
Double Q Network + Target Network
      ↓
Action Mask
      ↓
CAG-CQL Router
```

---

### 9.2 Item Encoder

每道题的输入包括文本特征和结构化特征。

文本特征：

```text
prompt embedding
rubric embedding
student_answer embedding
reference_answer embedding
```

结构化特征：

```text
question_type
dataset_id
answer_len
rubric_len
score_range
difficulty_score
current_score
uncertainty
conflict_score
done_flag
```

题目表示：

\[
h_i^{item}=MLP([emb_i;feat_i])
\]

---

### 9.3 Agent Capability Encoder

Agent 能力向量：

\[
c_a =
[
acc_{a,type,d},
mae_{a,type,d},
cost_a,
latency_a,
calibration_a,
load_a
]
\]

Agent 表示：

\[
h_a^{agent}=MLP(c_a)
\]

---

### 9.4 Budget Encoder

预算向量：

\[
b_t =
[
remaining\_cost,
remaining\_latency,
remaining\_calls,
remaining\_messages
]
\]

预算表示：

\[
h_B=MLP(b_t)
\]

---

## 10. Agent-Item Routing Graph Encoder

### 10.1 图结构

构造异构图：

\[
\mathcal{G}_t=(\mathcal{V}_I,\mathcal{V}_A,\mathcal{V}_B,\mathcal{E})
\]

节点类型：

```text
Item nodes: q1, q2, ..., qn
Agent nodes: CheapAgent, MidAgent, StrongAgent, EvidenceAgent, ArbitratorAgent
Budget node: B
```

边类型：

| 边类型 | 含义 |
|---|---|
| Item-Agent Edge | 某 Agent 是否适合处理某题 |
| Item-Budget Edge | 某题预计消耗预算 |
| Agent-Budget Edge | 某 Agent 的 cost、latency、load |
| Item-Item Edge | 同一试卷中题目之间竞争全局预算 |

---

### 10.2 节点特征

Item 节点：

\[
v_i =
[
h_i^{item},
difficulty_i,
uncertainty_i,
conflict_i,
done_i
]
\]

Agent 节点：

\[
v_a =
[
h_a^{agent},
agent\_type_a,
cost_a,
latency_a,
load_a
]
\]

Budget 节点：

\[
v_B = h_B
\]

---

### 10.3 边特征

Item-Agent 边：

\[
e_{i,a} =
[
match(i,a),
expected\_quality_{i,a},
expected\_cost_a,
expected\_latency_a,
historical\_mae_{i,a}
]
\]

其中：

- \(match(i,a)\)：题型与 Agent 专长是否匹配；
- \(expected\_quality_{i,a}\)：Agent 对该题型/难度的历史质量；
- \(expected\_cost_a\)：调用成本；
- \(expected\_latency_a\)：平均延迟；
- \(historical\_mae_{i,a}\)：相似题上的历史误差。

---

### 10.4 图编码器

使用 Heterogeneous Graph Transformer 或 Heterogeneous Graph Attention Network。

消息传递：

\[
h_i^{(l+1)}
=
\sigma
\left(
W_Ih_i^{(l)}
+
\sum_{a\in \mathcal{N}(i)}
\alpha_{ia}^{(l)}W_Ah_a^{(l)}
+
W_Ee_{i,a}
\right)
\]

注意力权重：

\[
\alpha_{ia}
=
softmax
\left(
\frac{
(W_Qh_i)^\top(W_Kh_a)+W_Re_{i,a}
}{
\sqrt{d}
}
\right)
\]

最终输出：

```text
h_i：题目节点表示
h_a：Agent 节点表示
h_G：全局图表示
```

该模块是本文核心创新之一，用于建模题目与 Agent 能力之间的动态匹配关系。

---

## 11. A2A History Encoder

### 11.1 消息序列

对第 \(i\) 道题，通信历史为：

\[
H_i^t=[m_1,m_2,\ldots,m_k]
\]

每条消息 \(m_j\) 包含：

```text
message_type
sender_agent
receiver_agent
score_before
score_after
confidence_before
confidence_after
disagreement_before
disagreement_after
cost
latency
```

---

### 11.2 消息嵌入

每条消息编码为：

\[
z_j =
[
emb(type_j),
emb(sender_j),
emb(receiver_j),
\Delta score_j,
\Delta confidence_j,
\Delta disagreement_j,
cost_j,
latency_j
]
\]

---

### 11.3 GRU / Transformer History Encoder

主实现采用 Transformer History Encoder，资源受限时可切换为 GRU。

GRU 版本：

\[
h_{H_i}=GRU(z_1,z_2,\ldots,z_k)
\]

Transformer 版本：

\[
Z_i=[z_1,z_2,\ldots,z_k]+PE
\]

\[
H_i=TransformerEncoder(Z_i)
\]

\[
h_{H_i}=Pool(H_i)
\]

其中 \(h_{H_i}\) 表示第 \(i\) 道题的 A2A 通信历史，用于 Q 网络动作价值估计。

---

## 12. Q 网络设计

### 12.1 Q 网络输入

对动作 \(a_t=(i,o)\)，Q 网络输入为：

\[
\phi(s_t,i,o)
=
[
h_i,
h_G,
h_{H_i},
h_B,
h_o,
h_{agent(o)}
]
\]

其中：

| 表示 | 含义 |
|---|---|
| \(h_i\) | Graph Encoder 输出的题目节点表示 |
| \(h_G\) | 全局试卷图表示 |
| \(h_{H_i}\) | A2A History Encoder 输出 |
| \(h_B\) | Budget Encoder 输出 |
| \(h_o\) | 动作类型 embedding |
| \(h_{agent(o)}\) | 动作对应 Agent 表示 |

Q 值：

\[
Q_\theta(s_t,i,o)=MLP(\phi(s_t,i,o))
\]

---

### 12.2 Double Q Network

维护两个 Q 网络：

\[
Q_{\theta_1}, Q_{\theta_2}
\]

用于减少动作价值过估计：

\[
Q_{min}(s,a)=\min(Q_{\theta_1}(s,a),Q_{\theta_2}(s,a))
\]

---

### 12.3 Target Network

维护两个 target networks：

\[
Q_{\bar{\theta}_1}, Q_{\bar{\theta}_2}
\]

使用 soft update：

\[
\bar{\theta}\leftarrow \tau\theta+(1-\tau)\bar{\theta}
\]

---

### 12.4 Masked Bellman Target

只在合法动作集合中计算下一步最大 Q 值：

\[
a'^{*}
=
\arg\max_{a'\in\mathcal{A}_{valid}(s')}
Q_{\theta_1}(s',a')
\]

\[
y=
r+\gamma
\min
\left(
Q_{\bar{\theta}_1}(s',a'^{*}),
Q_{\bar{\theta}_2}(s',a'^{*})
\right)
\]

TD loss：

\[
\mathcal{L}_{TD}
=
\sum_{j=1}^{2}
\mathbb{E}_{(s,a,r,s')\sim D}
[
(Q_{\theta_j}(s,a)-y)^2
]
\]

---

### 12.5 Masked CQL Conservative Penalty

CQL 保守项只在合法动作集合上计算：

\[
\mathcal{L}_{CQL}
=
\mathbb{E}_{s\sim D}
\left[
\log
\sum_{a'\in\mathcal{A}_{valid}(s)}
\exp(Q_\theta(s,a'))
-
Q_\theta(s,a)
\right]
\]

总损失：

\[
\mathcal{L}
=
\mathcal{L}_{TD}
+
\alpha_{cql}\mathcal{L}_{CQL}
+
\alpha_{bc}\mathcal{L}_{BC}
\]

其中：

- \(\mathcal{L}_{TD}\)：Bellman temporal-difference loss；
- \(\mathcal{L}_{CQL}\)：保守 Q 学习惩罚项；
- \(\mathcal{L}_{BC}\)：行为克隆正则；
- \(\alpha_{cql}\)：CQL 权重；
- \(\alpha_{bc}\)：行为克隆权重。

---

## 13. 奖励函数设计

### 13.1 单题质量奖励

对第 \(i\) 道题：

\[
R_i = score\_max_i-score\_min_i
\]

\[
E_i=\frac{|\hat{y}_i-y_i|}{R_i}
\]

\[
Q_i=1-E_i
\]

其中：

- \(Q_i\) 越大，评分越接近 gold score；
- \(Q_i\) 是归一化质量奖励。

---

### 13.2 步级奖励

对于非终止动作：

\[
r_t
=
-\beta cost(a_t)
-\gamma latency(a_t)
-\lambda msg(a_t)
+
\omega \max(0,\Delta Conflict_i)
-
\eta P_{useless}
\]

其中：

- \(cost(a_t)\)：当前动作成本；
- \(latency(a_t)\)：当前动作延迟；
- \(msg(a_t)\)：当前动作是否产生 A2A 消息；
- \(\Delta Conflict_i\)：通信前后分歧下降量；
- \(P_{useless}\)：无效通信惩罚。

分歧下降量：

\[
\Delta Conflict_i
=
Conflict_i^{before}
-
Conflict_i^{after}
\]

如果通信后分歧没有下降：

\[
P_{useless}=1
\]

否则：

\[
P_{useless}=0
\]

---

### 13.3 终止奖励

当动作是 `STOP(i)` 时：

\[
r_{final}
=
\alpha Q_i
-
\beta \frac{Cost_i}{B_c}
-
\gamma \frac{Latency_i}{B_l}
-
\lambda \frac{Msg_i}{B_m}
-
\xi Violation_i
\]

---

### 13.4 试卷级奖励

整张试卷 \(P\) 的最终奖励：

\[
R(P)
=
\frac{1}{N}
\sum_{i=1}^{N}
\alpha Q_i
-
\beta \frac{Cost(P)}{B_c}
-
\gamma \frac{Makespan(P)}{B_l}
-
\lambda \frac{Messages(P)}{B_m}
-
\xi Violation(P)
\]

其中：

- \(Cost(P)\)：整张试卷总成本；
- \(Makespan(P)\)：整张试卷完成时间；
- \(Messages(P)\)：整张试卷 A2A 通信数；
- \(Violation(P)\)：是否超出预算。

---

## 14. 离线轨迹构建

### 14.1 Agent 缓存轨迹来源

对每道题缓存所有 Agent 输出后，自动构造多条候选轨迹。

基础轨迹：

```text
T1: ROUTE_CHEAP → STOP
T2: ROUTE_MID → STOP
T3: ROUTE_STRONG → STOP
T4: ROUTE_CHEAP → VERIFY → STOP
T5: ROUTE_CHEAP → A2A_ASK → STOP
T6: ROUTE_CHEAP → A2A_ASK → ARBITRATE → STOP
T7: ROUTE_MID → A2A_ASK → ARBITRATE → STOP
T8: ROUTE_CHEAP → VERIFY → A2A_ASK → ARBITRATE → STOP
```

---

### 14.2 边界轨迹

加入两类边界轨迹：

```text
Always-Cheap Trajectory
Always-Strong Trajectory
```

作用：

- Always-Cheap 提供成本下界；
- Always-Strong 提供质量上界；
- 中间轨迹帮助 Router 学会何时升级、何时通信、何时仲裁。

Budget-Aware Agentic Routing 提出了利用 always-small 和 always-large 这类 boundary policies 构造难度分类与训练信号的思想；本文将其迁移为自动阅卷中的成本边界轨迹构造方式。([arxiv.org](https://arxiv.org/abs/2602.21227?utm_source=chatgpt.com))

---

### 14.3 Hindsight Budget Relabeling

对每条轨迹生成多个预算版本：

```text
原始轨迹 cost = 0.42

重标注：
B = 0.30 → violation = 1
B = 0.50 → violation = 0
B = 0.80 → violation = 0
```

通过 Hindsight Budget Relabeling，Router 可以学习：

```text
预算紧张时减少通信和仲裁；
预算宽松时允许验证和强模型调用；
预算快耗尽时及时 STOP；
高风险题应保留预算给 StrongAgent 或 ArbitratorAgent。
```

SeqRoute 中的 Hindsight Budget Relabeling 通过对历史轨迹施加不同假设预算扩展离线训练数据，并提升预算泛化能力；本文沿用该思想，但将任务从多轮 LLM routing 改为试卷级自动阅卷路由。([arxiv.org](https://arxiv.org/abs/2605.25424?utm_source=chatgpt.com))

---

## 15. Cost-QWK Curve 设计

### 15.1 成本点生成方式

不同成本点不通过改变预算，而是通过改变奖励函数中的成本惩罚系数 \(\beta\) 得到。

设置：

\[
\beta \in \{0.05,0.1,0.2,0.4,0.6,0.8,1.0\}
\]

含义：

```text
β 小：更重视评分质量，允许更多 StrongAgent、A2A_ASK 和 ARBITRATE。
β 大：更重视成本控制，更倾向 CheapAgent 和提前 STOP。
```

---

### 15.2 曲线设置

横轴：

```text
Cost per Paper
```

纵轴：

```text
QWK
```

比较方法：

```text
Static Difficulty Router
CP-Router-Grade
SeqRoute-Grade
A2A-DyGrade-RL
```

希望观察到：

```text
1. 同等成本下，A2A-DyGrade-RL 的 QWK 更高；
2. 同等 QWK 下，A2A-DyGrade-RL 的成本更低；
3. A2A-DyGrade-RL 更接近 Cost-QWK Pareto Frontier；
4. 高成本区域中，A2A 通信和仲裁继续带来收益；
5. 低成本区域中，Router 能自动减少通信和强模型调用。
```

---

## 16. Baseline 设计

本文不与自动评分单模型 SOTA 直接比较，因为本文研究对象不是单模型自动评分器，而是多 Agent 动态路由策略。

### 16.1 Baseline 列表

| 方法 | 类型 | 说明 |
|---|---|---|
| Cheap-only | 模型 baseline | 所有题都用 CheapAgent |
| Strong-only | 模型 baseline | 所有题都用 StrongAgent |
| Static Difficulty Router | 静态路由 baseline | Easy→Cheap，Medium→Mid，Hard→Strong |
| CP-Router-Grade | 他人方法改造 baseline | 基于不确定性决定是否升级强模型 |
| SeqRoute-Grade | 他人方法改造 baseline | 预算感知 CQL 路由，但不使用 A2A 与 Agent-Item Graph |
| A2A-DyGrade-RL | 本文方法 | CAG-CQL Router |

CP-Router 是一种训练无关、模型无关的不确定性感知路由框架，它使用 conformal prediction 和 entropy 信息在普通 LLM 与强推理模型之间动态选择，以减少 token 使用并保持性能；本文将其改造为自动阅卷中的不确定性升级 baseline。([arxiv.org](https://arxiv.org/abs/2505.19970?utm_source=chatgpt.com)) SeqRoute 将 LLM routing 形式化为有限时域 MDP，并使用 CQL 进行离线强化学习，同时将剩余预算纳入状态空间；本文将其改造为预算感知阅卷路由 baseline，但去掉 A2A 通信、Agent-Item Graph 和通信历史编码，以突出本文方法差异。([arxiv.org](https://arxiv.org/abs/2605.25424?utm_source=chatgpt.com))

---

## 17. 消融实验设计

最终设置 5 个消融版本。

| 消融版本 | 去掉内容 | 验证目的 |
|---|---|---|
| w/o A2A Communication | 去掉 `VERIFY`、`A2A_ASK`、`ARBITRATE` | 验证 A2A 通信是否有效 |
| w/o Budget State | 去掉剩余 cost、latency、calls、messages | 验证预算状态是否必要 |
| w/o Difficulty State | 去掉题目难度特征 | 验证难度建模是否有效 |
| w/o Agent Capability State | 去掉 Agent 能力画像，只保留 Agent ID | 验证 Agent 能力建模是否有效 |
| w/o HBR | 去掉 Hindsight Budget Relabeling | 验证预算重标注是否有效 |

不进行强化学习算法对比，不设置 BC、DT、普通 CQL 横向比较。本文只保留一个主算法：**CAG-CQL**。

---

## 18. 评价指标

### 18.1 评分质量指标

| 指标 | 含义 |
|---|---|
| QWK | 自动评分主指标 |
| MAE | 平均绝对误差 |
| RMSE | 均方根误差 |
| Within-1 Accuracy | 预测分与 gold score 相差不超过 1 的比例 |

主表主要报告 QWK 和 MAE。

---

### 18.2 成本与效率指标

| 指标 | 含义 |
|---|---|
| Cost per Paper | 单张试卷平均成本 |
| Paper Latency | 单张试卷完成时间 |
| Token Usage | 平均 token 消耗 |
| Agent Calls | 平均 Agent 调用次数 |

---

### 18.3 A2A 通信指标

| 指标 | 含义 |
|---|---|
| A2A Messages | 平均通信次数 |
| Useful Communication Rate | 通信后分歧下降的比例 |
| Disagreement Reduction | 通信前后分歧下降幅度 |
| Arbitration Rate | 触发仲裁比例 |

---

### 18.4 预算指标

| 指标 | 含义 |
|---|---|
| Budget Violation Rate | 超预算比例 |
| Cost-QWK Curve | 成本—质量折中曲线 |
| Pareto Efficiency | 是否接近最优成本—质量前沿 |

---

## 19. 实验研究问题

### RQ1：A2A-DyGrade-RL 是否优于简单模型与静态路由？

比较：

```text
Cheap-only
Strong-only
Static Difficulty Router
A2A-DyGrade-RL
```

指标：

```text
QWK
MAE
Cost per Paper
Paper Latency
```

---

### RQ2：A2A-DyGrade-RL 是否优于已有 routing 方法改造版？

比较：

```text
CP-Router-Grade
SeqRoute-Grade
A2A-DyGrade-RL
```

指标：

```text
QWK
MAE
Cost per Paper
Budget Violation Rate
```

---

### RQ3：核心模块是否有效？

比较：

```text
Full CAG-CQL
w/o A2A
w/o Budget State
w/o Difficulty State
w/o Agent Capability State
w/o HBR
```

指标：

```text
QWK
MAE
Cost
Latency
A2A Messages
Budget Violation Rate
```

---

### RQ4：A2A-DyGrade-RL 是否形成更优 Cost-QWK Curve？

比较：

```text
Static Difficulty Router
CP-Router-Grade
SeqRoute-Grade
A2A-DyGrade-RL
```

不同成本点由成本惩罚系数 \(\beta\) 控制：

```text
β = 0.05, 0.1, 0.2, 0.4, 0.6, 0.8, 1.0
```

指标：

```text
Cost per Paper
QWK
Pareto frontier
```

---

## 20. 实验表格设计

### 20.1 主实验表

| Method | QWK ↑ | MAE ↓ | Cost ↓ | Paper Latency ↓ | A2A Msg ↓ | Budget Violation ↓ |
|---|---:|---:|---:|---:|---:|---:|
| Cheap-only |  |  |  |  |  |  |
| Strong-only |  |  |  |  |  |  |
| Static Difficulty Router |  |  |  |  |  |  |
| CP-Router-Grade |  |  |  |  |  |  |
| SeqRoute-Grade |  |  |  |  |  |  |
| A2A-DyGrade-RL |  |  |  |  |  |  |

---

### 20.2 消融实验表

| Method | QWK ↑ | MAE ↓ | Cost ↓ | Latency ↓ | Msg ↓ | Violation ↓ |
|---|---:|---:|---:|---:|---:|---:|
| Full CAG-CQL |  |  |  |  |  |  |
| w/o A2A |  |  |  |  |  |  |
| w/o Budget State |  |  |  |  |  |  |
| w/o Difficulty State |  |  |  |  |  |  |
| w/o Agent Capability State |  |  |  |  |  |  |
| w/o HBR |  |  |  |  |  |  |

---

### 20.3 Cost-QWK 曲线

图设置：

```text
x-axis: Cost per Paper
y-axis: QWK
methods:
  - Static Difficulty Router
  - CP-Router-Grade
  - SeqRoute-Grade
  - A2A-DyGrade-RL
```

---

## 21. 整体框架路径

### 21.1 离线训练阶段

```text
公开数据集
   ↓
数据清洗与统一格式化
   ↓
构造 item-level 数据
   ↓
自动组合 paper-level 试卷
   ↓
运行所有 Agent 并缓存输出
   ↓
构建题目难度标签
   ↓
构建 Agent Capability Table
   ↓
构建 A2A 通信轨迹
   ↓
Hindsight Budget Relabeling
   ↓
训练 CAG-CQL Router
```

---

### 21.2 在线推理阶段

```text
输入已切分试卷
   ↓
Item Encoder 编码每道题
   ↓
Agent Capability Encoder 编码 Agent 能力
   ↓
Budget Encoder 编码剩余预算
   ↓
构建 Agent-Item Routing Graph
   ↓
A2A History Encoder 编码通信历史
   ↓
CAG-CQL Router 选择动作
   ↓
执行 ROUTE / VERIFY / A2A_ASK / ARBITRATE / STOP
   ↓
更新状态与预算
   ↓
直到所有题目完成
   ↓
输出整张试卷评分、成本、时延、通信日志
```

---

## 22. 项目文件规划

项目名：

```text
A2A-DyGrade/
```

完整目录：

```text
A2A-DyGrade/
│
├── README.md
├── requirements.txt
├── pyproject.toml
├── .env.example
│
├── configs/
│   ├── dataset.yaml
│   ├── agents.yaml
│   ├── router.yaml
│   ├── cag_cql.yaml
│   └── experiment.yaml
│
├── data/
│   ├── raw/
│   │   ├── dress/
│   │   ├── asap_sas/
│   │   └── sas_bench/
│   │
│   ├── processed/
│   │   ├── items_train.jsonl
│   │   ├── items_dev.jsonl
│   │   ├── items_test.jsonl
│   │   ├── papers_train.jsonl
│   │   ├── papers_dev.jsonl
│   │   ├── papers_test.jsonl
│   │   └── difficulty_labels.jsonl
│   │
│   └── trajectories/
│       ├── train_trajectories.jsonl
│       ├── dev_trajectories.jsonl
│       ├── test_trajectories.jsonl
│       └── hbr_trajectories.jsonl
│
├── prompts/
│   ├── cheap_scorer.txt
│   ├── mid_scorer.txt
│   ├── strong_scorer.txt
│   ├── evidence_agent.txt
│   └── arbitrator_agent.txt
│
├── src/
│   ├── datasets/
│   │   ├── load_dress.py
│   │   ├── load_asap_sas.py
│   │   ├── load_sas_bench.py
│   │   ├── normalize.py
│   │   ├── build_items.py
│   │   ├── build_papers.py
│   │   └── split.py
│   │
│   ├── agents/
│   │   ├── base_agent.py
│   │   ├── cheap_agent.py
│   │   ├── mid_agent.py
│   │   ├── strong_agent.py
│   │   ├── evidence_agent.py
│   │   ├── arbitrator_agent.py
│   │   └── agent_registry.py
│   │
│   ├── a2a/
│   │   ├── agent_card.py
│   │   ├── message_schema.py
│   │   ├── message_bus.py
│   │   ├── message_encoder.py
│   │   └── audit_log.py
│   │
│   ├── graph/
│   │   ├── graph_builder.py
│   │   ├── hetero_graph.py
│   │   ├── graph_transformer.py
│   │   └── graph_attention.py
│   │
│   ├── router/
│   │   ├── state.py
│   │   ├── action.py
│   │   ├── action_mask.py
│   │   ├── reward.py
│   │   ├── item_encoder.py
│   │   ├── agent_encoder.py
│   │   ├── budget_encoder.py
│   │   ├── a2a_history_encoder.py
│   │   ├── routing_graph_encoder.py
│   │   ├── q_network.py
│   │   ├── target_network.py
│   │   └── cag_cql_policy.py
│   │
│   ├── rl/
│   │   ├── replay_buffer.py
│   │   ├── trajectory_builder.py
│   │   ├── boundary_trajectory_builder.py
│   │   ├── hindsight_budget_relabeling.py
│   │   ├── cql_loss.py
│   │   ├── train_cag_cql.py
│   │   └── evaluate_policy.py
│   │
│   ├── baselines/
│   │   ├── cheap_only.py
│   │   ├── strong_only.py
│   │   ├── static_difficulty_router.py
│   │   ├── cp_router_grade.py
│   │   └── seqroute_grade.py
│   │
│   ├── scheduler/
│   │   ├── parallel_scheduler.py
│   │   ├── budget_manager.py
│   │   └── task_queue.py
│   │
│   ├── evaluation/
│   │   ├── metrics_quality.py
│   │   ├── metrics_cost.py
│   │   ├── metrics_latency.py
│   │   ├── metrics_budget.py
│   │   ├── metrics_a2a.py
│   │   ├── metrics_routing.py
│   │   └── plot_cost_qwk_curve.py
│   │
│   └── utils/
│       ├── io.py
│       ├── logging.py
│       ├── llm_client.py
│       ├── json_utils.py
│       └── seed.py
│
├── scripts/
│   ├── 01_build_items.py
│   ├── 02_build_papers.py
│   ├── 03_run_agent_cache.py
│   ├── 04_build_difficulty_labels.py
│   ├── 05_build_trajectories.py
│   ├── 06_train_cag_cql.py
│   ├── 07_eval_baselines.py
│   ├── 08_eval_ablation.py
│   └── 09_plot_cost_qwk_curve.py
│
├── outputs/
│   ├── agent_cache/
│   ├── profiles/
│   │   └── agent_capability_table.csv
│   ├── checkpoints/
│   │   └── cag_cql/
│   ├── predictions/
│   ├── logs/
│   │   ├── router_logs.jsonl
│   │   ├── a2a_logs.jsonl
│   │   └── budget_logs.jsonl
│   └── reports/
│       ├── main_results.csv
│       ├── ablation_results.csv
│       ├── cost_qwk_curve.csv
│       └── case_study.md
│
└── tests/
    ├── test_dataset.py
    ├── test_agents.py
    ├── test_a2a.py
    ├── test_graph_encoder.py
    ├── test_action_mask.py
    ├── test_reward.py
    └── test_cag_cql.py
```

---

## 23. 实现顺序

### 阶段 1：数据处理

```text
1. 下载 DREsS、ASAP-SAS、SAS-Bench；
2. 编写 loader；
3. 统一成 items.jsonl；
4. 自动构造 papers.jsonl；
5. 完成 train/dev/test 划分。
```

---

### 阶段 2：Agent 缓存

```text
1. 实现 CheapAgent、MidAgent、StrongAgent；
2. 实现 EvidenceAgent、ArbitratorAgent；
3. 对所有训练样本缓存 Agent 输出；
4. 记录 score、confidence、cost、latency、token_usage。
```

---

### 阶段 3：难度与能力建模

```text
1. 根据 Agent 误差和分歧自动生成 difficulty labels；
2. 构建 Agent Capability Table；
3. 分析不同 Agent 在不同题型和难度上的表现。
```

---

### 阶段 4：离线轨迹构建

```text
1. 构造基础评分轨迹；
2. 构造 A2A 通信轨迹；
3. 构造 Always-Cheap / Always-Strong 边界轨迹；
4. 执行 Hindsight Budget Relabeling；
5. 生成 replay buffer。
```

---

### 阶段 5：CAG-CQL 训练

```text
1. 实现 Agent-Item Routing Graph Encoder；
2. 实现 Transformer / GRU A2A History Encoder；
3. 实现 Double Q Network；
4. 实现 Target Network；
5. 实现 Action Mask；
6. 实现 Masked CQL Conservative Penalty；
7. 训练 CAG-CQL Router。
```

---

### 阶段 6：实验评估

```text
1. 运行 5 个 baseline；
2. 运行 A2A-DyGrade-RL；
3. 运行 5 个消融实验；
4. 绘制 Cost-QWK Curve；
5. 输出 case study。
```

---

## 24. 预期创新点

### 创新点 1：试卷级多 Agent 动态路由建模

不同于单题自动评分或单模型自动评分，本文将一张试卷建模为多个可并行处理的评分子任务，并在全局预算下动态选择 Agent、通信、仲裁和停止动作。

### 创新点 2：Agent-Item Routing Graph Encoder

本文显式构建题目节点、Agent 节点和预算节点之间的异构图，用于建模不同题型、不同难度与不同 Agent 能力之间的匹配关系。

### 创新点 3：A2A History Encoder

本文将 Agent 间通信历史作为状态的一部分，使用 GRU 或 Transformer 编码通信序列，使 Router 能够学习通信是否有效、是否降低分歧、是否值得继续仲裁。

### 创新点 4：动作掩码下的 CAG-CQL Router

本文在离线强化学习中引入动作掩码、Double Q Network、Target Network 和 Masked CQL Conservative Penalty，使 Router 在合法动作空间中学习稳定的预算感知路由策略。

### 创新点 5：Cost-QWK Pareto Frontier 优化

本文不单纯追求最高 QWK，而是通过改变奖励函数中的成本惩罚系数 \(\beta\)，系统评估不同成本约束下的 QWK 表现，验证方法是否形成更优成本—质量折中。

---

## 25. 最终论文方法一句话

本文提出 **A2A-DyGrade-RL**，一种面向自动阅卷的通信感知多智能体动态路由框架。其核心 **CAG-CQL Router** 将试卷级自动阅卷建模为预算约束下的离线强化学习问题，通过 Agent-Item Routing Graph Encoder 建模题目与 Agent 的能力匹配关系，通过 GRU / Transformer A2A History Encoder 编码 Agent 间通信轨迹，并结合动作掩码、Double Q Network、Target Network、CQL Conservative Penalty 和 Hindsight Budget Relabeling，学习在不同成本惩罚系数下动态选择低成本评分、强模型评分、证据验证、A2A 第二意见、仲裁或停止，从而优化自动阅卷中的 Cost-QWK Pareto Frontier。
