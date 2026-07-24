# A2A-DyGrade-RL 项目宪法与 AI 协作规则

本文件是本项目的**最高项目规则 / 单一事实来源**。无论是否调用 spec-kit，AI 协作者都必须优先读取并遵守本文件。

`.specify/memory/constitution.md` 仅作为 spec-kit 入口指针存在；若两者出现不一致，以本文件为准。

## 核心原则

### I. 简体中文优先

本项目后续由 AI 生成的规格、计划、任务清单、实验方案、报告、代码评审意见、总结和协作文档，默认必须使用**简体中文**。

文件路径、命令、脚本名、类名、函数名、变量名、配置键、数据字段、模型名、指标名、论文方法名和通用技术缩写可以保留英文，例如 `Agent`、`Router`、`QWK`、`JSONL`、`Cost-QWK`、`CAG-CQL`、`scripts/01_build_items.py`。

如果用户明确要求英文或中英双语，则按用户当次要求执行。修改或生成 spec-kit 文档时，正文、标题、任务描述、验收标准和备注应使用简体中文，只保留必要工程标识为英文。

### II. 论文实验成果优先

本项目的核心目标是：**写代码、跑实验、产出可信实验结果，并支撑后续论文写作**。

所有实现选择都应服务于论文实验主线：验证 A2A-DyGrade-RL 是否改善自动阅卷场景中的评分质量、成本、延迟、通信效率和 Cost-QWK Pareto Frontier。

第一阶段优先保证实验设计、数据处理、Agent 缓存、轨迹构建、训练评价、结果表格、曲线图和 case study 可复现。

默认不把第一版实现扩展为生产级 Web 服务、在线阅卷系统、教师端平台、学生端平台、用户登录系统、权限系统或在线 API 服务。如果某个需求不能直接帮助实验复现、指标计算、结果分析或论文写作，应默认推迟到论文实验完成之后再考虑。

### III. 可复现实验优先

每个主要实验阶段都必须保存输入、配置、随机种子、中间产物、预测结果和日志，使报告中的表格和指标可以从已保存产物重新计算。

实验产物应优先采用可检查、可版本化的文件形式，例如 `JSONL`、`CSV`、`YAML`、日志文件和 checkpoint。任何重要表格、曲线或 case study 都必须能追溯到对应 predictions、logs 和 config。

### IV. 数据集划分与数据完整性优先

主实验必须严格划分 `train/dev/test`。测试集数据不得以任何形式混入训练集、验证集、难度标签拟合、Agent 能力画像拟合、Router 训练、超参数选择或 prompt/策略调试过程。

数据集处理只能进行确定性清洗、规范化、划分和 paper-level 重组，不引入额外人工标签。

必须同时防止以下泄漏：

- **Item 泄漏**：同一个 `item_id` 不得同时出现在 `train/dev/test` 任意两个 split 中。
- **Prompt 泄漏**：同一原始题目、同一 prompt group 或高度等价 prompt 不得同时出现在训练相关 split 与 test split 中。
- **Paper 泄漏**：同一 paper 或由同一测试 item 组成的 paper 不得参与训练轨迹构建。
- **统计泄漏**：difficulty labels、Agent capability profiles、normalization statistics、阈值、校准参数和超参数选择不得使用 test split 的 gold score 或预测结果。
- **缓存泄漏**：允许为 test split 生成 Agent cache 以供最终评价，但这些 test cache records 不得参与训练、调参、能力画像拟合或离线 replay buffer 构建。

数据划分必须生成可审计的 split manifest，记录每个 `item_id`、prompt group、paper_id、split、随机种子和构造规则版本。所有训练、调参和画像构建脚本必须默认拒绝读取 test split，除非脚本明确处于 final evaluation 模式。

### V. 公平评价

所有 baseline、消融版本和 A2A-DyGrade-RL 主方法必须共享相同 prepared data、paper budgets、Agent cache 和评价脚本。

任何方法特有的额外信息、预算差异、训练数据差异、调参策略差异或评价设置差异都必须显式记录。实验报告必须声明 `train/dev/test` 划分策略，并记录 test split 只用于最终评价。

### VI. 先 Smoke Test 后全量实验

在运行完整数据处理、实时 Agent 缓存或完整训练前，必须先保证 fixture 或小样本 smoke workflow 可以端到端完成。

进入实现前，应优先完成 schema、校验、fixture 和 smoke test。数据处理阶段必须先实现并运行 split leakage check，确认 item、prompt、paper 和统计信息没有跨 split 泄漏后，才允许进入 Agent 缓存和 Router 训练阶段。

## 实施范围

- 第一版默认实现为离线研究实验流水线，不做生产级 Web 服务或在线阅卷系统。
- 计划和任务应围绕可独立验证的实验阶段拆分：数据构建、Agent 缓存、难度/能力建模、轨迹构建、Router 训练、baseline/消融评价、报告生成和论文结果分析。
- 如果某个功能不能直接帮助实验复现、指标计算、结果解释或论文写作，应默认推迟，不进入第一版实现范围。

## 开发流程

- 规格、计划和任务生成后，应检查是否存在英文模板残留、未替换占位符和未解决澄清项。
- spec-kit 文档和普通项目文档都必须遵守本文件；`.specify/memory/constitution.md` 只用于提醒 spec-kit 回到本文件。
- 实现后应使用 spec-kit 的 verify、verify-tasks 或 review 流程检查任务完成度、规格一致性和代码质量。

## 仓库文件管理规范

AI 在本仓库中创建、移动或修改文件时，必须遵守以下目录职责。不能因为方便而把写好的代码、日志、实验结果或文档放在错误位置。

### 标准目录结构

```text
D:/A2A-DyGrade-RL/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .agents/
│   └── skills/
├── .specify/
│   └── memory/constitution.md
├── specs/
│   └── 001-a2a-dygrade-rl/
├── docs/
│   ├── design/
│   ├── paper/
│   └── logs/
├── configs/
│   ├── dataset.yaml
│   ├── agents.yaml
│   ├── router.yaml
│   ├── cag_cql.yaml
│   └── experiments/
├── prompts/
├── src/
│   └── a2a_dygrade_rl/
│       ├── datasets/
│       ├── agents/
│       ├── a2a/
│       ├── graph/
│       ├── router/
│       ├── rl/
│       ├── baselines/
│       ├── evaluation/
│       └── utils/
├── scripts/
├── data/
│   ├── raw/
│   ├── processed/
│   └── trajectories/
├── outputs/
│   └── runs/
│       └── <run_id>/
│           ├── configs/
│           ├── logs/
│           ├── predictions/
│           ├── checkpoints/
│           ├── reports/
│           └── figures/
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/
```

### 文件放置硬性约束

- 实验模块代码只能进入 `src/a2a_dygrade_rl/<module>/`。
- 端到端命令脚本只能进入 `scripts/`，脚本只做流程编排，不堆业务逻辑。
- 测试代码只能进入 `tests/unit/`、`tests/integration/`、`tests/fixtures/`。
- spec-kit 文件只能进入 `specs/` 和 `.specify/`。
- AI skills 只能进入 `.agents/skills/`，不得放实验模块代码。
- 开发文档、设计说明、论文草稿、人工开发日志只能进入 `docs/`。
- 原始数据、处理后数据和轨迹数据只能进入 `data/`。
- 运行日志、预测结果、checkpoint、报告和图只能进入 `outputs/runs/<run_id>/`。
- 禁止把实验结果、日志、checkpoint、数据文件直接放在仓库根目录。
- 禁止把业务代码写进 `scripts/`、`docs/`、`specs/`、`.agents/` 或 `.specify/`。
- 禁止把 test split 相关训练产物放入训练 run 的 replay buffer 或能力画像目录。

### 依赖与环境安装规则

AI 在执行任务时，如果发现本机缺少依赖包、软件、运行时、开发工具、模型权重、外部数据集或其他环境组件，不得直接下载安装、自动联网拉取或静默修改系统环境，必须先向用户说明缺失内容、用途、安装位置和可能影响，并获得用户明确同意后才可以继续。

凡是用于本项目论文实验、数据处理、模型训练、Agent 缓存、评价复现或论文结果生成的依赖包、软件、运行时、虚拟环境、模型权重和数据缓存，默认不得安装或下载到 C 盘；必须优先放在 D 盘的项目目录、专用实验目录或用户明确指定的 D 盘路径下，并在相关配置、脚本或运行日志中记录路径。

### 运行产物规则

每次实验运行必须传入或生成唯一 `run_id`。该次运行的配置快照、日志、预测结果、checkpoint、报告和图必须全部写入同一个 `outputs/runs/<run_id>/` 目录，不得覆盖其他 run。

仓库结构规范测试通过后，如果该测试脚本只用于一次性验证目录规范落地，必须删除该临时测试脚本以及测试过程中产生的所有临时数据。

## 治理

本文件优先于自动生成模板、spec-kit constitution 占位内容和历史摘要文件。若用户当次明确要求英文、双语或其他格式，则以用户当次要求为准，但应在相关文档中记录该例外。

**版本**：1.4.0 | **通过日期**：2026-07-04 | **最后修订**：2026-07-06
