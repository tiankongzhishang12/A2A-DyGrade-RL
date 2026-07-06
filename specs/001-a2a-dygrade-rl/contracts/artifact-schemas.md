# 产物 Schema 合约

本合约定义实验产物必须暴露的最小字段，确保下游阶段可以互操作。

除 `data/` 下的数据型产物外，运行期产物必须归属到 `outputs/runs/<run_id>/`。每个 run 必须保存配置快照、日志、预测结果、报告和图，避免不同实验互相覆盖。

## Item JSONL

必需字段：

- `item_id`
- `dataset`
- `question_type`
- `subject`
- `prompt`
- `student_answer`
- `reference_answer`
- `rubric`
- `gold_score`
- `score_min`
- `score_max`
- `metadata`

## Paper JSONL

必需字段：

- `paper_id`
- `items`
- `paper_budget.max_cost`
- `paper_budget.max_latency`
- `paper_budget.max_agent_calls`
- `paper_budget.max_a2a_messages`

## Agent Cache JSONL

必需字段：

- `item_id`
- `agent_id`
- `pred_score`
- `confidence`
- `justification`
- `cost`
- `latency`
- `token_usage`
- `gold_score`

## Trajectory JSONL

必需字段：

- `trajectory_id`
- `paper_id`
- `source_policy`
- `steps`
- `total_cost`
- `makespan`
- `messages`
- `final_scores`
- `quality_metrics`
- `budget_violation`

每个 step 必须包含：

- `state`
- `action`
- `reward`
- `next_state`
- `valid_action_mask`
- `done`

## Report CSV

必需列：

- `run_id`
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
- `budget_violation_rate`

## Run Directory

每个 `outputs/runs/<run_id>/` 必须按需包含：

- `configs/`：该次运行实际生效配置快照。
- `logs/`：训练、评价和数据处理日志。
- `predictions/`：Agent cache、baseline predictions 和 Router predictions。
- `checkpoints/`：训练得到的模型 checkpoint。
- `reports/`：CSV 或 Markdown 结果表。
- `figures/`：Cost-QWK 曲线和论文候选图。
