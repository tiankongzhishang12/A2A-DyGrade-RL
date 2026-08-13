# 价格与费用上限

## 主成本：Official API-Equivalent Token Cost

```text
input_tokens / 1,000,000 × official_input_price
+
output_tokens / 1,000,000 × official_output_price
```

该指标用于Router预算与跨Agent公平比较，**不是实际API账单**。官方模型页在2026-08-13重新核验显示：3B为输入/输出各$0.10/M Token，8B各$0.15/M，14B各$0.20/M，三者官方上下文均为256K。

官方模型卡未单列 cached input 或 cache-write 价格；因此本项目的API等价代理对这两类Token使用普通输入价，作为显式、保守且可复算的约定，不宣称这是Mistral实际缓存账单。价格快照位于：

```text
configs/pricing/ministral3_official_api_equivalent_20260812.yaml
```

## 辅助成本：Actual Server Allocated Cost

```text
server_hourly_price_usd × request_latency_seconds / 3600
```

只有服务器小时价和分摊方法均写入run配置时才计算；模型加载、空闲和重启开销另列运维开销。

## Canonical与重试

- 每个 `Item × Agent` 只有一个canonical成功成本。
- 所有HTTP attempt写入`logs/call_attempts.jsonl`。
- 失败attempt成本计入`operational_retry_overhead`，不重复写入canonical成本。

## 真实5 Item待审批硬门

```yaml
canonical_calls: 15
agents: [CheapAgent, MidAgent, StrongAgent]
max_attempts_per_logical_call: 2
concurrency: 1
max_model_len: 32768
max_output_tokens: 768
temperature: 0.0
enable_thinking: false
```

服务器每小时价格、最大租用时长和最大实际租金仍为 `PENDING_USER_APPROVAL`，未批准前不得启动服务器阶段。
