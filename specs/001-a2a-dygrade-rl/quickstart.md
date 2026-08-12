# 快速开始：A2A-DyGrade-RL 实验流水线

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
