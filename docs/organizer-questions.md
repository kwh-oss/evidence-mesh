# 待向主办方确认的问题

以下问题来自 SDK v2.2.0 实际接口、梧桐使用指南和当前 Registry 页面之间尚未闭合的
环节。可直接转发给主办方。

## 优先问题

1. 我们采用 ACPs SDK v2.2.0，自行开发一个 Leader 和三个 Partner。Registry 提交
   ACS 时，`aic`、`active`、`lastModifiedTime` 应该删除、填写占位值，还是由网页在
   保存草稿时自动覆盖？
2. ACS 的 `endPoints` 必须在首次提交审核时就是已公网可访问的正式 HTTPS 地址吗？
   因为 AIC 和 EAB 要在审核通过后才能取得，而服务启用 mTLS 又需要先取得证书。官方
   推荐的先后顺序和占位方式是什么？
3. 梧桐是否为参赛者提供智能体运行托管、公网域名或反向代理？如果不提供，是否允许
   参赛者使用自己的云服务器，并在同一域名下用四个不同路径部署四个智能体？
4. 四个实际运行的智能体在注册表单“是否可派生（本体）”一项是否都应选择“否”？
   比赛是否要求先注册本体，再派生实体，还是可以直接注册四个普通实体？
5. 每个智能体是否都必须分别申请 `clientAuth` 和 `serverAuth` 两套证书？Leader 作为
   调用方、Partner 作为被调用方时，官方建议的证书用途组合是什么？

## SDK/文档差异

6. `acps-sdk 2.2.0` 的 `AipRpcClient` 在身份绑定开启时要求
   `expected_partner_aic`，`add_aip_rpc_router` 又要求 `local_aic`；但官方 AIP 教程的
   最小示例没有传这两个参数。比赛验收应以 SDK 当前行为为准吗？是否有更新示例？
7. Partner 前置使用 Nginx/Caddy 等反向代理终止 mTLS 时，如何把客户端证书传递给
   FastAPI/ASGI，才能让 SDK 的 `get_request_peer_aic()` 正确读取证书 AIC？主办方是否
   提供推荐部署模板？
8. 主办方答复称外部 AMP 端点 `wt.ioa.pub:19092` 为 Kafka/TLS，但当前该端口会终止
   TLS 握手（无服务端证书），明文 Kafka metadata 和 Fluent Bit 转发则可正常工作；
   官方 AMP 页面示例也未配置 TLS。请问 TLS 是否应使用另一端口，或是否有需要配置的
   CA、客户端证书、SASL 参数？如果当前阶段就是明文 Kafka，请确认后续是否会切换。

## 希望主办方给出的材料

- 一份当前 Registry 网页可直接提交的 ACS JSON 示例；
- SDK v2.2.0 的完整 mTLS Direct RPC 部署示例；
- 比赛环境 AMP 传输加密配置和验收检查清单；
- 是否允许同一公网主机承载多个 AIC 的明确答复。
