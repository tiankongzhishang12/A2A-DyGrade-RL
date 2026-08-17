# AutoDL部署命令模板（待阶段门禁后执行）

> 本模板使用实际AutoDL数据盘路径。不得直接复制仍含占位符的命令执行；安装、下载、GPU启动和真实模型调用必须满足对应任务与用户审批。服务器租金不进入论文实验成本。

## 1. 核对远程仓库

```bash
cd /root/autodl-tmp/a2a-dygrade/repo
git status --short --branch
git rev-parse HEAD
```

T113通过GitHub或Git bundle同步后，必须确认 `dirty_worktree=false`，并记录 `frozen_implementation_commit`、`core_handoff_contract_commit`、`desktop_smoke_status_commit`与 `final_document_convergence_commit`。

## 2. 核对最小数据传输

```bash
# 只读取T113A生成的接收manifest，不在此模板中执行未批准传输。
cat /root/autodl-tmp/a2a-dygrade/repo/outputs/runs/remote_data_transfer_<timestamp>/configs/data-transfer-receipt.json
```

只有receipt PASS后才执行图片Smoke和真实5 Item。

## 3. 创建推理环境

```bash
python -m venv /root/autodl-tmp/a2a-dygrade/runtime/venvs/a2a-dygrade-rl
source /root/autodl-tmp/a2a-dygrade/runtime/venvs/a2a-dygrade-rl/bin/activate
# pip install <APPROVED_LOCKED_DEPENDENCIES>
```

具体Python/PyTorch/vLLM/Transformers版本必须根据服务器Driver/CUDA核验后冻结，不能使用未替换占位符。

## 4. 模型目录

```text
/root/autodl-tmp/a2a-dygrade/models/ministral3/3b-bf16
/root/autodl-tmp/a2a-dygrade/models/ministral3/8b-bf16
/root/autodl-tmp/a2a-dygrade/models/ministral3/14b-bf16
```

当前只完成14B下载。14B Smoke PASS且用户批准后才下载3B/8B。

## 5. 生成服务器解析配置

不得覆盖仓库模板；解析配置写入真实run的 `configs/`：

```yaml
local_preparation_only: false
prepared_root: /root/autodl-tmp/a2a-dygrade/repo/data/processed/semantic_v2
provider:
  prepared_root: /root/autodl-tmp/a2a-dygrade/repo/data/processed/semantic_v2
  base_url: http://127.0.0.1:8000/v1
  server_hourly_price_usd: null
agents:
  cheap|mid|strong:
    model_revision: <EXACT_APPROVED_WEIGHT_REVISION>
```

除当前服务实际加载的模型外，三个阶段不得改变Prompt、Schema、生成参数、Token价格或路径。

## 6. 启动OpenAI-compatible服务

```bash
# 示例接口：POST http://127.0.0.1:8000/v1/chat/completions
<APPROVED_VLLM_SERVE_COMMAND> \
  --model <MODEL_PATH> \
  --served-model-name <EXACT_MODEL_ID> \
  --max-model-len 32768
```

## 7. 服务Smoke

```bash
curl http://127.0.0.1:8000/v1/models
# 再执行已冻结的文本、usage和图片Smoke输入。
```

顺序固定为：14B Smoke → 回传与本地复核 → 用户审批 → 3B/8B下载和Smoke → 真实5 Item。
