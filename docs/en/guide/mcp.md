# MCP Integration

FileCodeBox provides a **Model Context Protocol (MCP)** endpoint over Streamable HTTP. Compatible AI clients can create text or file shares through it.

## Connection

Add a remote HTTP server in your MCP client:

- **Transport**: Streamable HTTP
- **Server URL**: `http://<FileCodeBox host>:12345/mcp`
- **Authentication**: no token required by default

For a local instance, use `http://localhost:12345/mcp`. If the administrator disables guest uploads or enables MCP token validation in the admin settings, configure `Authorization: Bearer <admin token>` in the client. Never commit the token to public configuration or source code.

## Available tools

- `share_text`: create a text share. Required: `text`; optional: `expire_value`, `expire_style`.
- `share_file`: upload a Base64-encoded file and create a share. Required: `filename`, `content_base64`; optional: `content_type`, `expire_value`, `expire_style`.

`expire_style` accepts `day`, `hour`, `minute`, `forever`, or `count`; `expire_value` must be greater than zero. Successful calls return a share code, URL, and Markdown link.

## Security and limits

MCP uploads follow FileCodeBox's guest-upload switch, admin-token validation, upload-size and file-type limits, and upload rate limits. Expose the endpoint only to trusted AI clients. Use HTTPS for public deployments and keep the admin token secure.
