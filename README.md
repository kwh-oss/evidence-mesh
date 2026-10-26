# 证链 · Evidence Mesh

通过网页、浏览器侧栏或AIP互联平台，对自然问题和视频片段中的事实主张进行检索、材料比较与有据回答。

![系统架构](docs/figures/system-architecture.svg)

## 当前工程

四个独立AIP服务：总控组织任务并整合答案；资料检索伙伴获取正文与出处线索；材料支持度伙伴提供规则初筛；语义冲突伙伴在配置模型时比较意义与条件。伙伴可分别被梧桐/叮当调用。叮当分配与总控自身派单分别记录。

插件当前源码版本0.3.3，用户主动采集播放位置附近约30秒声音和最多6帧画面，提取事实主张后检索外部材料，不声称理解整个视频或鉴定真伪。

## 快速运行

Python 3.13，无密钥模式不调用付费搜索、模型或外部智能体：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/local_demo.py
```

Linux/macOS替换为`.venv/bin/python`。打开`http://127.0.0.1:8010/`，Ctrl+C停止全部子服务。自动闭环检查使用`python scripts/local_demo.py --smoke`。本地演示验证四服务AIP材料交接，完整联网产品需按[部署说明](docs/deployment.md)配置。

## 验证

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --test browser-extension/model.test.mjs
.\.venv\Scripts\python.exe scripts/check_public_repo.py
```

公开测试使用离线材料、模拟传输和合成凭据，不代表事实准确率。私有历史结果回放与身份迁移夹具不进入公开更新。CI从全新检出运行公开测试与本地闭环。

## 工程入口

- [系统设计与自主实现](docs/architecture.md)
- [运行、生产配置与插件安装](docs/deployment.md)
- [本次工程更新与验证范围](docs/engineering-release.md)
- [AIP社区分享稿与贡献路线](docs/community-sharing.md)
- [浏览器扩展](browser-extension/README.md)
- [任务编排](src/evidence_mesh/leader.py)、[语义与引文](src/evidence_mesh/semantic_review.py)、[内外协作](src/evidence_mesh/hybrid_collaboration.py)

复用[AIP-PUB/ACPs-community](https://github.com/AIP-PUB/ACPs-community)的SDK，开发环境2.2.0；团队实现边界见[NOTICE](NOTICE)，自研代码与文档采用[Apache-2.0](LICENSE)。真实密钥、身份私钥、插件访问文件、原始音视频、私有配置及运行日志留在部署者私有环境。

<details>
<summary>历史开发记录（以下旧日期、版本与审核状态不代表当前部署）</summary>

## 初始项目记录

本仓库用于第八届全球校园人工智能算法精英大赛“智能体互联”赛题的开发、验证与材料留存。

## 当前阶段

- 阶段：Registry、部署与可信身份接入准备
- 官方截止：2026-10-15 20:00
- 当前目标：完成公开仓库整理、正式域名切换、Registry 审核、AIC/EAB/mTLS 与线上验证
- 暂不执行：在真实端点和身份材料缺失时伪造 ACS 字段或宣称平台验收通过

## 目录约定

- `docs/`：规则、技术路线、决策和证据索引
- `src/`：后续参赛产品代码
- `tests/`：自动化验证
- `evidence/`：平台截图、日志、测试数据与提交材料证据
- `vendor/`：官方发行包与版本清单
- `tmp/`：网页调研和临时文件，不作为正式交付物

## 第一里程碑

1. 校验官方 WIT/SDK 发行包。
2. 在隔离虚拟环境中安装依赖。
3. 运行发行预检。
4. 运行最小 Agent。
5. 运行最小 Leader/Partner Direct RPC。
6. 形成第一份可审计运行记录。

## 已完成

- 官方 SDK/WIT 安装、哈希校验和发布预检已通过。
- 本地 AIP Direct RPC Leader–Partner 闭环已通过自动断言。
- 四智能体 ACS 预注册草稿、环境化身份配置和本地部署骨架已完成。
- Registry 草稿/审核边界已核实，并加入阻止占位端点误提交的自动预检。
- Leader 与三个 Partner 均已保存为 Registry 草稿；公网 HTTPS 预演与三条 AIP-RPC
  状态机验证已通过；自有域名的可信 HTTPS、三个 Partner AIP-RPC 与 Leader 端到端
  验证也已完成，但尚未提交 Registry 审核、签发正式 mTLS 证书或完成平台验收。

## 公开仓库边界

- 公开源码只保存占位 ACS、可复现测试、脱敏验证记录和部署模板。
- Registry 实名主体、正式域名、AIC/EAB、私钥、证书与 `.env` 由私有配置注入。
- 历史验证记录中的临时公网端点仅证明当次测试，不代表永久服务地址或平台验收。
- 发布前运行 `python scripts/check_public_repo.py`，并确认输出为 `PUBLIC_REPO_CHECK_PASS`。
- 本项目自研代码采用 Apache License 2.0；官方 SDK/WIT 和其他第三方组件仍受各自
  许可证约束，公开仓库不二次分发本地下载的 wheel 二进制包。

详见：

- `docs/technical-roadmap.md`
- `docs/team-action-card.md`
- `docs/registry-self-service.md`
- `evidence/runs/2026-09-22-local-foundation/validation.md`

## 当前参赛方向

工作名称为“证链联研”：通过可发现、可替换的 AIP Leader/Partner 协作，对科研主张
执行来源核验、证据分级、反证检查和确定性冲突裁决。选题与规格见：

- `docs/topic-selection.md`
- `docs/product-spec-v0.1.md`

## 本地验证

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\evaluate_seed_benchmark.py
.\.venv\Scripts\python.exe scripts\check_public_repo.py
```

基准结果必须连同标签状态一起报告；`draft-machine-authored` 数据不得称为人工金标准。

## 许可证

本项目原创代码与文档采用 [Apache License 2.0](LICENSE)。第三方组件的归属和版本
边界见 [NOTICE](NOTICE)；项目许可证不会替代第三方组件自身的许可条款。

</details>

