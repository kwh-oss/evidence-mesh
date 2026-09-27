# 技术路线与里程碑

## 总体原则

当前已确认需要区分开发路径和注册模块：开发者可选 ACPs SDK 或 WIT 框架在本地
编写、运行智能体；ACPs Registry 用于登记能力信息和 ACS，并承担注册与审核流程。
Flux 当前是 WIT 发行包和文档门户，不是已证实的拖拽式在线编辑器。最终产品服务
仍需部署并通过 AIP/ACPs 接入梧桐互联系统。

## M0：平台与协议摸底

- [x] 阅读赛题规则与提交规范
- [x] 核对梧桐首页、使用指南、Registry、Flux/WIT入口
- [x] 核对 AIP-PUB `ACPs-community` v2.2.0 文档结构
- [x] 完成账号登录（用户操作）
- [x] 核对登录态下的创建入口与首屏页面字段
- [ ] 核对字段校验规则、“保存”语义和后续审核步骤
- [x] 核对官方开发选择：ACPs SDK 与 WIT
- [x] 确认 Flux 是 WIT 框架门户，不是已证实的在线拖拽编辑器
- [ ] 核对 WIT 自动注册、部署和模型配置的实际流程

## M1：本地最小闭环

- [x] 下载并校验 `acps-sdk 2.2.0`、`wit-framework 2.1.0`
- [x] 创建 Python 3.13 隔离环境
- [x] 通过 `wit-release-preflight`
- [ ] 运行最小 WIT Agent
- [x] 运行最小 Direct RPC Leader/Partner
- [x] 保存测试日志和版本信息

## M2：选题原型

- [x] 明确真实问题、目标用户和多智能体必要性
- [x] 用户确认“证链联研”为正式参赛方向（2026-09-25）
- [x] 定义 Leader、Partner、Capability 与数据边界
- [x] 实现本地最小业务闭环（3个 AIP Partner + 并行 Leader）
- [x] 实现用户可调用的最小 HTTP 产品入口与 Evidence Passport JSON
- [x] 完成三个 Partner 的真实跨进程 HTTP 联调
- [x] 实现面向非技术用户的表单与 Evidence Passport 可视化页面（本地 MVP）
- [ ] 接入 Discovery、身份绑定、mTLS 与 AMP 后完成线上业务闭环
- [x] 建立首版测试指标和失败场景

## M3：梧桐接入

- [x] 生成并用官方 SDK 审查四份 ACS 预注册草稿
- [x] 实现 AIC、Partner 地址、mTLS 客户端材料和身份绑定的环境化配置门禁
- [x] 准备四服务本地容器部署骨架（本机无 Docker，镜像构建待验证）
- [x] 完成自有域名 DNS、可信 HTTPS、三个 Partner AIP-RPC 与 Leader 端到端验证
- [ ] Registry 创建草稿并提交审核
- [ ] 获得 AIC、EAB 与 mTLS 证书
- [ ] 完成 Discovery、Direct/Group 调用与 AMP 日志
- [ ] 留存后台访问量、交互记录和截图

## M4：作品与材料

- [ ] 稳定部署与访问量积累
- [ ] 技术报告
- [ ] 3-5 分钟演示视频
- [ ] 答辩 PPT/PDF
- [ ] 第三方资源、许可证与自主开发边界表
- [ ] 匿名与提交前检查

