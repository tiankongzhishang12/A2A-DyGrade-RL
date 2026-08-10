# 完整 Fixture Smoke 测试契约审核

**审核日期**：2026-07-29  
**审核阶段**：实现前契约审核  
**依据**：`AGENTS.md` 1.4.0、`spec.md`、`plan.md`、`tasks.md`、`contracts/artifact-schemas.md`、`contracts/cli-contract.md`

## 1. 审核结论

**结论：通过，可以进入测试先行实现。**

本结论只表示测试范围、隔离边界、输入输出和失败条件已经明确，不表示 Fixture Smoke 实现或运行已经通过。实现完成后必须再次执行代码、测试、任务真实性和运行产物审核。

## 2. 契约覆盖检查

| 检查项 | 结论 | 证据 |
|---|---|---|
| Fixture 静态输入单独存放 | 通过 | `tests/fixtures/quality_constrained_smoke/` |
| Fixture 配置与正式配置可区分 | 通过 | `configs/experiments/fixture_smoke.yaml`、`fixture_smoke_agents.yaml` |
| 集成测试位置固定 | 通过 | `tests/integration/test_quality_constrained_smoke.py` |
| 持久化产物独立 run | 通过 | `outputs/runs/fixture_smoke_<run_id>/` |
| 禁止写入正式 processed data | 通过 | FR-053、fixture isolation config、CLI 硬约束 |
| Fixture/Formal 机器可判别 | 通过 | `execution_mode=fixture_smoke`、`is_fixture=true`、`formal_eligible=false` |
| 禁止真实/在线 Agent | 通过 | `online_agent_calls=false/0` 与 CLI 非零退出要求 |
| 核心业务逻辑不得分叉 | 通过 | Plan 4.9、FR-054 与 CLI 合约要求复用正式模块 |
| train_fit/train_calibration/Dev/test-like 职责 | 通过 | 端到端阶段与禁止行为计数已定义 |
| 固定参考准入失败淘汰整个 Package | 通过 | 验收场景17、T045A |
| 资源更低但冠军保护失败不得排序 | 通过 | 验收场景17、T045A |
| 相同输入与种子确定性 | 通过 | 验收场景18、T045A |
| 全部失败结果和审计产物保留 | 通过 | Artifact contract 的必需产物清单 |
| 正式 QWK/Bootstrap 规则不被 Smoke 放宽 | 通过 | Fixture 配置继续读取 `configs/quality_protocol.yaml` |

## 3. STOP 校准规则审核

Fixture 配置中的 `risk_limit=0.05` 是在运行结果产生前写入配置的**预注册安全约束**，不是研究者看结果后调整的 STOP 决策边界。真正的 `stop_boundary` 必须由 `train_calibration` 上的程序从候选预测风险中自动产生。

实现必须满足：

1. 候选边界来自当前 checkpoint 的 calibration 风险预测；
2. 以每 dataset 最小 STOP 支持度、单侧95%安全上界和风险上限自动判断可行性；
3. 只在可行候选中按“覆盖率最大 -> 最坏安全上界更低 -> 边界更低”固定词典序选唯一边界；
4. 没有可行边界时输出 failure，不手工放宽 `risk_limit`、支持度或置信水平；
5. calibration 不更新参数、不写 replay、不比较 checkpoint、不产生升级阈值。

## 4. 实现后阻塞性审核项

以下任一项失败，都不能宣布完整 Fixture Smoke 通过：

- `formal_data_reads != 0`；
- `formal_asset_acceptances != 0`；
- `cross_mode_cache_reuse != 0`；
- `online_agent_calls != 0`；
- `calibration_gradient_updates != 0`；
- `calibration_replay_writes != 0`；
- `calibration_checkpoint_rankings != 0`；
- `dev_boundary_updates != 0`；
- `quality_champion_resource_reads != 0`；
- `quality_champion_manual_overrides != 0`；
- `test_like_training_reads != 0`；
- 任一 internal Item/Prompt/Component/Paper overlap、跨 split 引用、非5题或 strict mix 违规；
- 任一候选因资源更低绕过固定参考或 Quality Champion 质量门；
- 重复选择得到不同参考映射、STOP 边界、冠军、保护集合或最终 checkpoint；
- Fixture 结果进入正式实验汇总。

## 5. 当前状态

契约已通过实现前审核；实现与运行结果尚未审核。下一步按 TDD 创建失败测试，再补齐 T048、T049、T050、T050A、T051、T052 与 T045A 所需实现。
