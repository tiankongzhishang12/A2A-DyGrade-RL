# 数据目录说明

本项目只在 `data/` 下保存数据型产物：

- `data/raw/<dataset>/`：用户已授权获取的原始公开数据文件。
- `data/processed/`：规范化后的 `items_*.jsonl`、`papers_*.jsonl`、split manifest 和 paper manifest。
- `data/trajectories/`：后续离线 RL 轨迹数据。

当前目标数据集：

- `dress`：等待官方 release 或作者仓库直链核验后写入 `configs/dataset_sources.yaml`。
- `asap_sas`：通常需要 Kaggle/竞赛授权，授权下载后放入 `data/raw/asap_sas/`。
- `sas_bench`：等待官方 release 或作者仓库直链核验后写入 `configs/dataset_sources.yaml`。

检查本地 raw data 是否就绪：

```bash
python scripts/00_download_datasets.py --manifest configs/dataset_sources.yaml --check-only
```

如果 `configs/dataset_sources.yaml` 中已有经核验的公开 URL，可运行：

```bash
python scripts/00_download_datasets.py --manifest configs/dataset_sources.yaml
```
