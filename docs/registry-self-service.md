# Registry 自助试注册清单

## 当前结论

四份 ACS 已通过本项目安装的官方 SDK 校验，可以用于**保存草稿**；它们还不能提交
审核。当前正确动作是先用 Leader 做一次草稿保存试验，确认页面生成一条 `DRAFT`
记录后，再依次保存三个 Partner。

`保存`和`提交审核`是两个独立动作：保存调用创建/更新接口，记录状态为 `DRAFT`；
提交审核会把它改为 `PENDING`。本阶段只做前者。

## 第一次操作：只注册 Leader 草稿

1. 打开 [智能体注册页](https://wt.ioa.pub/registry/#/my-agents/index)，点击“注册”。
2. 图标可以暂时不上传。
3. 打开 `registry/acs-drafts/evidence-audit-leader.draft.json`，复制完整 JSON 到
   页面“ACS”框。页面应自动带出名称、版本和能力描述。
4. “是否可派生（本体）”选择“否”。我们的四个运行单元都是普通 Agent，不使用
   ATR 本体派生实体机制。
5. 检查名称为“证链联研总控智能体”，版本为 `0.1.0`。
6. 点击“保存”。**不要点击“提交审核”。**
7. 返回列表，确认状态是 `DRAFT`（或页面中文对应的“草稿”），并截一张包含名称、
   版本和状态的图。

Leader 草稿保存成功后，三个 Partner 使用相同流程：

- `registry/acs-drafts/source-verifier.draft.json`
- `registry/acs-drafts/evidence-grader.draft.json`
- `registry/acs-drafts/contradiction-scout.draft.json`

## 为什么草稿里允许暂时保留占位字段

| 字段 | 草稿阶段 | 审核/批准阶段 |
| --- | --- | --- |
| `aic` | ACS Schema 要求存在，因此使用明确占位值 | Registry 批准后签发并覆盖 |
| `active` | 固定为 `false`，不宣称已经上线 | Registry 按真实状态维护 |
| `lastModifiedTime` | 使用草稿生成时间 | Registry 修改 ACS 时更新 |
| `provider` | 仅保留结构占位 | 批准时替换为账号已核验资料；`verifiedFields` 由注册方写入 |
| `endPoints` | `.invalid` 明确表示不可路由 | 提交审核前必须换成真实公网端点 |

因此，出现 `DRAFT` 只能证明“Registry 接受了草稿记录”，不能证明智能体已上线、
已通过审核、已取得 AIC 或已完成 mTLS。

## 自动预检

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\registry_preflight.py
```

正常结果应是四份文件均显示 `DRAFT_SAVE_READY`，同时显示
`submission: BLOCKED`。后者是保护机制，不是故障。

正式提交审核前运行：

```powershell
.\.venv\Scripts\python.exe scripts\registry_preflight.py --require-submission-ready
```

只要占位 AIC、组织名、`.invalid` 端点或 `environment=draft` 仍存在，该命令就会以
失败状态退出，防止误提交。

## 仍未解决、需要部署后再处理的事项

- 四个真实公网 HTTPS/JSON-RPC 端点；
- Registry 审批和正式 AIC；
- EAB、证书签发及 mTLS 双向验证；
- 梧桐发现、跨智能体真实调用与 AMP 记录。
