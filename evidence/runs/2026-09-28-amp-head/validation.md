# AMP 0.1.1 平台接入验证

日期：2026-09-28

## 已验证

- 四个 0.1.1 智能体在启动时立即写入 AMP heartbeat，并按 15 秒周期续写。
- 一次合成 AIP mTLS 全链路任务生成 Leader 与三个 Partner 的 audit 记录，以及
  Leader 调用端和三个 Partner 接收端的成对 access 记录。
- heartbeat 与 audit 内的 AIC 分别匹配四个 Registry 0.1.1 AIC。
- 四份 audit 均使用各自平台证书私钥产生 EdDSA `integrity` 签名。
- 部署端验证器返回 `AMP_HEAD_OK`；四个智能体均有连续心跳，三个调用关系的
  `correlationId` 与 `taskId` 一致，Leader/Partner 两侧均能配对。
- 同轮回归中，完整 AIP mTLS smoke 返回 `AIP_MTLS_SMOKE_OK`，公网 8440–8443
  均通过带证书访问并拒绝无证书访问，443 健康检查正常。

本地日志验证脚本：`scripts/validate_amp_logs.py`

## 平台入库与在线状态

- 按官方“使用 SDK 开发智能体”与 AMP 页面提供的链路，Agent Emitter 写入 JSONL，
  `fluent/fluent-bit:4.2.2` 从只读日志目录采集并转发至 `wt.ioa.pub:19092`。
- Forwarder 已启用 `amp.heartbeat`、`amp.access`、`amp.audit` 三个主题，并使用持久化
  tail DB；`Read_From_Head` 为 `False`，避免首次启动重放历史记录。
- 2026-09-28 平台侧抽样结果：最近十分钟内 `amp.heartbeat=160`、`amp.access=7`、
  `amp.audit=4` 条记录匹配本项目四个 AIC。检查脚本为
  `scripts/check_kafka_forwarding.sh`，只输出计数，不打印业务载荷。
- 调用官方 Discovery `POST https://wt.ioa.pub/discovery/acps-adp-v2/discover`，以
  `type=recent` 查询时，四个 AIC 均出现在 `result.aliveMap` 且 `alive=true`；同次查询
  的最新时间为 `2026-09-28T06:26:48.65Z`。
- 官方说明指出，外部参赛者不需要拥有 Monitor 管理员 OIDC 权限；平台在线状态以
  Discovery `aliveMap` 为可用验收证据。

因此，本记录证明“Agent AMP Emitter + Fluent Bit 转发 + Kafka 主题可见 + Discovery
在线”链路已完成；这不等同于取得 Monitor 管理员查询权限。

## 传输安全差异

主办方文字答复称端点为“Kafka/TLS”。但在 2026-09-28 的实际探测中，
`wt.ioa.pub:19092` 会直接终止 TLS 握手（无服务端证书），而标准明文 Kafka metadata
请求可以成功列出 AMP 主题；官方 AMP 页面给出的 Fluent Bit 示例也未配置 TLS。
当前部署因此按照官方页面示例和实际监听器使用明文 Kafka，不能把这一段链路表述为
TLS 加密。该差异需要主办方确认：TLS 是否计划启用在另一端口，或是否有尚未公开的
CA/客户端证书/SASL 配置。AMP 中只上报身份、任务、状态和审计元数据，不上报论文原文
或敏感证据正文。
