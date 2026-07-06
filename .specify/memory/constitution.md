# A2A-DyGrade-RL spec-kit 宪法入口

本项目的最高项目规则和完整宪法统一维护在仓库根目录的 `AGENTS.md`。

使用 spec-kit 生成规格、计划、任务、检查清单、实现或验证结果时，必须先读取并遵守：

```text
AGENTS.md
```

本文件只作为 spec-kit 的入口指针存在，避免 `AGENTS.md` 与 `.specify/memory/constitution.md` 维护两套互相漂移的规则。

若本文件与 `AGENTS.md` 出现不一致，以 `AGENTS.md` 为准。

当前有效规则摘要：

- 默认使用简体中文生成计划、方案、规格、任务、报告和评审意见。
- 项目目标是写代码、跑实验、产出可信实验结果，并支撑论文写作。
- 第一版不做生产级 Web 服务、在线阅卷系统、用户平台、权限系统或在线 API 服务。
- 必须严格划分 `train/dev/test`，防止 item、prompt、paper、统计信息和 cache 泄漏。
- 测试集只允许用于最终评价，不得参与训练、调参、能力画像拟合或 replay buffer 构建。
- 所有 baseline、消融版本和主方法必须共享相同 prepared data、paper budgets、Agent cache 和评价脚本。
- 必须先通过 fixture 或小样本 smoke workflow，再进入全量实验。

**版本**：1.1.0 | **指向规则版本**：AGENTS.md 1.4.0 | **最后修订**：2026-07-06
