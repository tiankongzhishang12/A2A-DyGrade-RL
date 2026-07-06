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
