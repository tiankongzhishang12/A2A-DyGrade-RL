# 自托管 Ministral 3 Pilot 服务器交接包

> **当前入口**：远程服务器、模型、GPU、任务与审批状态以 `remote-codex-handoff.md` 为准。原P8“未租服务器、未下载模型”描述只属于2026-08-13之前的本地准备历史边界。

## 当前状态（2026-08-17）

- V1.6本地准备P1–P8、AutoDL服务器、远程Git仓库、14B BF16下载与完整性检查均已完成。
- 冻结5 Item的10个最小文件已传输并通过hash receipt；Dev/Test和非checkpoint train传输数均为0。
- 远程Codex CLI、共享`CODEX_HOME`、两个ChatGPT账号手动切换、进程级Mihomo、App Server和跨账号同一Thread续接Smoke已完成。
- 本机Codex官方SSH Connection UI及其只读Smoke仍为`PENDING_USER_UI`。
- 14B下载Profile A回传、本地复核、推理环境和真实14B Smoke尚未执行；GPU当前关闭。
- 3B/8B、真实5 Item、30 Item和Formal均未解锁。
- 评分质量优先，资源不可补偿质量失败；论文主成本只使用Official API-Equivalent Token Cost，服务器租金不进入实验指标。

## 当前执行顺序

1. 在本机Codex桌面端注册`autodl-a2a`官方SSH Connection，并完成无GPU只读Smoke；
2. 将现有14B下载run按Profile A回传本地并完成hash复核；
3. 复核Token价格和调用预算冻结状态；
4. 经用户批准恢复GPU，执行14B环境、文本和多模态Smoke并回传本地；
5. 14B PASS且用户批准后下载和验证3B/8B；
6. 三模型Smoke均PASS后执行真实5 Item并回传本地重算；
7. 用户批准后构建30 Item专用传输包；
8. 执行30 Item、回传和诊断，再决定是否进入Formal。

## 文件索引

- `remote-codex-handoff.md`：远程Codex当前接手入口、状态、门禁与首次提示词。
- `model-approval-manifest.yaml`：服务器与各模型revision、下载和Smoke状态。
- `environment-lock.md`：真实硬件、目录、软件和分阶段门禁。
- `data-transfer-manifest.json`：冻结5 Item最小10文件、目标路径和接收审计契约。
- `pricing-and-budget.md`：Token等价价格与调用预算；不记录服务器租金。
- `deployment-command-template.md`：使用AutoDL真实路径的部署模板。
- `checkpoint-runbook.md`：真实5 Item顺序执行、validator、回传与本地复核。
- `artifact-return-manifest.md`：Download、Smoke、5 Item和30 Item四类产物回传契约。

## 历史冻结实现

```text
frozen_implementation_commit: 44f3e5fcf825794d4516455b9c7dd3fd3c5bc796
workspace_handoff_commit: 7422cdbaa04e8fb0310ad926dd1f823c7a1d6bb2
```

后续文档提交不得静默改变冻结执行代码、配置、Prompt或测试。真实run必须同时记录两个commit语义。

## 禁止内容

交接包不得包含API Key、Codex/OAuth Token、SSH私钥、服务器密码、Mihomo订阅、模型权重、虚拟环境、下载缓存、未批准的Dev/Test或全量train数据。
