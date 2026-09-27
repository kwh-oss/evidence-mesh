# 部署准备

## 本地容器闭环

`compose.local.yml` 用同一镜像启动一个 Leader 和三个独立 Partner，只用于复现本地
HTTP/AIP 闭环。它显式关闭身份绑定，不能作为平台验收证据。

```powershell
docker compose -f deploy/compose.local.yml config
docker compose -f deploy/compose.local.yml up --build
```

启动后访问 `http://127.0.0.1:8010/`。

## 生产身份配置

代码现在支持下列环境变量：

| 变量 | 使用方 | 含义 |
|---|---|---|
| `AIP_IDENTITY_BINDING_ENABLED` | 全部 | 生产环境必须为 `true` |
| `AGENT_AIC` | 每个 Partner | Registry 分配给该 Partner 的真实 AIC |
| `LEADER_AIC` | Leader | Registry 分配给 Leader 的真实 AIC |
| `*_AIC` | Leader | 预期对端 Partner AIC，用于证书与消息身份双重核对 |
| `*_URL` | Leader | 三个 Partner 的公开 HTTPS JSON-RPC 地址 |
| `AIP_CLIENT_CA_FILE` | Leader | 平台信任包路径 |
| `AIP_CLIENT_CERT_FILE` | Leader | Leader clientAuth 证书路径 |
| `AIP_CLIENT_KEY_FILE` | Leader | Leader 私钥路径 |

身份绑定开启后，缺少任一必要 AIC 或证书文件都会失败，不会自动退回不安全模式。
Leader 客户端强制最低 TLS 1.3。

Partner 服务端 TLS 由 Uvicorn 或前置反向代理终止，并且必须把客户端证书信息保留给
ASGI 连接，使 SDK 能从对端证书提取 CN 和唯一的 `acps://{AIC}` URI SAN。本项目的
生产入口 `python -m evidence_mesh.serve_partner` 已接入 SDK 的
`AipPeerCertH11Protocol` 和证书中间件；每个 Partner 需分别提供 serverAuth 证书、
私钥、信任包和真实 AIC。正式部署前必须做真实 mTLS 握手测试；不能只检查 HTTPS
页面可打开。

## 云服务器两阶段部署

建议使用一台 Linux 服务器承载全部四个服务。最低需要开放：

- `22/tcp`：SSH，只允许维护来源访问；
- `80/tcp`、`443/tcp`：Caddy 自动签发 HTTPS 和 Leader 网页入口；
- `8441/tcp`、`8442/tcp`、`8443/tcp`：取得平台证书后，三个 Partner 的直连
  mTLS JSON-RPC 入口。

### 临时 IP/HTTP 预演

在尚未取得域名与主办方证书时，可先用公网 IP 验证容器编排和演示界面：

```bash
docker compose -f deploy/compose.ip-preview.yml up -d --build
```

运行前必须通过 `PUBLIC_HOST` 环境变量提供预演主机名；Caddy 会自动申请可信 HTTPS
证书。启动后访问
`https://<PUBLIC_HOST>/`。三个 Partner 的健康检查分别位于：

```text
https://<PUBLIC_HOST>/source-verifier/health
https://<PUBLIC_HOST>/evidence-grader/health
https://<PUBLIC_HOST>/contradiction-scout/health
```

该配置关闭 AIP 身份绑定且不提供 TLS，只用于部署预演和无敏感数据的功能演示，不能
作为 Registry、mTLS 或梧桐平台验收证据。取得域名后应停止该配置并切换阶段 A。

### 阶段 A：审核前公网 HTTPS 验证

1. 将域名 A/AAAA 记录指向服务器。
2. 复制 `deploy/.env.server.example` 为 `deploy/.env.server`，至少填写
   `PUBLIC_HOST`。
3. 在项目根目录运行：

```bash
docker compose --env-file deploy/.env.server -f deploy/compose.review.yml up -d --build
```

此时可检查：

```text
https://<PUBLIC_HOST>/
https://<PUBLIC_HOST>/source-verifier/health
https://<PUBLIC_HOST>/evidence-grader/health
https://<PUBLIC_HOST>/contradiction-scout/health
```

对应审核前 ACS endpoint 为：

```text
https://<PUBLIC_HOST>/source-verifier/rpc
https://<PUBLIC_HOST>/evidence-grader/rpc
https://<PUBLIC_HOST>/contradiction-scout/rpc
https://<PUBLIC_HOST>/rpc
```

其中 `/rpc` 是 Registry ACS 声明的 AIP JSON-RPC 入口；`/audit` 继续作为网页前端使用的
普通 JSON HTTP 接口，不写入 ACS。

阶段 A 的 Partner 身份绑定暂时关闭，只用于确认公网路由和 HTTPS，不是最终安全验收。
不要处理真实敏感数据，也不要把它描述成 mTLS 或梧桐验收通过。

### 阶段 B：审核后切换平台 mTLS

审核取得 AIC/EAB 后，每个 Partner 分别申请 `serverAuth` 证书；Leader 申请
`clientAuth` 证书。ACS 中的 `certificate.altNames.dns` 必须提前写入
`PUBLIC_HOST`，否则签发的服务端证书无法通过域名校验。

把材料放入下列目录，文件名保持一致：

```text
deploy/secrets/leader/{trust-bundle.pem,client-cert.pem,client-key.pem,server-cert.pem,server-key.pem}
deploy/secrets/source-verifier/{trust-bundle.pem,server-cert.pem,server-key.pem}
deploy/secrets/evidence-grader/{trust-bundle.pem,server-cert.pem,server-key.pem}
deploy/secrets/contradiction-scout/{trust-bundle.pem,server-cert.pem,server-key.pem}
```

The public demo remains on `443`. Strict AIP mTLS uses one listener and one
Registry-issued server identity per Agent so that certificate identity cannot be
confused by path routing:

```text
Leader               https://<PUBLIC_HOST>:8440/rpc
Source Verifier      https://<PUBLIC_HOST>:8441/rpc
Evidence Grader      https://<PUBLIC_HOST>:8442/rpc
Contradiction Scout  https://<PUBLIC_HOST>:8443/rpc
```

在 `deploy/.env.server` 填入四个真实 AIC，然后执行：

```bash
docker compose --env-file deploy/.env.server -f deploy/compose.review.yml down
docker compose --env-file deploy/.env.server -f deploy/compose.mtls.yml up -d --build
```

最终 Partner endpoint 使用：

```text
https://<PUBLIC_HOST>:8441/rpc
https://<PUBLIC_HOST>:8442/rpc
https://<PUBLIC_HOST>:8443/rpc
```

只有真实证书握手、AIC身份匹配、Discovery调用和AMP记录全部验证后，才能作为平台
接入证据。

### 回滚

如果阶段 B 无法启动，先保存日志，再退回阶段 A：

```bash
docker compose --env-file deploy/.env.server -f deploy/compose.mtls.yml logs --no-color > mtls-failure.log
docker compose --env-file deploy/.env.server -f deploy/compose.mtls.yml down
docker compose --env-file deploy/.env.server -f deploy/compose.review.yml up -d
```

回滚不会删除 Caddy 数据卷或证书目录。

## 无 Docker 的本地四进程验证

当前机器没有 Docker 时，可运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\live_http_smoke.py
```

脚本会临时启动四个独立进程，完成健康检查和 Leader→三个 Partner 的真实回环 HTTP
调用，把结果写入 `evidence/runs/2026-09-26-local-http-topology/`，随后关闭全部进程。
此记录不代表 Registry、Discovery、mTLS、AMP、公网可达性或比赛平台验收。

本地生产型TLS链路还可以运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\local_mtls_smoke.py
```

它会生成一次性的本地CA、Leader `clientAuth`证书和三个Partner `serverAuth`证书，
完成TLS 1.3双向握手与AIC身份绑定测试后立即删除测试密钥。该测试只证明代码链路，
不替代Registry签发的正式证书。

## 正式部署仍需外部信息

- 主办方/Registry 分配的四个 AIC；
- EAB 与每个智能体对应的 clientAuth/serverAuth 证书；
- 可从梧桐访问的公网 HTTPS 域名；
- 主办方对“先提交带什么 endpoint 的 ACS，后取得证书”的准确要求；
- AMP Kafka/TLS 凭据及比赛环境的日志上报要求。

不要把 `.env`、私钥、证书或 EAB 文件提交到仓库。根目录 `.gitignore` 已覆盖这些
常见敏感文件，但部署时仍应使用宿主机密钥目录或 secret 管理器。
