# 数据模型：A2A-DyGrade-RL 实验流水线

## Item

表示一个学生对一个评分题目的作答。

字段：

- `item_id`：稳定唯一 item 标识。
- `dataset`：来源数据集名称。
- `question_type`：essay、long_answer 或 short_answer。
- `subject`：可用时记录科目或领域。
- `prompt`：题目文本。
- `student_answer`：学生作答文本。
- `reference_answer`：可用时的标准答案。
- `rubric`：可用时的评分量表或评分说明。
- `gold_score`：专家或数据集提供的分数。
- `score_min`：合法最低分。
- `score_max`：合法最高分。
- `metadata`：prompt 长度、answer 长度、rubric 长度、reference 是否存在、prompt group identifier 和来源字段。

校验规则：

- `score_max` 必须大于 `score_min`。
- `gold_score` 必须位于分数范围内。
- `prompt`、`student_answer` 和 `item_id` 必须存在。
- 被接受的评分 item 应至少包含 `rubric` 或 `reference_answer` 之一。

## Paper

表示由多个 items 组装而成的合成试卷级样本。

字段：

- `paper_id`：稳定 paper 标识。
- `items`：有序 item identifiers 列表。
- `paper_budget`：max cost、max latency、max Agent calls 和 max A2A messages。
- `metadata`：dataset mix、split name、seed 和 construction rule version。

校验规则：

- 主实验中每张 paper 必须包含 5 到 8 个 items。
- 每个引用 item 必须存在于同一 split。
- 预算值必须非负。

## Agent Output

表示一个 Agent 对一个 item 的缓存响应。

字段：

- `item_id`
- `agent_id`
- `pred_score`
- `confidence`
- `justification`
- `cost`
- `latency`
- `token_usage`
- `gold_score`
- `metadata`

校验规则：

- 应用规范化或截断规则后，`pred_score` 必须位于该 item 的分数范围内。
- `confidence` 必须位于 0 到 1。
- `cost`、`latency` 和 `token_usage` 必须非负。

## Difficulty Label

表示推导出的 item 难度。

字段：

- `item_id`
- `difficulty_score`
- `difficulty_label`：Easy、Medium 或 Hard。
- `signals`：static complexity、CheapAgent error、MidAgent error、disagreement 和 confidence variance。

校验规则：

- 每个被接受 item 应且仅应有一个 difficulty label。
- 标签使用的 signals 必须可追溯到 item metadata 或 Agent cache outputs。

## Agent Capability Profile

表示 Agent 按 question type 和 difficulty 聚合后的表现。

字段：

- `agent_id`
- `question_type`
- `difficulty_label`
- `qwk`
- `mae`
- `cost`
- `latency`
- `calibration`
- `sample_count`

校验规则：

- 聚合结果必须包含 sample counts。
- 低 sample count 的 profile 必须标记解释风险。

## A2A Message

表示一个通信事件。

字段：

- `message_id`
- `paper_id`
- `item_id`
- `message_type`：VERIFY、A2A_ASK、CHALLENGE、JUSTIFICATION 或 ARBITRATE。
- `sender`
- `receiver`
- `payload`
- `response`
- `cost`
- `latency`

校验规则：

- `message_type` 必须属于支持的消息类型。
- 通信 cost 和 latency 必须纳入 paper-level 总量。

## Routing State

表示 Router 在选择动作前看到的状态。

字段：

- `paper_id`
- `step`
- `item_states`
- `difficulty_state`
- `agent_capability_state`
- `a2a_history_state`
- `remaining_budget`
- `valid_action_mask`

校验规则：

- action mask 必须与 item completion status 和 remaining budget 一致。
- 如果没有记录 budget violation，remaining budget 不得变成负数。

## Trajectory

表示离线策略学习序列。

字段：

- `trajectory_id`
- `paper_id`
- `steps`：state、action、reward、next state、valid action mask 和 done flag。
- `total_cost`
- `makespan`
- `messages`
- `final_scores`
- `quality_metrics`
- `budget_violation`
- `source_policy`

校验规则：

- 每个非终止 step 必须有合法 next state。
- 终止轨迹必须包含 paper 中所有 items 的 final scores。

## Experiment Report

表示生成的评价输出。

字段：

- `method`
- `split`
- `seed`
- `qwk`
- `mae`
- `rmse`
- `within_1_accuracy`
- `cost_per_paper`
- `paper_latency`
- `token_usage`
- `agent_calls`
- `a2a_messages`
- `useful_communication_rate`
- `disagreement_reduction`
- `arbitration_rate`
- `budget_violation_rate`

校验规则：

- 同一比较表中的方法必须使用相同 split 和 paper set。
- 每一行报告结果都必须能从保存的 predictions 和 logs 复现。
