# 自托管 Ministral 3 Pilot 服务器交接包

## 当前边界

本目录是 **P8 本地准备产物**。截至 2026-08-13：

- 未租用或连接 GPU 服务器；
- 未下载任何模型权重；
- 未安装 CUDA、PyTorch、vLLM、SGLang、Pillow 或其他新依赖；
- 未执行真实模型推理；
- 本地 Fake checkpoint PASS 只证明请求、图片、Schema、Token/成本和 resume 契约成立；
- `30 Item Pilot` 仍未解锁；
- 已冻结本阶段实现提交：`44f3e5fcf825794d4516455b9c7dd3fd3c5bc796`；服务器必须拉取并核对该 commit。当前后续交接元数据提交不会改变已冻结的执行代码、配置、Prompt或测试。

## 服务器阶段顺序

1. 用户审批模型、GPU、时长、费用上限、磁盘路径与联网下载；
2. 本地工作树收敛为干净 Git commit；
3. 服务器拉取固定 commit；
4. 在服务器数据盘创建环境与缓存，不使用 C 盘路径；
5. 按审批 revision 下载三套模型权重；
6. 同步 `data/processed/semantic_v2/` 并核对 `data-transfer-manifest.json`；
7. 顺序启动 3B、8B、14B 服务做身份/usage/图像 smoke；
8. 执行真实 5 Item checkpoint，共15个 canonical 调用；
9. validator PASS 且用户审批后才可执行30 Item Pilot。

## 文件索引

- `model-approval-manifest.yaml`：候选模型与待审批revision/许可/精度。
- `environment-lock.md`：服务器环境、目录、版本冻结要求。
- `data-transfer-manifest.json`：只同步Semantic Readiness、实际引用图片和冻结5 Item checkpoint输入，共10个最小必要文件，逐文件记录大小与SHA-256；Dev/Test数据明确排除。
- `pricing-and-budget.md`：主成本、实际成本和费用硬门。
- `deployment-command-template.md`：部署命令模板；本地未执行。
- `checkpoint-runbook.md`：真实5 Item执行与故障恢复步骤。
- `artifact-return-manifest.md`：服务器必须返回的run产物。

## 禁止内容

交接包不得包含 API key、SSH 私钥、服务器密码、模型权重、本地 `.venv`、真实下载缓存或未审计的Test数据。
