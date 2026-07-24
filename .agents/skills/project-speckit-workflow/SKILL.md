---
name: project-speckit-workflow
description: 按 A2A-DyGrade-RL 项目宪法调度 speckit 工作流。Use when the user asks to “按项目工作流/按 speckit 流程/用 speckit 技能”完成任务，或任务涉及新功能规格、实验方案、实现计划、任务拆分、代码实现、实现后验证、代码评审、任务收敛、spec/plan/tasks 一致性检查。
---

# Project Speckit Workflow

## 核心规则

先读取并遵守仓库根目录 `AGENTS.md`。若 `AGENTS.md` 与 spec-kit 模板、历史摘要或其他文档冲突，以 `AGENTS.md` 为准。

默认使用简体中文产出规格、计划、任务、评审意见和总结。保留必要的英文工程标识，例如 `QWK`、`JSONL`、`Router`、`CAG-CQL`。

默认目标是离线研究实验流水线：优先支持可复现实验、数据划分完整性、Agent 缓存、轨迹构建、训练评价、结果表格、曲线图和 case study。不要把第一版扩展成生产级 Web 服务或在线阅卷平台，除非用户明确要求。

## 路由表

根据用户请求选择最小必要 speckit skill，并在执行前完整读取对应 `SKILL.md`。

| 任务类型 | 调用顺序 |
| --- | --- |
| 新功能、新实验方向、需求还没有 spec | `speckit-specify` -> 需要澄清时 `speckit-clarify` |
| 已有 spec，需要设计实现方案 | `speckit-plan` |
| 已有 plan，需要拆任务 | `speckit-tasks` |
| 已有 `tasks.md`，用户要求开始写代码 | `speckit-implement` |
| 实现后验证规格、计划、任务一致性 | `speckit-verify-run` |
| 只验证已勾选任务是否真实完成 | `speckit-verify-tasks-run` |
| 发现 spec/plan/tasks 与代码不收敛 | `speckit-converge` -> `speckit-implement` |
| 用户要求代码评审或实现风险检查 | `speckit-review-run`，或按问题选择 `speckit-review-code/tests/errors/types/comments/simplify` |
| 用户要求生成检查清单 | `speckit-checklist` |
| 用户要求跨文档质量分析但不改代码 | `speckit-analyze` |

## 阶段门禁

本工作流的目标是减少用户手动选择 speckit skill 的负担，而不是跳过关键产物审阅。默认采用“自动调度 + 人工确认门禁”：

- 生成或更新 `spec.md` 后，必须停止并请用户审阅需求范围、验收标准和未解决澄清项；用户确认后才进入 `speckit-plan`。
- 生成或更新 `plan.md` 后，必须停止并请用户审阅技术方案、实验设计、数据泄漏防护、可复现产物和风险；用户确认后才进入 `speckit-tasks`。
- 生成或更新 `tasks.md` 后，必须停止并请用户审阅任务粒度、依赖顺序、测试与 smoke workflow 覆盖；用户确认后才进入 `speckit-implement`。
- 进入 `speckit-implement` 前必须确认用户已经批准当前 `spec.md`、`plan.md` 和 `tasks.md`，除非用户当次明确要求“全自动继续”“无需确认”“直接实现”或等价表达。
- 验证、评审、收敛类 skill 可以在实现后自动串联，但如果会新增任务或扩大实现范围，必须再次停止并请用户确认。

用户只需要说“继续”“确认 plan”“按这个计划拆任务”“按任务实现”等自然语言即可跨过对应门禁；不要要求用户手动点名下一个 speckit skill。

## 返修循环

若用户对当前阶段产物提出修改意见，必须进入返修循环，而不是继续推进工作流：

- 用户指出 `spec.md` 问题时，只修改需求规格相关内容，并重新汇报新版需求范围、验收标准、非目标、约束和未解决澄清项；用户确认前不得进入 `speckit-plan`。
- 用户指出 `plan.md` 问题时，只修改实现计划和实验方案相关内容，并重新汇报新版技术路线、实验设计、数据泄漏防护、可复现产物和风险；用户确认前不得进入 `speckit-tasks`。
- 用户指出 `tasks.md` 问题时，只修改任务清单相关内容，并重新汇报新版任务分组、依赖顺序、测试覆盖和 smoke workflow；用户确认前不得进入 `speckit-implement`。
- 若返修意见会影响上游文档，例如修改 `tasks.md` 时发现必须调整 `plan.md`，必须先说明影响范围并回到对应上游阶段返修；用户确认新版上游文档后，再重新生成或更新下游文档。
- 每次返修后都要明确说明“已停留在当前阶段等待确认”，除非用户当次明确要求全自动继续。

## 默认闭环

对于“按项目工作流做”“用 speckit 做完这个需求”这类完整任务，按以下闭环执行：

1. 读取 `AGENTS.md` 与当前 feature 的 `spec.md`、`plan.md`、`tasks.md`（若存在）。
2. 若需求未规格化，运行 `speckit-specify`；若仍有关键不确定项，运行 `speckit-clarify`。
3. 若第 2 步生成或更新了 `spec.md`，先汇报关键内容并等待用户确认；确认后再运行 `speckit-plan`。
4. 运行 `speckit-plan` 后必须停止，汇报 `plan.md` 的关键设计选择、实验复现路径、泄漏防护和风险点，等待用户确认。
5. 用户确认 `plan.md` 后，运行 `speckit-tasks`，确保任务围绕可复现实验拆分。
6. 运行 `speckit-tasks` 后必须停止，汇报任务分组、执行顺序、测试覆盖和 smoke workflow，等待用户确认。
7. 用户确认 `tasks.md` 后，运行 `speckit-implement`，实现前先补 schema、校验、fixture 和 smoke test。
8. 运行最小可行测试或 smoke workflow；涉及数据划分时必须先执行 split leakage check。
9. 运行 `speckit-verify-run` 或 `speckit-verify-tasks-run`。
10. 视风险运行 `speckit-review-run` 或专项 review skill。
11. 若验证或评审发现未完成工作，运行 `speckit-converge` 追加任务；追加任务后先请用户确认，再继续实现。

任一门禁阶段收到用户修改意见时，暂停默认闭环并执行“返修循环”；只有用户确认返修后的新版产物，才恢复后续闭环。

## 实验红线

始终防止 `train/dev/test` 泄漏，尤其是 item、prompt、paper、统计信息和缓存泄漏。训练、调参、能力画像、replay buffer 构建默认不得读取 test split；只有 final evaluation 模式可以使用 test cache 做最终评价。

所有 baseline、消融版本和主方法必须共享相同 prepared data、paper budgets、Agent cache 和评价脚本。任何差异必须在 spec、plan、配置或报告中显式记录。

每次实验运行必须使用唯一 `run_id`，并将配置快照、日志、预测、checkpoint、报告和图写入同一个 `outputs/runs/<run_id>/`。

## 文件放置

遵守 `AGENTS.md` 的目录职责：

- 实验模块代码放入 `src/a2a_dygrade_rl/<module>/`。
- 端到端编排脚本放入 `scripts/`，不堆业务逻辑。
- 测试放入 `tests/unit/`、`tests/integration/` 或 `tests/fixtures/`。
- spec-kit 文档放入 `specs/` 和 `.specify/`。
- AI skill 只放入 `.agents/skills/`。
- 数据放入 `data/`；运行产物放入 `outputs/runs/<run_id>/`。
- 不要把实验结果、日志、checkpoint 或数据文件直接放在仓库根目录。

## 汇报格式

工作中简短说明当前调用了哪些 speckit skill 以及原因。最终回复用简体中文总结：已调用流程、改动文件、验证结果、剩余风险或下一步。
