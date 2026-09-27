# 公网 HTTPS 预演 ACS

本目录由 `scripts/build_preview_acs.py` 从正式草稿生成，用于记录当前可访问的公网 HTTPS
endpoint。文件显式移除了 mTLS 声明，并保留 `active=false`、占位 AIC 和提供方占位值，
因此不能直接提交审核。

当前预演证明公网 TLS 和 AIP-RPC 状态机可用，不证明 Registry 审核、AIC 身份、mTLS、
Discovery、AMP 或梧桐平台验收完成。正式草稿仍位于 `registry/acs-drafts/`。
