# 管理面板

FileCodeBox 提供了功能完善的管理面板，让管理员可以方便地管理文件、查看系统状态和修改配置。本文档介绍管理面板的各项功能和使用方法。

## 访问管理面板

### 登录方式

管理面板位于 `/admin` 路径。访问方式：

1. 在浏览器中访问 `http://your-domain.com/admin`
2. 输入管理员密码（`admin_token` 配置项的值）
3. 点击登录按钮

::: tip 提示
默认管理员密码是 `FileCodeBox2023`。请务必在生产环境中修改此密码，详见 [安全设置](/guide/security)。
:::

### 显示管理入口

默认情况下，首页不显示管理面板入口。您可以通过配置控制是否显示：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `showAdminAddr` | int | `0` | 是否在首页显示管理入口（1=显示，0=隐藏） |

::: warning 安全建议
在公开服务中，建议保持 `showAdminAddr` 为 `0`，通过直接访问 `/admin` 路径进入管理面板，减少被恶意扫描的风险。
:::

### 认证机制

管理面板使用 JWT（JSON Web Token）进行身份认证：

1. 登录成功后，服务器返回一个包含管理员身份的 Token
2. 后续请求通过 `Authorization: Bearer <token>` 头部携带 Token
3. Token 用于验证管理员身份，确保只有授权用户可以访问管理功能

## 仪表盘

登录后首先看到的是仪表盘页面，展示系统的整体运行状态。

### 统计指标

仪表盘显示以下关键指标：

| 指标 | 说明 |
|------|------|
| **文件总数** (`totalFiles`) | 系统中存储的文件总数量 |
| **存储使用量** (`storageUsed`) | 所有文件占用的总存储空间（字节） |
| **系统运行时间** (`sysUptime`) | 系统首次启动的时间 |
| **昨日上传数** (`yesterdayCount`) | 昨天一整天上传的文件数量 |
| **昨日上传量** (`yesterdaySize`) | 昨天上传文件的总大小（字节） |
| **今日上传数** (`todayCount`) | 今天到目前为止上传的文件数量 |
| **今日上传量** (`todaySize`) | 今天上传文件的总大小（字节） |

### 指标说明

- **文件总数**：包括所有未过期的文件和文本分享
- **存储使用量**：显示实际文件占用的存储空间，不包括数据库等系统文件
- **昨日/今日统计**：基于文件创建时间计算，用于了解系统使用趋势

::: tip 提示
存储使用量显示的是字节数。例如 `10485760` 表示约 10MB。
:::

## 文件管理

### 文件列表

文件管理页面展示系统中所有已分享的文件，支持分页浏览和搜索。

**列表信息包括：**
- 文件 ID
- 提取码（code）
- 文件名前缀（prefix）
- 文件后缀（suffix）
- 文件大小
- 创建时间
- 过期时间
- 剩余下载次数

### 搜索文件

使用搜索功能可以快速找到特定文件：

1. 在搜索框中输入关键词
2. 系统会根据文件名前缀（prefix）进行模糊匹配
3. 搜索结果实时更新

**搜索示例：**
- 输入 `report` 可以找到所有文件名包含 "report" 的文件
- 输入 `.pdf` 可以找到所有 PDF 文件（如果文件名包含此字符串）

### 分页浏览

文件列表支持分页显示：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `page` | `1` | 当前页码 |
| `size` | `10` | 每页显示数量 |

### 删除文件

管理员可以删除任意文件：

1. 在文件列表中找到要删除的文件
2. 点击删除按钮
3. 确认删除操作

::: danger 警告
删除操作不可恢复！文件将从存储后端永久删除，同时删除数据库中的记录。
:::

**删除流程：**
1. 系统首先从存储后端（本地/S3/OneDrive 等）删除实际文件
2. 然后从数据库中删除文件记录
3. 删除后，对应的提取码将失效

### 下载文件

管理员可以直接下载任意文件：

1. 在文件列表中找到目标文件
2. 点击下载按钮
3. 文件将通过浏览器下载

对于文本分享，系统会直接返回文本内容而不是下载文件。

### 修改文件信息

管理员可以修改已分享文件的部分信息：

| 可修改字段 | 说明 |
|------------|------|
| `code` | 提取码（必须唯一，不能与其他文件重复） |
| `prefix` | 文件名前缀 |
| `suffix` | 文件后缀名 |
| `expired_at` | 过期时间 |
| `expired_count` | 剩余下载次数 |

**修改提取码：**
```
原提取码：abc123
新提取码：myfile2024
```

::: warning 注意
修改提取码时，系统会检查新提取码是否已被使用。如果已存在相同的提取码，修改将失败。
:::

## 本地文件管理

除了管理已分享的文件，管理面板还提供了本地文件管理功能，用于管理 `data/local` 目录中的文件。

### 查看本地文件

本地文件列表显示 `data/local` 目录中的所有文件：

| 信息 | 说明 |
|------|------|
| 文件名 | 文件的完整名称 |
| 创建时间 | 文件的创建时间 |
| 文件大小 | 文件大小（字节） |

### 分享本地文件

可以将本地文件快速分享：

1. 在本地文件列表中选择要分享的文件
2. 设置过期方式和过期值
3. 点击分享按钮
4. 系统生成提取码

**分享参数：**

| 参数 | 说明 |
|------|------|
| `filename` | 要分享的文件名 |
| `expire_style` | 过期方式（day/hour/minute/forever/count） |
| `expire_value` | 过期值（天数/小时数/分钟数/下载次数） |

### 删除本地文件

可以删除 `data/local` 目录中的文件：

1. 在本地文件列表中找到要删除的文件
2. 点击删除按钮
3. 确认删除

::: tip 使用场景
本地文件管理功能适用于：
- 批量上传文件到服务器后进行分享
- 管理通过其他方式上传到服务器的文件
- 清理不需要的本地文件
:::

## 系统设置

### 查看配置

在系统设置页面可以查看当前所有配置项的值。配置项按类别分组显示：

- 基础设置（站点名称、描述等）
- 上传设置（文件大小限制、频率限制等）
- 存储设置（存储类型、路径等）
- 主题设置（主题选择、透明度等）
- 安全设置（管理员密码、错误限制等）

### 修改配置

管理员可以通过管理面板修改大部分配置：

1. 进入系统设置页面
2. 找到要修改的配置项
3. 输入新的值
4. 点击保存按钮

**可修改的配置项：**

| 类别 | 配置项示例 |
|------|------------|
| 基础设置 | `name`, `description`, `keywords`, `notify_title`, `notify_content` |
| 上传设置 | `uploadSize`, `uploadMinute`, `uploadCount`, `openUpload`, `enableChunk` |
| 过期设置 | `expireStyle`, `max_save_seconds` |
| 主题设置 | `themesSelect`, `opacity`, `background` |
| 安全设置 | `admin_token`, `showAdminAddr`, `errorMinute`, `errorCount` |
| 存储设置 | `file_storage`, `storage_path` 及各存储后端的配置 |

::: warning 注意
- `admin_token`（管理员密码）不能设置为空
- `themesChoices`（主题列表）不可通过管理面板修改
- 修改存储设置后，已有文件不会自动迁移
:::

### 配置生效

配置修改后立即生效，无需重启服务。配置保存在数据库中，重启后仍然有效。

**配置存储位置：**
- 数据库：`data/filecodebox.db`
- 表名：`keyvalue`
- 键名：`settings`

## API 接口

管理面板的所有功能都通过 REST API 实现，以下是主要接口：

### 认证接口

**登录**
```
POST /admin/login
Content-Type: application/json

{
    "password": "your-admin-password"
}
```

响应：
```json
{
    "code": 200,
    "detail": {
        "token": "eyJhbGciOiJIUzI1NiIs...",
        "token_type": "Bearer"
    }
}
```

### 仪表盘接口

**获取统计数据**
```
GET /admin/dashboard
Authorization: Bearer <token>
```

### 文件管理接口

**获取文件列表**
```
GET /admin/file/list?page=1&size=10&keyword=
Authorization: Bearer <token>
```

**删除文件**
```
DELETE /admin/file/delete
Authorization: Bearer <token>
Content-Type: application/json

{
    "id": 123
}
```

**下载文件**
```
GET /admin/file/download?id=123
Authorization: Bearer <token>
```

**修改文件信息**
```
PATCH /admin/file/update
Authorization: Bearer <token>
Content-Type: application/json

{
    "id": 123,
    "code": "newcode",
    "expired_at": "2024-12-31T23:59:59"
}
```

### 本地文件接口

**获取本地文件列表**
```
GET /admin/local/lists
Authorization: Bearer <token>
```

**删除本地文件**
```
DELETE /admin/local/delete
Authorization: Bearer <token>
Content-Type: application/json

{
    "filename": "example.txt"
}
```

**分享本地文件**
```
POST /admin/local/share
Authorization: Bearer <token>
Content-Type: application/json

{
    "filename": "example.txt",
    "expire_style": "day",
    "expire_value": 7
}
```

### 配置接口

**获取配置**
```
GET /admin/config/get
Authorization: Bearer <token>
```

**更新配置**
```
PATCH /admin/config/update
Authorization: Bearer <token>
Content-Type: application/json

{
    "admin_token": "new-password",
    "uploadSize": 52428800
}
```

## 常见问题

### 忘记管理员密码

如果忘记了管理员密码，可以通过以下方式重置：

1. 停止 FileCodeBox 服务
2. 使用 SQLite 工具打开 `data/filecodebox.db`
3. 查询 `keyvalue` 表中 `key='settings'` 的记录
4. 修改 JSON 中的 `admin_token` 值
5. 重启服务

```sql
-- 查看当前配置
SELECT * FROM keyvalue WHERE key = 'settings';

-- 或者删除配置，恢复默认密码
DELETE FROM keyvalue WHERE key = 'settings';
```

### 文件删除失败

如果删除文件时出现错误，可能的原因：

1. **存储后端连接失败**：检查存储配置是否正确
2. **文件已不存在**：文件可能已被手动删除
3. **权限不足**：检查存储目录的写入权限

### 配置修改不生效

如果修改配置后没有生效：

1. 检查是否点击了保存按钮
2. 刷新页面查看配置是否已保存
3. 检查浏览器控制台是否有错误信息
4. 确认配置值的格式是否正确（如数字类型不要输入字符串）

## 下一步

- [配置说明](/guide/configuration) - 了解所有配置选项的详细说明
- [安全设置](/guide/security) - 了解如何增强系统安全性
- [存储配置](/guide/storage) - 配置不同的存储后端
