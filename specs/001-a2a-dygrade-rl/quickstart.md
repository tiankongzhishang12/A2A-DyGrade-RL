# 快速开始：A2A-DyGrade-RL 实验流水线

## V1.7 当前服务器执行入口

V1.6 P1–P8本地准备已经完成。当前不要从本文件直接启动真实服务器实验；远程执行必须先阅读：

1. `AGENTS.md`；
2. `docs/design/server_handoff/remote-codex-handoff.md`；
3. `specs/001-a2a-dygrade-rl/tasks.md` Phase 10；
4. `docs/design/server_handoff/environment-lock.md`；
5. `docs/design/server_handoff/checkpoint-runbook.md`。

当前下一步是T113文档提交/远程同步和T113A最小10文件数据传输，不是直接启动GPU、vLLM或真实5 Item。统一远程路径为 `/root/autodl-tmp/a2a-dygrade/`；服务器租金不进入论文实验成本。

---

## V1.6 自托管 Ministral 3 Pilot 本地准备（P1–P8）

本阶段禁止真实模型调用、模型下载、依赖安装和服务器操作。全部命令在仓库根目录执行，运行产物使用唯一 `run_id`。

### 1. 验证配置、Prompt 与多模态资产

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/unit/test_selfhosted_client.py `
  tests/unit/test_multimodal_assets.py `
  tests/unit/test_selfhosted_costing.py `
  tests/unit/test_selfhosted_checkpoint.py
```

预期：所有测试通过；4个 ASAP-SAS source asset 的 hash/MIME/尺寸通过，2个 TIFF 可确定性无损转为 PNG。

### 2. 构建固定5题 checkpoint

```powershell
$runId = "real_pilot_selfhosted_checkpoint_prepare_20260812_002"
.\.venv\Scripts\python.exe scripts/08_prepare_selfhosted_checkpoint.py `
  --papers-path data/processed/semantic_v2/papers_train_fit.jsonl `
  --items-path data/processed/semantic_v2/items_train.jsonl `
  --internal-item-manifest data/processed/semantic_v2/internal_item_split_manifest.csv `
  --semantic-readiness-manifest data/processed/semantic_v2/semantic_readiness_manifest.json `
  --run-id $runId
```

预期：生成1份strict Paper、5个唯一train_fit Item、覆盖三个数据集、至少一个图片Item，`gold_fields_read_for_selection=0`。

### 3. 运行Fake Chat Completions端到端workflow

```powershell
$runId = "fixture_smoke_selfhosted_ministral3_20260812_007"
.\.venv\Scripts\python.exe scripts/09_run_selfhosted_agent_cache.py `
  --config configs/experiments/selfhosted_ministral3_checkpoint.yaml `
  --items-path outputs/runs/real_pilot_selfhosted_checkpoint_prepare_20260812_002/predictions/checkpoint_inputs/items_train_fit_checkpoint.jsonl `
  --internal-item-manifest outputs/runs/real_pilot_selfhosted_checkpoint_prepare_20260812_002/configs/internal_item_split_manifest.checkpoint.csv `
  --run-id $runId `
  --transport fake `
  --fixture
```

预期：15条 Cheap/Mid/Strong canonical 成功记录，0条 Evidence/Arbitrator，所有序列化body无Gold。

### 4. 验证checkpoint与resume

```powershell
.\.venv\Scripts\python.exe scripts/10_validate_selfhosted_checkpoint.py `
  --run-dir outputs/runs/fixture_smoke_selfhosted_ministral3_20260812_007 `
  --items-path outputs/runs/real_pilot_selfhosted_checkpoint_prepare_20260812_002/predictions/checkpoint_inputs/items_train_fit_checkpoint.jsonl `
  --transport-kind fake

.\.venv\Scripts\python.exe scripts/09_run_selfhosted_agent_cache.py `
  --config configs/experiments/selfhosted_ministral3_checkpoint.yaml `
  --items-path outputs/runs/real_pilot_selfhosted_checkpoint_prepare_20260812_002/predictions/checkpoint_inputs/items_train_fit_checkpoint.jsonl `
  --internal-item-manifest outputs/runs/real_pilot_selfhosted_checkpoint_prepare_20260812_002/configs/internal_item_split_manifest.checkpoint.csv `
  --run-id fixture_smoke_selfhosted_ministral3_20260812_007 `
  --transport fake `
  --fixture `
  --resume
```

预期：resume新增HTTP请求数为0，canonical成本不重复累计。Fake PASS只证明本地契约成立，`unlocks_30_item_pilot=false`。

### 5. 全量验证

```powershell
# 本阶段只读确认已冻结 Semantic Readiness，不重写 prepared manifest。
.\.venv\Scripts\python.exe -c "import json,pathlib; p=pathlib.Path('data/processed/semantic_v2/semantic_readiness_manifest.json'); assert json.loads(p.read_text(encoding='utf-8'))['status']=='PASS'"

.\.venv\Scripts\python.exe -m pytest -q

.\.venv\Scripts\python.exe scripts/11_audit_selfhosted_local_readiness.py `
  --run-id selfhosted_local_readiness_20260812_001 `
  --fake-run-id fixture_smoke_selfhosted_ministral3_20260812_007
```

服务器阶段需另行批准；不得在本Quickstart中执行模型下载或部署模板。

### 单卡服务器按模型分阶段执行

服务器只常驻一个模型时，三个阶段必须复用同一 `run_id`，并用 `--agents` 每次只执行当前已启动模型对应的 Agent：

```bash
# 3B服务已启动
python scripts/09_run_selfhosted_agent_cache.py ... \
  --run-id real_pilot_selfhosted_ministral3_<UNIQUE_ID> \
  --transport urllib --server-approved --agents CheapAgent

# 停止3B、启动8B后，只补MidAgent；同一run使用--resume
python scripts/09_run_selfhosted_agent_cache.py ... \
  --run-id real_pilot_selfhosted_ministral3_<UNIQUE_ID> \
  --transport urllib --server-approved --agents MidAgent --resume

# 停止8B、启动14B后，只补StrongAgent
python scripts/09_run_selfhosted_agent_cache.py ... \
  --run-id real_pilot_selfhosted_ministral3_<UNIQUE_ID> \
  --transport urllib --server-approved --agents StrongAgent --resume
```

三个阶段完成后再运行 validator；不得在只启动一个模型时省略 `--agents`，否则客户端会尝试调用尚未部署的另外两个模型。


---
## Dataset Semantic V2 正式数据整改

旧 `data/processed/` 根目录产物视为 legacy。自托管模型实验必须先构建并冻结 `data/processed/semantic_v2/`；本阶段不会下载权重、安装新依赖或调用模型。

建议使用唯一运行标识：

```powershell
$runId = "dataset_semantic_v2_build_20260811_001"
```

1. 构建 Semantic V2 Item、原始图片、quarantine、split 和 build manifest。

```powershell
python scripts/01_build_items.py --config configs/dataset_semantic_v2.yaml --output-dir data/processed/semantic_v2 --output-root outputs/runs --run-id $runId
```

2. 构建固定5题外部 strict Paper，并生成外部 leftover 清单。

```powershell
python scripts/02_build_papers.py --config configs/dataset_semantic_v2.yaml --input-dir data/processed/semantic_v2 --output-dir data/processed/semantic_v2 --output-root outputs/runs --run-id $runId
```

3. 运行通用 prepared data audit。

```powershell
python scripts/00_audit_prepared_data.py --config configs/dataset_semantic_v2.yaml --processed-dir data/processed/semantic_v2 --output-root outputs/runs --min-paper-items 5 --max-paper-items 5 --run-id $runId
```

4. 运行 fail-closed Semantic Readiness。

```powershell
python scripts/00b_audit_semantic_readiness.py --config configs/dataset_semantic_v2.yaml --processed-dir data/processed/semantic_v2 --output-root outputs/runs --run-id $runId --overwrite
```

只有 `data/processed/semantic_v2/semantic_readiness_manifest.json` 为 `PASS`，才允许进入本地多模态模型的5 Item checkpoint。模型专用图片缩放、Tokenizer/Processor、视觉 Token 和实际 Token 用量必须写入对应 Agent cache run，不得回写 prepared data。

5. 从新外部 train strict Paper 范围构建内部 `train_fit/train_calibration` Item split。

```powershell
python scripts/04a_build_internal_split.py --config configs/dataset_semantic_v2.yaml --items data/processed/semantic_v2/items_train.jsonl --paper-manifest data/processed/semantic_v2/paper_manifest.csv --output-dir data/processed/semantic_v2 --output-root outputs/runs --run-id $runId
```

6. 分别重建内部 strict Paper 并运行内部审计。

```powershell
python scripts/04c_build_internal_papers.py --config configs/dataset_semantic_v2.yaml --items data/processed/semantic_v2/items_train.jsonl --internal-item-manifest data/processed/semantic_v2/internal_item_split_manifest.csv --external-paper-manifest data/processed/semantic_v2/paper_manifest.csv --output-dir data/processed/semantic_v2 --output-root outputs/runs --run-id $runId
```

下文旧 Smoke Validation 仅保留为历史入口；正式自托管实验不得读取 legacy prepared data。
本指南用于在运行完整实验前，基于 fixtures 或公开数据小样本验证端到端功能。

## 前置条件

- Python 3.11+
- 已安装项目依赖
- 已准备小型 fixture data 或已下载公开数据集样本
- 仅当启用实时 Agent 调用时，才需要可选模型凭据

## Smoke Validation

以下示例使用 `run_id=smoke_001`。所有运行日志、配置快照、预测、报告和图都必须进入 `outputs/runs/smoke_001/`。

1. 构建规范化 items。

```bash
python scripts/01_build_items.py --config configs/dataset.yaml --sample-size 20 --output-dir data/processed --run-id smoke_001
```

预期结果：item JSONL 文件存在，并包含产物 schema 合约中的必需字段。

2. 构建 paper-level samples。

```bash
python scripts/02_build_papers.py --config configs/dataset.yaml --input-dir data/processed --output-dir data/processed --seed 42 --run-id smoke_001
```

预期结果：paper JSONL 文件存在，且每张 paper 都引用合法 items。

3. 构建或校验 Agent cache。

```bash
python scripts/03_run_agent_cache.py --config configs/agents.yaml --items data/processed/items_train.jsonl --output-dir outputs/runs/smoke_001/predictions/agent_cache --sample-size 20 --run-id smoke_001
```

预期结果：每个被接受样本都有合法 Agent cache records。

4. 构建 difficulty 和 capability 产物。

```bash
python scripts/04_build_difficulty_labels.py --items data/processed/items_train.jsonl --cache-dir outputs/runs/smoke_001/predictions/agent_cache --output-dir data/processed --report-dir outputs/runs/smoke_001/reports --run-id smoke_001
```

预期结果：生成 difficulty labels 和 capability profile。

5. 构建 trajectories。

```bash
python scripts/05_build_trajectories.py --papers data/processed/papers_train.jsonl --cache-dir outputs/runs/smoke_001/predictions/agent_cache --output-dir data/trajectories --run-id smoke_001
```

预期结果：basic、A2A、boundary 和 HBR trajectories 均存在。

6. 以 smoke mode 训练 Router。

```bash
python scripts/06_train_cag_cql.py --config configs/cag_cql.yaml --trajectories data/trajectories/train_trajectories.jsonl --dev-trajectories data/trajectories/dev_trajectories.jsonl --run-dir outputs/runs/smoke_001 --smoke
```

预期结果：创建 checkpoint 和 training log。

7. 评价 baselines 和 ablations。

```bash
python scripts/07_eval_baselines.py --config configs/experiment.yaml --papers data/processed/papers_test.jsonl --cache-dir outputs/runs/smoke_001/predictions/agent_cache --output outputs/runs/smoke_001/reports/main_results.csv --run-id smoke_001
python scripts/08_eval_ablation.py --config configs/experiment.yaml --papers data/processed/papers_test.jsonl --cache-dir outputs/runs/smoke_001/predictions/agent_cache --output outputs/runs/smoke_001/reports/ablation_results.csv --run-id smoke_001
```

预期结果：main report 和 ablation report CSV 文件包含完整方法行。

8. 构建 Cost-QWK curve。

```bash
python scripts/09_plot_cost_qwk_curve.py --input outputs/runs/smoke_001/reports --output outputs/runs/smoke_001/reports/cost_qwk_curve.csv --figure-dir outputs/runs/smoke_001/figures --run-id smoke_001
```

预期结果：Cost-QWK 数据包含所有配置的 cost-penalty points。

9. 验证 run 目录可复算主要指标。

```bash
python scripts/07_eval_baselines.py --config outputs/runs/smoke_001/configs/experiment.yaml --papers data/processed/papers_test.jsonl --cache-dir outputs/runs/smoke_001/predictions/agent_cache --output outputs/runs/smoke_001/reports/main_results_recomputed.csv --run-id smoke_001
```

预期结果：可以从 `outputs/runs/smoke_001/` 中保存的配置、预测和日志复算主要指标。
