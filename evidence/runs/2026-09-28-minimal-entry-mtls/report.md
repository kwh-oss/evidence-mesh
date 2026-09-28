# 最小输入单入口 mTLS 验证

- 日期：2026-09-28（Asia/Shanghai）
- 环境：公网云服务器、Registry 正式身份、TLS 1.3 双向认证
- 入口：证链联研总控智能体 AIP-RPC
- 输入：仅 `schema_version`、`claim_text`、`source_excerpt`
- 未输入：`claim_id`、来源编号、标题与定位信息

## 验证结果

```json
{
  "claim_id": "task-74deabcd-71b6-49af-aec8-bd6933089c9a",
  "decision": "needs-review",
  "input_mode": "minimal",
  "leader_state": "completed",
  "partner_product_count": 3,
  "partner_task_count": 3,
  "product_type": "evidence-passport",
  "status": "AIP_MTLS_SMOKE_OK"
}
```

## 结论边界

该记录证明：总控可在正式 mTLS 链路上为最小输入自动采用 AIP `taskId` 作为
`claim_id`，并完成三个 Partner 的调用和汇总。缺少来源元数据时，来源核验结果会
标记为 `incomplete`，总决策为 `needs-review`，不会伪造来源。

该记录不证明平台 Group 调用已经通过，也不代表真实科研场景准确率或比赛平台验收。
