# AMP 0.1.1 接入验证

日期：2026-09-28

## 已验证

- 四个 0.1.1 智能体在启动时立即写入 AMP heartbeat，并按 15 秒周期续写。
- 一次合成 AIP mTLS 全链路任务生成 Leader 与三个 Partner 的 audit 记录。
- heartbeat 与 audit 内的 AIC 分别匹配四个 Registry 0.1.1 AIC。
- 四份 audit 均使用各自平台证书私钥产生 EdDSA `integrity` 签名。
- 部署端验证器返回 `AMP_HEAD_OK`；验证时每个智能体已有 8 条连续心跳。
- 同轮回归中，完整 AIP mTLS smoke 返回 `AIP_MTLS_SMOKE_OK`，公网 8440–8443
  均通过带证书访问并拒绝无证书访问，443 健康检查正常。

验证脚本：`scripts/validate_amp_logs.py`

## 平台侧边界

- 官方 Monitor 健康入口 `https://wt.ioa.pub/monitor/health` 返回 AMP Monitor Server
  2.2.0，依赖检查均为 `ok`。
- 官方 OpenAPI 只提供 AMP 查询接口，没有 Agent 直传日志接口；规范要求本地 Emitter
  文件由平台部署的 Forwarder 采集后入库。
- 当前比赛平台没有向参赛者公开 Forwarder 的 Kafka/TLS/采集目录参数。直接查询四个
  AIC 的 liveness 需要独立 Monitor OIDC bearer token；Registry 登录令牌不能替代。

因此，本记录证明“Agent AMP 头 + 连续写入 + 已签名审计”已经完成；在官方提供
Forwarder/Monitor OIDC 接入参数之前，不把本地日志宣称为“已被官方 Monitor 入库”。
