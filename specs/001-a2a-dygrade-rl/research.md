# V1.6 自托管 Ministral 3 Pilot 本地准备研究决策

## 决策1：首轮候选模型族

- **Decision**：Cheap/Mid/Strong分别使用Ministral 3 Instruct 3B/8B/14B BF16，同一Prompt、Schema与解码参数。
- **Rationale**：三档同家族且均支持图文输入，部署规模相对可控，适合先验证动态路由的成本—能力分层；不混入Qwen或MoE以减少Tokenizer、Processor和训练来源混杂。
- **Alternatives considered**：Qwen3.5 2B/4B/27B作为能力跨度更大的备用族；不在同一正式三档中混用两家模型。

## 决策2：本地与服务器边界

- **Decision**：P1–P8仅做本地实现、Mock/Fixture、审计与交接材料；模型权重、推理依赖和GPU运行推迟到单独审批的服务器阶段。
- **Rationale**：避免按小时服务器被开发调试消耗，遵守依赖/下载审批和先Smoke后真实调用规则。
- **Alternatives considered**：直接租服务器现场开发，因成本、环境漂移和复现风险被拒绝。

## 决策3：服务协议

- **Decision**：新增OpenAI-compatible Chat Completions客户端，并保留旧Responses客户端用于历史CLIProxy证据。
- **Rationale**：vLLM/SGLang更稳定地暴露`/v1/chat/completions`；独立客户端避免破坏旧Pilot行为。
- **Alternatives considered**：复用Responses客户端或绑定某个推理引擎私有SDK，前者协议不符，后者增加依赖和平台耦合。

## 决策4：TIFF处理

- **Decision**：使用标准库实现当前ASAP-SAS两张LZW RGB TIFF的确定性无损解码与PNG编码；不安装Pillow。
- **Rationale**：原资产仅4张且TIFF编码特征已审计，标准库实现可满足本轮固定数据契约并保持依赖安装数为0。
- **Alternatives considered**：安装Pillow、服务器端直接发送TIFF或裁剪/转JPEG；分别因审批、兼容性和有损/语义风险被拒绝。

## 决策5：Token与价格语义

- **Decision**：主成本为官方API等价Token成本，实际服务器分摊成本为并列辅助指标；二者都不称为Actual API Bill。
- **Rationale**：统一Router预算单位，同时诚实反映自托管实际支付的是服务器租金。正式Token只接受服务端usage；图片分解缺失会阻塞真实checkpoint。
- **Alternatives considered**：字符数估算、Tokenizer离线估算或只用服务器时长，均不能同时满足多模态精确Token和跨模型可比性。

## 决策6：重试记账

- **Decision**：稳定logical call对应唯一canonical成功成本；所有HTTP尝试进入独立attempt账本，失败费用进入operational overhead。
- **Rationale**：避免网络波动和resume导致同一Item成本被重复计入论文实验主账本，同时保留真实运维开销。
- **Alternatives considered**：把全部attempt求和为Item成本或删除失败记录，分别会污染公平比较或破坏审计。

## 决策7：5 Item选择

- **Decision**：从train_fit strict Paper确定性选择一份覆盖三数据集且至少有一个图片Item的Paper，选择逻辑不得读取Gold。
- **Rationale**：同时验证Paper级5题、三类评分语义和多模态链路；固定Paper比从不同Paper拼5题更贴近后续episode契约。
- **Alternatives considered**：任意平衡抽5题或按Gold挑难题，前者破坏Paper语义，后者产生统计泄漏。

---

# 研究决策：A2A-DyGrade-RL 实验流水线

## 决策：使用离线文件型研究流水线

**理由**：本项目是实验工作流，不是生产级阅卷服务。JSONL、CSV、YAML、日志和 checkpoint 让中间产物可检查、可复现。

**考虑过的替代方案**：

- 数据库驱动流水线：第一版拒绝，因为会增加运维复杂度，但不能直接增强研究问题。
- Web 服务：拒绝，因为当前目标是可复现实验执行，不是交互式部署。

## 决策：先使用确定性 fixtures 和 smoke workflow

**理由**：如果使用实时 LLM 调用，Agent 缓存可能成本较高。fixtures 可先验证 schema、metrics、trajectories、action masks 和 report generation，再进行全量 Agent 运行。

**考虑过的替代方案**：

- 先做完整实时 Agent 流水线：拒绝，因为失败成本高且难定位。
- 只做 metrics 原型：拒绝，因为无法验证 routing states、actions、logs 或 trajectories。

## 决策：主评价使用 prompt-level 和 paper-level split

**理由**：主要有效性风险是同一 prompt 或题目泄漏到训练集和测试集。prompt-level 与 paper-level split 能让路由性能报告更可信。

**考虑过的替代方案**：

- item-level random split：可用于诊断，但不足以支撑主实验结论。
- dataset-level holdout：更严格，但第一版可能因数据集差异过大而变得脆弱。

## 决策：以 Agent cache 作为 LLM 调用和离线 RL 的边界

**理由**：一旦缓存所有 Agent 输出，Router 训练、消融和 baseline 评价都可以公平重复。这样也能稳定统计 cost 和 latency。

**考虑过的替代方案**：

- 训练策略时实时调用 Agents：拒绝，因为这会破坏离线 RL 和复现性。
- 只缓存部分 Agent：拒绝，因为难度标签、能力画像和反事实轨迹都需要多个 Agent 输出。

## 决策：围绕可独立测试的实验故事生成任务

**理由**：数据准备、Agent 缓存和策略评价是可分离增量。MVP 可以先完成数据准备故事；后续故事再加入缓存、路由和评价。

**考虑过的替代方案**：

- 只按模块顺序拆任务：拒绝，因为它会模糊每个任务解锁的研究结果。
