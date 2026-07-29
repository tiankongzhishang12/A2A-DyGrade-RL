# 任务清单：面向模拟试卷级自动阅卷的质量约束 A2A-DyGrade-RL 实验流水线

**输入**：来自 `specs/001-a2a-dygrade-rl/` 的设计文档

**同步版本**：V1.4 最终职责分离、先按题目组拆 Item 后分别重建内部 Paper，并继承 V1.3 正式质量协议（2026-07-29）

**前置文档**：plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md

**测试**：包含 pytest 单元测试和集成测试，因为实现计划要求 smoke validation 和可复现实验产物检查。

**组织方式**：任务按用户故事分组，确保每个故事都能独立实现和测试。

## 格式：`[ID] [P?] [Story] 任务描述`

- **[P]**：可与同阶段其他标记任务并行执行
- **[Story]**：任务所属用户故事
- 每个任务都包含明确文件路径

## Phase 1：Setup（共享基础设施）

**目的**：创建项目脚手架、配置文件和共享工具。

- [X] T001 在 `src/a2a_dygrade_rl/`、`configs/experiments/`、`scripts/`、`tests/`、`data/`、`outputs/runs/`、`docs/` 和 `prompts/` 中创建项目目录结构
- [X] T002 在 `pyproject.toml` 中创建 Python 项目元数据和依赖声明
- [X] T003 [P] 在 `configs/dataset.yaml` 中创建数据集配置默认值
- [X] T004 [P] 在 `configs/agents.yaml` 中创建 Agent 配置默认值
- [X] T005 [P] 在 `configs/router.yaml`、`configs/cag_cql.yaml`、`configs/experiment.yaml` 和 `configs/experiments/` 中创建 Router 与实验配置默认值
- [X] T006 [P] 在 `prompts/cheap_scorer.txt`、`prompts/mid_scorer.txt`、`prompts/strong_scorer.txt`、`prompts/evidence_agent.txt` 和 `prompts/arbitrator_agent.txt` 中创建 prompt 模板占位内容
- [X] T007 在 `src/a2a_dygrade_rl/utils/io.py` 中创建 JSONL、CSV、YAML 和路径共享工具
- [X] T008 在 `src/a2a_dygrade_rl/utils/seed.py` 中创建确定性随机种子工具
- [X] T009 在 `src/a2a_dygrade_rl/utils/logging.py` 中创建日志工具

---

## Phase 2：Foundational（阻塞性前置能力）

**目的**：定义所有用户故事都会使用的 schema、校验、指标和 CLI 约定。

**关键要求**：完成本阶段前不得开始任何用户故事开发。

- [X] T010 在 `src/a2a_dygrade_rl/utils/schemas.py` 中创建 Item、Paper、AgentOutput、A2AMessage、RoutingState、Trajectory 和 ExperimentReport 的标准数据 schema
- [X] T011 在 `src/a2a_dygrade_rl/utils/validation.py` 中创建 score range、budget、item reference 和必填字段的 schema 校验工具
- [X] T012 [P] 在 `src/a2a_dygrade_rl/evaluation/metrics_quality.py` 中实现 QWK、MAE、RMSE 和 Within-1 Accuracy 评分质量指标
- [X] T013 [P] 在 `src/a2a_dygrade_rl/evaluation/metrics_cost.py`、`src/a2a_dygrade_rl/evaluation/metrics_latency.py`、`src/a2a_dygrade_rl/evaluation/metrics_budget.py` 和 `src/a2a_dygrade_rl/evaluation/metrics_routing.py` 中实现成本、延迟、预算和路由指标工具
- [X] T014 [P] 在 `src/a2a_dygrade_rl/evaluation/metrics_a2a.py` 中实现 A2A 通信指标
- [X] T015 在 `src/a2a_dygrade_rl/utils/cli.py` 中创建通用 CLI 参数解析工具
- [X] T016 [P] 在 `tests/fixtures/sample_items.jsonl` 和 `tests/fixtures/sample_agent_cache.jsonl` 中添加 smoke test fixture 数据
- [X] T017 [P] 在 `tests/unit/test_schemas.py` 中添加 schema 和校验单元测试
- [X] T018 [P] 在 `tests/unit/test_metrics.py` 中添加评价指标单元测试

**检查点**：基础层就绪后，用户故事实现可以开始。

---

## Phase 3：用户故事 1：构建可比较的实验数据（优先级：P1）MVP

**目标**：将公开评分数据准备成可比较的 item-level 和 paper-level 产物，保留原始分数范围并支持实验设计方案第 6 节定义的归一化评分误差，完成防泄漏 split。

**独立测试**：在 fixtures 或小样本上运行数据准备流程，校验 item 文件、paper 文件和 split 完整性。

### 用户故事 1 的测试

- [X] T019 [P] [US1] 在 `tests/unit/test_dataset_loaders.py` 中添加数据集 loader 测试，校验规范化必填字段
- [X] T020 [P] [US1] 在 `tests/integration/test_data_pipeline.py` 中添加 paper 构造和 prompt 泄漏测试

### 用户故事 1 的实现

- [X] T021 [P] [US1] 在 `src/a2a_dygrade_rl/datasets/load_dress.py` 中实现 DREsS loader
- [X] T022 [P] [US1] 在 `src/a2a_dygrade_rl/datasets/load_asap_sas.py` 中实现 ASAP-SAS loader
- [X] T023 [P] [US1] 在 `src/a2a_dygrade_rl/datasets/load_sas_bench.py` 中实现 SAS-Bench loader
- [X] T024 [US1] 在 `src/a2a_dygrade_rl/datasets/normalize.py` 中实现共享 item 规范化逻辑
- [X] T025 [US1] 在 `src/a2a_dygrade_rl/datasets/build_items.py` 中实现 item 构建编排
- [X] T026 [US1] 在 `src/a2a_dygrade_rl/datasets/split.py` 中实现 prompt-level 和 paper-level split 逻辑
- [X] T027 [US1] 在 `src/a2a_dygrade_rl/datasets/build_papers.py` 中实现可配置的 paper 构造规则和 dataset mix 偏离记录；主实验最终固定5题 strict mix 的实现与审计由 T030G-T030J 完成
- [X] T028 [US1] 在 `scripts/01_build_items.py` 中创建 item 构建 CLI
- [X] T029 [US1] 在 `scripts/02_build_papers.py` 中创建 paper 构建 CLI
- [X] T030 [US1] 在 `scripts/01_build_items.py` 和 `scripts/02_build_papers.py` 中添加数据产物校验命令支持
- [X] T030A [US1] 在 `src/a2a_dygrade_rl/datasets/normalize.py` 中实现分数范围与归一化评分误差工具，严格使用实验设计方案公式 `R_i = score_max_i - score_min_i`、`E_i = abs(pred_score_i - gold_score_i) / R_i`
- [X] T030B [US1] 在 `src/a2a_dygrade_rl/datasets/audit.py` 中实现 prepared data 审计逻辑，校验 `R_i > 0`、score range 合法、归一化误差公式可用于后续 Agent 误差、difficulty labels、capability profiles 和历史 reward 兼容，并统计 paper dataset mix 是否符合 2-3 ASAP-SAS、1-2 SAS-Bench、1 DREsS 的设计目标；该历史 reward/difficulty 产物不作为 V1.3 正式质量约束目标
- [X] T030C [US1] 在 `scripts/00_audit_prepared_data.py` 中创建数据审计 CLI，生成 `outputs/runs/<run_id>/reports/data_audit.md` 和 `outputs/runs/<run_id>/reports/data_distribution.csv`
- [X] T030D [P] [US1] 在 `tests/integration/test_data_audit.py` 中添加数据审计集成测试，覆盖分数范围错误、归一化误差计算、item/prompt/paper 泄漏和 paper 引用错误
- [X] T030E [US1] 运行真实 `data/processed/` 数据审计并记录结果，确认归一化评分误差可审计、split 无泄漏、paper 引用合法后再进入 Agent cache
- [X] T030F [US1] 在 `src/a2a_dygrade_rl/datasets/split.py` 中实现 prompt group 与 exact prompt-answer key 的连通分量防泄漏 split，确保同题面同答案不得跨 train/dev/test
- [X] T030G [US1] 在 `src/a2a_dygrade_rl/datasets/build_papers.py` 中实现主实验 strict paper mix 构造，每张 paper 固定 5 题并满足 ASAP-SAS 2/3、SAS-Bench 1/2、DREsS 1
- [X] T030H [US1] 在 `paper_manifest.csv` 中补齐 dataset、prompt_group、paper_dataset_mix、mix_status、deviation_reason、split_scope 等可审计字段
- [X] T030I [US1] 在 `src/a2a_dygrade_rl/datasets/audit.py` 中将 exact prompt-answer 跨 split、strict paper mix 偏离和 manifest prompt_group 为空升级为阻塞性审计错误，并补充对应测试
- [X] T030J [US1] 重新生成 `data/processed/` prepared data，运行 data audit v2，确认三项隐患归零或被明确隔离到非主实验 relaxed 产物后再进入 Agent cache

**检查点**：当 `items_*.jsonl` 和 `papers_*.jsonl` 能够独立生成，通过 split leakage check，并且 `data_audit.md` 明确记录 score range、`R_i` 与归一化评分误差公式后，用户故事 1 才算完成。

---

## Phase 4：用户故事 2：缓存多 Agent 阅卷证据（优先级：P2）

**目标**：完成可复用 Agent cache、初始 difficulty 工程产物和 Agent capability profiles；正式 Router 阶段将把静态 difficulty 语义收敛为动态未解决评分风险。

**独立测试**：在样本 items 上运行 Agent cache，验证 cache、difficulty 和 capability 产物完整。

### 用户故事 2 的测试

- [X] T031 [P] [US2] 在 `tests/unit/test_agents.py` 中添加 Agent schema、稳定 cache key、gold 隔离、运行模式隔离和 fixture-cache 测试，覆盖 `run_id`、`execution_mode`、`is_fixture` 以及统一 Agent cache 字段
- [X] T032 [P] [US2] 在 `tests/integration/test_agent_cache_pipeline.py` 中添加 fixture Agent cache、difficulty 和 capability 集成测试，覆盖确定性重跑、`D_i = alpha*Err_cheap + beta*Err_mid + gamma*Disagreement_i + delta*Complexity_i`、train 阈值、Easy/Medium/Hard 分层和 capability table 字段；该 difficulty 公式仅是已完成的历史 fixture/诊断逻辑，不作为 V1.3 正式路由质量边界

### 用户故事 2 的实现

- [X] T033 [P] [US2] 在 `src/a2a_dygrade_rl/agents/base_agent.py` 中实现基础 Agent 接口
- [X] T034 [P] [US2] 在 `src/a2a_dygrade_rl/agents/cheap_agent.py`、`src/a2a_dygrade_rl/agents/mid_agent.py` 和 `src/a2a_dygrade_rl/agents/strong_agent.py` 中实现 CheapAgent、MidAgent 和 StrongAgent wrappers
- [X] T035 [P] [US2] 在 `src/a2a_dygrade_rl/agents/evidence_agent.py` 和 `src/a2a_dygrade_rl/agents/arbitrator_agent.py` 中实现 EvidenceAgent 和 ArbitratorAgent wrappers
- [X] T036 [US2] 在 `src/a2a_dygrade_rl/agents/agent_registry.py` 中实现 Agent registry 和 `fixture_smoke` mode，注册五类 Agent 并拒绝 fixture client 进入真实运行模式
- [X] T037 [US2] 在 `src/a2a_dygrade_rl/utils/llm_client.py` 中实现 provider-neutral client 抽象和确定性 `FixtureClient`，请求中不得包含 `gold_score`
- [X] T038 [US2] 在 `src/a2a_dygrade_rl/agents/cache.py` 中实现 Agent cache writer、manifest、validator、断点续跑和模式隔离，按 split/Agent 写入 `outputs/runs/<run_id>/predictions/agent_cache/`
- [X] T039 [US2] 在 `scripts/03_run_agent_cache.py` 中创建 Agent cache CLI，支持 `--execution-mode`、`--fixture`、`--resume` 和 test final-evaluation 门禁
- [X] T040 [US2] 在 `src/a2a_dygrade_rl/router/difficulty.py` 中实现旧阶段 train difficulty supervision、train-only 阈值、推理可见特征和 predictor 接口；当时主 predictor 为 `HistGradientBoostingRegressor`、`Ridge` 仅作诊断，V1.3 中该产物降级为诊断/可选初始特征，正式停止安全语义由 T051 Stop-Risk Head 承担
- [X] T041 [US2] 在 `src/a2a_dygrade_rl/agents/capability.py` 中实现旧阶段 train-only Agent capability profile builder，输出按 Agent、dataset、question type、difficulty 聚合的 QWK、原始/归一化 MAE、Cost、Latency、Calibration、样本量和能力向量 `c_a`；V1.3 Formal 画像由 T050A 按 `train_fit/train_calibration` 职责重建
- [X] T042 [US2] 在 `scripts/04_build_difficulty_labels.py` 中创建 difficulty 和 capability CLI，产物全部写入同一 `outputs/runs/<run_id>/` 并拒绝 test/跨模式输入
- [X] T042A [US2] 在 difficulty labels 和 Agent capability profiles 中使用实验设计方案定义的归一化评分误差 `E_i` 计算 Agent error，原始尺度 MAE 仅作为报告指标保留

**检查点**：Fixture Agent cache、difficulty/capability 工程流程已经完成；正式真实模型 cache、主路由范围和 V1.3 风险校准仍需后续任务完成。

### 已完成追加修复

- [X] T072 [US2] 修复 `src/a2a_dygrade_rl/agents/cache.py` 的失败缓存断点续跑语义：`--resume` 仅复用 `status=success` 的合法记录，对已有失败记录重新执行，重建失败日志并补充瞬时失败后 resume 成功的集成测试

---

## Phase 5：用户故事 3A：V1.4 内部 Paper、协议基础、正式 Agent Pilot 与 Formal Cache（优先级：P3）

**目标**：先从当前27,375条 train 主路由 Item 按 prompt/exact-answer/leakage 传递连通分量划分，再分别重建 `train_fit/train_calibration` strict Paper；实现 V1.3 质量协议和 V1.4 职责门禁，完成用户批准的真实 Agent Pilot 与 Formal cache，为后续 train_fit-only Router 训练提供可信数据。

**独立测试**：使用 fixture Item 完成 component 原子分配、两个 split 的 strict Paper 重建、内部 leakage audit、正式质量指标、per-checkpoint STOP 校准、Calibration Package 和 Dev-only selector；验证 calibration 不训练参数、不进入 replay、不跨 checkpoint 排名。

### 用户故事 3A 的测试

- [ ] T043 [P] [US3] 在 `tests/unit/test_internal_split.py` 中添加 V1.4 Item-level component 拆分测试：输入仅限当前27,375条 train 主路由 Item，以 `dataset+prompt_group` 与 exact-answer/leakage component 的传递连通分量为原子，覆盖目标80/20、确定性、group不跨 split、旧 `paper_train_*` 不作为分配单元、manifest 字段和拒绝 dev/test
- [ ] T043A [P] [US3] 在 `tests/unit/test_capability_profile.py` 中添加能力画像 `train_fit` 拟合、`train_calibration` 仅自动校准支持度边界、拒绝 dev/test、无 Item 级 oracle 标签和重复运行一致性测试
- [ ] T043B [P] [US3] 在 `tests/integration/test_internal_paper_rebuild.py` 中添加分别重建 `papers_train_fit.jsonl/papers_train_calibration.jsonl` 的测试，覆盖新 paper ID、固定5题、strict mix、仅引用本 split Item、Item不重复、leftover可追踪、内部 Item/Prompt/Component/Paper overlap=0，以及直接拆旧 train Paper 必须失败
- [ ] T044 [P] [US3] 在 `tests/unit/test_hidden_cache_env.py` 和 `tests/unit/test_action_mask.py` 中添加未调用 cache 隐藏、结构动作掩码、四维预算掩码、support catalog 外/缺失 active cache 动作屏蔽、无分数禁止 STOP、单意见禁止 ARBITRATE 和禁止在线补算测试
- [ ] T045 [P] [US3] 在 `tests/unit/test_quality_constraints.py`、`tests/unit/test_calibration.py` 和 `tests/unit/test_checkpoint_selector.py` 中添加职责分离测试：calibration 对每个冻结 checkpoint 只输出 STOP 边界或 failure，禁止梯度/replay/跨 checkpoint 排名/最终选择/主方法升级阈值；Dev 只比较边界冻结 Package，执行全预算质量门和跨预算资源词典序并输出唯一 checkpoint
- [ ] T045A [US3] 在 `tests/integration/test_quality_constrained_smoke.py` 中添加 `item component split -> separate paper rebuild -> train_fit candidate checkpoint -> train_calibration STOP boundary/package -> Dev fixed-package gate/select -> freeze -> test-like` 端到端 smoke，验证 calibration 不排名、Dev 不改边界、任一预算失败淘汰整个 Package、相同种子输出唯一 checkpoint
- [ ] T045B [P] [US3] 在 `tests/unit/test_quality_protocol_v13.py`、`tests/unit/test_qwk_readiness.py` 和 `tests/unit/test_paired_bootstrap_gate.py` 中添加 Gate Error 非法/Deferral=1、Severe >0.25、Extreme >=0.50、Unsafe Stop 分母与零 STOP=NA、Macro-NMAE、half-up `0..10` 共11档完整 labels、QWK readiness、Paper 配对5000次单侧95%零界、置信区间跨0失败及固定种子可重复测试

### 用户故事 3A 的实现

- [ ] T046 [P] [US3] 在 `src/a2a_dygrade_rl/datasets/internal_split.py` 和 `scripts/04a_build_internal_split.py` 中实现 V1.4 Item-level internal split：读取当前 train `paper_manifest.csv` 引用的27,375条 Item，构造 prompt/exact-answer connected components，按固定种子和目标80/20确定性分配，优先保持component完整、三数据集覆盖与strict Paper可构造性，输出 `data/processed/internal_item_split_manifest.csv` 和实际比例/偏差
- [ ] T046A [US3] 在 `src/a2a_dygrade_rl/datasets/build_internal_papers.py`、`src/a2a_dygrade_rl/datasets/audit_internal_split.py` 和 `scripts/04c_build_internal_papers.py` 中分别从两个内部 Item 池重建固定5题 strict Paper，将 `papers_train_fit.jsonl`、`papers_train_calibration.jsonl`、`internal_paper_manifest.csv` 和 `leftover_items.csv` 写入 `data/processed/`，并将 `internal_split_audit.md` 写入对应 run 的 `reports/`；拒绝跨 split 借题、重复 Item、旧 paper ID 继承、泄漏和 strict mix 违规
- [ ] T047 [P] [US3] 在 `src/a2a_dygrade_rl/utils/schemas.py`、`src/a2a_dygrade_rl/utils/validation.py`、`configs/dataset.yaml`、`configs/router.yaml`、`configs/cag_cql.yaml` 和 `configs/quality_protocol.yaml` 中扩展 InternalItemSplitManifest、InternalPaperManifest、LeftoverRecord、CalibrationPackage、PolicyPackage、QualityMetricProtocol、QWKReadinessRecord、PairedBootstrapGateResult、QualityReference/Budget/Freeze manifests；加入目标约80/20及优先级、禁止直接拆旧Paper、calibration_no_gradient/no_replay/no_checkpoint_ranking、Dev boundary immutable 和协议 hash 校验
- [ ] T048 [P] [US3] 在 `src/a2a_dygrade_rl/agents/cache.py` 和 `scripts/03_run_agent_cache.py` 中实现以 `internal_item_split_manifest.csv` 为 train 侧 Formal cache split 来源、以外部 manifests 为 Dev/Test 来源；拒绝根据旧 `paper_train_*` 推断内部 split，冻结有限 `context_support_catalog.json`、范围/目录指纹，并为 Arbitrator 强制绑定仅含已暴露意见的 `context_hash`
- [ ] T063C [US3] 在新建的 `src/a2a_dygrade_rl/evaluation/quality_protocol.py`、`qwk_readiness.py` 以及现有 `metrics_safety.py`、`metrics_quality.py`、`metrics_budget.py` 和 `failure_registry.py` 中实现 Gate Error 非法/Deferral=1、Severe/Extreme、Unsafe Stop 与零 STOP=NA、Macro/Micro-NMAE、half-up 固定 `0..10` 共11档完整 labels QWK、readiness、Budget Exhaustion、Deferral 和失败保留；修复当前按实际标签 union 计算 QWK 的实现
- [ ] T063E [US3] 在新建的 `src/a2a_dygrade_rl/evaluation/paired_bootstrap.py` 和 `statistical_gate.py` 中实现以 Paper 为 cluster、候选/参考配对、5000次、单侧95%、零非劣效界、固定种子 `20260729` 的 Bootstrap，计算 Severe/Unsafe 最坏数据集差值、Macro-NMAE/QWK 差值及 UCB/LCB；任一指标未定义或置信区间跨0时输出 `quality_noninferiority_inconclusive`，并保存逐次或可重建的重采样产物
- [ ] T049 [P] [US3] 在 `src/a2a_dygrade_rl/rl/quality_reference.py` 中实现预定义 reference policies 按预算档位的 train_calibration 自动选择：先要求指标/STOP/QWK readiness，再按 Worst-Dataset Severe、Worst-Dataset Unsafe Stop、Macro-NMAE、Macro-QWK、资源和 Policy ID 固定顺序选择，输出全部参考候选及 `budget_id -> reference_policy_id` 的 `quality_reference_manifest.json`；此任务只确定质量门参考，不读取或排名 Router checkpoint
- [ ] T050 [P] [US3] 在 `src/a2a_dygrade_rl/rl/budget_calibration.py` 中仅使用重建后的 Formal `paper_train_calibration_*` 和固定 behavior/reference policies 统计 Paper 级四维资源分布，按预注册分位数生成 Tight/Medium/Loose 并输出含 internal manifest hash 的 `budget_calibration_manifest.json`；Pilot 分位数不得充当正式预算
- [ ] T050A [P] [US3] 在 `src/a2a_dygrade_rl/agents/capability.py` 和 `scripts/04b_build_capability_profiles.py` 中实现 Formal 能力画像：只用 `train_fit` 拟合画像统计，`train_calibration` 仅按预注册程序校准 low-support/uncertainty 边界，保存输入 split、支持度、算法和指纹 manifest
- [ ] T051 [P] [US3] 在 `src/a2a_dygrade_rl/router/stop_risk_head.py` 和 `src/a2a_dygrade_rl/rl/calibration.py` 中实现基于 `Gate Error > 0.25` 的 train_fit Stop-Risk 训练接口，以及对每个冻结 checkpoint 在 `paper_train_calibration_*` 上独立校准唯一 STOP 安全概率边界；禁止参数更新、replay写入、跨checkpoint排名、最终选择和主方法升级阈值，Dev不得移动边界
- [ ] T052 [US3] 在 `src/a2a_dygrade_rl/rl/policy_package.py` 中实现 Calibration Package builder：每个固定 checkpoint 只打包其 STOP 边界或 calibration failure、参考映射、预算、support/quality/internal manifest hashes，输出 `calibration_package_manifest.jsonl`；schema 禁止跨 checkpoint Dev rank、`selected_final_router` 和资源冠军字段
- [ ] T052A [US3] 在 `configs/agents.yaml`、`prompts/*.txt` 和 `src/a2a_dygrade_rl/utils/llm_client.py` 中准备真实 Agent provider-neutral 配置、严格 JSON 输出和请求权限；任何 SDK、权重、API 或联网调用须先获得用户批准并记录 D 盘路径与费用上限
- [ ] T052B [US3] 在用户批准后从 V1.4 重建的完整 strict `paper_train_fit_*` 抽取约100个 Item（约20份5题 Paper）运行 `real_pilot_<run_id>`，审计 JSON 成功率、分数越界、Agent 互补性、Evidence/Arbitrator 增益、context catalog 规模、实际 token/cost/elapsed time/calls/exchanges，并生成是否允许进入 Formal cache 的门禁报告；Pilot 分位数不直接作为正式预算
- [ ] T052C [US3] 在 Pilot 门禁通过且 Formal Agent/Prompt/解析/成本配置与 context support catalog 冻结后，按 V1.4 internal item manifest 生成独立 `formal_agent_cache_<run_id>` 的 train_fit/train_calibration cache，并按外部 manifest 生成 Dev cache；Test cache 推迟到最终 freeze，Pilot active cache 不得复制或晋升
- [ ] T052D [US3] 在 T052C 后仅用 Formal train_fit cache 拟合能力画像主体，仅用 Formal train_calibration rebuilt Paper/cache 冻结支持度边界、质量参考和预算，生成并审计 `agent_capability_manifest.json`、`quality_reference_manifest.json`、`budget_calibration_manifest.json`；此任务不校准 checkpoint、不选择最终 Router，拒绝 Dev/Test

**检查点**：Fixture V1.3 指标、readiness、per-checkpoint STOP 校准、Calibration Package 和 Dev-only selector smoke 通过；真实 Pilot 获得单独批准并证明 Agent 具有非平凡互补性；Formal train_fit/train_calibration/dev cache 与 internal manifests 一致；质量参考、正式预算和画像支持度边界已由 calibration 程序冻结。正式 per-checkpoint STOP 边界必须等待 Phase 6 候选 checkpoint 产生后再运行；Test 尚未参与。

---

## Phase 6：用户故事 3B：质量约束 CAG-CQL Router 与公平评价（优先级：P3）

**目标**：在隐藏 cache 的多题共享资源环境中，只用 train_fit 训练带 Stop-Risk Head 的质量约束 CAG-CQL；随后对候选 checkpoint 执行独立 calibration Package 构建和 Dev-only 选择，并与强分类、Bandit、greedy 和 knapsack baseline 公平比较。

**独立测试**：运行 `train_fit candidate checkpoints -> train_calibration STOP boundary/package -> Dev fixed-package gate/select -> report` smoke，验证训练、校准和最终选择的数据职责完全分离，并生成每预算档位四项配对统计质量门、QWK/STOP readiness、跨预算资源排序、唯一 Policy Package/checkpoint、消融表和失败注册表。

### 用户故事 3B 的测试

- [ ] T053 [P] [US3] 在 `tests/unit/test_routing_state.py` 和 `tests/unit/test_a2a.py` 中添加可见状态、A2A exchange、Arbitrator context hash、累计 elapsed time 和预算状态转移测试
- [ ] T054 [P] [US3] 在 `tests/unit/test_reward_and_trajectories.py` 中添加 Gate Error、Severe `>0.25` 标签、STOP counterfactual、hidden-cache trajectory、预算耗尽、Deferral/非法结果最坏损失=1和 HBR 不改变质量标签测试
- [ ] T055 [P] [US3] 在 `tests/unit/test_quality_constrained_cql.py` 中添加 Routing Q Head、Stop-Risk Head、Resource Critic、Masked CQL、质量可行动作筛选和 STOP 风险约束测试
- [ ] T056 [US3] 在 `tests/integration/test_smoke_experiment.py` 中完成全部 baseline、消融、自动 checkpoint 选择、失败保留和报告重算的端到端 smoke test

### 用户故事 3B 的实现

- [ ] T057 [P] [US3] 在 `src/a2a_dygrade_rl/a2a/message_schema.py`、`message_bus.py`、`history_encoder.py` 和 `audit_log.py` 中实现 A2A exchange 与通信历史，规定 `A2A_ASK` 计一次 exchange、`ARBITRATE` 不额外计 exchange
- [ ] T058 [P] [US3] 在 `src/a2a_dygrade_rl/router/action.py`、`action_mask.py`、`state.py` 和 `src/a2a_dygrade_rl/rl/hidden_cache_env.py` 中实现任务—操作动作、四维预算、逐步 cache reveal、context/cache-support 动作掩码、预算耗尽和 deferral 状态，评价阶段禁止在线 Agent fallback
- [ ] T059 [P] [US3] 在 `src/a2a_dygrade_rl/router/item_encoder.py`、`agent_encoder.py`、`budget_encoder.py`、`a2a_encoder.py` 和 `src/a2a_dygrade_rl/graph/` 中实现仅编码可见信息的 CAG shared encoder
- [ ] T060 [US3] 在 `src/a2a_dygrade_rl/rl/trajectory_builder.py`、`replay_buffer.py` 和 `scripts/05_build_trajectories.py` 中仅从 V1.4 重建的 `paper_train_fit_*` 与 train_fit hidden cache 构建 behavior trajectories、STOP 风险标签、A2A/仲裁轨迹、预算条件轨迹和 replay buffer；loader 必须拒绝 calibration/dev/test Paper 或 cache
- [ ] T061 [US3] 在 `src/a2a_dygrade_rl/router/q_network.py`、`target_network.py`、`resource_critic.py` 和 `cag_cql_policy.py` 中实现 Double Q、Target Network、Routing Q Head、Resource Critic、Stop-Risk Head 接入和 Masked Conservative Penalty
- [ ] T062 [US3] 在 `src/a2a_dygrade_rl/rl/quality_constraints.py`、`train_cag_cql.py` 和 `scripts/06_train_cag_cql.py` 中仅用 train_fit replay 实现单一预算条件质量约束离线训练，输出预注册范围内候选 checkpoint、训练曲线和 `candidate_checkpoint_manifest.json`；本任务不得读取 calibration/dev/test，不得校准 STOP 边界、组装最终 Package、执行 Dev 排名或 freeze，也不得以手工 `QWK-beta*Cost` 权重选择模型或为不同预算训练后挑不同 checkpoint
- [ ] T052E [US3] 在 `src/a2a_dygrade_rl/rl/checkpoint_selector.py` 中实现 Dev-only selector：拒绝未冻结边界或缺失 manifest/hash 的 Package，在 Tight/Medium/Loose 各档执行质量门，淘汰任一预算失败候选，只对全预算质量可行 Package 计算跨预算等权资源键并按冻结词典序输出唯一 `checkpoint_selection.csv` 与 `policy_freeze_manifest.json`；禁止移动边界，相同输入重复运行必须一致
- [ ] T063 [P] [US3] 在 `src/a2a_dygrade_rl/baselines/fixed_agents.py`、`calibrated_threshold.py`、`static_classifier.py` 和 `fixed_cascade.py` 中实现固定 Agent、自动校准阈值、静态分类器、固定级联和完整多 Agent baseline；阈值 baseline 只可在 train_calibration 按预注册算法自动校准并在 Dev 前冻结，主方法的升级动作不得复用这些阈值
- [ ] T063A [P] [US3] 在 `src/a2a_dygrade_rl/baselines/contextual_bandit.py`、`myopic_router.py`、`greedy_router.py` 和 `knapsack_router.py` 中实现非 RL 强 baseline，所有方法共享同一隐藏 cache 环境与预算
- [ ] T063B [US3] 在 `src/a2a_dygrade_rl/rl/evaluate_policy.py`、`scripts/07_eval_baselines.py` 和 `scripts/08_eval_ablation.py` 中编排正式职责链：对 T062 候选 checkpoint 调用 T051/T052，仅用 train_calibration 生成 STOP 边界或 failure 与 Calibration Package；再对边界冻结 Package、参考、baseline 和消融在 Dev 的同 Paper/同 cache/同预算上调用正式指标、QWK/STOP readiness 与 Paper Bootstrap Gate，并交给 T052E 产生唯一选择；任何未定义或 inconclusive 结果必须判为质量不可行，且记录 calibration 无排名、Dev 无边界修改审计
- [ ] T063D [US3] 在 `src/a2a_dygrade_rl/evaluation/report_tables.py`、`plot_cost_qwk_curve.py`、`case_study.py` 和 `scripts/09_plot_cost_qwk_curve.py` 中生成含 internal manifest、calibration boundary/failure、Dev selector 状态、每预算质量可行、Package 全预算质量可行、四项统计边界、QWK/STOP readiness、Stop Coverage、Deferral 和资源指标的主表、分数据集表、消融表、预算前沿、失败注册表及成功/失败 case study；只有质量可行方法报告资源节省

**检查点**：Smoke 能端到端生成可重算报告；T062 只输出候选 checkpoint，T051/T052 只在 calibration 固定边界并组装 Package，T052E 只在 Dev 选择；主方法与分类器/Bandit/greedy/knapsack 共享 internal papers、cache、预算、quality protocol、Bootstrap 和评价脚本。若无 checkpoint 在全部预算档位通过四项配对统计质量门，系统输出失败并停止资源成功声明。

---

## Phase 7：Polish、Final Evaluation 与复现包

**目的**：完成文档、正式 Test 一次性评价、产物审计和论文材料。

- [ ] T064 [P] 在 `README.md` 和 `data/README.md` 中更新外部 Paper 与 V1.4 内部 Item split/重建 Paper 的区别、`train_fit/train_calibration/dev/test` 最终职责、V1.3 正式质量协议、质量可行后资源优先流程、真实数据许可和完整实验 workflow
- [ ] T065 [P] 在 `specs/001-a2a-dygrade-rl/data-model.md`、`contracts/artifact-schemas.md`、`contracts/cli-contract.md` 和 `quickstart.md` 中同步 InternalItemSplitManifest、InternalPaperManifest、LeftoverRecord、CalibrationPackage、QualityMetricProtocol、QWKReadinessRecord、PairedBootstrapGateResult、单一预算条件 PolicyPackage、按预算参考映射、预算/STOP 校准、Stop-Risk Head、隐藏 cache、Dev-only selector 和 final-evaluation 门禁
- [ ] T066 [P] 在 `docs/design/report-columns.md` 中添加 internal split/paper/leftover 字段、Gate Error、Severe/Extreme、Unsafe Stop/Stop Coverage/Deferral、Macro-NMAE、固定11档 QWK/readiness、四项 UCB/LCB、per-checkpoint calibration boundary/failure、Dev 资源排序和资源指标字段字典
- [ ] T067 在 `tests/integration/test_smoke_experiment.py` 中补充 quickstart smoke、禁止直接拆旧 train Paper、内部 split/rebuild 零泄漏、calibration no-gradient/no-ranking、Dev boundary immutable、Deferral 最坏损失、零 STOP=NA、QWK undefined、CI 跨0失败、selector 重复运行一致性、测试数据拒绝训练和报告重算校验
- [ ] T068 在唯一 Package 完成 Dev freeze 后生成隔离 test cache，校验 external/internal manifests、quality protocol/reference/budget、calibration package、STOP boundary、cache/code hashes，执行一次性 final evaluation `final_evaluation_<run_id>`，保存 `policy_freeze_manifest.json`、`qwk_readiness.csv`、`quality_gate_bootstrap.csv` 和 Test one-shot 记录；不得根据结果返回调参
- [ ] T069 根据 `specs/001-a2a-dygrade-rl/contracts/artifact-schemas.md` 审计 internal item/paper/leftover manifests、Formal cache split、capability/reference/budget manifests、每 checkpoint calibration package、Dev-only selection、quality protocol/hash、QWK readiness、Bootstrap 重采样可重建性和 failure registry
- [ ] T070 在 `outputs/runs/<run_id>/reports/experiment_readiness.md` 中记录外部数据审计、V1.4 component split与两套Paper重建、Agent Pilot、Formal cache、quality protocol、STOP/QWK readiness、质量参考、预算/支持度/每checkpoint STOP校准、calibration无排名审计、Dev-only选择、Test freeze 和复现门禁
- [ ] T071 运行完整测试套件，将命令、V1.3 指标/Bootstrap 固定种子重复性、V1.4 internal split/rebuild 确定性和 calibration/Dev 职责隔离结果写入 `outputs/runs/<run_id>/logs/test_run.log`，并在临时目录完成仓库结构规范校验后删除临时脚本与数据

---

## 依赖关系与执行顺序

### 阶段依赖

```text
已完成 External Prepared Data
→ 已完成 Agent fixture 工程
→ V1.4 Item component split
→ train_fit/train_calibration 分别重建 strict Paper 与内部审计
→ V1.3 quality protocol、QWK readiness、paired Bootstrap
→ calibration/Dev 职责隔离 fixture smoke
→ 用户批准真实 Agent Pilot
→ Formal train_fit/train_calibration/dev cache
→ train_fit能力画像主体 + calibration支持度/质量参考/预算冻结
→ train_fit hidden environment、轨迹、replay与候选checkpoint训练
→ train_calibration per-checkpoint STOP boundary与Package
→ Dev固定Package质量门、唯一选择与freeze
→ 一次性 Test final evaluation
```

### 用户故事依赖

- **US1**：已完成外部 prepared data；V1.4 追加内部 Item split 与 Paper rebuild 后，才向后续阶段提供可信的 `train_fit/train_calibration` episode。
- **US2**：Fixture 工程已完成；真实 Pilot 和 Formal cache 由 Phase 5 收敛，并严格读取 internal manifests。
- **US3A**：依赖 US1/US2；T046/T046A 先产生内部数据，T047/T063C/T063E 固定 schema、指标与统计门，T049/T050/T050A 冻结全局 calibration 产物，T051/T052/T052E 提供职责分离组件。
- **US3B**：依赖 US3A 的 rebuilt Paper、Formal cache、参考/预算/支持度和协议 manifest；T062 只训练候选 checkpoint，T063B 才调用 calibration Package 与 Dev selector 完成正式选择。

### 关键任务依赖

```text
T043/T043A/T043B/T044/T045/T045B（测试先行）
→ T046/T046A/T047/T048
→ T063C（指标与readiness）
→ T063E（paired bootstrap gate）
→ T049/T050/T050A/T051/T052/T052E
→ T045A（fixture端到端门禁）
→ T052A（Pilot配置，不联网）
→ 用户审批
→ T052B → T052C → T052D
→ T057-T062（只到候选checkpoint）
→ T063/T063A
→ T063B（正式calibration Package + Dev-only评价/选择）
→ T063D（报告）
→ T064-T071
```

### 并行机会

- T043、T043A、T043B、T044、T045、T045B 可并行编写测试。
- T046 与 T047 可在接口约定后并行；T046A 依赖 T046 的冻结 Item split，T048 依赖 internal manifest schema。
- T063C 与 T050A 可并行；T063E 依赖 T063C 的指标接口。
- T049、T050、T050A 在 Formal calibration cache 可用后可并行运行；T051/T052/T052E 可先用 fixture 实现，但正式 per-checkpoint 执行必须等待 T062。
- T057–T059 可并行实现 A2A、环境和编码器。
- T063 与 T063A 可并行实现 baseline；其 calibration 边界必须在 Dev 前冻结。
- T063D 依赖 T063B 的统一评价产物；T064–T066 可在 contract 稳定后并行。

## 实现策略

### 最近的可执行 MVP

1. 先完成 T043、T043A、T043B、T044、T045、T045B 的 V1.4 测试定义，不修改测试以迎合实现结果；
2. 完成 T046、T046A、T047、T048、T063C、T063E，落实先拆 Item component、后分别重建 Paper、quality protocol、QWK readiness 和配对统计门；
3. 完成 T049、T050、T050A、T051、T052、T052E 的参考/预算/支持度/STOP校准/Package/Dev selector 自动化；
4. 运行 T045A 的 `item component split -> separate paper rebuild -> train_fit candidate checkpoint -> train_calibration STOP boundary/package -> Dev fixed-package gate/select -> freeze -> test-like` fixture smoke；
5. 完成 T052A 的 Pilot 候选配置、费用上限和 support catalog 草案，但不联网调用；
6. 向用户提交基于重建后 train_fit strict Paper 的真实 Agent Pilot 审批；
7. 获批后依次执行 T052B–T052D，再进入 T057–T062 Router 实现；正式 calibration 与 Dev 选择只能在 T062 候选 checkpoint 产生后由 T063B 编排。

### 验证策略

1. 每个新模块先有 unit test；
2. 禁止直接拆旧 train Paper、component跨split、跨split借题、5题/strict mix违规为阻塞性测试；
3. Gate Error 未完成赋值、Severe/Extreme 边界、零 STOP=NA、half-up 11档 labels 和 QWK readiness 为阻塞性测试；
4. Paired Bootstrap 必须验证同一 Paper 索引、5000次、固定种子、单侧边界和 CI 跨0失败；
5. calibration梯度/replay/跨checkpoint排名为0、Dev边界修改为0、Test训练读取为0，均为阻塞性职责审计；
6. 隐藏 cache、support catalog、质量门和资源优先自动选择为阻塞性集成测试；
7. 所有拆分、Paper重建、自动校准、Bootstrap 和 checkpoint 选择必须可重复；
8. 所有报告行可追溯到 predictions、logs、config、external/internal manifests、calibration package、protocol hash 和统计产物；
9. 失败结果不得删除。

## 备注

- 已完成任务保持 `[X]`，本次未把任何新增或改写任务虚假标记完成。
- 原尚未实现的 Router 任务已按 V1.4 最终职责拆分：T062 只训练候选 checkpoint，T051/T052 负责 per-checkpoint calibration Package，T052E 负责 Dev-only selector。
- 当前任务总数为99，其中54项已完成、45项待执行；V1.4 新增 T043B、T046A 与 T052E 均保持未完成。
- 真实 SDK、权重、API 和付费调用必须获得用户单独批准。
- `docs/design/研究定义与实验约束同步方案.md` V1.4 是本轮同步依据；后续若改变内部拆分顺序、四阶段职责、质量指标、Bootstrap 或 Dev 顺序，必须先回到规格/计划阶段。
- 更新 `tasks.md` 后停留在用户审阅门禁，不自动进入 `speckit-implement`。
