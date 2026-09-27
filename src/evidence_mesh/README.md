# 证链联研本地 MVP

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
