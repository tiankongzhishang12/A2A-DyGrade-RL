# 快速开始：A2A-DyGrade-RL 实验流水线

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
