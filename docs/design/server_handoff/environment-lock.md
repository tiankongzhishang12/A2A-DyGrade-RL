# 服务器环境冻结要求

## 待审批硬件

- GPU：模型官方上下文上限为256K，但首轮Pilot人为批准的运行上限固定为32K；服务器必须能够以统一精度稳定容纳14B模型、视觉编码器和该32K以内KV cache。首选单卡48GB以上，最终以部署 smoke 峰值显存为准。
- GPU数量：首轮顺序加载，默认1张；不得为同时常驻三模型额外租卡。
- 系统盘/数据盘：模型、虚拟环境、缓存、prepared data和run产物全部放服务器数据盘；禁止写入本地C盘约定路径。
- 磁盘空间：审批前核对三套权重、容器/环境缓存和run产物总量，保留至少20%余量。

## 待冻结软件版本

真实部署后必须在run配置中保存：

```text
OS image / image digest
GPU model and count
NVIDIA driver
CUDA runtime
Python
PyTorch
vLLM or SGLang
Transformers / Mistral processor stack
pip freeze or container digest
```

P1–P8没有安装或声称某个具体版本可用。服务器应先根据模型官方说明做兼容性 smoke，再把真实版本写入 `outputs/runs/<run_id>/configs/environment-lock.json`。

## 目录模板

```text
/mnt/experiments/A2A-DyGrade-RL/       # Git工作区
/mnt/models/ministral3/{3b,8b,14b}/    # 权重
/mnt/cache/huggingface/                 # 下载缓存
/mnt/data/semantic_v2/                  # prepared data
/mnt/outputs/runs/<run_id>/             # 实验产物
```

## 安全门

- 真实run必须记录干净commit，`dirty_worktree=false`。
- 模型revision不得保留`pending_server_freeze`。
- `/v1/models`和每个响应的`model`必须匹配请求。
- 多模态响应必须返回视觉Token分解。
- 服务器解析配置的两个 prepared_root 均必须为 /mnt/data/semantic_v2，命令必须显式传入 --output-root /mnt/outputs/runs。
- 未通过上述门禁时不执行5 Item。
