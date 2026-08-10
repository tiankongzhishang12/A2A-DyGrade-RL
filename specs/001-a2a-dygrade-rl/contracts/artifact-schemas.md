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
- `paper_budget.max_elapsed_time`
- `paper_budget.max_agent_calls`
- `paper_budget.max_a2a_exchanges`

旧 fixture 的 `max_latency`、`max_a2a_messages` 只允许作为显式兼容输入；新产物必须序列化为正式字段。

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

## 完整 Fixture Smoke 隔离合约

完整 Fixture Smoke 不是正式实验的小 run，而是 fixture-only 端到端验收。静态输入必须位于 `tests/fixtures/quality_constrained_smoke/`，配置位于 `configs/experiments/`，测试位于 `tests/`，持久化产物只位于 `outputs/runs/fixture_smoke_<run_id>/`。不得写入 `data/processed/` 或任何 `formal_agent_cache_*`、正式 checkpoint、正式结果汇总目录。

### FixtureSmokeRunManifest JSON

必需字段：

- `manifest_version`
- `run_id`，必须以 `fixture_smoke_` 开头
- `execution_mode=fixture_smoke`
- `is_fixture=true`
- `formal_eligible=false`
- `online_agent_calls=0`
- `seed`
- `fixture_blueprint_hash`
- `fixture_config_hash`
- `fixture_agent_config_hash`
- `quality_protocol_file_hash` 与 `quality_protocol_hash`
- `entrypoint_hash`
- `core_pipeline_modules`
- `core_module_hashes`：覆盖 `src/a2a_dygrade_rl/**/*.py` 的逐文件 SHA-256
- `source_tree_hash`：对 `core_module_hashes` 按稳定字典序序列化后计算的 SHA-256
- `audit_counters`

`audit_counters` 至少包含并要求为0：

- `formal_data_reads`
- `formal_asset_acceptances`
- `cross_mode_cache_reuse`
- 任何 `status=success` 但 schema、run identity、mode、hash 或 Item 约束无效的 cache 记录不得静默复用；重建前必须写入 `logs/cache_reuse_rejections.<split>.jsonl`，且历史拒绝记录不得删除。
- `online_agent_calls`
- `calibration_gradient_updates`
- `calibration_replay_writes`
- `calibration_checkpoint_rankings`
- `dev_boundary_updates`
- `quality_champion_resource_reads`
- `quality_champion_manual_overrides`
- `test_like_training_reads`


### FixtureArtifactManifest JSON

`configs/fixture_artifact_manifest.json` 必须在成功 run 的最后一步生成，并逐文件覆盖该 run 中除 inventory 自身外的全部文件。必需字段：

- `manifest_version=fixture_artifact_manifest_v1`
- `execution_mode=fixture_smoke`
- `is_fixture=true`
- `formal_eligible=false`
- `covered_artifact_count`
- `uncovered_artifact_count=0`
- `inventory_self_marked=true`
- `artifacts`：每条包含相对路径、SHA-256、字节数、`execution_mode=fixture_smoke`、`is_fixture=true`、`formal_eligible=false`

任何运行文件未被 inventory 覆盖，或 inventory 中出现 `formal_eligible=true`，完整 Fixture Smoke 必须失败。

### Source Path / Formal Loader Audit

- `reports/fixture_isolation_audit.json` 必须证明蓝图只来自 `tests/fixtures/quality_constrained_smoke/`、Fixture 配置只来自 `configs/experiments/`、共享质量协议只来自 `configs/`，且没有读取 `data/` 正式数据。
- `reports/formal_loader_rejection_probes.json` 必须实际调用 run manifest、cache scope 和 capability profile 的 Formal 入口，记录 `accepted=false`；不得用常量0替代探针。
- `cross_mode_cache_reuse` 必须从本 run 的 active cache records 实际模式标记计算。

### STOP 边界与预算执行证据

Router candidate 进入 Dev 与 test-like 时，每条预测必须记录 `predicted_stop_risk`、冻结 `stop_boundary`、是否允许早停及对应动作。风险超过边界时必须执行下一步验证操作并计入 Cost、Elapsed Time 和 Agent Calls；预算不可行候选必须在参考准入前淘汰。Arbitrator 暴露的基础 Agent 意见必须计入 `A2A Exchanges`，不得把该维资源恒写为0。
### ContextSupportCatalog JSON

必需字段：

- `catalog_version`
- `execution_mode`
- `scope_source` 与 `scope_fingerprint`
- `agent_ids`
- `arbitrator_contexts`：有限、排序稳定的已允许 Agent 意见集合
- `catalog_hash`

Arbitrator cache record 的 `metadata.context_agents` 必须命中 catalog；`context_hash` 必须由该次实际暴露的公开意见内容计算，不得仅按 Agent 名称或未调用输出计算。

### QualityReferenceManifest JSON

必需字段：

- `manifest_version`
- `split=train_calibration`
- `budget_to_reference_policy`
- `budget_failures`
- `candidates`：保留全部预定义参考候选、readiness、质量键、资源键和淘汰原因
- `quality_protocol_hash`
- `internal_manifest_hash`
- `cache_hash`
- `seed`

禁止包含 Router `checkpoint_id`、`package_id` 或跨 checkpoint 排名。

### BudgetCalibrationManifest JSON

必需字段：

- `manifest_version`
- `split=train_calibration`
- `budgets.Tight/Medium/Loose`，每档包含 `max_cost`、`max_elapsed_time`、`max_agent_calls`、`max_a2a_exchanges`
- `quantiles`，正式顺序固定为0.25/0.50/0.75
- `policy_ids`
- `internal_manifest_hash`、`cache_hash`、`config_hash`
- `seed`

输入只能是预注册固定 behavior/reference policy 的 train_calibration Paper 级资源记录，不得读取 Router checkpoint 或 Dev/Test。

### CapabilitySupportManifest JSON

必需字段：

- `manifest_version`
- `fit_split=train_fit`
- `calibration_split=train_calibration`
- `support_quantile` 与自动产生的支持度/不确定性边界
- `fit_profile_hash`、`calibration_support_hash`
- `internal_manifest_hash`、`cache_hash`
- `calibration_no_gradient=true`
- `no_item_oracle_labels=true`

画像主体只能由 train_fit 拟合；train_calibration 只允许校准 support/uncertainty 边界。

### StopBoundaryCalibrationRecord JSON

必需字段：

- `checkpoint_id`、`checkpoint_hash`
- `calibration_split=train_calibration`
- `calibration_status`
- `stop_boundary` 或 `failure_reason` 二选一
- `coverage`
- `per_dataset_support` 与单侧安全上界
- `risk_limit`、`confidence_level`、`min_stops_per_dataset`
- `calibration_no_gradient=true`
- `calibration_no_replay=true`
- `calibration_no_checkpoint_ranking=true`

STOP 边界候选、支持度、置信上界和选择顺序必须由预注册算法自动完成。

### CalibrationPackage / PolicyPackage

每个 checkpoint 独立输出 CalibrationPackage。成功记录才可生成 Router candidate PolicyPackage；失败记录必须保留但不得进入 Dev selector。CalibrationPackage 禁止出现 `selected_final_router`、`dev_rank`、`checkpoint_rank`、`resource_champion` 或主方法升级阈值。

### Fixture Smoke 验收产物

`outputs/runs/fixture_smoke_<run_id>/` 至少包含：

- `configs/fixture_smoke_run_manifest.json`
- `configs/context_support_catalog.json`
- `configs/agent_cache_manifest.json`
- `configs/fixture_artifact_manifest.json`
- `predictions/fixture_inputs/` 下的确定性输入副本与 manifests
- `predictions/agent_cache/{train_fit,train_calibration,dev,test}/`
- `checkpoints/fixture_candidates/`
- `reports/fixture_isolation_audit.json`
- `reports/formal_loader_rejection_probes.json`
- `reports/internal_split_audit.md`
- `reports/agent_capability_manifest.json`
- `reports/quality_reference_manifest.json`
- `reports/budget_calibration_manifest.json`
- `reports/stop_boundary_calibration.jsonl`
- `reports/calibration_package_manifest.jsonl`
- `reports/policy_package_manifest.jsonl`
- `reports/checkpoint_selection.csv`
- `reports/policy_freeze_manifest.json`
- `reports/test_like_evaluation.json`
- `reports/fixture_smoke_summary.json`
- `reports/fixture_smoke_contract_review.md`

Fixture 产物只允许证明契约和流水线连通性，不能进入论文主结果表。
