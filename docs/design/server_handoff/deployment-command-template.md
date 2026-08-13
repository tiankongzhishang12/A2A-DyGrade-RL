# 部署命令模板（未执行）

> 这些命令仅用于服务器审批后的runbook模板。本地P1–P8没有执行安装、下载或服务启动。

## 1. 拉取固定代码

```bash
git clone <APPROVED_REPOSITORY_URL> /mnt/experiments/A2A-DyGrade-RL
cd /mnt/experiments/A2A-DyGrade-RL
git checkout <APPROVED_COMMIT_SHA>
git status --porcelain  # 必须为空
```

## 2. 创建环境

```bash
# 具体Python/torch/vLLM版本需根据模型官方说明和服务器CUDA在审批后填入。
python -m venv /mnt/experiments/venvs/a2a-dygrade-rl
source /mnt/experiments/venvs/a2a-dygrade-rl/bin/activate
pip install <APPROVED_LOCKED_DEPENDENCIES>
```

## 3. 下载权重

```bash
# 逐模型使用审批后的精确revision，下载到/mnt/models/ministral3/。
<APPROVED_MODEL_DOWNLOAD_COMMAND>
```

## 4. 生成服务器解析配置

不得直接使用仓库中的本地锁定配置发起真实调用。为真实5 Item run复制一份服务器解析配置，并至少完成以下替换：

```yaml
local_preparation_only: false
prepared_root: /mnt/data/semantic_v2
provider:
  prepared_root: /mnt/data/semantic_v2
  base_url: http://127.0.0.1:8000/v1
  server_hourly_price_usd: <APPROVED_SERVER_HOURLY_PRICE_USD_OR_NULL>
agents:
  cheap|mid|strong:
    model_revision: <EXACT_APPROVED_WEIGHT_REVISION>
```

服务器解析配置必须写入该真实 `run_id` 的 `configs/`，不得覆盖仓库模板；三个模型阶段复用同一份解析配置，除当前服务实际加载的模型外不得改变 Prompt、Schema、参数、价格或路径。

## 5. 启动OpenAI-compatible服务

```bash
# 示例接口目标：POST http://127.0.0.1:8000/v1/chat/completions
<APPROVED_VLLM_OR_SGLANG_SERVE_COMMAND> \
  --model <MODEL_PATH> \
  --served-model-name <EXACT_MODEL_ID> \
  --max-model-len 32768
```

## 6. 服务Smoke

```bash
curl http://127.0.0.1:8000/v1/models
# 再发送1个不进入正式账本的已批准身份/usage/图像smoke请求。
```

不得直接复制模板中的占位符执行。
