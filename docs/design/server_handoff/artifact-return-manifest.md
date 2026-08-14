# 服务器返回产物分阶段契约

> 远程run完成不等于任务完成。每个run都必须生成全文件SHA-256、回传本地相同 `run_id` 并完成本地复核。模型权重、下载缓存、虚拟环境和任何凭据不得回传。服务器租金不属于论文实验指标，pricing manifest只包含Token等价价格。

## 通用目录与必需文件

远程来源：

```text
/root/autodl-tmp/a2a-dygrade/repo/outputs/runs/<run_id>/
```

本地目标：

```text
D:/A2A-DyGrade-RL/outputs/runs/<run_id>/
```

所有Profile至少包含：

```text
configs/run_manifest.json
configs/environment-lock.json（适用时）
configs/model-manifest.json（适用时）
configs/resolved-config.yaml（适用时）
configs/pricing_manifest.yaml（Token价格）
logs/
reports/artifact-sha256.json
reports/artifact-return-summary.md
artifact-return-receipt.json
```

`artifact-sha256.json`必须覆盖run目录内除自身与接收端receipt外的全部文件。`artifact-return-receipt.json`由本地接收端在传输和hash复核后生成，不属于远程源清单。回传不得覆盖已有同名run；如本地已存在，必须先比较manifest并在不一致时停止。

## Profile A：Model Download

适用：3B、8B、14B权重下载和完整性验证。

必须返回：

```text
configs/model-download-manifest.json
configs/model-file-hashes.json
configs/model-identity.json
logs/download.log
reports/download-validation.json
reports/disk-usage.json
reports/artifact-sha256.json
artifact-return-receipt.json
```

当前14B历史文件 `model-14b-download-manifest.json`允许作为Profile A的模型下载manifest；后续统一名称时必须在receipt中记录映射。不得返回模型权重、临时分片或Hugging Face缓存。

## Profile B：Per-Model Smoke

适用：`selfhosted_14b_smoke_*`、`selfhosted_8b_smoke_*`、`selfhosted_3b_smoke_*`。

必须返回：

```text
configs/run_manifest.json
configs/environment-lock.json
configs/model-manifest.json
configs/resolved-config.yaml
configs/prompts_manifest.json
configs/pricing_manifest.yaml
logs/call_attempts.jsonl
logs/service/
logs/gpu/
predictions/text-smoke.jsonl
predictions/multimodal-smoke.jsonl
reports/model-identity-validation.json
reports/usage-validation.json
reports/multimodal-validation.json
reports/memory-latency-summary.csv
reports/smoke-validation.md
reports/artifact-sha256.json
artifact-return-receipt.json
```

## Profile C：Real 5 Item Checkpoint

必须返回：

```text
configs/run_manifest.json
configs/checkpoint_sample_manifest.csv
configs/internal_item_split_manifest.checkpoint.csv
configs/selfhosted_checkpoint_manifest.json
configs/environment-lock.json
configs/model-manifest.json
configs/pricing_manifest.yaml
configs/prompts_manifest.json
configs/prompts/{CheapAgent,MidAgent,StrongAgent}.txt
logs/call_attempts.jsonl
logs/failures.train_fit.jsonl（如有）
logs/service/
logs/gpu/
predictions/checkpoint_inputs/
predictions/agent_cache/train_fit/{CheapAgent,MidAgent,StrongAgent}.jsonl
predictions/agent_cache/train_fit/cache_manifest.csv
reports/selfhosted_checkpoint_validation.json
reports/selfhosted_checkpoint_validation.csv
reports/selfhosted_checkpoint_validation.md
reports/agent_cache_cost_summary.train_fit.csv
reports/agent_cache_audit.train_fit.md
reports/resume_audit.json
reports/artifact-sha256.json
artifact-return-receipt.json
```

本地回传后必须重新运行checkpoint validator；远程与本地结果一致才算Profile C完成。

## Profile D：30 Item Pilot

必须返回：

```text
configs/run_manifest.json
configs/pilot30_input_manifest.json
configs/pilot30-data-transfer-manifest.json
configs/environment-lock.json
configs/model-manifest.json
configs/pricing_manifest.yaml
configs/prompts_manifest.json
logs/call_attempts.jsonl
logs/failures.train_fit.jsonl（如有）
logs/service/
logs/gpu/
predictions/pilot30_inputs/
predictions/agent_cache/train_fit/{CheapAgent,MidAgent,StrongAgent}.jsonl
predictions/agent_cache/train_fit/cache_manifest.csv
reports/qwk_readiness.csv
reports/quality_diagnostics.csv
reports/agent_disagreement.csv
reports/best_fixed_vs_oracle.csv
reports/token_cost_summary.csv
reports/latency_summary.csv
reports/failure_recovery.md
reports/pilot30_report.md
reports/artifact-sha256.json
artifact-return-receipt.json
```

若正式QWK readiness不满足，报告必须包含：

```text
formal_macro_qwk = NA
exploratory_not_formal = true
```

## 明确禁止回传

- 模型权重与Hugging Face缓存；
- Python虚拟环境、容器层缓存；
- Codex认证文件、OAuth Token、API Key；
- SSH私钥、服务器密码；
- Mihomo订阅、节点或代理凭据；
- 未经批准的Dev/Test或全量train数据。
