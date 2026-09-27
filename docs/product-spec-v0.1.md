# 证链联研 v0.1 产品与技术规格

状态：2026-09-25 经团队确认，进入正式产品开发。

## 用户输入

- 一个需要核验的结论或问题。
- 可选的来源链接、文献元数据、原文片段或本地材料。
- 核验边界：只核对所给材料，或允许检索公开来源。

## 多智能体结构

### Leader：Evidence Audit Leader

- 把输入拆成最小可核验 Claim。
- 通过 Discovery 按 Capability 选择 Partner。
- 并行委派并跟踪 AIP 任务状态。
- 对结构化 Findings 做确定性聚合和冲突裁决。
- 输出 Evidence Passport，并保留 taskId 与来源追踪。

### Partner 1：Source Verifier

- 核对来源是否存在、标题/作者/年份/标识符是否一致。
- 返回来源定位和元数据异常，不评价超出来源文本的机制结论。

### Partner 2：Evidence Grader

- 把证据分为：直接、间接、条件性、不支持、冲突。
- 明确证据能够支持的最窄结论和不能支持的扩展结论。

### Partner 3：Contradiction Scout

- 查找输入材料内部冲突、反例和未控制变量。
- 在未找到反证时返回“未发现”，不得返回“已证明没有反证”。

## 核心数据契约

三个 Partner 返回职责分离的结构化产品，避免把“来源存在”“证据支持”和“未发现
反证”混成同一个判断：

- Source Verifier → `SourceCheck`：`verified | incomplete | invalid` 与问题清单。
- Evidence Grader → `EvidenceFinding`：
  `direct | indirect | conditional | unsupported | conflicting`、理由、来源和置信度。
- Contradiction Scout → `ContradictionCheck`：
  `none-found | possible | confirmed` 与冲突指示器。

所有 AIP 文本产品使用 `schema_version=1.0` 和显式 `product_type`。其中
`none-found` 只表示本次输入中未发现反证，不表示反证不存在。

Leader 输出 `AuditSummary`：

- 每条 Claim 的 Findings 和最终状态
- 证据覆盖率
- 冲突与缺失标志
- 所有 AIP taskId / correlationId
- 对用户可见的限制和下一步验证建议

## MVP 演示闭环

1. 用户输入一条包含 2-4 个子主张的科研结论。
2. Leader 拆分主张并发现三个 Partner。
3. Leader 通过 AIP Direct RPC 并行委派任务。
4. Partner 返回结构化产品与状态。
5. Leader 识别至少一个“间接证据被过度解释”或来源冲突。
6. Leader 输出 Evidence Passport。
7. 梧桐后台能够看到注册、发现、访问记录；AMP 日志用 taskId 关联双方。

## 验收指标

| 指标 | MVP 目标 |
|---|---:|
| AIP 任务完成率 | >= 95% |
| 结构化产品解析成功率 | 100% |
| 已标注测试集证据等级准确率 | >= 80% |
| 明显不支持主张检出率 | >= 85% |
| 重复运行裁决一致率 | >= 90% |
| 本地 P95 协作延迟（不含外部检索） | <= 5 秒 |

这些是工程目标，不是已经取得的结果。任何报告数字必须来自保存的原始测试记录。

## 失败场景

- Partner 超时、拒绝或返回 Failed。
- 产品 JSON 缺字段或枚举值非法。
- 同一 Claim 同时出现 direct 与 conflicting。
- 来源不存在或元数据不一致。
- Discovery 无匹配 Agent。
- mTLS/身份绑定失败。
- 外部模型或检索服务不可用。

Leader 必须降级并明确标记缺口，不能静默生成一个看似完整的答案。当前本地实现
已经对缺 Partner、非法 schema、Partner Failed、条件性证据和确认冲突采取 fail-closed
处理；Discovery、mTLS 和 AMP 仍待接入。

## 里程碑

- 09-23 至 09-25：数据契约、人工标注样例和确定性聚合器。
- 09-26 至 09-30：三个 Partner 与单元测试。
- 10-01 至 10-04：Leader、Discovery、并行调度和故障注入。
- 10-05 至 10-07：Registry、AIC、EAB、mTLS 和线上部署。
- 10-08 至 10-10：真实试用、指标采集和访问量积累。
- 10-11 至 10-13：技术报告、演示视频和答辩材料。
- 10-14：冻结版本、匿名检查、材料完整性检查。
- 10-15 12:00：内部提交截止，给官方 20:00 截止预留缓冲。
