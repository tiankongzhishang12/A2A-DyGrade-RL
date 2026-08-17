# 远程 Codex 接手说明

> **用途**：本文件是远程 Codex 首次连接 AutoDL 服务器后的单一接手入口，负责说明当前研究目标、服务器状态、已完成内容、立即任务、实验门禁和禁止事项。
>
> **状态快照日期**：2026-08-17（Asia/Shanghai）
>
> **优先级**：项目长期规则以仓库根目录 `AGENTS.md` 为最高事实来源；研究需求以 `specs/001-a2a-dygrade-rl/spec.md` 为准；本文件只负责当前远程执行状态。若本文件与旧服务器交接摘要中的阶段状态冲突，以时间戳更新且经过 Git 审核的文件为准，但任何文件都不得覆盖 `AGENTS.md` 的硬规则。

## 1. 首次接手时的强制阅读顺序

远程 Codex 在修改文件、安装依赖、联网下载、启动服务或产生费用之前，必须依次阅读：

1. `AGENTS.md`
2. `docs/design/server_handoff/remote-codex-handoff.md`
3. `specs/001-a2a-dygrade-rl/spec.md`
4. `specs/001-a2a-dygrade-rl/plan.md`
5. `specs/001-a2a-dygrade-rl/tasks.md`
6. `docs/design/server_handoff/environment-lock.md`
7. `docs/design/server_handoff/model-approval-manifest.yaml`
8. `docs/design/server_handoff/pricing-and-budget.md`
9. `docs/design/server_handoff/checkpoint-runbook.md`
10. `docs/design/server_handoff/artifact-return-manifest.md`

阅读完成后，先汇报以下内容，暂时不要执行修改或安装：

- 当前 Git 分支、`HEAD`、远程跟踪分支和工作树状态；
- 当前主机名、项目路径、数据盘空间和 GPU 状态；
- 对“质量优先、资源不可补偿质量失败”的理解；
- 当前已经完成和仍未完成的阶段；
- 准备执行的下一步、是否联网、是否安装依赖、是否需要 GPU、是否产生费用；
- 计划使用的唯一 `run_id` 和产物目录。

## 2. 论文研究目标

本项目研究**面向模拟试卷级自动阅卷的质量约束多智能体动态路由方法**。一份评分 episode 由固定 5 个 Item 组成；Router 在共享预算下联合决定下一道 Item、评分 Agent、证据核验、独立二评、仲裁和安全停止动作。

评分 Agent 的模型、Prompt、生成参数、输出 Schema、解析规则和成本定义在正式 cache 前冻结。本文不训练或微调评分 Agent；研究对象是：

> 在评分 Agent 固定、未调用 Agent 输出不可提前观察、多道 Item 共享资源的条件下，A2A-DyGrade-RL 能否在评分质量和严重错分风险不下降的前提下，减少完成可靠评分所需的资源。

本文不以生产级 Web 服务、教师端、学生端、权限系统或在线阅卷平台为第一阶段目标。

## 3. 最高实验原则：评分质量优先

评分质量和严重错分风险是第一评价层；成本、累计延迟、Agent Calls 和 A2A Exchanges 是第二评价层。二者不是可自由加权交换的目标。

正式候选必须按以下顺序选择：

```text
固定参考策略零容忍配对统计准入门
→ 仅按质量确定唯一 Quality Champion
→ 候选相对 Quality Champion 的零容忍质量保护门
→ 仅在质量可行候选之间比较资源
```

质量保护至少覆盖：

- `Severe Error` 不增加；
- `Unsafe Stop` 不增加；
- `Macro-NMAE` 不恶化；
- `Macro-QWK` 不下降；
- 正式指标必须满足 readiness 和预注册的配对统计要求。

任何候选只要不能证明质量不劣于对应基准，就必须在资源排序前淘汰。以下结果均不得作为有效研究成果：

- 通过少调用 StrongAgent 换取评分质量下降；
- 通过提前 STOP 换取严重错分或 Unsafe Stop 增加；
- 通过更低 Token、延迟或调用数补偿质量门失败；
- 只报告更低成本而隐藏 Macro-QWK、Macro-NMAE 或严重错分恶化；
- 把质量下降的点作为 Cost-QWK Pareto 改进。

基础评分 Agent 的绝对指标可以低于生产部署水平，但数据语义、Rubric、Gold 和模型输出必须有效且非退化。A2A-DyGrade-RL 若要声明资源收益，必须先证明相对质量没有下降。

## 4. 公平比较和数据边界

所有 baseline、消融版本和 A2A-DyGrade-RL 必须共享：

- 相同 prepared data；
- 相同 Paper 和预算档位；
- 相同冻结 Agent cache；
- 相同 Prompt、解析和失败处理；
- 相同质量协议、Bootstrap 和评价脚本。

必须严格防止 Item、Prompt、Paper、统计信息和 cache 跨 split 泄漏。`test` 只能用于最终一次性评价，不得用于 Prompt 调试、Agent 能力画像、Router 训练、阈值校准、超参数选择或 checkpoint 选择。

当前数据主线为 Dataset Semantic V2：

- DREsS：无 Anchor 的 `Content`、`Organization`、`Language` 三维评分；
- ASAP-SAS：必须使用恢复后的官方 Prompt、Rubric 和 Training Materials，最终 Gold 使用冻结定义；
- SAS-Bench：使用完整学生回答 Item，不把单个 Step 当作完整作答；
- 语义占位、缺失 Rubric、错误评分单位、常数输出或近随机退化环境不得进入正式实验；
- `semantic_readiness_manifest.json.status` 必须为 `PASS` 且正式资格成立后，才能进入真实 Agent Pilot 或 Formal cache。

## 5. 当前 Git 和代码冻结状态

### Commit双重语义

```text
frozen_implementation_commit: 44f3e5fcf825794d4516455b9c7dd3fd3c5bc796
last_verified_remote_commit: 7422cdbaa04e8fb0310ad926dd1f823c7a1d6bb2
workspace_handoff_commit: 7422cdbaa04e8fb0310ad926dd1f823c7a1d6bb2
```

- `frozen_implementation_commit`证明自托管Pilot执行代码、配置、Prompt和测试的冻结基线。
- `last_verified_remote_commit`是 2026-08-17 方案 A 后端验收时本地、Git 远程和 AutoDL 工作树共同核验的提交。
- `workspace_handoff_commit`记录已经审核并推送到Git远程仓库的交接内容冻结提交。由于提交无法自引用，后续只更新该指针、任务状态或验收摘要的 metadata-only 提交可以晚于该commit；不得借 metadata 提交静默改变执行代码、配置、Prompt或测试。
- 文档提交可以位于冻结实现之后，但必须核对 `src/`、`scripts/`、`configs/`、`prompts/` 和 `tests/` 未出现未批准变化。

### 仓库路径

```text
本地：D:/A2A-DyGrade-RL
本地分支：codex/selfhosted-ministral3-pilot
远程：/root/autodl-tmp/a2a-dygrade/repo
```

禁止在工作树不干净、commit 未记录或来源不明时执行真实实验。不得使用强制 reset、递归删除或覆盖未审计产物来“恢复干净状态”。

## 6. 远程服务器状态快照

截至 2026-08-17，已知状态如下：

```text
远程项目：/root/autodl-tmp/a2a-dygrade/repo
数据盘根：/root/autodl-tmp/a2a-dygrade
Git分支：codex/selfhosted-ministral3-pilot
最近核验HEAD：7422cdbaa04e8fb0310ad926dd1f823c7a1d6bb2
工作树：干净
GPU：当前关闭；nvidia-smi 返回 No devices found
低资源保留状态：约 0.5 CPU / 2 GB RAM / 无 GPU
GPU实例启动后：RTX 4090D 约 48 GB / 约 20 CPU / 约 90 GB RAM
数据盘：最近核验约已用 27 GB、剩余 264 GB；执行前必须重新检查
当前后台任务：无模型下载、校验、推理或残留 Codex App Server 进程；Mihomo 仅作为远程 Codex 网络辅助运行
```

低资源保留状态可以用于 SSH、文档整理、轻量 Git 操作和远程 Codex 基础配置，但不用于 vLLM、模型加载、大规模测试或并行数据处理。Codex 远程控制本身不需要 GPU；只有本地模型加载和推理需要恢复 GPU。

### 最小数据传输状态

```yaml
five_item_data_transfer:
  run_id: remote_data_transfer_20260815T044106Z
  status: PASS
  expected_files: 10
  received_files: 10
  hash_mismatch_count: 0
  dev_test_file_count: 0
  non_checkpoint_train_file_count: 0
  prepared_root: /root/autodl-tmp/a2a-dygrade/repo/data/processed/semantic_v2
```

Git同步不会携带被 `.gitignore` 排除的 Semantic V2 和 checkpoint 输入，因此这 10 个文件已经按 `data-transfer-manifest.json` 单独传输并完成接收 receipt。数据传输门已通过，但图片 Smoke 和真实 5 Item 仍受模型 Smoke、环境、预算和用户批准等后续门禁约束。

### 方案 A：官方 SSH Remote 控制面状态

```text
主入口：本机 Codex 桌面端 → 官方 SSH Remote → AutoDL Codex App Server
SSH Host别名：autodl-a2a
远程项目：/root/autodl-tmp/a2a-dygrade/repo
远程Codex CLI：0.147.0
共享CODEX_HOME：/root/autodl-tmp/a2a-dygrade/runtime/codex/home
账号配置：account-a、account-b；最终活动账号 account-a
Mihomo：127.0.0.1:7890，allow-lan=false，仅注入Codex子进程
后端状态：PASS
桌面Connection UI：PENDING_USER_UI
桌面只读Smoke：PENDING_USER_UI
```

远程后端验收 run 为：

```text
outputs/runs/official_ssh_remote_20260817T091500Z/
```

已验证专用 SSH key 免密连接、新登录 Shell 的 Codex PATH、ChatGPT 登录、Mihomo 连通性、App Server、干净 Git 工作树、GPU 关闭、两个账号凭据不同以及共享会话状态不变。账号 B 已通过 `codex exec resume` 续接账号 A 创建的同一 Thread，并复述相同标记。该 Smoke 使用 2 次远程 Codex 操作性模型调用，但论文实验模型调用、论文 Token 成本与 GPU 调用均为 0。

账号切换只能由用户显式执行：

```bash
codex-account list
codex-account status
codex-account switch account-a
codex-account switch account-b
codex-account verify
```

禁止自动额度检测、自动轮询账号或自动重发。两个账号共享会话数据库，但只共享历史与配置，不共享认证文件；`auth.json` 和账号保险库权限必须保持 `600/700`。

## 7. 模型状态

候选 Agent 家族固定为 Ministral 3 Instruct BF16：

| Agent | 模型 | 当前状态 |
|---|---|---|
| CheapAgent | `mistralai/Ministral-3-3B-Instruct-2512-BF16` | 未下载，revision 待冻结 |
| MidAgent | `mistralai/Ministral-3-8B-Instruct-2512-BF16` | 未下载，revision 待冻结 |
| StrongAgent | `mistralai/Ministral-3-14B-Instruct-2512-BF16` | 已下载并完成完整性检查，尚未执行真实推理 Smoke |

14B 当前冻结信息：

```text
模型目录：/root/autodl-tmp/a2a-dygrade/models/ministral3/14b-bf16
模型revision：3cea74c1ebaf5ce5f5a2553de470e2ceab825142
权重分片：6 / 6
必要文件：19 / 19
目录大小：约 26.007 GiB
精度：BF16
官方 LFS SHA-256：全部通过
重复 consolidated.safetensors：未下载
```

远程下载与校验 manifest：

```text
/root/autodl-tmp/a2a-dygrade/repo/outputs/runs/selfhosted_14b_download_20260813T082720Z/configs/model-14b-download-manifest.json
```

该下载run尚未按 `artifact-return-manifest.md` Profile A回传本地；T112A必须在14B Smoke前生成全文件hash、下载验证摘要和本地receipt。模型权重本身不得回传。

当前批准的推理上下文上限为：

```text
official_context_tokens: 262144
approved_runtime_max_model_len: 32768
```

首轮 Smoke 和 Pilot 不得擅自把 `max_model_len` 提高到官方上限。3B、8B 只有在14B Smoke远程PASS、产物回传本地复核PASS且用户再次批准后才能下载。

## 8. 已完成内容

- Dataset Semantic V2 数据整改主线已经实现并合并；
- Semantic Readiness、Gold 隔离和 split leakage 门禁已进入正式流水线；
- 无 Anchor 主实验协议已经冻结；
- Cheap/Mid/Strong 自托管请求、统一 Prompt、响应 Schema、Token、成本、attempt 和 resume 契约已经实现；
- 固定 5 Item Checkpoint 输入已经构建；
- Fake Chat Completions 端到端 workflow 已通过；Fake validator PASS 只证明工程契约成立，不代表真实模型质量通过；
- 服务器项目已搬迁到数据盘，Git 分支、HEAD 和干净工作树已核验；
- 14B BF16模型已下载并完成文件、权重索引、架构、精度和SHA-256检查；
- 冻结 5 Item 所需 10 个最小文件已传输，receipt 为 10/10、hash mismatch 0、Dev/Test 0；
- 远程 Codex CLI、共享 `CODEX_HOME`、两个账号保险库、手动切换器和进程级 Mihomo 已配置；
- 远程 bootstrap Smoke、App Server Smoke 与跨账号同一 Thread 续接 Smoke 已通过；
- GPU保持关闭，当前没有执行真实14B推理、真实5 Item或30 Item。

权威本地准备 run 包括：

```text
outputs/runs/real_pilot_selfhosted_checkpoint_prepare_20260812_002/
outputs/runs/fixture_smoke_selfhosted_ministral3_20260812_007/
outputs/runs/selfhosted_local_readiness_20260812_001/
```

## 9. 当前尚未完成内容

- 本机 Codex 桌面端尚未在 `Settings → Connections → SSH` 注册 `autodl-a2a`，官方 SSH Remote 的 UI 只读 Smoke 仍需用户完成；
- 现有14B下载run尚未执行T112A Profile A回传和本地hash复核；
- Token价格与真实调用预算尚未完成 T115A 冻结；
- 远程推理虚拟环境及 vLLM/依赖尚未形成最终环境锁；
- 14B BF16 尚未启动服务；
- 14B 文本身份、结构化输出、usage 和延迟 Smoke 尚未执行；
- 14B 多模态输入、视觉 Token 和图像处理 Smoke 尚未执行；
- GPU峰值显存、首Token延迟、总延迟和失败恢复尚未记录；
- 3B、8B尚未下载或验证；
- 三档Agent真实互补性尚未得到实验确认；
- 真实5 Item Checkpoint尚未执行；
- 30 Item Pilot与Formal cache仍锁定；
- Router正式训练、Dev选择和Test一次性评价均未开始。

## 10. 当前立即目标和执行顺序

当前立即目标按任务门禁顺序执行：

### 阶段 A：完成本机 Codex 官方 SSH Remote UI Smoke（不需要GPU）

1. 在本机 Codex 桌面端打开 `Settings → Connections → SSH → Add`；
2. 添加已有 SSH Host 别名 `autodl-a2a`，远程目录选择 `/root/autodl-tmp/a2a-dygrade/repo`；
3. 从该 Connection 新建远程任务，只执行 `pwd`、`hostname`、Git branch/HEAD/status、读取 `AGENTS.md` 和本文件、确认 GPU 关闭；
4. 将结果补入 `official_ssh_remote_20260817T091500Z`，把两个 `PENDING_USER_UI` 检查改为 PASS；
5. 不安装依赖、不打开 GPU、不启动模型服务、不进行论文实验调用。

### 阶段 B：完成下载产物回传与预算冻结（不需要GPU）

1. T112A将现有14B下载run按Profile A回传本地并完成hash复核，不回传模型权重；
2. T115A冻结 Token 价格、canonical 调用数、attempt、并发、超时、上下文和输出上限；
3. `server_hourly_price_usd=null`，服务器租金不进入论文指标；
4. 复核 10 文件 receipt、远程 Git clean tree 和全部前置 gate 后，才允许申请恢复 GPU。

### 日常使用、历史和改动查看

- 从本机 Codex 桌面端官方 SSH Connection 创建的任务，其历史记录显示在本机 Codex 任务侧栏；任务的 Shell、文件读取和修改实际发生在 AutoDL。
- 远程 CLI 会话保存在共享 `CODEX_HOME`，可通过 `codex resume` 或 `codex exec resume <thread_id>` 续接；切换账号不会删除该历史。
- VS Code Remote-SSH 只用于浏览远程文件、Git diff、终端、测试和日志，不是远程 Codex 会话历史的唯一入口；Codex IDE Extension 不作为方案 A 的前置门禁。
- 查看代码改动时，以远程仓库中的 `git status`、`git diff`、`git log` 和 `outputs/runs/<run_id>/` 为准。

建议运行时目录：

```text
/root/autodl-tmp/a2a-dygrade/runtime/codex/
/root/autodl-tmp/a2a-dygrade/runtime/vscode/
/root/autodl-tmp/a2a-dygrade/runtime/mihomo/
```

### 阶段 C：Token预算与14B真实Smoke（需要GPU）

1. T115A冻结Token价格、调用数、attempt、并发、超时、上下文和输出上限；
2. `server_hourly_price_usd=null`，服务器租金不进入论文指标；
3. 恢复GPU并核验RTX 4090D、Driver、CUDA、CPU和RAM；
4. 在数据盘创建独立环境并冻结PyTorch、vLLM、Transformers和Processor版本；
5. 以 `max_model_len=32768` 加载14B BF16，执行身份、文本、结构化输出、usage与图片Smoke；
6. 保存Token/视觉Token、显存、延迟、错误和环境锁；
7. 生成artifact hash，回传本地相同run_id并复核；
8. 任一远程或本地门禁失败时停止，不进入3B/8B和真实5 Item。

## 11. 5 Item、30 Item与Formal的硬门禁

| 阶段 | 当前状态 | 解锁条件 |
|---|---|---|
| Semantic Readiness | PASS | 已完成 |
| V1.7文档提交与远程同步 | BASELINE_PASS / UPDATE_PENDING | 三方同步基线为 `7422cdbaa04e8fb0310ad926dd1f823c7a1d6bb2`；本次状态文档仍需提交、推送和同步后才能关闭T113 |
| 5 Item最小数据传输 | PASS | `remote_data_transfer_20260815T044106Z` receipt：10/10、hash mismatch=0、Dev/Test=0 |
| 远程Codex后端 | PASS | CLI、共享会话双账号、Mihomo、App Server和bootstrap均通过；论文实验调用/成本与GPU调用为0 |
| 本机Codex官方SSH Remote UI | PENDING_USER_UI | 注册 `autodl-a2a` 并从桌面 Connection 完成只读 Smoke |
| 14B下载与完整性校验 | 远程PASS / 回传LOCKED | T112已完成远程校验；T112A Profile A回传和本地复核通过后闭环 |
| 14B真实推理Smoke | LOCKED / 未执行 | Token预算、环境、身份、usage、图片、显存和延迟通过并回传本地复核 |
| 3B/8B下载与Smoke | LOCKED | 14B远程/本地Smoke通过且用户批准 |
| 真实5 Item Checkpoint | LOCKED | 三档模型远程/本地Smoke、环境锁、数据hash和Token预算门全部通过 |
| 30 Item Pilot | LOCKED | 真实5 Item远程/本地validator PASS、用户批准且30 Item专用传输manifest PASS |
| Formal Agent Cache | LOCKED | Pilot证明语义、稳定性和互补性，全部产物回传本地可重算 |
| Router正式训练 | LOCKED | Formal train_fit cache与全部前置门禁通过 |
| Test最终评价 | LOCKED | Dev完成唯一Package选择并完全freeze |

任何 Agent 不得把 Fake checkpoint PASS、模型文件校验 PASS 或单模型 Smoke PASS 解释为30 Item或Formal已经解锁。

## 12. Token和成本记账

### 论文主成本：Official API-Equivalent Token Cost

```text
input_tokens / 1,000,000 × official_input_price
+
output_tokens / 1,000,000 × official_output_price
```

缓存命中、缓存未命中、文本和视觉 Token 必须按冻结配置与服务器返回的 usage 字段记录。官方未单列的缓存价格只能按已经冻结的保守代理规则计算，不得临时编造新价格。

### 不属于论文实验成本

AutoDL服务器租金、GPU空闲、模型下载、模型加载、环境安装、远程Codex和人工等待均不进入Router、Baseline、Cost-QWK、Pareto Frontier或论文结果表格。真实配置固定 `server_hourly_price_usd=null`；代码中的服务器成本兼容字段保持 `null`，不得作为必填字段。

### Canonical与重试

- 每个成功的 `Item × Agent` 只有一个 canonical 成本；
- 网络失败、解析失败和服务失败的 attempt 保留在 `logs/call_attempts.jsonl`；
- 失败 attempt 的额外消耗进入 `operational_retry_overhead`；
- `--resume` 只补缺失的 canonical 记录；
- 不得因为重新执行而重复累计已经成功 Item 的论文主成本。

## 13. 运行产物规则

每次真实或 Smoke 运行必须使用唯一 `run_id`，并将配置、日志、预测、checkpoint、报告和图放入同一个目录：

```text
/root/autodl-tmp/a2a-dygrade/repo/outputs/runs/<run_id>/
├── configs/
├── logs/
├── predictions/
├── checkpoints/
├── reports/
└── figures/
```

任何关键结论必须能够追溯到：

- Git commit和工作树状态；
- 模型ID、revision和文件hash；
- 环境版本或容器digest；
- 输入manifest、split和随机种子；
- Prompt和Schema版本；
- 原始usage、attempt与canonical记录；
- validator和报告重算结果。

禁止把实验日志、预测、checkpoint、模型权重或数据文件直接放在仓库根目录。

远程run完成后必须按 `artifact-return-manifest.md` 生成全文件SHA-256，回传本地相同 `run_id` 并本地复核。Download、Per-Model Smoke、Real 5 Item和30 Item使用不同Profile；模型权重、缓存、虚拟环境和凭据不得回传。远程完成但未回传、hash不一致或本地validator不一致时，任务不得标记完成。

## 14. 安全和敏感信息

本文件、仓库和run产物中不得出现：

- SSH密码或私钥；
- ChatGPT/Codex访问Token；
- `auth.json`内容；
- API Key；
- Mihomo/Clash订阅URL、代理密码或节点凭据；
- 任何可复用的登录Cookie或OAuth凭据。

远程 Codex 若使用认证缓存，必须保存在仓库外的数据盘私密目录，并限制文件权限。Mihomo如确有必要，应优先使用进程级代理，只监听 `127.0.0.1`，不得对公网开放端口，不得在正式推理进程中静默设置全局代理。

此前任何已经在聊天或终端中暴露的服务器密码都应视为需要轮换，不得复制到本文件。

## 15. 禁止操作

未经相应门禁和用户批准，远程 Codex 不得：

- 绕过 `AGENTS.md`、Semantic Readiness或split leakage检查；
- 使用test数据训练、调参、画像、校准或选择checkpoint；
- 为降低成本而接受评分质量下降；
- 修改Gold、Rubric、Prompt或评价协议以迎合已有结果；
- 下载3B、8B或其他新模型；
- 擅自提高`max_model_len`或同时常驻三模型；
- 擅自执行真实5 Item、30 Item或Formal cache；
- 把失败attempt重复记入canonical成本；
- 在未核验绝对路径时执行递归删除、移动或覆盖；
- 强制清理未知Git改动；
- 将密钥、密码、代理订阅或Token写入仓库；
- 把依赖、模型、缓存或运行产物放在服务器系统盘；
- 把Fixture产物用于正式论文结论。

## 16. 远程 Codex 首次启动提示词

首次连接后，用户可以直接发送：

```text
你正在接手A2A-DyGrade-RL远程服务器实验。

请先依次阅读：
1. AGENTS.md
2. docs/design/server_handoff/remote-codex-handoff.md
3. specs/001-a2a-dygrade-rl/spec.md
4. specs/001-a2a-dygrade-rl/tasks.md
5. docs/design/server_handoff/environment-lock.md
6. docs/design/server_handoff/checkpoint-runbook.md

然后只汇报：
- 当前Git分支、HEAD和工作树状态；
- 当前服务器、磁盘和GPU状态；
- 当前研究目标与“质量优先、资源不可补偿质量失败”原则；
- 已完成、未完成和当前被锁定的阶段；
- 你建议的下一步及其是否需要联网、安装依赖或打开GPU；服务器租金不属于论文实验成本。
- 冻结5 Item的10个最小数据文件是否已传输并通过远程hash receipt。
- 最近一个远程run是否已经回传本地并通过本地复核。

暂时不要修改文件、安装依赖、下载模型、启动服务或运行实验。
```

## 17. 接手成功判定

远程 Codex 只有同时满足以下条件，才算接手成功：

- 能正确复述质量优先的两层选择规则；
- 能区分绝对Agent能力较低与允许Router牺牲质量之间的差异；
- 能识别14B已下载但尚未完成真实推理Smoke；
- 能识别3B、8B、真实5 Item、30 Item和Formal仍被锁定；
- 能确认Codex远程配置阶段不需要GPU；
- 能确认10个最小数据文件的receipt状态和统一prepared root；
- 能区分远程 Codex CLI bootstrap、官方 SSH Remote、VS Code Remote-SSH 和 Codex IDE Extension 四个不同入口/状态；
- 能说明两个账号共享会话数据库但认证文件独立，且切换只能由用户显式触发；
- 能区分远程run完成与产物回传、本地复核完成；
- 不把服务器租金加入论文实验成本；
- 能报告Git、磁盘、GPU和后台进程的真实状态；
- 不读取或输出任何敏感凭据；
- 不在未经批准时执行安装、下载、推理或产生费用的操作。
