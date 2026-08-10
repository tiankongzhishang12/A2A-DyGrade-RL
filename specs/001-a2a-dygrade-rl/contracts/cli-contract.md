# CLI 合约

实验流水线通过阶段脚本暴露命令。每个脚本必须支持配置路径、输入路径、输出路径、相关 split 名称、随机种子，以及用于 smoke validation 的 dry-run 或 sample-size 选项。

每次运行必须传入或生成唯一 `run_id`。除 `data/` 下的数据型产物外，运行日志、配置快照、预测结果、checkpoint、报告和图必须写入 `outputs/runs/<run_id>/` 的对应子目录。

## 阶段命令

| 脚本 | 目的 | 必需输出 |
|---|---|---|
| `scripts/01_build_items.py` | 将 raw datasets 规范化为 item JSONL 文件 | `data/processed/items_*.jsonl` |
| `scripts/02_build_papers.py` | 构建 paper-level samples 和 splits | `data/processed/papers_*.jsonl` |
| `scripts/03_run_agent_cache.py` | 生成或校验 cached Agent outputs | `outputs/runs/<run_id>/predictions/agent_cache/*.jsonl` |
| `scripts/04_build_difficulty_labels.py` | 构建旧阶段 difficulty labels 和 capability fixture | `data/processed/difficulty_labels.jsonl`、`outputs/runs/<run_id>/reports/agent_capability_table.csv` |
| `scripts/04a_build_internal_split.py` | 构建 train 内部 Item component split | `data/processed/internal_item_split_manifest.csv` 与 run audit |
| `scripts/04c_build_internal_papers.py` | 在两个内部 Item 池分别重建固定5题 strict Paper | `papers_train_fit.jsonl`、`papers_train_calibration.jsonl`、internal manifests |
| `scripts/04d_run_quality_constrained_fixture_smoke.py` | 运行隔离的完整质量约束 Fixture Smoke | `outputs/runs/fixture_smoke_<run_id>/reports/fixture_smoke_summary.json` |
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

## 完整 Fixture Smoke CLI

命令：

`scripts/04d_run_quality_constrained_fixture_smoke.py`

必需参数：

- `--config configs/experiments/fixture_smoke.yaml`
- `--run-id fixture_smoke_<unique_id>`

可选参数：

- `--output-root`，默认 `outputs/runs`

硬约束：

1. `run_id` 不以 `fixture_smoke_` 开头或不是单一安全路径组件时立即失败，禁止 `/`、`\` 和路径遍历。
2. 配置不是 `execution_mode=fixture_smoke`、`formal_eligible=false` 或声明允许在线 Agent 时立即失败。
3. 目标 run 目录已存在且非空时立即失败，不提供覆盖正式或既有 Smoke 的选项；若 `output_root` 位于仓库内，则必须位于 `outputs/runs/` 下，禁止指向 `data/processed/`、正式 cache 或其他项目目录。
4. CLI 只能编排 `src/a2a_dygrade_rl/` 的正式核心模块，不得内置另一套质量门、阈值或 selector。
5. 完整运行必须保存配置、输入、Fixture 工厂/编排器/CLI/核心代码指纹、日志、全部成功/失败候选、Package、选择和 test-like 结果。
6. CLI 不接受真实 provider、API key、SDK 或网络开关；Fixture Smoke 中在线 Agent 调用计数必须为0。
7. CLI 完成后必须执行契约自审，任一禁止行为计数非0、产物缺失、路径越界、Formal loader 探针误接受、预算不可行候选晋级、冻结 STOP 边界未实际应用、A2A 资源未计数、artifact inventory 未覆盖全部运行文件或完整确定性检查失败时返回非零退出码。
8. `formal_data_reads`、`formal_asset_acceptances` 和 `cross_mode_cache_reuse` 必须分别由路径白名单、实际 Formal 入口拒绝探针和 active cache 模式扫描得到，禁止直接写死为0。
9. 成功 run 的最后一步必须生成 `configs/fixture_artifact_manifest.json`；之后不得再创建未纳入 inventory 的运行文件。
10. 相同输入重复检查必须同时覆盖固定参考映射、每 checkpoint STOP 边界、Quality Champion、质量保护集合和唯一最终 checkpoint。

### Agent cache CLI 的 V1.4 split 参数

`scripts/03_run_agent_cache.py` 必须支持 `train_fit`、`train_calibration`、`dev`、`test`。train 侧必须通过 `--internal-item-manifest` 从 `internal_item_split_manifest.csv` 解析；Dev/Test 必须通过 `--external-split-manifest` 解析。Formal 模式禁止使用旧 `paper_train_*` 或只看 Item metadata 推断内部 split。
