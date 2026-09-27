# 三 Partner AIP 与 Leader 验证

日期：2026-09-23

## 实现对象

- `source-verifier`：返回 `source-check`。
- `evidence-grader`：返回 `evidence-finding`。
- `contradiction-scout`：返回 `contradiction-check`。
- `evidence-audit-leader`：通过 AIP 并行委派，生成 `evidence-passport`。

## 协议验证

- 三个 Partner 均通过 `acps-sdk 2.2.0` 的 FastAPI `/rpc` 路由接收任务。
- 测试实际发送 AIP `start`，检查 `awaiting-completion`，再发送 `complete` 并检查
  `completed`。
- 非法 JSON 返回 `failed`，不会伪造空产品。
- Leader 保留三个独立 taskId，并在 Partner 缺失或失败时返回 `incomplete`。
- 当前测试使用 ASGI 内存传输并关闭身份绑定，只证明协议路由与状态机，不代表完成
  Registry、Discovery、AIC、mTLS 或公网部署。

## 自动测试结果

```text
Ran 18 tests in 0.065s
OK
```

覆盖内容包括：

- 3 个 Partner 的业务处理基线。
- 3 个 Partner 的真实 AIP RPC 状态流和结构化产品。
- 非法 schema、非法 JSON、未知 Claim、非法置信度。
- 缺失证据、条件性证据、方向相反证据和确认冲突。
- Leader 并行委派、任务追踪和 fail-closed 裁决。
