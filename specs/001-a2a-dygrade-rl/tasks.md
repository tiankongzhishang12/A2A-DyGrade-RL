# 任务清单：A2A-DyGrade-RL 实验流水线

**输入**：来自 `specs/001-a2a-dygrade-rl/` 的设计文档

**前置文档**：plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md

**测试**：包含 pytest 单元测试和集成测试，因为实现计划要求 smoke validation 和可复现实验产物检查。

**组织方式**：任务按用户故事分组，确保每个故事都能独立实现和测试。

## 格式：`[ID] [P?] [Story] 任务描述`

- **[P]**：可与同阶段其他标记任务并行执行
- **[Story]**：任务所属用户故事
- 每个任务都包含明确文件路径

## Phase 1：Setup（共享基础设施）

**目的**：创建项目脚手架、配置文件和共享工具。

- [ ] T001 在 `src/a2a_dygrade_rl/`、`configs/experiments/`、`scripts/`、`tests/`、`data/`、`outputs/runs/`、`docs/` 和 `prompts/` 中创建项目目录结构
- [ ] T002 在 `pyproject.toml` 中创建 Python 项目元数据和依赖声明
- [ ] T003 [P] 在 `configs/dataset.yaml` 中创建数据集配置默认值
- [ ] T004 [P] 在 `configs/agents.yaml` 中创建 Agent 配置默认值
- [ ] T005 [P] 在 `configs/router.yaml`、`configs/cag_cql.yaml`、`configs/experiment.yaml` 和 `configs/experiments/` 中创建 Router 与实验配置默认值
- [ ] T006 [P] 在 `prompts/cheap_scorer.txt`、`prompts/mid_scorer.txt`、`prompts/strong_scorer.txt`、`prompts/evidence_agent.txt` 和 `prompts/arbitrator_agent.txt` 中创建 prompt 模板占位内容
- [ ] T007 在 `src/a2a_dygrade_rl/utils/io.py` 中创建 JSONL、CSV、YAML 和路径共享工具
- [ ] T008 在 `src/a2a_dygrade_rl/utils/seed.py` 中创建确定性随机种子工具
- [ ] T009 在 `src/a2a_dygrade_rl/utils/logging.py` 中创建日志工具

---

## Phase 2：Foundational（阻塞性前置能力）

**目的**：定义所有用户故事都会使用的 schema、校验、指标和 CLI 约定。

**关键要求**：完成本阶段前不得开始任何用户故事开发。

- [ ] T010 在 `src/a2a_dygrade_rl/utils/schemas.py` 中创建 Item、Paper、AgentOutput、A2AMessage、RoutingState、Trajectory 和 ExperimentReport 的标准数据 schema
- [ ] T011 在 `src/a2a_dygrade_rl/utils/validation.py` 中创建 score range、budget、item reference 和必填字段的 schema 校验工具
- [ ] T012 [P] 在 `src/a2a_dygrade_rl/evaluation/metrics_quality.py` 中实现 QWK、MAE、RMSE 和 Within-1 Accuracy 评分质量指标
- [ ] T013 [P] 在 `src/a2a_dygrade_rl/evaluation/metrics_cost.py`、`src/a2a_dygrade_rl/evaluation/metrics_latency.py`、`src/a2a_dygrade_rl/evaluation/metrics_budget.py` 和 `src/a2a_dygrade_rl/evaluation/metrics_routing.py` 中实现成本、延迟、预算和路由指标工具
- [ ] T014 [P] 在 `src/a2a_dygrade_rl/evaluation/metrics_a2a.py` 中实现 A2A 通信指标
- [ ] T015 在 `src/a2a_dygrade_rl/utils/cli.py` 中创建通用 CLI 参数解析工具
- [ ] T016 [P] 在 `tests/fixtures/sample_items.jsonl` 和 `tests/fixtures/sample_agent_cache.jsonl` 中添加 smoke test fixture 数据
- [ ] T017 [P] 在 `tests/unit/test_schemas.py` 中添加 schema 和校验单元测试
- [ ] T018 [P] 在 `tests/unit/test_metrics.py` 中添加评价指标单元测试

**检查点**：基础层就绪后，用户故事实现可以开始。

---

## Phase 3：用户故事 1：构建可比较的实验数据（优先级：P1）MVP

**目标**：将公开评分数据准备成可比较的 item-level 和 paper-level 产物，并完成防泄漏 split。

**独立测试**：在 fixtures 或小样本上运行数据准备流程，校验 item 文件、paper 文件和 split 完整性。

### 用户故事 1 的测试

- [ ] T019 [P] [US1] 在 `tests/unit/test_dataset_loaders.py` 中添加数据集 loader 测试，校验规范化必填字段
- [ ] T020 [P] [US1] 在 `tests/integration/test_data_pipeline.py` 中添加 paper 构造和 prompt 泄漏测试

### 用户故事 1 的实现

- [ ] T021 [P] [US1] 在 `src/a2a_dygrade_rl/datasets/load_dress.py` 中实现 DREsS loader
- [ ] T022 [P] [US1] 在 `src/a2a_dygrade_rl/datasets/load_asap_sas.py` 中实现 ASAP-SAS loader
- [ ] T023 [P] [US1] 在 `src/a2a_dygrade_rl/datasets/load_sas_bench.py` 中实现 SAS-Bench loader
- [ ] T024 [US1] 在 `src/a2a_dygrade_rl/datasets/normalize.py` 中实现共享 item 规范化逻辑
- [ ] T025 [US1] 在 `src/a2a_dygrade_rl/datasets/build_items.py` 中实现 item 构建编排
- [ ] T026 [US1] 在 `src/a2a_dygrade_rl/datasets/split.py` 中实现 prompt-level 和 paper-level split 逻辑
- [ ] T027 [US1] 在 `src/a2a_dygrade_rl/datasets/build_papers.py` 中实现 paper 构造规则
- [ ] T028 [US1] 在 `scripts/01_build_items.py` 中创建 item 构建 CLI
- [ ] T029 [US1] 在 `scripts/02_build_papers.py` 中创建 paper 构建 CLI
- [ ] T030 [US1] 在 `scripts/01_build_items.py` 和 `scripts/02_build_papers.py` 中添加数据产物校验命令支持

**检查点**：当 `items_*.jsonl` 和 `papers_*.jsonl` 能够独立生成并通过校验时，用户故事 1 完成。

---

## Phase 4：用户故事 2：缓存多 Agent 阅卷证据（优先级：P2）

**目标**：产出可复用 Agent cache、difficulty labels 和 Agent capability profiles。

**独立测试**：在样本 items 上运行 Agent cache，验证 cache、difficulty 和 capability 产物完整。

### 用户故事 2 的测试

- [ ] T031 [P] [US2] 在 `tests/unit/test_agents.py` 中添加 Agent schema 和 fixture-cache 测试
- [ ] T032 [P] [US2] 在 `tests/integration/test_agent_cache_pipeline.py` 中添加 difficulty 和 capability 集成测试

### 用户故事 2 的实现

- [ ] T033 [P] [US2] 在 `src/a2a_dygrade_rl/agents/base_agent.py` 中实现基础 Agent 接口
- [ ] T034 [P] [US2] 在 `src/a2a_dygrade_rl/agents/cheap_agent.py`、`src/a2a_dygrade_rl/agents/mid_agent.py` 和 `src/a2a_dygrade_rl/agents/strong_agent.py` 中实现 CheapAgent、MidAgent 和 StrongAgent wrappers
- [ ] T035 [P] [US2] 在 `src/a2a_dygrade_rl/agents/evidence_agent.py` 和 `src/a2a_dygrade_rl/agents/arbitrator_agent.py` 中实现 EvidenceAgent 和 ArbitratorAgent wrappers
- [ ] T036 [US2] 在 `src/a2a_dygrade_rl/agents/agent_registry.py` 中实现 Agent registry 和 fixture mode
- [ ] T037 [US2] 在 `src/a2a_dygrade_rl/utils/llm_client.py` 中实现 LLM 或 fixture client 抽象
- [ ] T038 [US2] 在 `src/a2a_dygrade_rl/agents/cache.py` 中实现 Agent cache writer 和 validator
- [ ] T039 [US2] 在 `scripts/03_run_agent_cache.py` 中创建 Agent cache CLI
- [ ] T040 [US2] 在 `src/a2a_dygrade_rl/router/difficulty.py` 中实现 difficulty scoring 和 labels
- [ ] T041 [US2] 在 `src/a2a_dygrade_rl/agents/capability.py` 中实现 Agent capability profile builder
- [ ] T042 [US2] 在 `scripts/04_build_difficulty_labels.py` 中创建 difficulty 和 capability CLI

**检查点**：当每个被接受样本 item 都拥有合法 cached Agent outputs，并生成 difficulty/capability 产物时，用户故事 2 完成。

---

## Phase 5：用户故事 3：训练并评价路由策略（优先级：P3）

**目标**：构建离线轨迹，训练 CAG-CQL Router，评价 baselines 和 ablations，并生成实验报告。

**独立测试**：运行小规模 data-to-report smoke experiment，验证 main results、ablations、logs 和 Cost-QWK curve data。

### 用户故事 3 的测试

- [ ] T043 [P] [US3] 在 `tests/unit/test_action_mask.py` 中添加 action mask 测试
- [ ] T044 [P] [US3] 在 `tests/unit/test_reward_and_trajectories.py` 中添加 reward 和 trajectory 测试
- [ ] T045 [P] [US3] 在 `tests/integration/test_smoke_experiment.py` 中添加端到端 smoke test

### 用户故事 3 的实现

- [ ] T046 [P] [US3] 在 `src/a2a_dygrade_rl/a2a/message_schema.py`、`src/a2a_dygrade_rl/a2a/message_bus.py`、`src/a2a_dygrade_rl/a2a/message_encoder.py` 和 `src/a2a_dygrade_rl/a2a/audit_log.py` 中实现 A2A message schema、bus、encoder 和 audit log
- [ ] T047 [P] [US3] 在 `src/a2a_dygrade_rl/router/action.py` 和 `src/a2a_dygrade_rl/router/action_mask.py` 中实现 routing action definitions 和 action masks
- [ ] T048 [P] [US3] 在 `src/a2a_dygrade_rl/router/state.py` 和 `src/a2a_dygrade_rl/router/reward.py` 中实现 routing state 和 reward calculation
- [ ] T049 [P] [US3] 在 `src/a2a_dygrade_rl/router/item_encoder.py`、`src/a2a_dygrade_rl/router/agent_encoder.py`、`src/a2a_dygrade_rl/router/budget_encoder.py` 和 `src/a2a_dygrade_rl/router/a2a_history_encoder.py` 中实现 item、Agent、budget 和 A2A history encoders
- [ ] T050 [P] [US3] 在 `src/a2a_dygrade_rl/graph/graph_builder.py`、`src/a2a_dygrade_rl/graph/hetero_graph.py` 和 `src/a2a_dygrade_rl/router/routing_graph_encoder.py` 中实现 graph builder 和 routing graph encoder
- [ ] T051 [US3] 在 `src/a2a_dygrade_rl/rl/trajectory_builder.py`、`src/a2a_dygrade_rl/rl/boundary_trajectory_builder.py` 和 `src/a2a_dygrade_rl/rl/hindsight_budget_relabeling.py` 中实现 basic、A2A、boundary 和 HBR trajectory builders
- [ ] T052 [US3] 在 `scripts/05_build_trajectories.py` 中创建 trajectory-building CLI
- [ ] T053 [US3] 在 `src/a2a_dygrade_rl/rl/replay_buffer.py` 中实现 replay buffer
- [ ] T054 [US3] 在 `src/a2a_dygrade_rl/router/q_network.py`、`src/a2a_dygrade_rl/router/target_network.py` 和 `src/a2a_dygrade_rl/rl/cql_loss.py` 中实现 Q network、target network 和 CQL loss
- [ ] T055 [US3] 在 `src/a2a_dygrade_rl/router/cag_cql_policy.py` 和 `src/a2a_dygrade_rl/rl/train_cag_cql.py` 中实现 CAG-CQL policy 和 training loop
- [ ] T056 [US3] 在 `scripts/06_train_cag_cql.py` 中创建 Router training CLI
- [ ] T057 [P] [US3] 在 `src/a2a_dygrade_rl/baselines/cheap_only.py`、`src/a2a_dygrade_rl/baselines/strong_only.py` 和 `src/a2a_dygrade_rl/baselines/static_difficulty_router.py` 中实现 Cheap-only、Strong-only 和 Static Difficulty Router baselines
- [ ] T058 [P] [US3] 在 `src/a2a_dygrade_rl/baselines/cp_router_grade.py` 和 `src/a2a_dygrade_rl/baselines/seqroute_grade.py` 中实现 CP-Router-Grade 和 SeqRoute-Grade baselines
- [ ] T059 [US3] 在 `src/a2a_dygrade_rl/rl/evaluate_policy.py` 中实现 policy evaluator
- [ ] T060 [US3] 在 `scripts/07_eval_baselines.py` 中创建 main baseline evaluation CLI
- [ ] T061 [US3] 在 `scripts/08_eval_ablation.py` 中创建 ablation evaluation CLI
- [ ] T062 [US3] 在 `src/a2a_dygrade_rl/evaluation/plot_cost_qwk_curve.py` 和 `scripts/09_plot_cost_qwk_curve.py` 中实现 Cost-QWK curve generation
- [ ] T063 [US3] 在 `src/a2a_dygrade_rl/evaluation/case_study.py` 中实现 case-study report generation

**检查点**：当 smoke evaluation 能够生成 main results、ablation results、Cost-QWK curve data、logs 和 case-study artifacts 时，用户故事 3 完成。

---

## Phase 6：Polish（收尾与横切事项）

**目的**：完善文档、质量检查和完整复现性。

- [ ] T064 [P] 在 `README.md` 中更新实验 workflow
- [ ] T065 [P] 在 `data/README.md` 中记录数据获取和许可证假设
- [ ] T066 [P] 在 `docs/design/report-columns.md` 中添加 report column dictionary
- [ ] T067 在 `tests/integration/test_smoke_experiment.py` 中补充 quickstart smoke workflow 校验
- [ ] T068 运行完整测试套件，并将命令和结果记录到 `outputs/runs/<run_id>/logs/test_run.log`
- [ ] T069 根据 `specs/001-a2a-dygrade-rl/contracts/artifact-schemas.md` 校验生成产物
- [ ] T070 将 `docs/design/实验计划.md` 中的最终实验检查项整理生成到 `outputs/runs/<run_id>/reports/experiment_readiness.md`
- [ ] T071 在临时目录中创建并运行一次性仓库结构规范校验脚本，校验通过后删除该临时脚本以及测试过程中产生的所有临时数据

---

## 依赖关系与执行顺序

### 阶段依赖

- **Setup（Phase 1）**：无依赖。
- **Foundational（Phase 2）**：依赖 Setup 完成，并阻塞所有用户故事。
- **用户故事 1（Phase 3）**：依赖 Foundational，是 MVP。
- **用户故事 2（Phase 4）**：依赖用户故事 1 的数据产物。
- **用户故事 3（Phase 5）**：依赖用户故事 1 和用户故事 2 的产物。
- **Polish（Phase 6）**：依赖所选用户故事完成。

### 用户故事依赖

- **US1**：foundation 后可独立开始，产出 prepared data artifacts。
- **US2**：需要 US1 的 prepared items，产出可复用 Agent cache 和 profiles。
- **US3**：需要 US1 和 US2 产出的 papers、Agent cache、difficulty labels 和 capability profiles。

### 并行机会

- T003 到 T006 可在 T001 后并行。
- T012 到 T018 可在 schema 初稿稳定后并行。
- 数据集 loaders T021 到 T023 可并行。
- Agent wrappers T033 到 T035 可并行。
- Router encoder 和 graph 相关任务 T046 到 T050 可在 action/state schema 稳定后并行。
- Baseline 实现 T057 和 T058 可并行。

## 并行示例：用户故事 1

```bash
Task: "在 src/a2a_dygrade_rl/datasets/load_dress.py 中实现 DREsS loader"
Task: "在 src/a2a_dygrade_rl/datasets/load_asap_sas.py 中实现 ASAP-SAS loader"
Task: "在 src/a2a_dygrade_rl/datasets/load_sas_bench.py 中实现 SAS-Bench loader"
Task: "在 tests/unit/test_dataset_loaders.py 中添加数据集 loader 测试"
```

## 并行示例：用户故事 3

```bash
Task: "在 src/a2a_dygrade_rl/a2a/ 中实现 A2A message schema、bus、encoder 和 audit log"
Task: "在 src/a2a_dygrade_rl/router/action.py 和 src/a2a_dygrade_rl/router/action_mask.py 中实现 routing action definitions 和 action masks"
Task: "在 src/a2a_dygrade_rl/router/ 中实现 item、Agent、budget 和 A2A history encoders"
Task: "在 src/a2a_dygrade_rl/baselines/ 中实现 Cheap-only、Strong-only 和 Static Difficulty Router baselines"
```

## 实现策略

### MVP 优先

1. 完成 Phase 1 和 Phase 2。
2. 完成用户故事 1。
3. 使用 fixture data 校验 item 和 paper 产物。
4. 暂停并审查数据假设，再进入 Agent cache。

### 增量交付

1. US1 产出可比较数据产物。
2. US2 增加可复用 Agent evidence 和 difficulty/capability summaries。
3. US3 增加 trajectories、CAG-CQL training、baselines、ablations 和 report generation。

### 验证策略

1. 保持 smoke fixtures 可在无实时模型调用时运行。
2. 下游阶段消费产物前先校验 schema。
3. 为每个 report row 保存 predictions 和 logs。
4. 最终验证时从保存输出重新计算 metrics。

## 备注

- `[P]` 任务触及不同文件，可以并行执行。
- 每个用户故事都有独立测试路径。
- fixture 和 smoke validation 通过前，不运行完整实时 Agent caching。
- 所有生成的实验产物必须能从保存配置和随机种子复现。

