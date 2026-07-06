# CLI 合约

实验流水线通过阶段脚本暴露命令。每个脚本必须支持配置路径、输入路径、输出路径、相关 split 名称、随机种子，以及用于 smoke validation 的 dry-run 或 sample-size 选项。

每次运行必须传入或生成唯一 `run_id`。除 `data/` 下的数据型产物外，运行日志、配置快照、预测结果、checkpoint、报告和图必须写入 `outputs/runs/<run_id>/` 的对应子目录。

## 阶段命令

| 脚本 | 目的 | 必需输出 |
|---|---|---|
| `scripts/01_build_items.py` | 将 raw datasets 规范化为 item JSONL 文件 | `data/processed/items_*.jsonl` |
| `scripts/02_build_papers.py` | 构建 paper-level samples 和 splits | `data/processed/papers_*.jsonl` |
| `scripts/03_run_agent_cache.py` | 生成或校验 cached Agent outputs | `outputs/runs/<run_id>/predictions/agent_cache/*.jsonl` |
| `scripts/04_build_difficulty_labels.py` | 构建 difficulty labels 和 capability profiles | `data/processed/difficulty_labels.jsonl`、`outputs/runs/<run_id>/reports/agent_capability_table.csv` |
| `scripts/05_build_trajectories.py` | 构建 offline RL trajectories | `data/trajectories/*.jsonl` |
| `scripts/06_train_cag_cql.py` | 训练 Router | `outputs/runs/<run_id>/checkpoints/cag_cql/`、`outputs/runs/<run_id>/logs/train.log` |
| `scripts/07_eval_baselines.py` | 评价主比较方法 | `outputs/runs/<run_id>/reports/main_results.csv` |
| `scripts/08_eval_ablation.py` | 评价消融版本 | `outputs/runs/<run_id>/reports/ablation_results.csv` |
| `scripts/09_plot_cost_qwk_curve.py` | 构建 Cost-QWK curve 数据和图 | `outputs/runs/<run_id>/reports/cost_qwk_curve.csv`、`outputs/runs/<run_id>/figures/` |

## 通用行为

- 命令在缺少必需输入时必须给出清晰错误。
- 命令必须原子写入输出，或除非显式传入 overwrite 标志，否则避免覆盖有效输出。
- 命令必须记录实际生效配置和随机种子。
- 命令必须把实际生效配置快照保存到 `outputs/runs/<run_id>/configs/`。
- 命令必须支持小样本 smoke mode。
- 命令不得把日志、预测、报告、checkpoint 或图直接写到仓库根目录或旧式平铺 `outputs/` 子目录。
