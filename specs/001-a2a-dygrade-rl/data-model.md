# 数据模型：A2A-DyGrade-RL 实验流水线

## V1.7 自托管 Ministral 3 Pilot 运行契约

本节覆盖下文历史API Pilot字段。P1–P8只构造和验证这些实体，不产生真实模型预测；V1.7服务器阶段继续复用相同实体，并将服务器费用兼容字段固定为可空且不进入论文指标。

### SelfHostedProviderConfig

- `type`：固定 `openai_chat_completions_compatible`。
- `base_url`、`api_key_env`：服务器阶段注入；配置不得保存密钥。
- `usage_source`：正式必须为 `server_reported`。
- `require_reported_model_match`、`require_usage`：正式均为true。
- `timeout_seconds`、`max_attempts`、`retry_backoff_seconds`、`concurrency`。
- `max_total_calls`、`max_cost_usd`：硬门。
- `pricing_manifest_path`、`prepared_root`。

### ModelCandidate

- `agent_id`：CheapAgent、MidAgent、StrongAgent。
- `model_id`：精确Ministral 3 Instruct BF16 ID。
- `model_revision`：本地阶段为 `pending_server_freeze`，真实运行前必须替换为可审计revision。
- `prompt_path`、`prompt_version`、`prompt_hash`。
- `generation_parameters`：temperature=0、统一max tokens、non-thinking。

### PreparedAssetRecord

- `asset_id`、`relative_path`、`source_uri`。
- `source_mime_type`、`source_byte_size`、`source_sha256`。
- `source_width`、`source_height`。
- `sent_mime_type`、`sent_byte_size`、`sent_sha256`。
- `sent_width`、`sent_height`。
- `transform`：`identity`或`tiff_lzw_to_png_lossless`。
- `data_url`：仅存在于瞬时请求对象，不写入prepared data或长期审计文件。

校验：路径解析后必须位于prepared root；源size/hash/MIME全部匹配；转换后尺寸不变；正式记录不得包含原始base64正文。

### AgentResponseV2

- `pred_score`：合法总分。
- `confidence`：0–1。
- `justification`。
- `evidence`：五个固定字段。
- `trait_scores`：DREsS为 `{content, organization, language}`，其他数据集为空对象。

校验：DREsS三个维度均在0–5，`pred_score=sum(trait_scores)`；非DREsS禁止返回非空trait scores。

### SelfHostedTokenUsage

在通用TokenUsage基础上记录：

- `input_tokens`、`output_tokens`、`total_tokens`；
- `input_text_tokens`、`input_vision_tokens`（服务器提供时）；
- `cached_input_tokens`、`cache_write_tokens`、`reasoning_tokens`（提供时）。

校验：总Token必须等于输入加输出；`cached_input_tokens`、`cache_write_tokens` 与普通输入共同组成输入计价分区，不得重复计费且缓存两类之和不得超过输入总量；正式图像checkpoint若缺少视觉分解则门禁失败。

### CallAttempt

- `logical_call_id`：稳定cache key。
- `attempt_id`：`logical_call_id + attempt_number`的hash。
- `attempt_number`、`latency_seconds`。
- `status`：success、retryable_failure、terminal_failure。
- `error`：包含错误类型与消息；HTTP失败由错误文本保留状态码。
- `requested_model_id`、`reported_model_id`、`pricing_model_id`、`response_id`、`usage`。
- `official_api_equivalent_cost_usd`；
- `actual_server_allocated_cost_usd`：历史兼容字段，本实验固定为 `null`，不得进入论文成本。
- `request_body_sha256`、`transport_kind`。

`asset_audit` 与 `gold_key_findings` 位于 canonical record 的客户端 metadata；attempt账本保留每次实际传输的身份、usage、成本、延迟和错误，不持久化base64正文。

每次HTTP尝试一条，不删除失败历史。

### CanonicalAgentRecord

沿用Agent cache record，并新增：

- `logical_call_id`；
- `canonical_attempt_id`；
- `official_api_equivalent_cost_usd`；
- `actual_server_allocated_cost_usd`：可空历史兼容字段，本实验固定为 `null`；
- `asset_audit`；
- `input_text_tokens`、`input_vision_tokens`；
- `serialized_request_sha256`。

同一个logical call只能有一条active成功canonical记录；retry overhead不得累计到该字段。

### CheckpointManifest

- `run_id`、`selection_seed`、`selection_rule_version`。
- `source_files`及SHA-256。
- `paper_id`、5个`item_ids`、数据集计数、图像Item数。
- `expected_agent_ids`、`expected_canonical_calls=15`。
- `formal_eligible=false`、`gold_fields_read_for_selection=0`。
- 输出路径与文件hash。

### CheckpointValidationReport

- `status`：PASS/FAIL。
- 每项gate的名称、通过状态、detail和证据路径。
- canonical/attempt数量、失败历史、HTTP请求数、resume新增请求数。
- `unlocks_30_item_pilot`：仅全部gate通过时为true；本地Fake报告即使PASS也保持false，真实服务器checkpoint才可能解锁。

### ServerHandoffManifest

- `frozen_implementation_commit`、`workspace_handoff_commit`、`dirty_worktree_required`；前者冻结执行代码，后者记录已审核并推送的交接内容提交。由于commit不能自引用，单纯写入该指针的metadata-only提交可以晚于该commit。
- 模型、许可证、revision冻结要求。
- 环境/GPU/磁盘路径和禁止C盘规则。
- data transfer文件、大小、SHA-256。
- Token价格、canonical/attempt/并发/超时/上下文/输出等调用上限；服务器租金不进入论文协议。
- deployment/checkpoint命令模板。
- 返回产物路径。
- `secrets_included=false`、`weights_included=false`；P1–P8历史准备另记录 `server_actions_executed=0`，V1.7服务器执行状态使用分阶段manifest。


## Dataset Semantic V2 数据契约

本节覆盖下文仍保留的历史 `Item` 说明。自托管模型只改变后续 Agent cache 阶段，不改变本节的 Gold、评分单位、split、Paper 或 quarantine 定义。

### Semantic V2 Item

在原有字段上新增并冻结：

- `schema_version`：固定为 `item_semantic_v2`。
- `scoring_unit`：当前三个数据集均为 `whole_response`，SAS-Bench 不再按 Step 拆成 Item。
- `scoring_mode`：ASAP-SAS 为 `holistic`，DREsS 为 `analytic_three_dimension`，SAS-Bench 为 `holistic_total_score`。
- `source_assets`：模型无关的原始多模态资产列表；每项必须包含 `asset_id`、prepared root 相对路径 `relative_path`、`sha256`、`mime_type` 和 `source_uri`。
- `metadata.formal_eligible`：正式数据必须为显式 `true`。
- `metadata.source_lineage_id`：用于 split 与审计的来源谱系标识。

prepared data 严禁写入 `input_ids`、`pixel_values`、视觉 Token、embedding、Tokenizer/Processor 名称或其他模型专用表示。图片缩放、视觉 Processor 与 Token 统计只允许在后续 Agent cache 运行目录中产生。

### 三个数据集的 Gold 契约

- ASAP-SAS：恢复 `Data_Set_Descriptions.zip` 中10个 EssaySet 的正式 Prompt/Rubric；`gold_score=Score1`，`Score2` 仅留在隐藏 metadata 作一致性审计；`Training_Materials.zip` Anchor 不读取、不进入模型请求。
- DREsS：只读取 `DREsS_Std.tsv` 与 `DREsS_New.tsv`；`gold_score=Content+Organization+Language`，三维各为0到5，总分0到15；raw `total` 只作审计；空作文 quarantine；`DREsS_CASE_*` 读取数必须为0。
- SAS-Bench：英文文件提供模型可见文本，中文同名文件提供权威数字标签；一个顶层完整回答对应一个 Item；`gold_score=manual_label`、`score_max=total`；Step label/error 仅留在隐藏 metadata。

### QuarantineRecord

字段：`dataset`、`source_file`、`source_record_id`、`reason`、`detail`、`transform_version`。任何空作文、来源无法对齐、非法分数、空 Step 带非零分或人工总分与 Step 分数和冲突的记录都不得静默丢弃，必须进入 `quarantine_manifest.csv`。

### SourceAsset 与 ResourceCatalog

ASAP-SAS DOCX 中的 JPEG/TIFF 保留原始字节，不在数据阶段转换。`resources/asap_sas/resource_catalog.json` 记录 EssaySet、DOCX 指纹、Prompt、Rubric 和资产列表；`resource_manifest.json` 汇总全部资产。资产路径必须位于 prepared root 内，文件 SHA-256 必须与 catalog 和 Item 引用一致。

### DatasetBuildManifest

`dataset_build_manifest.json` 至少记录：唯一 `run_id`、配置哈希、raw source 哈希、各数据集 accepted/quarantine/resource 数量、split 数量、输出产物哈希和安全计数。以下计数在数据整改运行中必须全部为0：在线 Agent 调用、模型下载、依赖安装、raw 数据写入、Anchor 读取和模型专用预处理记录。

### SemanticReadinessManifest

`semantic_readiness_manifest.json` 是后续本地模型 checkpoint 的 fail-closed 门禁。只有 Item 语义、Gold 来源、图片资产、模型可见 Gold 隔离、全局 split 防泄漏、strict Paper、leftover 对账、quarantine 和所有产物哈希均通过，状态才允许为 `PASS`。

### Split 与 Paper

外部 split 的原子单元是由以下关系形成的全局连通分量：同数据集 prompt group、相同完整 prompt、跨数据集 exact prompt-answer、source lineage 和既有 leakage component。每个 Item 必须完整进入一个 split。

外部及内部 Paper 均固定5题，并匹配批准的 strict quota。未进入外部 Paper 的 Item 必须写入 `external_leftover_items.csv`；内部未使用 Item 必须写入 `leftover_items.csv`。同一 Item 不得同时进入 Paper 与 leftover，也不得跨 split 借用。
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
