# 安全设置

FileCodeBox 提供了多层安全机制来保护您的文件分享服务。本文档介绍如何正确配置安全选项，确保系统安全运行。

## 管理员密码

### 修改默认密码

::: danger 重要安全警告
FileCodeBox 的默认管理员密码是 `FileCodeBox2023`。**在生产环境中必须立即修改此密码！**使用默认密码会导致任何人都可以访问您的管理面板。
:::

修改管理员密码有两种方式：

**方式一：通过管理面板修改（推荐）**

1. 访问 `/admin` 进入管理面板
2. 使用当前密码登录
3. 进入「系统设置」页面
4. 找到 `admin_token` 配置项
5. 输入新的安全密码并保存

**方式二：通过数据库修改**

配置存储在 `data/filecodebox.db` 数据库的 `keyvalue` 表中，可以直接修改 `admin_token` 的值。

### 密码安全建议

- 使用至少 16 个字符的强密码
- 包含大小写字母、数字和特殊字符
- 避免使用常见词汇或个人信息
- 定期更换密码

```python
# 推荐的密码格式示例
"admin_token": "Xk9#mP2$vL5@nQ8&wR3"
```

### 隐藏管理入口

默认情况下，管理面板入口是隐藏的。您可以通过 `showAdminAddr` 配置控制是否在首页显示管理入口：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `showAdminAddr` | int | `0` | 是否显示管理入口（1=显示，0=隐藏） |

::: tip 建议
在公开服务中，建议保持 `showAdminAddr` 为 `0`，通过直接访问 `/admin` 路径进入管理面板。
:::

## IP 速率限制

FileCodeBox 内置了基于 IP 的速率限制机制，可以有效防止滥用和攻击。

### 上传频率限制

限制单个 IP 在指定时间内的上传次数：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `uploadMinute` | int | `1` | 上传限制的时间窗口（分钟） |
| `uploadCount` | int | `10` | 在时间窗口内允许的最大上传次数 |

**工作原理：**
- 系统记录每个 IP 的上传请求
- 当某 IP 在 `uploadMinute` 分钟内的上传次数达到 `uploadCount` 时
- 该 IP 的后续上传请求将被拒绝，返回 HTTP 423 错误
- 等待时间窗口过期后，计数器重置

**配置示例：**

```python
# 宽松配置：5分钟内最多上传20次
{
    "uploadMinute": 5,
    "uploadCount": 20
}

# 严格配置：1分钟内最多上传3次
{
    "uploadMinute": 1,
    "uploadCount": 3
}
```

### 错误次数限制

限制单个 IP 的错误尝试次数，防止暴力破解提取码：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `errorMinute` | int | `1` | 错误限制的时间窗口（分钟） |
| `errorCount` | int | `1` | 在时间窗口内允许的最大错误次数 |

**工作原理：**
- 当用户输入错误的提取码时，系统记录该 IP 的错误次数
- 当错误次数达到 `errorCount` 时，该 IP 将被暂时锁定
- 锁定时间为 `errorMinute` 分钟
- 锁定期间，该 IP 的所有提取请求都将被拒绝

**配置示例：**

```python
# 防暴力破解配置：5分钟内最多允许3次错误
{
    "errorMinute": 5,
    "errorCount": 3
}
```

::: warning 注意
默认配置 `errorMinute=1, errorCount=1` 非常严格，意味着输入一次错误的提取码后需要等待1分钟才能重试。根据实际需求调整此配置。
:::

## 上传限制

### 文件大小限制

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `uploadSize` | int | `10485760` | 单文件最大上传大小（字节），默认 10MB |
| `openUpload` | int | `1` | 是否开启上传功能（1=开启，0=关闭） |

**常用大小换算：**
- 10MB = 10 * 1024 * 1024 = `10485760`
- 50MB = 50 * 1024 * 1024 = `52428800`
- 100MB = 100 * 1024 * 1024 = `104857600`
- 1GB = 1024 * 1024 * 1024 = `1073741824`

### 文件过期设置

通过文件过期机制，可以自动清理过期文件，减少存储占用和安全风险：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `expireStyle` | list | `["day","hour","minute","forever","count"]` | 可选的过期方式 |
| `max_save_seconds` | int | `0` | 文件最大保存时间（秒），0 表示不限制 |

**过期方式说明：**
- `day` - 按天数过期
- `hour` - 按小时过期
- `minute` - 按分钟过期
- `forever` - 永不过期（需要字符串提取码）
- `count` - 按下载次数过期

**安全建议：**

对于公开服务，建议：
1. 移除 `forever` 选项，避免文件永久存储
2. 设置 `max_save_seconds` 限制最长保存时间
3. 优先使用 `count` 方式，下载后自动删除

```python
# 公开服务推荐配置
{
    "expireStyle": ["hour", "minute", "count"],
    "max_save_seconds": 86400  # 最长保存1天
}
```

### 关闭上传功能

在某些情况下，您可能需要临时关闭上传功能：

```python
{
    "openUpload": 0  # 关闭上传功能
}
```

## 反向代理安全配置

在生产环境中，通常会使用 Nginx 或其他反向代理服务器。以下是安全配置建议：

### Nginx 配置示例

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # 强制 HTTPS 重定向
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL 证书配置
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers on;
    
    # 安全头部
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    
    # 限制请求体大小（与 uploadSize 配置一致）
    client_max_body_size 100M;
    
    # 传递真实 IP
    location / {
        proxy_pass http://127.0.0.1:12345;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # 静态资源缓存
    location /assets {
        proxy_pass http://127.0.0.1:12345;
        proxy_cache_valid 200 7d;
        add_header Cache-Control "public, max-age=604800";
    }
}
```

### 关键安全配置说明

**1. 传递真实 IP**

FileCodeBox 的 IP 限制功能依赖于获取客户端真实 IP。系统会按以下顺序获取 IP：
1. `X-Real-IP` 请求头
2. `X-Forwarded-For` 请求头
3. 直接连接的客户端 IP

确保反向代理正确设置这些头部：

```nginx
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

**2. 请求体大小限制**

Nginx 的 `client_max_body_size` 应该与 FileCodeBox 的 `uploadSize` 配置一致或略大：

```nginx
client_max_body_size 100M;  # 允许上传最大 100MB
```

**3. HTTPS 加密**

强烈建议在生产环境中启用 HTTPS：
- 保护用户上传的文件内容
- 保护管理员登录凭据
- 防止中间人攻击

### Caddy 配置示例

```nginx
your-domain.com {
    reverse_proxy localhost:12345
    
    header {
        X-Frame-Options "SAMEORIGIN"
        X-Content-Type-Options "nosniff"
        X-XSS-Protection "1; mode=block"
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }
}
```

## 安全检查清单

部署 FileCodeBox 前，请确认以下安全配置：

- [ ] 已修改默认管理员密码 `admin_token`
- [ ] 已隐藏管理入口 `showAdminAddr: 0`
- [ ] 已配置合适的上传频率限制
- [ ] 已配置错误次数限制防止暴力破解
- [ ] 已设置合理的文件大小限制
- [ ] 已配置文件过期策略
- [ ] 已启用 HTTPS 加密
- [ ] 反向代理已正确传递真实 IP
- [ ] 已设置安全响应头部

## 推荐安全配置

### 公开服务配置

```python
{
    "admin_token": "your-very-secure-password",
    "showAdminAddr": 0,
    "uploadSize": 10485760,           # 10MB
    "uploadMinute": 1,
    "uploadCount": 5,
    "errorMinute": 5,
    "errorCount": 3,
    "expireStyle": ["hour", "minute", "count"],
    "max_save_seconds": 86400,        # 最长1天
    "openUpload": 1
}
```

### 内部服务配置

```python
{
    "admin_token": "internal-secure-password",
    "showAdminAddr": 1,
    "uploadSize": 104857600,          # 100MB
    "uploadMinute": 5,
    "uploadCount": 50,
    "errorMinute": 1,
    "errorCount": 5,
    "expireStyle": ["day", "hour", "forever"],
    "max_save_seconds": 0,            # 不限制
    "openUpload": 1
}
```

## 下一步

- [配置说明](/guide/configuration) - 了解所有配置选项
- [存储配置](/guide/storage) - 配置安全的存储后端
- [文件分享](/guide/share) - 了解文件分享功能
