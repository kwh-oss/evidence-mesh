# 云服务器临时域名 HTTPS 预演验证

- 时间：2026-09-26（Asia/Shanghai）
- 主机：腾讯云轻量应用服务器，Ubuntu 24.04，Docker 27.5.1，Compose 2.32.4
- 拓扑：Caddy → Leader → Source Verifier / Evidence Grader / Contradiction Scout
- 配置：`deploy/compose.ip-preview.yml`
- 临时域名：`124-156-165-7.sslip.io`
- TLS：Caddy 自动签发的 Let’s Encrypt 证书

## 验证结果

服务器内部健康检查：

- Leader：`200`, `status=ok`
- Source Verifier：`200`, `status=ok`, `identity_binding=disabled`
- Evidence Grader：`200`, `status=ok`, `identity_binding=disabled`
- Contradiction Scout：`200`, `status=ok`, `identity_binding=disabled`

公网直连（绕过本机 HTTP 代理）验证：

- `/`：`200`
- `/health`：`200`
- `/source-verifier/health`：`200`
- `/evidence-grader/health`：`200`
- `/contradiction-scout/health`：`200`

随后将入口升级为 `https://124-156-165-7.sslip.io/`。DNS A 记录解析到服务器公网
IP，Caddy 的 ACME HTTP-01 验证成功，Let’s Encrypt 证书签发完成；HTTPS `/health`
公网验证返回 `200`。HTTP 入口会自动跳转到 HTTPS。

使用无敏感数据的合成请求 `claim_id=public-smoke-20260926` 调用 `/audit`，Leader
成功取得三个 Partner 的独立任务结果：

- Source Verifier task：`task-2c8461a6-9078-4bf1-ad9e-fe22ce26db76`
- Evidence Grader task：`task-9c8b61fd-c4d9-4a1c-87de-1f4007b01fdb`
- Contradiction Scout task：`task-66bf67bd-0d19-42e5-b517-aba0f9ef8244`
- 聚合结论：`decision=no-evidence`
- 风险标记：`claim:unsupported`

该结论符合测试输入：来源摘录明确声明为合成连通性文本，并未提供支持科研主张的真实
证据。

## 证据边界

本记录证明公网 HTTPS 路由、容器编排以及 Leader 到三个 Partner 的真实网络调用可用。
当前 TLS 只保护公开预演入口，`AIP_IDENTITY_BINDING_ENABLED=false`。它不证明 Registry 审核、
平台证书、mTLS、Discovery、AMP 或梧桐平台验收已经完成，也不得处理真实敏感数据。
