# 真实5 Item Checkpoint Runbook

## 研究边界

真实5 Item只验证模型身份、请求/响应契约、图片、Token、成本账本、attempt和resume链路，不用于证明正式评分准确率或QWK。真实PASS后仍需用户审批才能构建30 Item专用输入并执行Pilot。

## 前置门禁

- 最新文档提交已同步到远程，工作树干净。
- `frozen_implementation_commit`、`core_handoff_contract_commit`、`desktop_smoke_status_commit`与 `final_document_convergence_commit`均已记录。
- T113A的 `data-transfer-receipt.json.status=PASS`，10个最小文件全部hash匹配。
- `semantic_readiness_manifest.json.status=PASS`。
- 3B、8B、14B三个revision均已冻结，三个模型Smoke及本地回传复核均PASS。
- 真实run配置中的Token价格、调用上限、Prompt、Schema和输入manifest已冻结。
- `server_hourly_price_usd=null`；服务器租金不进入论文成本。
- 服务端返回精确 `model` 与有效 `usage`，图像请求含文本/视觉Token分解。

## 固定目录

```text
repo_root: /root/autodl-tmp/a2a-dygrade/repo
prepared_root: /root/autodl-tmp/a2a-dygrade/repo/data/processed/semantic_v2
output_root: /root/autodl-tmp/a2a-dygrade/repo/outputs/runs
prepare_run: /root/autodl-tmp/a2a-dygrade/repo/outputs/runs/real_pilot_selfhosted_checkpoint_prepare_20260812_002
```

## 固定输入

```text
paper: paper_train_fit_00621
items: 5
agents: CheapAgent, MidAgent, StrongAgent
canonical calls: 15
```

如果服务器重新构建checkpoint，必须用相同源hash、种子和选择规则得到完全相同的Paper/Item列表，否则停止。

## 顺序执行

1. 启动3B服务，核验 `/v1/models`，使用 `--agents CheapAgent` 运行5个Item；停止服务并确认显存释放。
2. 启动8B服务，核验身份，复用同一 `run_id`，使用 `--agents MidAgent --resume` 运行同5个Item；停止并确认显存释放。
3. 启动14B服务，核验身份，继续复用同一 `run_id`，使用 `--agents StrongAgent --resume` 运行同5个Item；停止并确认显存释放。
4. 每个成功logical call立即落盘；失败attempt保留，只补当前Agent缺失记录。
5. 三个Agent各有5条成功记录后运行validator。

## 真实命令形态

```bash
cd /root/autodl-tmp/a2a-dygrade/repo

python scripts/09_run_selfhosted_agent_cache.py \
  --config <SERVER_RESOLVED_CHECKPOINT_CONFIG> \
  --items-path /root/autodl-tmp/a2a-dygrade/repo/outputs/runs/real_pilot_selfhosted_checkpoint_prepare_20260812_002/predictions/checkpoint_inputs/items_train_fit_checkpoint.jsonl \
  --internal-item-manifest /root/autodl-tmp/a2a-dygrade/repo/outputs/runs/real_pilot_selfhosted_checkpoint_prepare_20260812_002/configs/internal_item_split_manifest.checkpoint.csv \
  --output-root /root/autodl-tmp/a2a-dygrade/repo/outputs/runs \
  --run-id real_pilot_selfhosted_ministral3_<UNIQUE_ID> \
  --transport urllib \
  --server-approved \
  --agents <CheapAgent|MidAgent|StrongAgent> \
  [--resume]
```

服务器解析配置中的顶层 `prepared_root` 与 `provider.prepared_root` 必须同时为：

```text
/root/autodl-tmp/a2a-dygrade/repo/data/processed/semantic_v2
```

## 远程PASS条件

必须通过模型身份、15条canonical、三数据集、图片、Gold隔离、DREsS三维、SAS whole-response、Token价格、attempt唯一性、调用硬门和resume幂等性。

## 回传与本地复核

远程validator结束后必须：

1. 生成 `reports/artifact-sha256.json`；
2. 按 `artifact-return-manifest.md` 的Real 5 Item Profile回传本地相同 `run_id`；
3. 本地核对全部hash；
4. 本地重新运行 `scripts/10_validate_selfhosted_checkpoint.py`；
5. 远程和本地PASS/FAIL一致后才提交用户审批。

任一步失败时，30 Item调用数必须为0。
