# 部署与身份绑定准备验证

日期：2026-09-25

## 实现内容

- Partner 从环境变量读取真实 `AGENT_AIC` 和身份绑定开关。
- Leader 从环境变量读取自身 AIC、三个预期 Partner AIC、Partner URL 和客户端证书路径。
- 身份绑定开启时，缺少 AIC、CA、证书或私钥会直接报错，不会降级到无身份模式。
- Partner 自定义处理器返回的 `senderId` 改为本地 AIC，满足 SDK 身份一致性要求。
- Leader 客户端开启身份绑定时向 SDK 传入 `expected_partner_aic` 和 TLS context。
- TLS 客户端最低版本设置为 TLS 1.3。
- 增加四服务 Dockerfile、开发态 Compose 骨架和生产环境变量模板。

## 自动测试

```text
Ran 25 tests
OK
```

新增测试覆盖：开发态默认身份、生产态缺 AIC 拒绝、非法布尔配置拒绝。

## 原生跨进程回归

使用独立 Uvicorn 进程启动：

- Leader：`127.0.0.1:8110`
- Source Verifier：`127.0.0.1:8121`
- Evidence Grader：`127.0.0.1:8122`
- Contradiction Scout：`127.0.0.1:8123`

结果：

- 条件性因果越界用例返回 `needs-review`；
- 明确支持用例返回 `supported`；
- 返回三个独立 Partner taskId；
- Partner `/health` 明确显示 `identity_binding=disabled`，避免把开发态误作安全验收。

## 未验证项

本机未安装 Docker，故 `compose.local.yml` 尚未执行 `docker compose config`、镜像构建或
容器运行测试。当前也没有主办方分配的 AIC、EAB、证书、正式域名或 AMP 凭据，因此
尚未做真实 mTLS 握手、Registry/Discovery 调用或 AMP 上报。

SDK v2.2.0 的身份绑定实际要求与公开教程最小示例之间存在参数差异，连同首次 ACS
提交时 endpoint 的填写时机等问题，已记录在 `docs/organizer-questions.md`。
