# 四智能体 ACS 预注册草稿验证

日期：2026-09-25

## 依据

- 官方 ACS 规范：`ACPs-spec-ACS-v02.02`
- 本地官方包：`acps-sdk 2.2.0`
- 官方规范地址：`https://github.com/AIP-PUB/ACPs-community/blob/v2.2.0/acps-specs/03-ACPs-spec-ACS/ACPs-spec-ACS.md`

规范明确：ACS 采用 JSON；`aic` 由注册服务分配，`active` 和 `lastModifiedTime`
由注册服务维护；技能描述应写明能力范围与限制。JSON-RPC 端点使用固定 RPC URL，
HTTP_JSON 端点使用服务基础 URL。

## 生成结果

- `evidence-audit-leader.draft.json`
- `source-verifier.draft.json`
- `evidence-grader.draft.json`
- `contradiction-scout.draft.json`

Leader 草稿声明 `HTTP_JSON`；三个 Partner 草稿声明 `JSONRPC`。四者均如实声明当前
不支持 SSE、异步通知或消息队列，并在描述中保留现阶段能力边界。

## 自动验证

执行：

```text
.venv\Scripts\python.exe scripts\validate_acs_drafts.py
```

结果：四份文件均可被官方 `AgentCapabilitySpec.from_file()` 成功解析。

项目全量回归：

```text
Ran 22 tests
OK
```

## 提交阻断项

以下项目未完成，因此四份文件只能称为“预注册草稿”：

- Registry 分配的真实 AIC；
- 真实提供者或参赛团队主体信息；
- 可由平台访问的正式 HTTPS 端点；
- EAB、证书申请、mTLS 握手和身份绑定验证；
- 登录态 Registry 表单对身份字段自动回填规则的实际验证。

草稿使用 `REGISTRY_ASSIGNED_*`、`REPLACE_*` 和保留域 `.invalid` 防止被误当成可提交
配置。正式提交前必须全部替换，并重新运行结构校验和在线端点验证。
