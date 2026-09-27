# 梧桐 Registry 注册材料

本目录保存“证链联研”四个智能体的 ACS 预注册草稿。草稿依据
`ACPs-spec-ACS-v02.02` 与本地安装的 `acps-sdk 2.2.0` 编写。

## 当前结论

四份草稿均描述目标部署能力，而不是当前本机端口。它们可以用于内容审查和 SDK
结构校验，但**现在不能原样提交**，因为以下字段仍是占位值：

- `aic`：由 Registry 审核通过后分配，不自行编造；它属于审核后待办，不是提交前
  可以消除的阻塞项。
- `active`、`lastModifiedTime`：由 Registry 维护；草稿值只用于通过结构校验。
- `provider.organization`：公开草稿保持占位值；送审前由私有配置换成平台注册时采用的
  真实主体或团队名称。
- `endPoints[].url`：需换成可由梧桐访问的正式 HTTPS 地址。
- `securitySchemes` 与端点 `security`：草稿声明目标使用 mTLS，只有完成 AIC、EAB、
  证书申请和真实握手验证后才能提交为已具备能力。

## Registry 页面字段映射

| 页面字段 | 填写来源 | 当前建议 |
|---|---|---|
| 名称 | ACS `name` | 分别使用四份草稿中的中文名称 |
| 版本 | ACS `version` | `0.1.0` |
| 能力描述 | ACS `description` | 原样使用，保留能力边界和限制 |
| 是否可派生（本体） | 部署形态 | 四个当前均选“否”，作为实际运行实体注册 |
| ACS | 整份 JSON | 替换全部占位值、完成部署和 mTLS 验证后粘贴 |

## 四个注册对象

| 顺序 | 文件 | 协议端点 | 角色 |
|---|---|---|---|
| 1 | `evidence-audit-leader.draft.json` | `HTTP_JSON` | 用户入口与协作总控 |
| 2 | `source-verifier.draft.json` | `JSONRPC` | AIP Partner，来源可追踪性检查 |
| 3 | `evidence-grader.draft.json` | `JSONRPC` | AIP Partner，证据支持强度分级 |
| 4 | `contradiction-scout.draft.json` | `JSONRPC` | AIP Partner，冲突侦测 |

## 提交前门禁

1. 部署四个服务并获得稳定公网域名；不要使用 `.invalid`、`localhost` 或局域网地址。
2. 填写真实团队主体，将 `active` 和 `entityMeta.environment` 改成部署态，并用正式
   endpoint 替换占位地址。
3. 运行 `scripts/validate_acs_drafts.py` 和 `scripts/registry_preflight.py`；AIC 占位符
   会单列为“审核后待办”，不会错误阻止提交审核。
4. 提交审核；审核通过并取得四个 AIC 后，再获取 EAB、申请证书并启用 mTLS。
5. 将真实 AIC 同步到本地 ACS 和运行环境，对公开端点完成健康检查、AIP 调用、
   Discovery 和证书握手验证。

官方依据：

- ACS v02.02：`https://github.com/AIP-PUB/ACPs-community/blob/v2.2.0/acps-specs/03-ACPs-spec-ACS/ACPs-spec-ACS.md`
- AIP SDK 教程：`https://github.com/AIP-PUB/ACPs-community/blob/v2.2.0/acps-docs/tutorials/aip-sdk-tutorial.md`
