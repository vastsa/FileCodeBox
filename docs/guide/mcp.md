# MCP 接入

FileCodeBox 提供 **Model Context Protocol (MCP)** 接口，支持通过 Streamable HTTP 让兼容的 AI 客户端创建文本或文件分享。

## 连接配置

在 MCP 客户端添加远程 HTTP 服务：

- **传输方式**：Streamable HTTP
- **服务地址**：`http://<FileCodeBox 地址>:12345/mcp`
- **认证**：默认无需 Token

例如本机部署时，地址为 `http://localhost:12345/mcp`。若管理员关闭了游客上传，或在管理设置中启用了 MCP Token 校验，请在客户端设置 `Authorization: Bearer <管理员 Token>`。不要把 Token 提交到公开配置或代码仓库。

## 可用工具

- `share_text`：创建文本分享。必填参数 `text`；可选 `expire_value`、`expire_style`。
- `share_file`：上传 Base64 文件并创建分享。必填参数 `filename`、`content_base64`；可选 `content_type`、`expire_value`、`expire_style`。

过期方式 `expire_style` 支持 `day`、`hour`、`minute`、`forever` 和 `count`，`expire_value` 必须大于 0。调用成功后返回分享码、链接和 Markdown 链接。

## 安全与限制

MCP 上传遵循 FileCodeBox 的游客上传开关、管理员 Token 校验、上传大小限制、文件类型校验及上传频率限制。仅向可信任的 AI 客户端提供服务地址；使用公网部署时请配置 HTTPS 并妥善保管管理员 Token。
