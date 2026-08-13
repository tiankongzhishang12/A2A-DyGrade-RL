# 服务器返回产物清单

每个真实run必须完整同步：

```text
outputs/runs/<run_id>/
├── configs/
│   ├── agents.resolved.yaml
│   ├── pricing_manifest.yaml
│   ├── prompts_manifest.json
│   ├── prompts/{CheapAgent,MidAgent,StrongAgent}.txt
│   ├── agent_cache_manifest.json
│   ├── context_support_catalog.json
│   ├── environment-lock.json
│   └── model-weight-manifest.json
├── logs/
│   ├── call_attempts.jsonl
│   ├── failures.train_fit.jsonl（如有）
│   └── service/GPU logs
├── predictions/agent_cache/train_fit/
│   ├── CheapAgent.jsonl
│   ├── MidAgent.jsonl
│   ├── StrongAgent.jsonl
│   └── cache_manifest.csv
└── reports/
    ├── selfhosted_checkpoint_validation.json
    ├── selfhosted_checkpoint_validation.csv
    ├── selfhosted_checkpoint_validation.md
    ├── agent_cache_cost_summary.train_fit.csv
    └── agent_cache_audit.train_fit.md
```

同步后本地必须再次验证所有文件hash、manifest身份和报告可重算性。不要只返回汇总截图或终端输出。
