# 任务清单：面向模拟试卷级自动阅卷的质量约束 A2A-DyGrade-RL 实验流水线

**输入**：来自 `specs/001-a2a-dygrade-rl/` 的设计文档

**同步版本**：V1.8 方案 A Official SSH Remote 控制面已完整验收；V1.7 AutoDL 交接与 V1.6 本地准备继续有效。当前下一步为14B下载产物回传与Token/预算复核，并继承 V1.4 Quality Champion 质量保护与正式质量协议

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

- [X] T072 [US2] 修复 `src/a2a_dygrade_rl/agents/cache.py` 的失败缓存断点续跑语义：`--resume` 仅复用 `status=success` 的合法记录，对已有失败记录重新执行；成功续跑只能清除 active failure，历史失败快照必须继续保留，补充瞬时失败后 resume 成功且 failure history 不被删除的集成测试

---

## Phase 5：用户故事 3A：V1.4 内部 Paper、协议基础、正式 Agent Pilot 与 Formal Cache（优先级：P3）

**目标**：先从当前27,375条 train 主路由 Item 按 prompt/exact-answer/leakage 传递连通分量划分，再分别重建 `train_fit/train_calibration` strict Paper；实现 V1.3 质量协议和 V1.4 职责门禁，完成用户批准的真实 Agent Pilot 与 Formal cache，为后续 train_fit-only Router 训练提供可信数据。

**独立测试**：使用 fixture Item 完成 component 原子分配、两个 split 的 strict Paper 重建、内部 leakage audit、正式质量指标、per-checkpoint STOP 校准、Calibration Package，以及 Dev 的固定参考准入、Quality Champion 保护和资源 selector；验证 calibration 不训练参数、不进入 replay、不跨 checkpoint 排名。

### 用户故事 3A 的测试

- [X] T043 [P] [US3] 在 `tests/unit/test_internal_split.py` 中添加 V1.4 Item-level component 拆分测试：输入仅限当前27,375条 train 主路由 Item，以 `dataset+prompt_group` 与 exact-answer/leakage component 的传递连通分量为原子，覆盖目标80/20、确定性、group不跨 split、旧 `paper_train_*` 不作为分配单元、manifest 字段和拒绝 dev/test
- [X] T043A [P] [US3] 在 `tests/unit/test_capability_profile.py` 中添加能力画像 `train_fit` 拟合、`train_calibration` 仅自动校准支持度边界、拒绝 dev/test、无 Item 级 oracle 标签和重复运行一致性测试
- [X] T043B [P] [US3] 在 `tests/integration/test_internal_paper_rebuild.py` 中添加分别重建 `papers_train_fit.jsonl/papers_train_calibration.jsonl` 的测试，覆盖新 paper ID、固定5题、strict mix、仅引用本 split Item、Item不重复、leftover可追踪、内部 Item/Prompt/Component/Paper overlap=0，以及直接拆旧 train Paper 必须失败
- [ ] T044 [P] [US3] 在 `tests/unit/test_hidden_cache_env.py` 和 `tests/unit/test_action_mask.py` 中添加未调用 cache 隐藏、结构动作掩码、四维预算掩码、support catalog 外/缺失 active cache 动作屏蔽、无分数禁止 STOP、单意见禁止 ARBITRATE 和禁止在线补算测试
- [X] T045 [P] [US3] 在 `tests/unit/test_quality_constraints.py`、`tests/unit/test_calibration.py` 和 `tests/unit/test_checkpoint_selector.py` 中添加职责分离与质量保护测试：calibration 对每个冻结 checkpoint 只输出 STOP 边界或 failure，禁止梯度/replay/跨 checkpoint 排名/最终选择/主方法升级阈值；Dev 必须先执行全预算固定参考准入门，再只按质量指标确定唯一 Quality Champion，对其他候选执行全预算冠军保护门，最后仅在保护可行候选中按资源词典序输出唯一 checkpoint
- [X] T045A [US3] 在 `tests/integration/test_quality_constrained_smoke.py` 中添加 `item component split -> separate paper rebuild -> fixture cache -> train_fit fixture candidate checkpoint -> train_calibration reference/budget/support/STOP boundary/package -> Dev fixed-reference admission -> Quality Champion -> candidate-to-champion protection -> resource select -> freeze -> test-like one-shot` 端到端 smoke，验证 calibration 不排名、Dev 不改边界、任一参考准入失败或预算不可行均淘汰整个 Package、资源更低但质量不能证明不劣于冠军的候选被淘汰、冻结 STOP 边界实际触发验证动作、Arbitrator A2A 资源被计数、相同种子输出同一参考映射/边界/冠军/保护集合/唯一 checkpoint，并验证全部禁止行为计数和 artifact inventory 未覆盖数为0
- [X] T045C [US3] 在 `spec.md`、`plan.md`、`contracts/artifact-schemas.md`、`contracts/cli-contract.md`、`configs/experiments/fixture_smoke.yaml` 和 `tests/fixtures/quality_constrained_smoke/` 中冻结 Fixture Smoke 隔离与复用契约：专用输入/config/test/run 位置、`formal_eligible=false`、禁止写入正式 data/cache/checkpoint/论文结果、禁止在线 Agent、正式 loader fail closed、核心业务模块不得分叉、source path/正式入口探针和逐文件 artifact inventory，并完成实现前契约审核
- [X] T045D [US3] 使用 `speckit-review-code`、`speckit-review-tests`、`speckit-review-errors`、`speckit-verify-run` 和 `speckit-verify-tasks-run` 对补充后的 Fixture Smoke 测试契约与实现执行实现后审核；必须保留预算不可行、NaN/重复安全证据、失败 cache 历史、路径越界、Formal loader 误接受、STOP 边界未应用、A2A 未计数、确定性不完整和 artifact inventory 漏项等反例证据，并输出 `outputs/runs/<fixture_run_id>/reports/fixture_smoke_implementation_review.md`
- [X] T045B [P] [US3] 在 `tests/unit/test_quality_protocol_v13.py`、`tests/unit/test_qwk_readiness.py` 和 `tests/unit/test_paired_bootstrap_gate.py` 中添加 Gate Error 非法/Deferral=1、Severe >0.25、Extreme >=0.50、Unsafe Stop 分母与零 STOP=NA、Macro-NMAE、half-up `0..10` 共11档完整 labels、QWK readiness、Paper 配对5000次单侧95%零界、置信区间跨0失败及固定种子可重复测试

### 用户故事 3A 的实现

- [X] T046 [P] [US3] 在 `src/a2a_dygrade_rl/datasets/internal_split.py` 和 `scripts/04a_build_internal_split.py` 中实现 V1.4 Item-level internal split：读取当前 train `paper_manifest.csv` 引用的27,375条 Item，构造 prompt/exact-answer connected components，按固定种子和目标80/20确定性分配，优先保持component完整、三数据集覆盖与strict Paper可构造性，输出 `data/processed/internal_item_split_manifest.csv` 和实际比例/偏差
- [X] T046A [US3] 在 `src/a2a_dygrade_rl/datasets/build_internal_papers.py`、`src/a2a_dygrade_rl/datasets/audit_internal_split.py` 和 `scripts/04c_build_internal_papers.py` 中分别从两个内部 Item 池重建固定5题 strict Paper，将 `papers_train_fit.jsonl`、`papers_train_calibration.jsonl`、`internal_paper_manifest.csv` 和 `leftover_items.csv` 写入 `data/processed/`，并将 `internal_split_audit.md` 写入对应 run 的 `reports/`；拒绝跨 split 借题、重复 Item、旧 paper ID 继承、泄漏和 strict mix 违规
- [X] T047 [P] [US3] 在 `src/a2a_dygrade_rl/utils/schemas.py`、`src/a2a_dygrade_rl/utils/validation.py`、`configs/dataset.yaml`、`configs/router.yaml`、`configs/cag_cql.yaml` 和 `configs/quality_protocol.yaml` 中扩展 InternalItemSplitManifest、InternalPaperManifest、LeftoverRecord、CalibrationPackage、PolicyPackage、QualityMetricProtocol、QWKReadinessRecord、PairedBootstrapGateResult、QualityReference/Budget/QualityChampion/QualityProtection/Freeze manifests；加入目标约80/20及优先级、禁止直接拆旧Paper、calibration_no_gradient/no_replay/no_checkpoint_ranking、Dev boundary immutable、quality_champion_no_resource、candidate_to_champion_gate 和协议 hash 校验
- [X] T048 [P] [US3] 在 `src/a2a_dygrade_rl/agents/cache.py` 和 `scripts/03_run_agent_cache.py` 中实现以 `internal_item_split_manifest.csv` 为 train 侧 Formal cache split 来源、以外部 manifests 为 Dev/Test 来源；拒绝根据旧 `paper_train_*` 推断内部 split，冻结有限 `context_support_catalog.json`、范围/目录指纹，并为 Arbitrator 强制绑定仅含已暴露意见的 `context_hash`
- [X] T063C [US3] 在新建的 `src/a2a_dygrade_rl/evaluation/quality_protocol.py`、`qwk_readiness.py` 以及现有 `metrics_safety.py`、`metrics_quality.py`、`metrics_budget.py` 和 `failure_registry.py` 中实现 Gate Error 非法/Deferral=1、Severe/Extreme、Unsafe Stop 与零 STOP=NA、Macro/Micro-NMAE、half-up 固定 `0..10` 共11档完整 labels QWK、readiness、Budget Exhaustion、Deferral 和失败保留；修复当前按实际标签 union 计算 QWK 的实现
- [X] T063E [US3] 在新建的 `src/a2a_dygrade_rl/evaluation/paired_bootstrap.py` 和 `statistical_gate.py` 中实现以 Paper 为 cluster、候选/比较基准配对、5000次、单侧95%、零非劣效界、固定种子 `20260729` 的通用 Bootstrap，支持固定参考准入门与 Quality Champion 保护门，计算 Severe/Unsafe 最坏数据集差值、Macro-NMAE/QWK 差值及 UCB/LCB；任一指标未定义或置信区间跨0时输出 `quality_noninferiority_inconclusive`，并保存逐次或可重建的重采样产物
- [X] T049 [P] [US3] 在 `src/a2a_dygrade_rl/rl/quality_reference.py` 中实现预定义 reference policies（Always-Cheap、Always-Mid、Always-Strong、Fixed Full Multi-Agent Workflow）按预算档位的 train_calibration 自动选择：先要求指标/STOP/QWK readiness，再按 Worst-Dataset Severe、Worst-Dataset Unsafe Stop、Macro-NMAE、Macro-QWK、资源和 Policy ID 固定顺序选择，输出全部参考候选及 `budget_id -> reference_policy_id` 的 `quality_reference_manifest.json`；此任务只确定质量门参考，不读取或排名 Router checkpoint
- [X] T050 [P] [US3] 在 `src/a2a_dygrade_rl/rl/budget_calibration.py` 中仅使用重建后的 Formal `paper_train_calibration_*` 和固定 behavior/reference policies 统计 Paper 级四维资源分布，按预注册分位数生成 Tight/Medium/Loose 并输出含 internal manifest hash 的 `budget_calibration_manifest.json`；Pilot 分位数不得充当正式预算
- [X] T050A [P] [US3] 在 `src/a2a_dygrade_rl/agents/capability.py` 和 `scripts/04b_build_capability_profiles.py` 中实现 Formal 能力画像：只用 `train_fit` 拟合画像统计，`train_calibration` 仅按预注册程序校准 low-support/uncertainty 边界，保存输入 split、支持度、算法和指纹 manifest
- [X] T051 [P] [US3] 在 `src/a2a_dygrade_rl/router/stop_risk_head.py` 和 `src/a2a_dygrade_rl/rl/calibration.py` 中实现基于 `Gate Error > 0.25` 的 train_fit Stop-Risk 训练接口，以及对每个冻结 checkpoint 在 `paper_train_calibration_*` 上独立校准唯一 STOP 安全概率边界；禁止参数更新、replay写入、跨checkpoint排名、最终选择和主方法升级阈值，Dev不得移动边界
- [X] T052 [US3] 在 `src/a2a_dygrade_rl/rl/policy_package.py` 中实现 Calibration Package builder：每个固定 checkpoint 只打包其 STOP 边界或 calibration failure、参考映射、预算、support/quality/internal manifest hashes，输出 `calibration_package_manifest.jsonl`；schema 禁止跨 checkpoint Dev rank、`selected_final_router` 和资源冠军字段
- [X] T052A [US3] 在 `configs/agents.yaml`、`prompts/*.txt` 和 `src/a2a_dygrade_rl/utils/llm_client.py` 中准备真实 Agent provider-neutral 配置、严格 JSON 输出和请求权限；任何 SDK、权重、API 或联网调用须先获得用户批准并记录 D 盘路径与费用上限
- [X] T052A1 [P] [US3] 在 `src/a2a_dygrade_rl/agents/pricing.py`、`src/a2a_dygrade_rl/utils/validation.py` 和 `tests/unit/test_real_agent_pricing.py` 中实现上游 usage 明细、缓存读写、reasoning 不重复计费、冻结官方 Standard API 价格、模型静默替换拒绝及调用/75 USD硬门
- [X] T052A2 [P] [US3] 在 `configs/experiments/real_pilot_cliproxy_gpt56.yaml`、`configs/pricing/openai_standard_20260730.yaml` 和 `prompts/real_pilot_v1/*.txt` 中冻结 Luna/Terra/Sol 五类Agent、8种候选Arbitrator context、严格JSON、并发/重试/超时与Prompt hash
- [X] T052A3 [US3] 在 `src/a2a_dygrade_rl/agents/cache.py`、`scripts/03_run_agent_cache.py`、`src/a2a_dygrade_rl/agents/pilot.py` 和 `scripts/05_prepare_real_agent_pilot.py` 中实现20份strict Paper固定样本、5/20/100同run checkpoint/resume、细分token审计和Pilot bootstrap隔离
- [ ] T052B0 [US3] 使用 `scripts/06_probe_cliproxy_models.py` 验证CLIProxy模型目录及实际响应分别为 `gpt-5.6-luna/terra/sol`；任何静默回退、usage缺失、认证不可用或代理错误均阻塞100 Item调用并保留独立run证据
- [ ] T052B [US3] 在用户批准后从 V1.4 重建的完整 strict `paper_train_fit_*` 抽取约100个 Item（约20份5题 Paper）运行 `real_pilot_<run_id>`，审计 JSON 成功率、分数越界、Agent 互补性、Evidence/Arbitrator 增益、context catalog 规模、实际 token/cost/elapsed time/calls/exchanges，并生成是否允许进入 Formal cache 的门禁报告；Pilot 分位数不直接作为正式预算
- [ ] T052B1 [US3] 在模型身份门通过后，对同一100 Item完整生成4类基础Agent与8种候选Arbitrator context共1,200条成功记录；5/20 Item仅作协议、成本、配额和稳定性停止门，最多120次重试，总调用不超过1,320且API成本不超过75 USD
- [ ] T052B2 [US3] 在 `src/a2a_dygrade_rl/agents/pilot_analysis.py` 和对应报告脚本中按协议资格、Severe/Extreme、Macro/Micro-NMAE、可用时QWK、累计成本/延迟/calls/exchanges、分歧子集增益及可达状态Pareto关系比较8种context，输出建议但不自动冻结Formal catalog
- [ ] T052B3 [US3] 100 Item报告完成后停止并提交用户审批；本阶段明确不运行1,000 Item耐久测试、不生成Formal cache、不读取Dev/Test，是否扩大规模由用户另行决定
- [ ] T052C [US3] 在 Pilot 门禁通过且 Formal Agent/Prompt/解析/成本配置与 context support catalog 冻结后，按 V1.4 internal item manifest 生成独立 `formal_agent_cache_<run_id>` 的 train_fit/train_calibration cache，并按外部 manifest 生成 Dev cache；Test cache 推迟到最终 freeze，Pilot active cache 不得复制或晋升
- [ ] T052D [US3] 在 T052C 后仅用 Formal train_fit cache 拟合能力画像主体，仅用 Formal train_calibration rebuilt Paper/cache 冻结支持度边界、质量参考和预算，生成并审计 `agent_capability_manifest.json`、`quality_reference_manifest.json`、`budget_calibration_manifest.json`；此任务不校准 checkpoint、不选择最终 Router，拒绝 Dev/Test

**检查点**：Fixture V1.3 指标、readiness、per-checkpoint STOP 校准、Calibration Package 和 Dev-only selector smoke 通过；真实 Pilot 获得单独批准并证明 Agent 具有非平凡互补性；Formal train_fit/train_calibration/dev cache 与 internal manifests 一致；质量参考、正式预算和画像支持度边界已由 calibration 程序冻结。正式 per-checkpoint STOP 边界必须等待 Phase 6 候选 checkpoint 产生后再运行；Test 尚未参与。

---

## Phase 6：用户故事 3B：质量约束 CAG-CQL Router 与公平评价（优先级：P3）

**目标**：在隐藏 cache 的多题共享资源环境中，只用 train_fit 训练带 Stop-Risk Head 的质量约束 CAG-CQL；随后对候选 checkpoint 执行独立 calibration Package 构建，以及 Dev 的固定参考准入、Quality Champion 保护和资源选择，并与强分类、Bandit 和 knapsack baseline 公平比较。

**独立测试**：运行 `train_fit candidate checkpoints -> train_calibration STOP boundary/package -> Dev fixed-reference admission -> Quality Champion -> candidate-to-champion protection -> resource select -> report` smoke，验证训练、校准和最终选择的数据职责完全分离，并生成参考准入门、冠军保护门、QWK/STOP readiness、跨预算资源排序、唯一 Policy Package/checkpoint、消融表和失败注册表。

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
- [X] T052E [US3] 在 `src/a2a_dygrade_rl/rl/checkpoint_selector.py` 中实现 Dev-only selector：拒绝未冻结边界或缺失 manifest/hash 的 Package；先在 Tight/Medium/Loose 各档执行候选对固定参考的准入门并淘汰任一预算失败候选，再仅在候选 Router Policy Package 中完全不使用资源指标，按跨预算 Severe、Unsafe Stop、Macro-NMAE、Macro-QWK 和 Package ID 确定唯一 Quality Champion，拒绝参考、Baseline 或消融进入冠军候选；随后对其余准入候选执行每档候选对冠军的四项零边界保护门，只对全预算保护可行 Package 计算跨预算等权资源键并输出唯一 `checkpoint_selection.csv` 与 `policy_freeze_manifest.json`；禁止移动边界或人工替换冠军，相同输入重复运行必须一致
- [ ] T063 [P] [US3] 在 `src/a2a_dygrade_rl/baselines/fixed_agents.py`、`calibrated_threshold.py` 和 `static_classifier.py` 中实现 Always-Cheap、Always-Mid、Always-Strong、完整多 Agent、自动校准阈值和静态分类器 baseline；不实现 Fixed Cascade，阈值 baseline 只可在 train_calibration 按预注册算法自动校准并在 Dev 前冻结，主方法的升级动作不得复用这些阈值
- [ ] T063A [P] [US3] 在 `src/a2a_dygrade_rl/baselines/contextual_bandit.py` 和 `knapsack_router.py` 中实现 Contextual Bandit 与 Top-k/Knapsack 非 RL 强 baseline；不实现 Per-item Myopic Router 和 Greedy Marginal Utility，所有保留方法共享同一隐藏 cache 环境与预算
- [ ] T063B [US3] 在 `src/a2a_dygrade_rl/rl/evaluate_policy.py`、`scripts/07_eval_baselines.py` 和 `scripts/08_eval_ablation.py` 中编排正式职责链：对 T062 候选 checkpoint 调用 T051/T052，仅用 train_calibration 生成 STOP 边界或 failure 与 Calibration Package；再对边界冻结 Package、参考、保留 baseline 和消融在 Dev 的同 Paper/同 cache/同预算上调用正式指标、QWK/STOP readiness 与 T063E 通用 Bootstrap，其中只有候选 Router Policy Package 交给 T052E 依次完成固定参考准入、Quality Champion 确定、候选对冠军质量保护和资源选择，参考、Baseline 和消融仅生成比较报告；任何未定义或 inconclusive 结果必须判为对应门失败，并记录 calibration 无排名、Dev 无边界修改及冠军无人工替换审计
- [ ] T063D [US3] 在 `src/a2a_dygrade_rl/evaluation/report_tables.py`、`plot_cost_qwk_curve.py`、`case_study.py` 和 `scripts/09_plot_cost_qwk_curve.py` 中生成含 internal manifest、calibration boundary/failure、固定参考准入状态、Quality Champion 与选择键、候选对冠军保护状态、两类四项统计边界、QWK/STOP readiness、Stop Coverage、Deferral 和资源指标的主表、分数据集表、消融表、预算前沿、失败注册表及成功/失败 case study；只有质量保护可行方法报告资源节省

**检查点**：Smoke 能端到端生成可重算报告；T062 只输出候选 checkpoint，T051/T052 只在 calibration 固定边界并组装 Package，T052E 只在 Dev 执行参考准入、Quality Champion 保护和资源选择；主方法与分类器/Bandit/knapsack 共享 internal papers、cache、预算、quality protocol、Bootstrap 和评价脚本。若无 checkpoint 通过全部预算档位参考准入门，系统输出失败；资源更低但质量不能证明不劣于冠军的候选不得形成资源成功声明。

---

## Phase 7：Polish、Final Evaluation 与复现包

**目的**：完成文档、正式 Test 一次性评价、产物审计和论文材料。

- [ ] T064 [P] 在 `README.md` 和 `data/README.md` 中更新外部 Paper 与 V1.4 内部 Item split/重建 Paper 的区别、`train_fit/train_calibration/dev/test` 最终职责、V1.3 正式质量协议、固定参考准入、Quality Champion 保护后资源选择流程、真实数据许可和完整实验 workflow
- [ ] T065 [P] 在 `specs/001-a2a-dygrade-rl/data-model.md`、`contracts/artifact-schemas.md`、`contracts/cli-contract.md` 和 `quickstart.md` 中同步 InternalItemSplitManifest、InternalPaperManifest、LeftoverRecord、CalibrationPackage、QualityMetricProtocol、QWKReadinessRecord、PairedBootstrapGateResult、QualityChampion、QualityProtectionGateResult、单一预算条件 PolicyPackage、按预算参考映射、预算/STOP 校准、Stop-Risk Head、隐藏 cache、Dev-only selector 和 final-evaluation 门禁
- [ ] T066 [P] 在 `docs/design/report-columns.md` 中添加 internal split/paper/leftover 字段、Gate Error、Severe/Extreme、Unsafe Stop/Stop Coverage/Deferral、Macro-NMAE、固定11档 QWK/readiness、四项 UCB/LCB、per-checkpoint calibration boundary/failure、固定参考准入、Quality Champion、候选对冠军质量保护、Dev 资源排序和资源指标字段字典
- [ ] T067 在 `tests/integration/test_smoke_experiment.py` 中补充 quickstart smoke、禁止直接拆旧 train Paper、内部 split/rebuild 零泄漏、calibration no-gradient/no-ranking、Dev boundary immutable、Quality Champion no-resource/no-manual-replacement、资源更低但冠军保护失败必须淘汰、Deferral 最坏损失、零 STOP=NA、QWK undefined、CI 跨0失败、selector 重复运行一致性、测试数据拒绝训练和报告重算校验
- [ ] T068 在唯一 Package 完成 Dev freeze 后生成隔离 test cache，校验 external/internal manifests、quality protocol/reference/budget、calibration package、STOP boundary、Quality Champion、质量保护结果、cache/code hashes，执行一次性 final evaluation `final_evaluation_<run_id>`，保存 `policy_freeze_manifest.json`、`qwk_readiness.csv`、`quality_gate_bootstrap.csv` 和 Test one-shot 记录；不得根据结果返回调参
- [ ] T069 根据 `specs/001-a2a-dygrade-rl/contracts/artifact-schemas.md` 审计 internal item/paper/leftover manifests、Formal cache split、capability/reference/budget manifests、每 checkpoint calibration package、固定参考准入、Quality Champion 选择、候选对冠军保护、Dev-only resource selection、quality protocol/hash、QWK readiness、Bootstrap 重采样可重建性和 failure registry
- [ ] T070 在 `outputs/runs/<run_id>/reports/experiment_readiness.md` 中记录外部数据审计、V1.4 component split与两套Paper重建、Agent Pilot、Formal cache、quality protocol、STOP/QWK readiness、质量参考、预算/支持度/每checkpoint STOP校准、calibration无排名审计、Dev固定参考准入、Quality Champion无资源/无人工替换审计、候选对冠军质量保护、Dev-only资源选择、Test freeze 和复现门禁
- [ ] T071 运行完整测试套件，将命令、V1.3 指标/Bootstrap 固定种子重复性、V1.4 internal split/rebuild 确定性和 calibration/Dev 职责隔离结果写入 `outputs/runs/<run_id>/logs/test_run.log`，并在临时目录完成仓库结构规范校验后删除临时脚本与数据

---


## Phase 8：Dataset Semantic V2 数据整改与自托管多模态准备（优先级：P1，已完成）

**目标**：在不下载模型、不调用API、不修改原始数据的前提下，生成语义正确、无Anchor、支持本地多模态模型且通过泄漏门禁的新 prepared data。

### 规格与测试先行

- [X] T072A [US1] 更新 spec.md、plan.md、data-model.md、quickstart.md 与规格质量清单，冻结 Dataset Semantic V2 和模型无关 source asset 契约
- [X] T073 [P] [US1] 在 tests/unit/test_dataset_semantic_v2.py 中添加 ASAP-SAS DOCX/图片资源、Score1 Gold、Anchor 排除测试
- [X] T074 [P] [US1] 在 tests/unit/test_dataset_semantic_v2.py 中添加 DREsS 三维 Gold、total 重建、空作文 quarantine、CASE 排除测试
- [X] T075 [P] [US1] 在 tests/unit/test_dataset_semantic_v2.py 中添加 SAS-Bench whole-response、中英文来源对齐、manual_label/total 和隐藏 Step Gold 测试
- [X] T076 [P] [US1] 在 tests/integration/test_dataset_semantic_v2_pipeline.py 中添加 build manifest、quarantine、source asset、split leakage、Gold 白名单与 Semantic Readiness fail-closed 集成测试

### Schema、资源与 Loader

- [X] T077 [US1] 新增 DatasetLoadResult、quarantine record 和 build manifest 结构，保持旧 loader 列表接口兼容
- [X] T078 [US1] 扩展 Item Semantic V2 字段和模型可见白名单，加入 scoring_unit、scoring_mode、schema_version 与 source_assets，禁止模型专用 Token/视觉表示进入 prepared data
- [X] T079 [US1] 实现 ASAP-SAS ZIP/DOCX XML 资源目录解析、图片原字节提取、Prompt/Rubric 恢复和 Score1 Gold loader
- [X] T080 [US1] 重写 DREsS loader，使用无Anchor三维评分、三维求和 total、空作文 quarantine 并排除 DREsS_CASE
- [X] T081 [US1] 重写 SAS-Bench loader，以完整顶层回答为 Item，对齐英文文本与中文标签，使用 manual_label/total 并隔离 Step Gold

### 构建、门禁与产物

- [X] T082 [US1] 扩展 build_items 生成 resources、quarantine_manifest.csv、dataset_build_manifest.json 和 versioned Item/split 产物
- [X] T083 [US1] 加强 split 与 leakage 校验，使用完整 prompt group/source lineage 并检查跨数据集 exact prompt-answer 泄漏
- [X] T084 [US1] 扩展外部 strict Paper 构建，生成外部 leftover 清单并记录新 Paper rule/version
- [X] T085 [US1] 新增 semantic_readiness.py 与 CLI，执行数据集专用语义、图片资源、Gold 隔离、manifest、split 和 Paper fail-closed 审计
- [X] T086 [US1] 新增 configs/dataset_semantic_v2.yaml 并更新数据构建/审计 CLI 的 versioned 默认路径和运行产物说明

### 全量重建与验证

- [X] T087 [US1] 运行新增及受影响单元/集成测试，修复回归并保存测试日志
- [X] T088 [US1] 使用唯一 run_id 全量构建 data/processed/semantic_v2 Item、资源、quarantine 和 split manifest
- [X] T089 [US1] 构建外部5题 strict Paper，运行 prepared data audit 与 Semantic Readiness，阻塞任何失败
- [X] T090 [US1] 从新外部 train Paper 范围重建 train_fit/train_calibration Item split 与 strict Paper，并运行 internal audit
- [X] T091 [US1] 更新任务状态并执行 spec/plan/tasks/实现一致性复核；未下载模型、未安装依赖、未调用真实 Agent 的计数必须为0

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
T043/T043A/T043B/T044/T045/T045B/T045C（测试与契约先行）
→ T046/T046A/T047/T048
→ T063C（指标与readiness）
→ T063E（paired bootstrap gate）
→ T049/T050/T050A/T051/T052/T052E
→ T045A（隔离的fixture端到端门禁）
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

1. 先完成 T043、T043A、T043B、T044、T045、T045B、T045C 的 V1.4 测试与 Fixture 隔离契约，不修改测试以迎合实现结果；
2. 完成 T046、T046A、T047、T048、T063C、T063E，落实先拆 Item component、后分别重建 Paper、quality protocol、QWK readiness 和配对统计门；
3. 完成 T049、T050、T050A、T051、T052、T052E 的参考/预算/支持度/STOP校准/Package/Dev selector 自动化；
4. 运行 T045A 的 `item component split -> separate paper rebuild -> train_fit candidate checkpoint -> train_calibration STOP boundary/package -> Dev fixed-reference admission -> Quality Champion -> candidate-to-champion protection -> resource select -> freeze -> test-like` fixture smoke；
5. 完成 T052A 的 Pilot 候选配置、费用上限和 support catalog 草案，但不联网调用；
6. 向用户提交基于重建后 train_fit strict Paper 的真实 Agent Pilot 审批；
7. 获批后依次执行 T052B–T052D，再进入 T057–T062 Router 实现；正式 calibration 与 Dev 选择只能在 T062 候选 checkpoint 产生后由 T063B 编排。

### 验证策略

1. 每个新模块先有 unit test；
2. 禁止直接拆旧 train Paper、component跨split、跨split借题、5题/strict mix违规为阻塞性测试；
3. Gate Error 未完成赋值、Severe/Extreme 边界、零 STOP=NA、half-up 11档 labels 和 QWK readiness 为阻塞性测试；
4. Paired Bootstrap 必须验证同一 Paper 索引、5000次、固定种子、单侧边界和 CI 跨0失败；
5. calibration梯度/replay/跨checkpoint排名为0、Dev边界修改为0、Quality Champion资源字段参与次数与人工替换次数为0、Test训练读取为0，均为阻塞性职责审计；
6. 隐藏 cache、support catalog、固定参考准入门、Quality Champion 保护门和保护通过后的资源自动选择为阻塞性集成测试；
7. 所有拆分、Paper重建、自动校准、Bootstrap 和 checkpoint 选择必须可重复；
8. 所有报告行可追溯到 predictions、logs、config、external/internal manifests、calibration package、protocol hash 和统计产物；
9. 失败结果不得删除。

## 备注

- 已完成任务保持 `[X]`，本次未把任何新增或改写任务虚假标记完成。
- 原尚未实现的 Router 任务已按 V1.4 最终职责拆分：T062 只训练候选 checkpoint，T051/T052 负责 per-checkpoint calibration Package，T052E 负责 Dev-only selector。
- 任务完成数必须由脚本实时统计，不再在本段维护易漂移的手工总数；T045C 已完成实现前契约审核，T045D 仅在实现后代码/测试/错误处理/规格一致性和任务真实性审核全部完成后才可勾选。
- 真实 SDK、权重、API 和付费调用必须获得用户单独批准。
- `docs/design/研究定义与实验约束同步方案.md` V1.4 是本轮同步依据；后续若改变内部拆分顺序、四阶段职责、质量指标、Bootstrap 或 Dev 顺序，必须先回到规格/计划阶段。
- 更新 `tasks.md` 后停留在用户审阅门禁，不自动进入 `speckit-implement`。


---

## Phase 9：V1.6 自托管 Ministral 3 Pilot 本地准备 P1–P8（优先级：P1，已完成）

**目标**：在不租服务器、不下载模型、不安装新依赖、不调用真实推理服务的前提下，完成自托管 Chat Completions 执行层、多模态资产、统一 Prompt/Schema、Token/成本/attempt 账本、固定5题 checkpoint、Fake workflow 和服务器交接材料。

**独立验收**：本地 Fake workflow 对固定5题和 Cheap/Mid/Strong 生成15条 canonical 成功记录；实际序列化请求 Gold 泄漏为0；TIFF 无损转换、DREsS 三维求和、Token/价格、失败重试与 resume 均通过；全仓测试与实现后审核无未解决 CRITICAL/HIGH。

### P1：规格、配置与测试契约

- [X] T092 [US2] 更新 `specs/001-a2a-dygrade-rl/spec.md`、`plan.md`、`research.md`、`data-model.md`、`quickstart.md`、`contracts/selfhosted-chat-completions.md` 和 `checklists/requirements.md`，冻结 P1–P8 本地边界、Ministral 3 候选、Token/成本语义与5 Item门禁
- [X] T093 [P] [US2] 新增 `tests/unit/test_selfhosted_client.py`，覆盖 Chat Completions body/JSON/model/usage、可重试与终止错误、Gold隔离和attempt audit
- [X] T094 [P] [US2] 新增 `tests/unit/test_multimodal_assets.py`，覆盖prepared root边界、4个正式资产、JPEG identity、TIFF LZW到PNG、hash/MIME/尺寸和prepared只读
- [X] T095 [P] [US2] 新增 `tests/unit/test_selfhosted_costing.py`，覆盖Chat usage别名、文本/视觉Token分解、官方API等价成本、服务器分摊成本、canonical与retry overhead隔离
- [X] T096 [P] [US2] 新增 `tests/unit/test_selfhosted_checkpoint.py` 与 `tests/integration/test_selfhosted_checkpoint_workflow.py`，覆盖无Gold确定性选卷、15调用、DREsS三维、图片、resume和Fake门禁

### P2–P5：执行层实现

- [X] T097 [US2] 在 `configs/experiments/selfhosted_ministral3_checkpoint.yaml`、`selfhosted_ministral3_pilot30.yaml` 和 `configs/pricing/ministral3_official_api_equivalent_20260812.yaml` 实现自托管配置、三档模型、硬预算和价格快照
- [X] T098 [US2] 在 `prompts/selfhosted_v1/scorer.txt` 冻结 Cheap/Mid/Strong 共用无Anchor评分 Prompt，并在 `src/a2a_dygrade_rl/utils/llm_client.py` 定义含DREsS traits的统一响应Schema
- [X] T099 [US2] 在 `src/a2a_dygrade_rl/utils/multimodal.py` 实现 source asset 边界/hash/MIME/尺寸审计、JPEG透传和TIFF LZW无损PNG转换
- [X] T100 [US2] 在 `src/a2a_dygrade_rl/utils/selfhosted_client.py` 实现可注入transport的 Chat Completions 客户端、真实urllib transport、Fake transport、实际body捕获、模型/usage/JSON fail-closed校验和attempt记录
- [X] T101 [US2] 扩展 `src/a2a_dygrade_rl/agents/pricing.py`、`base_agent.py`、`cache.py` 和 `agent_registry.py`，写入文本/视觉Token、logical_call_id、canonical attempt、API等价成本、服务器成本与retry overhead，保持旧Responses Pilot兼容

### P6：固定5 Item checkpoint与门禁

- [X] T102 [US2] 在 `src/a2a_dygrade_rl/agents/selfhosted_checkpoint.py` 实现从 Semantic V2 train_fit strict Paper 无Gold确定性选择1份覆盖三数据集且含图像的5题checkpoint，并生成冻结manifest
- [X] T103 [US2] 在 `src/a2a_dygrade_rl/agents/selfhosted_validation.py` 实现15条canonical、身份、Schema、范围、DREsS三维、SAS whole-response、图片、Gold、Token、成本、attempt和resume门禁
- [X] T104 [US2] 新增 `scripts/08_prepare_selfhosted_checkpoint.py`、`09_run_selfhosted_agent_cache.py`、`10_validate_selfhosted_checkpoint.py` 和 `11_audit_selfhosted_local_readiness.py`，脚本仅编排业务模块并强制唯一run_id/fixture与real边界

### P7：本地Fake/Fixture验证

- [X] T105 [US2] 运行新增单元测试并修复问题；使用唯一run_id生成固定5题checkpoint，执行15调用Fake workflow、validator与resume，所有产物写入 `outputs/runs/<run_id>/`
- [X] T106 [US2] 复核 Semantic Readiness、运行全仓pytest和仓库结构检查，保存 `outputs/runs/selfhosted_local_readiness_20260812_001/logs/` 与 `reports/`，确认在线调用/下载/依赖安装/服务器操作计数均为0

### P8：服务器交接与实现后审核

- [X] T107 [US2] 在 `docs/design/server_handoff/` 生成模型审批、环境锁定、数据传输hash、价格/费用上限、部署命令模板、5 Item runbook和返回产物manifest；不得包含密钥、权重或实际服务器操作
- [X] T108 [US2] 执行 spec/plan/tasks 一致性分析、`verify-tasks`、`verify` 和代码/测试/错误处理审查，修复所有CRITICAL/HIGH后重跑，并将结果写入 `outputs/runs/selfhosted_local_readiness_20260812_001/reports/`
- [X] T109 [US2] 完成逐项 P1–P8 审计，更新本阶段任务为真实完成状态；只有证据证明所有要求完成且真实服务器相关计数为0时才能关闭本阶段

### 依赖顺序

```text
T092 → T093-T096 → T097-T101 → T102-T104 → T105 → T106-T107 → T108 → T109
```

### 并行机会

- T093、T094、T095、T096 可在契约冻结后并行编写测试。
- T099 与 T097/T098 可并行；T100 依赖Schema和多模态接口，T101依赖客户端metadata契约。
- T107 可在实现稳定后与T106的测试运行并行准备，但最终hash/commit字段必须在收敛后更新。
---

## Phase 10：AutoDL 服务器接管、远程 Codex 与真实 Ministral 3 Pilot（优先级：P1，当前执行）

**目标**：在不改变 Dataset Semantic V2、无 Anchor、Gold、split、Paper、Prompt、Schema 和正式质量协议的前提下，将已冻结的自托管 Pilot 安全迁移到 AutoDL 数据盘；先完成远程 Codex 接手和 14B BF16 单模型 Smoke，再按门禁决定 3B/8B、真实 5 Item 和 30 Item。评分质量和严重错分风险始终优先，任何资源下降不得补偿质量失败。

**当前状态快照（2026-08-17）**：AutoDL 服务器、远程仓库迁移、14B BF16 权重下载/完整性校验、冻结 5 Item 的 10 文件传输、远程 Codex CLI、进程级 Mihomo、双账号共享会话切换、远程 bootstrap Smoke、跨账号同一 Thread 续接 Smoke、本机 Codex 官方 SSH Connection UI 与桌面只读 Smoke 已完成；GPU 当前关闭。14B 下载产物回传、Token/预算复核、推理环境、14B 真实推理、3B/8B、真实 5 Item 和 30 Item 尚未完成。详细状态以 `docs/design/server_handoff/remote-codex-handoff.md` 为当前接手入口。

**独立验收**：远程 Codex 能在 GPU 关闭时读取并遵守 `AGENTS.md` 与交接文件，远程仓库保持干净且提交/hash 可审计；14B 服务在批准的 `max_model_len=32768` 下完成身份、结构化输出、文本/视觉 Token、图片、显存和延迟 Smoke；只有 3B/8B/14B 均通过相同契约后才能执行固定 5 Item 共 15 条 canonical 调用；5 Item validator PASS 且用户批准后才允许执行 30 Item。任何质量门失败、语义退化、身份不符、usage 缺失、OOM 或费用越界都必须 fail closed。

### S0：服务器、代码和14B权重实际完成记录

- [X] T110 [US2] 在 AutoDL 实例核验 RTX 4090D 约48GB、约20核CPU、约90GB内存和数据盘容量，并将 GPU 关闭后的低资源状态与数据盘路径记录到 `docs/design/server_handoff/remote-codex-handoff.md`
- [X] T111 [US2] 将完整 Git 仓库迁移到 `/root/autodl-tmp/a2a-dygrade/repo`，核验冻结执行提交 `44f3e5fcf825794d4516455b9c7dd3fd3c5bc796`、远程 origin 和干净工作树，并在 `docs/design/server_handoff/remote-codex-handoff.md` 保留代码冻结说明
- [X] T112 [US2] 将 `mistralai/Ministral-3-14B-Instruct-2512-BF16` revision `3cea74c1ebaf5ce5f5a2553de470e2ceab825142` 下载到 `/root/autodl-tmp/a2a-dygrade/models/ministral3/14b-bf16`，完成19/19必要文件、6/6权重分片、架构/BF16/索引和官方LFS SHA-256校验，并保存 `/root/autodl-tmp/a2a-dygrade/repo/outputs/runs/selfhosted_14b_download_20260813T082720Z/configs/model-14b-download-manifest.json`
- [ ] T112A [US2] 按 `docs/design/server_handoff/artifact-return-manifest.md` Profile A 为现有14B下载run补齐全文件artifact SHA-256和下载验证摘要，回传本地相同 `run_id` 目录并生成 `artifact-return-receipt.json`；只回传manifest、日志和报告，不回传模型权重、缓存、虚拟环境或凭据，远程/本地hash不一致时禁止14B Smoke

### S1：交接文档提交与远程Codex接管（不需要GPU）

- [X] T113 [US2] 完成交接文档与全部 server_handoff 契约核对，跨文档 analyze 为 PASS（CRITICAL/HIGH=0）、`git diff --check`、JSON/YAML解析均通过；提交 `f1d08f2e539d0498acf030128a6343886246e9eb` 已推送并 fast-forward 同步到 `/root/autodl-tmp/a2a-dygrade/repo`，本地/远程 commit、治理文件 SHA-256 和 `dirty_worktree=false` 均已核验
- [X] T113A [US2] 按 `docs/design/server_handoff/data-transfer-manifest.json` 将冻结 5 Item 所需 10 个最小文件传输到远程对应相对路径；`remote_data_transfer_20260815T044106Z` receipt 为 expected=10、received=10、hash mismatch=0、Dev/Test=0、non-checkpoint train=0，状态 PASS
- [X] T114 [US2] 经用户批准，将远程 Codex CLI、共享 `CODEX_HOME`、账号保险库和必要日志放在 `/root/autodl-tmp/a2a-dygrade/runtime/codex/`，为可选 VS Code Server 保留 `/root/autodl-tmp/a2a-dygrade/runtime/vscode/`；在直连不可用后配置仅监听 `127.0.0.1` 的 Codex 进程级 Mihomo，未将认证Token、SSH凭据或代理订阅写入仓库
- [X] T114A [US2] 配置两个独立 ChatGPT 账号保险库与单一共享 `CODEX_HOME`，实现只替换活动 `auth.json` 的显式手动切换；完成 `account-a → account-b → account-a` 验证和跨账号同一 Thread 续接 Smoke，确认凭据不同、持久会话状态不变，最终活动账号恢复为 `account-a`
- [X] T115 [US2] 使用 `run_id=remote_codex_bootstrap_20260815T050326Z` 保存远程接手 Smoke，完成治理文件读取、Git/磁盘/GPU/后台任务报告、只读 `git status` 和批准路径最小写入/撤销；该 bootstrap 的 GPU 调用数、真实模型调用数和论文实验 Token 成本均为 0
- [ ] T115A [US2] 更新 `docs/design/server_handoff/pricing-and-budget.md` 和真实 run 配置，冻结 Token 价格、canonical 调用数、最大 attempt、并发、超时、`max_model_len`、输出上限、`temperature` 与 Thinking 模式；`server_hourly_price_usd` 保持 `null`，服务器租金不进入论文指标，任一调用或 Token 硬门超限时 fail closed
- [X] T115B [US2] 已在本机 Codex 桌面端注册 `remote-ssh-discovered:autodl-a2a` 并从该 Connection 对 `/root/autodl-tmp/a2a-dygrade/repo` 完成只读 Smoke；远程会话 `01a01069-d270-7f81-9c98-c0199e79a6e6` 的 `originator=Codex Desktop`，验证 cwd/hostname、分支、`HEAD=fc61512f2786c6e9cf011e4721f339a387381443`、clean tree、`account-a`、GPU关闭、治理原则理解和锁定阶段均正确，证据写入 `official_ssh_remote_20260817T091500Z`

### S2：14B推理环境与真实Smoke（需要GPU）

- [ ] T116 [US2] 在已批准的14B Smoke范围内恢复GPU，在 `/root/autodl-tmp/a2a-dygrade/runtime/` 创建独立推理环境和缓存，安装并冻结 NVIDIA Driver/CUDA/Python/PyTorch/vLLM/Transformers/Processor版本，将配置快照和 `pip freeze` 或容器digest写入 `outputs/runs/selfhosted_14b_smoke_<timestamp>/configs/environment-lock.json`
- [ ] T117 [US2] 以 `max_model_len=32768`、BF16、`temperature=0`、非Thinking和单模型常驻启动14B服务，运行模型身份、文本请求、统一JSON Schema、分数范围、DREsS三维和usage Smoke，并把服务日志、请求/响应、Token分解、显存峰值、首Token延迟和总延迟写入 `outputs/runs/selfhosted_14b_smoke_<timestamp>/`
- [ ] T118 [US2] 使用冻结5 Item中实际引用的图像执行14B多模态Smoke，验证JPEG透传、TIFF无损PNG、source asset hash、模型可见Gold为0、文本/视觉Token分解和响应可解析性，并将失败attempt与canonical结果分别写入 `outputs/runs/selfhosted_14b_smoke_<timestamp>/logs/` 和 `predictions/`
- [ ] T119 [US2] 为 `outputs/runs/selfhosted_14b_smoke_<timestamp>/` 生成 14B Smoke 审计报告，逐项判定身份、Schema、图片、usage、视觉 Token、显存、延迟、OOM 和 Token 预算门；任一阻塞项失败时保持 3B/8B、真实 5 Item 和 30 Item 调用数为 0
- [ ] T119A [US2] 为 14B Smoke run 生成完整 artifact SHA-256 清单，将配置、服务/GPU 日志、请求/响应、usage、显存和 Smoke 报告回传本地相同 `run_id` 目录；本地验证 hash 与 Smoke 状态，不回传模型权重、缓存、虚拟环境或凭据

### S3：3B/8B下载与同契约Smoke

- [ ] T120 [US2] 仅在T119 PASS且用户批准后，为CheapAgent和MidAgent冻结3B/8B官方revision与下载manifest，将权重分别下载到 `/root/autodl-tmp/a2a-dygrade/models/ministral3/3b-bf16` 和 `/root/autodl-tmp/a2a-dygrade/models/ministral3/8b-bf16`，逐文件记录大小与SHA-256并保留至少20%数据盘余量
- [ ] T120A [US2] 分别按 Profile A 为3B和8B下载run生成完整artifact SHA-256并回传本地相同 `run_id`，本地验证revision、文件清单、下载校验与receipt；两个模型任一下载产物未回传或hash不一致时不得进入对应Smoke
- [ ] T121 [US2] 顺序加载3B和8B，复用14B完全相同的Prompt、Schema、生成参数、文本/图片Smoke和usage审计，在 `outputs/runs/selfhosted_3b_smoke_<timestamp>/` 与 `outputs/runs/selfhosted_8b_smoke_<timestamp>/` 保存环境、请求、响应、Token、显存、延迟和失败证据；禁止为某一Agent单独修改输入语义
- [ ] T121A [US2] 为 3B 和 8B Smoke run 分别生成 artifact SHA-256 清单并回传本地相同 `run_id` 目录，本地验证模型身份、配置公平性、图片/usage、显存、延迟和 Smoke PASS；两个模型任一回传或复核失败时不得进入真实 5 Item

### S4：真实5 Item Checkpoint与门禁

- [ ] T122 [US2] 在3B/8B/14B Smoke全部PASS后，按 `docs/design/server_handoff/checkpoint-runbook.md` 使用同一唯一 `run_id` 顺序执行 CheapAgent、MidAgent、StrongAgent，对冻结1份5题Paper生成15条canonical成功记录；模型切换时使用 `--agents` 与 `--resume` 只补当前Agent缺失记录，失败attempt不得重复计入canonical成本
- [ ] T123 [US2] 对真实 5 Item run 执行 `scripts/10_validate_selfhosted_checkpoint.py`，验证模型身份、15 条 canonical、三数据集、图像、Gold 隔离、DREsS 三维、SAS 完整回答、Token/价格、attempt 和 resume，并把 PASS/FAIL、API 等价 Token 成本与 retry Token overhead 写入 `outputs/runs/<run_id>/reports/`；FAIL 时 30 Item 调用数必须为 0
- [ ] T123A [US2] 将真实 5 Item 完整 run 回传本地相同 `outputs/runs/<run_id>/`，核对远程/本地 artifact manifest，并在本地重新运行 `scripts/10_validate_selfhosted_checkpoint.py`；远程和本地结果一致后才提交用户审批
- [ ] T123B [US2] 在真实 5 Item PASS 且用户批准后，确定性冻结 30 Item 输入并生成独立 `pilot30-data-transfer-manifest.json`，只传输 30 Item 所需输入、lineage、readiness 和实际引用图片；Dev/Test 与未批准全量 train 数据传输数必须为 0

### S5：30 Item Pilot与进入Formal的决策门

- [ ] T124 [US2] 只有T123 validator PASS且用户再次批准后，使用 `configs/experiments/selfhosted_ministral3_pilot30.yaml` 执行30 Item、Cheap/Mid/Strong共90条canonical调用，复用相同prepared data、Prompt、Schema、价格快照、预算、attempt和resume规则，并将全部产物写入唯一 `outputs/runs/<run_id>/`
- [ ] T125 [US2] 基于 30 Item 结果输出各数据集有效完成数、Gold bin 数、expected disagreement 和 `qwk_readiness`；不满足正式 readiness 时，正式 dataset QWK 与 `Macro-QWK` 必须为 `NA`，探索性 QWK 必须标记 `exploratory_not_formal=true` 且不得进入质量门。30 Item 主要报告 `Macro-NMAE`、MAE、Within-1、Severe/Extreme Error、非法输出率、Unsafe Stop、Agent 分歧、Best-fixed、Item Oracle headroom、API 等价 Token 成本、延迟和失败恢复，并判断三档 Agent 是否具有非平凡互补性；在报告审阅前不得执行新的 100 Item Formal Pilot、Formal cache 或 1,000 Item 耐久性验证
- [ ] T125A [US2] 将 30 Item 完整 run、输入 manifest、Agent cache、attempt 账本、Token 成本、失败记录、质量诊断和 QWK readiness 报告回传本地；生成 `artifact-return-receipt.json` 并验证全部 hash 和报告可重算性，回传完成前不得决定是否进入 Formal

### Phase 10依赖顺序

```text
已完成服务器基线：T110 → T111 → T112
已完成方案A：T113 + T113A + T114 + T114A + T115 + T115B
当前无GPU下一步：T112A（14B下载产物回传）、T115A（预算复核）
T112A + T115A → T116 → T117 → T118 → T119 → T119A
T119A PASS + 用户批准 → T120 → T120A → T121 → T121A
T121A PASS → T122 → T123 → T123A
T123A PASS + 用户批准 → T123B → T124 → T125 → T125A
```

### Phase 10并行机会

- T113、T113A和T115B已完成。T112A与T115A均不需要GPU，可以并行；T116必须等待两者PASS并获得恢复GPU批准。
- T116中环境版本记录和磁盘/显存监控脚本准备可并行；14B服务启动必须等待环境锁完成。
- T117的文本Smoke与T118的图片资产预检查可以并行准备，但真实模型调用应顺序执行并复用同一冻结服务配置。
- 3B与8B下载在磁盘、带宽和费用批准后可并行；各自Profile A回传与本地复核可并行，但T120A必须全部PASS后才能顺序加载单卡真实Smoke，避免同时常驻造成不公平资源条件。
- T124 与 T125 不可并行；30 Item 完整产物落盘后才能分析能力互补性，T125A 回传和本地复算完成后才能判断 Formal 可行性。

### Phase 10用户审阅门禁

- 本次用户指令只批准完成V1.7文档、manifest和模板并提交/推送Git远程仓库；不执行AutoDL工作树同步、数据传输、环境安装、GPU或真实模型操作。
- T110–T112 按服务器实际完成证据标记为 `[X]`；T112A、T113–T125A 保持 `[ ]`，不得把文档已写、模型已下载或 Fake PASS 误报为下载产物回传、远程 Codex、真实 Smoke、数据传输、5 Item、30 Item或产物回传完成。
- 用户已确认并要求完成文档提交与Git远程推送；T113仍保持 `[ ]`，直到其AutoDL同步、commit/hash和clean tree验收全部完成。
