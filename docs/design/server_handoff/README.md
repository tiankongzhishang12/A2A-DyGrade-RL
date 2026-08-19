# 自托管 Ministral 3 Pilot 服务器交接包

> **当前入口**：远程服务器、模型、GPU、任务与审批状态以 `remote-codex-handoff.md` 为准。原P8“未租服务器、未下载模型”描述只属于2026-08-13之前的本地准备历史边界。

## 当前状态（2026-08-19）

- AutoDL已克隆到新实例 `autodl-container-74204da04f-3f9e1fa7`；本机SSH别名继续使用 `autodl-a2a`，密钥认证、Git和数据盘迁移核验均通过。
- 新数据盘为200GB，已用约27GB、剩余约174GB；项目路径继续保持 `/root/autodl-tmp/a2a-dygrade`，无需修改实验路径配置。
- 14B BF16模型19/19个冻结文件已按原下载manifest重新计算SHA-256并全部匹配；三份关键历史run和五份治理文档的共享文件hash均一致。
- 冻结5 Item的10个最小文件已传输并通过hash receipt；Dev/Test和非checkpoint train传输数均为0。
- 远程Codex CLI、共享`CODEX_HOME`、两个ChatGPT账号手动切换、进程级Mihomo、App Server和跨账号同一Thread续接能力均保留；账号保险库与认证文件权限仍为700/600。
- 原本机Codex官方SSH Connection UI和只读Smoke证据继续作为方案A历史验收；克隆后Desktop只读重连也已通过，确认hostname、项目路径、分支、HEAD和clean tree均指向新实例。
- 14B下载Profile A已完成：19/19模型文件和17/17 payload文件hash均PASS；本地receipt状态PASS，hash/size/overlap/敏感/禁回传异常均为0，模型权重未回传。T115A价格与调用预算已冻结并通过预检；阶段B完成。GPU当前关闭，新实例GPU/Driver/CUDA须在T116恢复GPU后重新核验。
- 3B/8B、真实5 Item、30 Item和Formal均未解锁。
- 评分质量优先，资源不可补偿质量失败；论文主成本只使用Official API-Equivalent Token Cost，服务器租金不进入实验指标。

## 当前执行顺序

1. T112A Profile A本地回传复核与T115A预算冻结均已PASS，阶段B完成；
2. 提交并同步本轮7份收敛文档，重新确认远程Git状态；
3. 用户批准后恢复GPU，执行14B环境、文本和多模态Smoke并回传本地；
4. 14B PASS且用户批准后下载和验证3B/8B；
5. 三模型Smoke均PASS后执行真实5 Item并回传本地重算；
6. 用户批准后构建30 Item专用传输包；
7. 执行30 Item、回传和诊断，再决定是否进入Formal。

## 文件索引

- `remote-codex-handoff.md`：远程Codex当前接手入口、状态、门禁与首次提示词。
- `model-approval-manifest.yaml`：服务器与各模型revision、下载和Smoke状态。
- `environment-lock.md`：真实硬件、目录、软件和分阶段门禁。
- `data-transfer-manifest.json`：冻结5 Item最小10文件、目标路径和接收审计契约。
- `pricing-and-budget.md`：Token等价价格与调用预算；不记录服务器租金。
- `deployment-command-template.md`：使用AutoDL真实路径的部署模板。
- `checkpoint-runbook.md`：真实5 Item顺序执行、validator、回传与本地复核。
- `artifact-return-manifest.md`：Download、Smoke、5 Item和30 Item四类产物回传契约。

## 冻结实现与验收提交链

```text
frozen_implementation_commit: 44f3e5fcf825794d4516455b9c7dd3fd3c5bc796
core_handoff_contract_commit: f1d08f2e539d0498acf030128a6343886246e9eb
desktop_smoke_status_commit: 6141f1f67a9f3a2a2e81136268c31b3d748cf335
final_document_convergence_commit: 3050fd701ed6f66c65397d936a220be1ede8034d
```

- `frozen_implementation_commit`冻结自托管Pilot执行代码、配置、Prompt和测试。
- `core_handoff_contract_commit`冻结方案A后端与核心交接契约。
- `desktop_smoke_status_commit`记录本机Codex官方SSH Remote只读Smoke完成状态。
- `final_document_convergence_commit`记录方案A审计链、门禁表述和文档状态的最终内容收敛基线。

包含上述指针的后续 metadata-only 提交因无法自引用，可以晚于 `final_document_convergence_commit`，但不得静默改变冻结执行代码、配置、Prompt或测试。真实run必须记录当前工作区commit、`frozen_implementation_commit`和适用的验收提交语义。

## 禁止内容

交接包不得包含API Key、Codex/OAuth Token、SSH私钥、服务器密码、Mihomo订阅、模型权重、虚拟环境、下载缓存、未批准的Dev/Test或全量train数据。
