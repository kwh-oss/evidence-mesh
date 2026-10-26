# 运行、配置与部署

## 1. 无密钥协议演示

Python 3.13，安装`requirements.txt`后执行`python scripts/local_demo.py`。四服务仅绑定127.0.0.1的8010、8021—8023端口；Ctrl+C停止。`--smoke`发送一条合成材料任务，验证三个子任务后退出。模型、联网检索、外部伙伴、AMP、Group及身份绑定明确关闭。

该模式复现AIP材料交接，不是完整联网核验产品。默认语义伙伴未检查不应显示为语义通过。现有`deploy/compose.local.yml`提供容器版本；Docker需自行安装，构建时需要互联网。

## 2. 生产AIP服务

四个应用入口分别为`source_partner:app`、`grader_partner:app`、`contradiction_partner:app`及`leader_app:app`，模块前缀为`evidence_mesh.`。启用身份时使用`python -m evidence_mesh.serve_partner`或`python -m evidence_mesh.serve_leader`，不要直接把无身份演示暴露为生产端点。

必须配置：`AIP_IDENTITY_BINDING_ENABLED=true`、各自真实AIC、客户端与服务端CA/证书/私钥路径；总控配置三个伙伴的预期AIC及HTTPS端点。缺身份或文件时失败，不自动降级。具体变量见`runtime_config.py`及`deploy/.env.production.example`。

`deploy/compose.mtls.yml`等早期模板保留为历史示例，其中端口与身份不自动对应任何现存服务器。维护者须按自己的注册结果填写新配置并验证双向TLS、发现与访问。此更新不切换线上服务器，不重置既有预算或证书。

## 3. 启用独立检索与语义模型

以下设置在服务器私有配置中注入，不填写真实值到公开文件。

| 变量 | 用途 |
|---|---|
| `PUBLIC_RETRIEVAL_ENABLED=true` | 开启真实搜索/正文获取 |
| `PUBLIC_SEARCH_PROVIDER=tavily` | 选择Tavily；Searx模式另配`PUBLIC_SEARCH_ENDPOINT` |
| `TAVILY_KEY_FILE` | 私有密钥文件，只读挂载 |
| `TAVILY_SEARCH_BUDGET_FILE` | 搜索预算SQLite，独立持久化 |
| `TAVILY_SEARCH_MAX_CALLS` | 本地搜索尝试预算，当前允许1—500；不是账户剩余额度 |
| `PUBLIC_RETRIEVAL_ARCHIVE_ROOT` | 私有证据归档目录 |
| `SCHOLARLY_METADATA_ENABLED=true` | 按需开启文献元数据；不等于取得全文 |
| `EVIDENCE_SEMANTIC_ENABLED=true` | 开启配置的语义模型 |
| `DEEPSEEK_MODEL` | 账号实际可用模型名，显式填写 |
| `DEEPSEEK_API_KEY_FILE` | 模型私有密钥文件 |
| `DEEPSEEK_BUDGET_FILE` | 模型尝试预算，不能与搜索数据库混用 |
| `DEEPSEEK_MAX_CALLS` | 本地尝试上限，持久化预算模式当前最多300 |
| `EXTERNAL_COLLABORATION_CONFIG` | 私有外部伙伴清单与调度配置 |

失败尝试同样消耗本地预算，不通过重启或新建数据库绕过。默认示例不联系外部伙伴。外部服务的AIC、端点、能力、超时、任务上限及持久化journal必须由部署者核实；参见`external_collaboration.py`的配置校验。

## 4. 网页与插件

`evidence_mesh.web_test_app:app`是受保护的桥接服务，`web_message.html`是网页资源。配置`WEB_TEST_TOKEN_FILE`、总控/调用方AIC、端点、伙伴映射及客户端mTLS材料后启动。任务恢复数据库和插件访问配置使用私有持久化挂载，不能打包进浏览器资源。

`browser-extension/`支持Edge/Chrome开发者模式“加载解压缩的扩展”。安装与权限见其README。网页访问口令与插件独立凭据不同；插件凭据只在浏览器会话保存。当前采样为播放位置附近约30秒声音和最多6帧，需用户主动启动。

音频转写服务位于`deploy/audio-transcriber/`，使用独立镜像和私有网络，不开放宿主端口；首次运行下载模型。其依赖不属于主Python环境。插件完整视频链路需要此服务、图像模型及检索配置，不能用无密钥协议演示代替。

## 5. 验证与交付

从全新检出运行公开Python测试、插件模型测试、安全检查和`local_demo.py --smoke`。Docker容器构建、真实提供商请求及平台注册流程分别验收，不能因单元测试通过就宣称完成。

镜像构建仅复制requirements和src。不要上传真实`.env`、密钥、证书私钥、访问文件、预算数据库、原始音视频或日志。最终仓库commit可写入技术报告的源码版本，线上部署是否与该commit一致须另外核对。
