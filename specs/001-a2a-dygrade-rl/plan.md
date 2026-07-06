# 实现计划：A2A-DyGrade-RL 实验流水线

**分支**：`001-a2a-dygrade-rl` | **日期**：2026-07-04 | **规格**：[spec.md](./spec.md)

**输入**：来自 `specs/001-a2a-dygrade-rl/spec.md` 的功能规格

## 摘要

构建一套可复现的 A2A-DyGrade-RL 离线研究流水线。该流水线负责将公开自动评分数据集准备为 item-level 和 paper-level 产物，缓存五类 Agent 输出，推导难度标签和 Agent 能力画像，构建离线路由轨迹，训练通信感知且预算感知的路由策略，并与固定模型、静态难度、不确定性升级和预算感知 baseline 比较。

实现顺序优先保证可运行 smoke workflow，再扩展到完整数据集缓存和完整实验表格。

## 技术上下文

**语言/版本**：Python 3.11+

**主要依赖**：PyTorch 用于路由模型和离线强化学习；pandas/numpy/scikit-learn 用于表格处理和指标；pydantic 或 dataclasses 用于 schema；PyYAML 用于配置；tqdm 用于批处理进度；matplotlib 用于绘图；pytest 用于验证。

**存储**：使用 `data/` 保存数据型产物，使用 `outputs/runs/<run_id>/` 保存每次实验运行产物；JSONL 存储记录和轨迹，CSV 存储结果表，YAML 存储配置快照，checkpoint 文件存储训练策略。

**测试**：pytest 单元测试和集成测试；smoke experiment 命令必须能在小 fixtures 上验证端到端 data-to-report 路径。

**目标平台**：Windows 或 Linux 本地研究工作站与可脚本化批处理环境。

**项目类型**：单体 Python 研究流水线，提供 CLI 脚本。

**性能目标**：smoke run 可在不调用实时模型的样本 fixtures 上完成；完整实验复用 Agent caches，Router 训练和评价阶段不重复调用模型。

**约束**：不增加人工标签；主 split 必须防止 prompt-level leakage；所有报告必须能从保存的输入、配置、随机种子、predictions 和 logs 复现；实验输出不得散落在仓库根目录或旧式 `outputs/reports`、`outputs/logs` 等平铺目录。

**规模/范围**：三个公开数据集；每张合成 paper 5 到 8 个 item；五类 Agent 角色；六个主方法；五个消融版本；七个 Cost-QWK cost-penalty points。

## Constitution 检查

*门禁：Phase 0 research 前必须通过；Phase 1 design 后再次检查。*

项目最高规则统一维护在仓库根目录 `AGENTS.md`，`.specify/memory/constitution.md` 只作为 spec-kit 指针。本计划应用以下门禁：

- 可复现性：每个主要阶段必须产生保存产物。
- 数据完整性：主测试评价中不得发生 prompt 泄漏。
- 范围纪律：第一版是离线研究流水线，不是生产级阅卷服务。
- 评价公平性：所有方法必须共享相同 prepared data、budgets、Agent cache 和 metrics。
- 文件管理：代码、文档、数据、运行日志和实验结果必须进入 `AGENTS.md` 规定的目录；每次运行必须写入 `outputs/runs/<run_id>/`。

门禁状态：通过。

## 项目结构

### 文档结构（本功能）

```text
specs/001-a2a-dygrade-rl/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── artifact-schemas.md
│   └── cli-contract.md
└── tasks.md
```

### 源代码结构（仓库根目录）

```text
configs/
├── dataset.yaml
├── agents.yaml
├── router.yaml
├── cag_cql.yaml
├── experiment.yaml
└── experiments/

data/
├── raw/
├── processed/
└── trajectories/

docs/
├── design/
├── paper/
└── logs/

prompts/
├── cheap_scorer.txt
├── mid_scorer.txt
├── strong_scorer.txt
├── evidence_agent.txt
└── arbitrator_agent.txt

src/
└── a2a_dygrade_rl/
    ├── datasets/
    ├── agents/
    ├── a2a/
    ├── graph/
    ├── router/
    ├── rl/
    ├── baselines/
    ├── evaluation/
    └── utils/

scripts/
├── 01_build_items.py
├── 02_build_papers.py
├── 03_run_agent_cache.py
├── 04_build_difficulty_labels.py
├── 05_build_trajectories.py
├── 06_train_cag_cql.py
├── 07_eval_baselines.py
├── 08_eval_ablation.py
└── 09_plot_cost_qwk_curve.py

outputs/
└── runs/
    └── <run_id>/
        ├── configs/
        ├── logs/
        ├── predictions/
        ├── checkpoints/
        ├── reports/
        └── figures/

tests/
├── unit/
├── integration/
└── fixtures/
```

**结构决策**：采用单体 Python 项目，使用 `src/a2a_dygrade_rl/` 包结构承载实验模块，使用 `scripts/` 做阶段编排，使用 `outputs/runs/<run_id>/` 隔离每次运行产物。这样可以独立实现数据层、Agent 缓存层、轨迹层、模型层和评价层，同时保持实验可从命令行复现，并避免代码、日志和实验结果放错位置。

## 复杂度跟踪

当前没有需要说明的 constitution 违规。
