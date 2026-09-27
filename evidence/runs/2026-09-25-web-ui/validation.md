# 证链联研网页 MVP 验证

日期：2026-09-25

## 已实现

- Leader 根路径 `/` 提供中文核验表单。
- 用户可填写待核验结论、来源 ID、来源标题、精确位置和证据原文。
- 页面调用现有 `/audit` 接口，并展示总判定、风险标记、三个 Partner 结果和 AIP taskId。
- 页面明确提示：当前版本不自动检索外部文献，不应输入隐私、密钥或未获授权材料。

## 验证结果

- `compileall`：通过。
- `unittest discover`：`Ran 21 tests`，`OK`。
- 静态资源测试：主页、CSS 和 JavaScript 均返回 HTTP 200。
- 视觉检查：Microsoft Edge 无头模式，`1440 x 1800`，表单、标题、按钮与页脚未见重叠或截断。
- 真实接口请求：Leader 返回 HTTP 200、`decision=needs-review`、三个独立 Partner taskId。

## 可复核产物

- 页面：`src/evidence_mesh/static/index.html`
- 样式：`src/evidence_mesh/static/styles.css`
- 交互：`src/evidence_mesh/static/app.js`
- API 挂载：`src/evidence_mesh/leader_app.py`
- 自动测试：`tests/test_leader_app.py`
- 本地视觉检查截图：`tmp/ui-qa/homepage-full.png`

## 边界

本次仅证明本地网页、Leader API 与既有三个 AIP Partner 可以形成可操作闭环。它不代表
系统已经公网部署、注册到梧桐 Registry，或已经通过 Discovery、AIC、mTLS、AMP 和平台
审核。截图属于开发期临时验证产物，不作为正式比赛平台数据。
