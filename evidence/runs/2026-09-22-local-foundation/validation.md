# 本地技术底座验证记录

日期：2026-09-22  
环境：Windows / Python 3.13.2 / 项目独立 `.venv`

## 官方文件完整性

- `acps_sdk-2.2.0-py3-none-any.whl`
  - manifest：`3bad5c3669319209db868411ca73ae7622bd98c7e17ccd9e06cb5910a35ec822`
  - 本地计算：一致
- `wit_framework-2.1.0-cp312.cp313.cp314-none-any.whl`
  - manifest：`21720d2401a380484fa6c4dd0b4bf5ccba9a1157b597365dbf263f174e52efaa`
  - 本地计算：一致

## 导入与版本

```text
python=ok
acps-sdk=2.2.0
wit-framework=2.1.0
acps_sdk_import=acps_sdk
wit_import=wit
```

## 官方发布预检

命令在完整发布目录 `vendor/wit/v2.1.0` 中执行：

```text
{"acpsSdkVersion":"2.2.0","aipPersistence":"passed","witVersion":"2.1.0"}
exit_code=0
```

## 本地 Direct RPC

Partner 健康检查：

```json
{"status":"ok","aic":"competition-local-partner"}
```

Leader 自动断言：

```text
direct_rpc_assertions=passed
startState=awaiting-completion
finalState=completed
products=['Partner received: 梧桐平台本地协议联调']
```

服务端共收到两轮测试的四个 `POST /rpc` 请求，均返回 HTTP 200。

## 适用边界

此验证只证明当前机器上的 SDK 安装、AIP 任务状态流和 Direct RPC 产品返回正常。
本地示例显式关闭身份绑定，不代表已经完成梧桐 Registry 注册、AIC 分配、EAB/mTLS
认证或线上部署。最小 WIT Agent 还需要可用的模型 API 配置后另行验证。
