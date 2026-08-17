# 服务器环境冻结要求

> **状态快照**：2026-08-17。硬件与14B权重、远程Codex控制面和10文件传输已经核验；推理软件环境尚未安装和冻结。所有路径必须位于AutoDL数据盘。

## 已核验硬件

- GPU：NVIDIA GeForce RTX 4090D，显存约48GB。
- GPU数量：1张；Cheap/Mid/Strong顺序加载，不为同时常驻三模型额外租卡。
- CPU：GPU实例启动后约20核。
- 内存：GPU实例启动后约90GB。
- 低资源保留状态：约0.5核CPU、2GB内存、无GPU。
- 当前GPU状态：关闭。
- 磁盘：模型、虚拟环境、缓存、prepared data和run产物全部放数据盘；任何阶段开始前重新检查容量并保留至少20%余量。

## 已冻结远程控制面

- Codex CLI、共享 `CODEX_HOME`、账号保险库、切换器和日志位于 `/root/autodl-tmp/a2a-dygrade/runtime/codex/`。
- Mihomo位于 `/root/autodl-tmp/a2a-dygrade/runtime/mihomo/`，只监听 `127.0.0.1`，且只由Codex包装器注入Codex子进程。
- 可选VS Code Server目录预留为 `/root/autodl-tmp/a2a-dygrade/runtime/vscode/`；它不是方案A的阻塞项。
- 两个ChatGPT账号共享会话状态但使用独立认证文件；只允许用户显式手动切换。
- 当前GPU关闭；远程Codex操作性模型调用不计入论文实验成本。

## 待冻结软件版本

T116恢复GPU后，必须在唯一run配置中记录：

```text
OS image / image digest
GPU model and count
NVIDIA driver
CUDA runtime
Python
PyTorch
vLLM
Transformers / Mistral processor stack
pip freeze or container digest
```

实际版本写入：

```text
outputs/runs/selfhosted_14b_smoke_<timestamp>/configs/environment-lock.json
```

在真实版本形成前，不得把模板版本或本地版本写成服务器已验证版本。

## 冻结目录

```text
project_root: /root/autodl-tmp/a2a-dygrade
repo_root: /root/autodl-tmp/a2a-dygrade/repo
model_root: /root/autodl-tmp/a2a-dygrade/models/ministral3
runtime_root: /root/autodl-tmp/a2a-dygrade/runtime
prepared_root: /root/autodl-tmp/a2a-dygrade/repo/data/processed/semantic_v2
output_root: /root/autodl-tmp/a2a-dygrade/repo/outputs/runs
```

真实解析配置中的顶层 `prepared_root` 与 `provider.prepared_root` 必须同时等于上述 `prepared_root`；命令必须显式传入上述 `output_root`。不得继续使用历史模板中的 `/mnt/...` 路径。

## Commit与工作树门禁

- `frozen_implementation_commit=44f3e5fcf825794d4516455b9c7dd3fd3c5bc796`。
- `workspace_handoff_commit=f1d08f2e539d0498acf030128a6343886246e9eb` 已存在于本地、Git远程和AutoDL工作树，且同步时核验了分支、提交、交接文件hash与 `dirty_worktree=false`；后续只更新指针或任务状态的 metadata-only 提交可以晚于该commit。
- 真实run必须记录当前工作区commit、冻结实现commit和 `dirty_worktree=false`。
- 新文档提交可以位于冻结实现commit之后，但 `src/`、`scripts/`、`configs/`、`prompts/` 和 `tests/` 相对冻结实现不得出现未批准变化。

## 数据门禁

- 14B图片Smoke和真实5 Item前，T113A的 `data-transfer-receipt.json.status` 必须为 `PASS`。
- 接收结果必须满足expected=10、received=10、hash mismatch=0、Dev/Test=0、non-checkpoint train=0。
- 30 Item使用独立 `pilot30-data-transfer-manifest.json`，不得把5 Item最小manifest冒充30 Item输入。

## 分阶段模型revision门禁

- 14B Smoke：只要求StrongAgent revision冻结且下载manifest PASS。
- 3B Smoke：要求CheapAgent revision冻结。
- 8B Smoke：要求MidAgent revision冻结。
- 真实5 Item：要求Cheap/Mid/Strong三个revision全部冻结，且三个模型Smoke均PASS。

## 服务与Token门禁

- `/v1/models`和每个响应的 `model` 必须匹配请求。
- 服务必须返回有效 `prompt_tokens`、`completion_tokens` 和 `total_tokens`。
- 多模态Smoke和真实checkpoint必须返回文本/视觉Token分解。
- `max_model_len=32768`、`temperature=0`、非Thinking、单模型常驻。
- 服务器租金不属于论文实验成本；`server_hourly_price_usd`固定为 `null`。
- 未通过任一阶段门禁时，不执行其后续模型、真实5 Item或30 Item。
