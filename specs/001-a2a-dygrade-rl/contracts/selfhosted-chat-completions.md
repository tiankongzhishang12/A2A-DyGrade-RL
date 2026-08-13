# 自托管 Chat Completions 接口契约

## Endpoint

```text
POST {base_url}/chat/completions
```

配置中的 `base_url` 必须以 `/v1` 结束或由客户端规范化；密钥只从环境变量读取。

## Request

```json
{
  "model": "mistralai/Ministral-3-3B-Instruct-2512-BF16",
  "messages": [
    {"role": "system", "content": "<统一评分Prompt>"},
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "<模型可见Item JSON>"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
      ]
    }
  ],
  "temperature": 0.0,
  "max_tokens": 768,
  "response_format": {
    "type": "json_schema",
    "json_schema": {
      "name": "a2a_dygrade_agent_output_v2",
      "strict": true,
      "schema": "<AGENT_RESPONSE_SCHEMA_V2>"
    }
  }
}
```

硬性约束：

- body 递归不存在禁用 Gold 键；
- 图片只能来自校验通过的 source asset；
- 不发送本地绝对路径；
- 三个 Agent 除 `model` 外请求语义完全相同；
- `temperature=0`，不启用 Thinking。

## Response

```json
{
  "id": "chatcmpl-...",
  "model": "mistralai/Ministral-3-3B-Instruct-2512-BF16",
  "choices": [
    {
      "index": 0,
      "finish_reason": "stop",
      "message": {
        "role": "assistant",
        "content": "{...AgentResponseV2 JSON...}"
      }
    }
  ],
  "usage": {
    "prompt_tokens": 1500,
    "completion_tokens": 180,
    "total_tokens": 1680,
    "prompt_tokens_details": {
      "text_tokens": 1200,
      "image_tokens": 300,
      "cached_tokens": 0
    }
  }
}
```

客户端必须兼容标准字段别名：`prompt_tokens/input_tokens`、`completion_tokens/output_tokens`。正式响应必须包含正数总 Token 并自洽；图像 checkpoint 必须包含可审计视觉 Token 分解。

## Error contract

- HTTP 408/409/429/500/502/503/504：可按冻结次数重试；
- 其他 HTTP 错误：终止；
- 响应 `model` 必须与请求 ID 精确相等；任何后缀、别名或替换，以及 usage 缺失/不自洽、JSON 非法、分数/trait 非法：终止该 attempt 并记录失败；
- 所有 attempt 写入审计；active cache 只保留最终 canonical 状态。
