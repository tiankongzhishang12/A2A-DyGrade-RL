# 真实5 Item Checkpoint Runbook

## 前置门禁

- 用户已批准服务器、模型、下载、依赖和费用。
- Git commit与环境锁定完成，工作树干净。
- `data-transfer-manifest.json`中10个最小必要Semantic V2/checkpoint文件全部hash匹配。
- `semantic_readiness_manifest.json.status=PASS`。
- 三个模型revision均已冻结。
- 服务端返回`model`与`usage`，图像请求含视觉Token分解。

## 固定输入

```text
prepare run: real_pilot_selfhosted_checkpoint_prepare_20260812_002
paper: paper_train_fit_00621
items: 5
agents: CheapAgent, MidAgent, StrongAgent
canonical calls: 15
```

如果服务器重新构建checkpoint，必须用相同源hash、种子和选择规则得到完全相同的paper/item列表，否则停止。

## 顺序执行

1. 启动3B服务，使用 `--agents CheapAgent` 运行5个Item，停止并确认显存释放。
2. 启动8B服务，复用同一 `run_id`，使用 `--agents MidAgent --resume` 运行同5个Item，停止并确认显存释放。
3. 启动14B服务，继续复用同一 `run_id`，使用 `--agents StrongAgent --resume` 运行同5个Item，停止并确认显存释放。
4. 每个成功logical call立即落盘；失败attempt保留，后续阶段和故障恢复都只补当前指定Agent的缺失记录。
5. 三个Agent各有5条成功记录后，运行`10_validate_selfhosted_checkpoint.py`。

## 真实命令形态

```bash
python scripts/09_run_selfhosted_agent_cache.py \
  --config <SERVER_RESOLVED_CHECKPOINT_CONFIG> \
  --items-path /mnt/outputs/runs/real_pilot_selfhosted_checkpoint_prepare_20260812_002/predictions/checkpoint_inputs/items_train_fit_checkpoint.jsonl \
  --internal-item-manifest /mnt/outputs/runs/real_pilot_selfhosted_checkpoint_prepare_20260812_002/configs/internal_item_split_manifest.checkpoint.csv \
  --output-root /mnt/outputs/runs \
  --run-id real_pilot_selfhosted_ministral3_<UNIQUE_ID> \
  --transport urllib \
  --server-approved \
  --agents <CheapAgent|MidAgent|StrongAgent> \
  [--resume]
```


服务器解析配置中的顶层 `prepared_root` 与 `provider.prepared_root` 必须同时指向 `/mnt/data/semantic_v2`；否则图片相对路径会在错误目录解析。运行输出必须显式使用 `/mnt/outputs/runs`，与数据传输和返回产物目录保持一致。
## PASS条件

必须通过身份、15条canonical、三数据集、图片、Gold隔离、DREsS三维、SAS whole-response、Token、价格、attempt和resume门。真实PASS后仍需用户审批才能执行30 Item。
