# 本地 AIP Direct RPC 验证

这是一个不调用大模型、不需要梧桐账号或证书的最小协议闭环，用于先确认
`acps-sdk 2.2.0` 的 Leader–Partner 通信、任务状态和产品返回能够正常工作。

在项目根目录打开两个终端：

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn platform_lab.partner:app --host 127.0.0.1 --port 8011
```

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m platform_lab.leader
```

预期 Leader 输出包含：

- `startState: awaiting-completion`
- `finalState: completed`
- `Partner received: 梧桐平台本地协议联调`

这里显式关闭身份绑定，仅限本地开发验证。接入梧桐 EAB/mTLS 时必须改为正式
AIC、证书和身份校验配置。
