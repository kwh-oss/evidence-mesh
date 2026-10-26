# Evidence Mesh 服务代码

当前运行方式见[根目录README](../../README.md)，架构和配置见[系统设计](../../docs/architecture.md)与[部署说明](../../docs/deployment.md)。

服务入口为`source_partner:app`、`grader_partner:app`、`contradiction_partner:app`、`leader_app:app`。生产mTLS入口使用`serve_partner`或`serve_leader`；网页/插件桥接为`web_test_app:app`。历史文件名中的test不代表可以绕过凭据。

以下保留早期本地MVP操作记录，仅用于开发模式，不代表当前平台注册或部署状态。

## 历史本地 MVP

在四个终端中从项目根目录启动服务：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn evidence_mesh.source_partner:app --port 8021
```

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn evidence_mesh.grader_partner:app --port 8022
```

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn evidence_mesh.contradiction_partner:app --port 8023
```

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn evidence_mesh.leader_app:app --port 8010
```

用户向 `POST http://127.0.0.1:8010/audit` 提交 `schema_version=1.0` 的 Claim、来源
信息和来源片段。Leader 会并行调用三个 AIP Partner，返回含独立 taskId、Partner
产品、裁决和风险标志的 Evidence Passport。

当前仅用于本地开发：服务明确关闭 AIP 身份绑定，尚未配置 Registry、AIC、mTLS、
Discovery 或 AMP。
