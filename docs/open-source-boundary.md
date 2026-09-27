# 开源与公开边界

## 可公开内容

- Leader、三个 Partner、确定性裁决逻辑及测试代码；
- 使用占位身份和占位端点的 ACS 草稿；
- 不含个人信息、凭据和真实科研敏感数据的合成示例；
- 脱敏后的测试结果、架构说明和部署模板；
- 官方公开发行包的版本、来源提交号和 SHA-256 清单；本地下载的 wheel 二进制包不
  进入本仓库。

## 不进入公开仓库

- Registry 实名主体、身份证明和账号信息；
- 正式域名账户、DNS 管理凭据和云平台凭据；
- AIC/EAB、API Key、Token、Cookie、密码；
- mTLS 私钥、客户端或服务端证书、信任包；
- 未获授权的论文全文、实验原始数据或个人信息；
- 包含学校名称、校徽、指导教师或其他身份线索的匿名参赛材料。

私有部署值应保存在被 `.gitignore` 排除的 `.env`、`deploy/secrets/`、
`registry/acs-private/` 或 `evidence/private/` 中，通过环境变量或部署时生成步骤注入。

## 发布前检查

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\check_public_repo.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\validate_acs_drafts.py
```

历史公网验证记录可以保留当次端点，用于证明测试可审计；它们不作为当前部署配置，
也不得包含凭据、实名信息或未授权数据。

## 许可证

团队已选择 Apache License 2.0 用于本项目原创代码与文档。官方 ACPs SDK、WIT 和
其他第三方组件继续适用各自的许可条款；本项目许可证不覆盖这些第三方材料。
