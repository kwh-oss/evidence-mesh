# Registry 草稿预检记录

日期：2026-09-25

## 核验来源

- 梧桐 Registry 线上公开 OpenAPI：创建草稿和提交审核为不同接口；
- 梧桐 Registry 线上公开 ACS 示例：AIC、激活状态和修改时间由注册服务维护，
  `provider.verifiedFields` 由注册方写入；
- ACPs-community v2.2.0 Registry 源码：新建记录初始状态为 `DRAFT`，批准时签发 AIC
  并同步 ACS；
- 当前 Registry 前端代码：保存调用创建/更新接口，提交审核使用单独接口。

## 本地验证

- 四份 ACS 草稿均通过已安装官方 SDK 的 `AgentCapabilitySpec` 校验；
- `scripts/registry_preflight.py` 将四份文件判定为 `DRAFT_SAVE_READY`；
- 同一预检将四份文件判定为 `submission: BLOCKED`，原因包括占位 AIC、占位组织、
  不可路由 `.invalid` 端点以及 `environment=draft`；
- 自动测试总数由 25 增至 26。

## 线上草稿保存结果

2026-09-26，用户在登录后的 Registry 页面保存了第一条 Leader 草稿。截图显示：

- 名称：证链联研总控智能体；
- 版本：`0.1.0`；
- 类型：实体；
- 状态：草稿；
- 页面提供“提交审核”操作，说明尚未进入审核流程。

截图文件：`leader-draft-saved.png`  
SHA-256：`5944A8CEA3FE8F67E8F94586D2C8F81C5746A0E4644E3A0F099BBAD0BC9BFEB8`

## 证据边界

随后，用户完成其余三个 Partner 的草稿保存。完整列表截图显示四条记录均为版本
`0.1.0`、类型“实体”、状态“草稿”，且提交时间、处理时间和处理意见均为空：

- 证链冲突侦测智能体；
- 证链证据分级智能体；
- 证链来源核验智能体；
- 证链联研总控智能体。

完整列表截图：`four-agent-drafts-saved.png`  
SHA-256：`37B08FE3483EFF84C24C09F5070546A10B4EB456C220B27687A362FEE9CF1592`

上述结果支持“四个智能体材料均已成功创建 Registry 草稿记录”。它不证明审核通过、
AIC 签发、证书签发、mTLS、发现服务、AMP 或真实公网互联。
