# 证据登记表

本表只登记已经实际完成并可复核的证据，不用计划或推测替代结果。

| ID | 日期 | 证据对象 | 状态 | 文件/链接 | 可支持的结论 | 限制 |
|---|---|---|---|---|---|---|
| E-001 | 2026-09-22 | 赛题PDF | 已核对 | `E:/AIC竞赛/互联赛题.pdf` | 官方规则、评分、材料与时间线 | 后续通知可能更新 |
| E-002 | 2026-09-22 | 梧桐公开使用指南 | 已核对 | `https://wt.ioa.pub/docs.html` | SDK/WIT、注册、证书、发现的公开流程 | 未进入账号登录态 |
| E-003 | 2026-09-22 | ACPs-community v2.2.0 | 已核对并完成本地协议验证 | `https://github.com/AIP-PUB/ACPs-community/tree/v2.2.0` | 当前公开SDK、CLI、Demo和协议文档结构；Direct RPC 可在本机运行 | 本地验证未等同于梧桐正式注册接入 |
| E-004 | 2026-09-22 | WIT v2.1.0 官方发布包 | 校验通过 | `vendor/wit/v2.1.0/` | 两个 wheel 的 SHA-256 与官方 manifest 一致 | 仅证明下载完整性和版本对应关系 |
| E-005 | 2026-09-22 | WIT 官方发布预检 | 通过 | `evidence/runs/2026-09-22-local-foundation/validation.md` | `acpsSdkVersion=2.2.0`、`witVersion=2.1.0`、`aipPersistence=passed` | 未调用外部模型服务 |
| E-006 | 2026-09-22 | 本地 AIP Direct RPC 闭环 | 通过 | `src/platform_lab/`、`evidence/runs/2026-09-22-local-foundation/validation.md` | Leader/Partner 启动、完成和产品返回均通过自动断言 | 身份绑定为本地开发而关闭，未使用 AIC/EAB/mTLS |
| E-007 | 2026-09-23 | Registry 登录态“我的智能体”页面 | 用户截图核对 | `docs/registry-ui-observations.md` | 登录成功；存在注册入口、查询条件、审核状态和处理意见字段 | 尚未进入注册表单；原截图含账号名称，未复制进仓库 |
| E-008 | 2026-09-23 | 梧桐官方使用指南 | 当前页面核对 | `https://wt.ioa.pub/docs.html`、`docs/development-path-decision.md` | 官方提供 SDK 与 WIT 两条开发路线；确认 SDK 注册、AIC、EAB、mTLS 顺序 | 指南未替代登录态下实际提交流程验证 |
| E-009 | 2026-09-23 | 证链联研数据契约与聚合器 | 5项测试通过 | `src/evidence_mesh/`、`tests/test_evidence_mesh.py`、`evidence/runs/2026-09-23-topic-contract/validation.md` | 缺失、冲突、非法置信度和未知 Claim 均有确定性处理 | 尚未实现 AIP Partner，也没有真实应用指标 |
| E-010 | 2026-09-23 | 三 Partner 与并行 Leader | 18项测试通过 | `src/evidence_mesh/`、`tests/`、`evidence/runs/2026-09-23-aip-partners/validation.md` | 三个 Partner 通过 AIP RPC 返回结构化产品，Leader 保留 taskId 并 fail-closed 裁决 | 使用内存传输且关闭身份绑定；尚未完成 Discovery、mTLS、AMP 与公网部署 |
| E-011 | 2026-09-23 | 合成种子基准 v0.1 | 首次基线冻结 | `benchmarks/evidence_seed_v0.1.jsonl`、`evidence/runs/2026-09-23-seed-benchmark/baseline.md` | 来源21/21、证据14/21、冲突19/21；定位同义改写与间接证据短板 | 标签为机器草拟、待人工盲审；不得表述为真实应用准确率 |
| E-012 | 2026-09-25 | 跨进程产品 MVP | 通过 | `src/evidence_mesh/leader_app.py`、`evidence/runs/2026-09-25-cross-process-mvp/validation.md` | 用户请求经 Leader 并行调用三个独立 AIP Partner，返回 Evidence Passport 和三个 taskId | 本机联调、身份绑定关闭；尚未接入 Registry/Discovery/mTLS/AMP |
| E-013 | 2026-09-25 | 非技术用户网页 MVP | 通过 | `src/evidence_mesh/static/`、`tests/test_leader_app.py`、`evidence/runs/2026-09-25-web-ui/validation.md` | 中文表单可提交 Claim 与证据片段，Leader 返回可视化 Evidence Passport；21项自动测试通过 | 仅完成本地页面与接口验证，尚未公网部署或通过梧桐平台验收 |
| E-014 | 2026-09-25 | 四智能体 ACS 预注册草稿 | SDK 校验通过 | `registry/acs-drafts/`、`registry/README.md`、`evidence/runs/2026-09-25-acs-drafts/validation.md` | 四份 ACS 符合本地官方 `acps-sdk 2.2.0` 数据模型；全量22项测试通过 | AIC、提供者、正式端点和 mTLS 尚未取得；草稿不能原样提交或视为注册完成 |
| E-015 | 2026-09-25 | 部署与身份绑定准备 | 代码与原生跨进程验证通过 | `src/evidence_mesh/runtime_config.py`、`deploy/`、`docs/organizer-questions.md`、`evidence/runs/2026-09-25-deployment-prep/validation.md` | AIC、预期对端、证书路径和身份绑定可由环境注入且缺失时 fail-closed；25项测试和四进程回归通过 | 本机无 Docker；尚无真实 AIC、证书、公网域名，未完成真实 mTLS 或平台验证 |

