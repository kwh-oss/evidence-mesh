# 证链联研选题与数据契约验证

日期：2026-09-23

## 已形成

- 赛题评分驱动的候选方向比较。
- 主选题“证链联研：科研证据链协同核验系统”。
- Leader、三个 Partner、输入输出边界和 MVP 演示闭环。
- `EvidenceLevel`、`SourceRef`、`EvidenceFinding`、`AuditSummary` 数据契约。
- 不依赖大模型的确定性聚合与冲突规则。

## 自动测试

```text
test_direct_and_unsupported_is_conflicting ... ok
test_direct_only_is_supported ... ok
test_invalid_confidence_is_rejected ... ok
test_missing_finding_is_not_silently_accepted ... ok
test_unknown_claim_is_rejected ... ok

Ran 5 tests
OK
compile_exit=0
```

## 当前边界

- 测试只覆盖业务数据契约和聚合规则，不代表三个 AIP Partner 已实现。
- 指标表是目标值，尚未产生真实准确率、延迟或平台访问量。
- 选题仍需用人工标注样例验证需求和效果，不得仅凭内部测试宣称应用成效。
