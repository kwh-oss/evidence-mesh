# 证链联研跨进程 MVP 验证

日期：2026-09-25

## 拓扑

- Leader HTTP API：`127.0.0.1:8010`
- Source Verifier AIP Partner：`127.0.0.1:8021/rpc`
- Evidence Grader AIP Partner：`127.0.0.1:8022/rpc`
- Contradiction Scout AIP Partner：`127.0.0.1:8023/rpc`

四个服务分别由独立 Uvicorn 进程运行。用户向 Leader 的 `/audit` 提交一次请求，Leader
并行调用三个 Partner；每个 Partner 完成 `start` 与 `complete` 两次 AIP RPC，全部返回
HTTP 200，Leader 最终返回 HTTP 200。

## 演示结果

输入 Claim 为“处理导致细胞死亡”，来源片段只陈述“相关”与“可能”。系统输出：

- `decision=needs-review`
- `risk_flags=[claim:evidence-conditional]`
- Source Verifier：`verified`
- Evidence Grader：`conditional`
- Contradiction Scout：`none-found`
- 返回三个独立 AIP taskId

## 自动测试

新增 Leader HTTP API 校验后：

```text
Ran 20 tests
OK
```

## 边界

本次验证为本机跨进程 HTTP/AIP 联调，身份绑定仍关闭，来源元数据为演示数据。它不能
替代梧桐 Registry、Discovery、AIC、mTLS、AMP 或真实论文案例验证。
