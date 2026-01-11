# FileCodeBox API 文档

## API 版本: 2.1.0

## 目录
- [认证](#认证)
- [分享接口](#分享接口)
- [管理接口](#管理接口)

## 认证

部分接口需要在请求头中携带 `Authorization` 进行认证：

```
Authorization: Bearer <token>
```

### 获取 Token

当管理面板关闭了游客上传（`openUpload=0`）时，需要先登录获取 token：

```bash
curl -X POST "http://localhost:12345/admin/login" \
  -H "Content-Type: application/json" \
  -d '{"password": "FileCodeBox2023"}'
```

**响应示例：**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "token": "xxx.xxx.xxx",
    "token_type": "Bearer"
  }
}
```

## 分享接口

### 分享文本

**POST** `/share/text/`

分享文本内容，获取分享码。

**请求参数：**

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|-------|------|------|--------|------|
| text | string | 是 | - | 要分享的文本内容 |
| expire_value | integer | 否 | 1 | 过期时间值 |
| expire_style | string | 否 | "day" | 过期时间单位(day/hour/minute/count/forever) |

**cURL 示例：**

```bash
# 游客上传（openUpload=1 时）
curl -X POST "http://localhost:12345/share/text/" \
  -F "text=这是要分享的文本内容" \
  -F "expire_value=1" \
  -F "expire_style=day"

# 需要认证时（openUpload=0 时）
curl -X POST "http://localhost:12345/share/text/" \
  -H "Authorization: Bearer xxx.xxx.xxx" \
  -F "text=这是要分享的文本内容"
```

**响应示例：**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "code": "abc123"
  }
}
```

### 分享文件

**POST** `/share/file/`

上传并分享文件，获取分享码。

**请求参数：**

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|-------|------|------|--------|------|
| file | file | 是 | - | 要上传的文件 |
| expire_value | integer | 否 | 1 | 过期时间值 |
| expire_style | string | 否 | "day" | 过期时间单位(day/hour/minute/count/forever) |

**cURL 示例：**

```bash
# 上传文件（默认1天有效期）
curl -X POST "http://localhost:12345/share/file/" \
  -F "file=@/path/to/file.txt"

# 上传文件（7天有效期）
curl -X POST "http://localhost:12345/share/file/" \
  -F "file=@/path/to/file.txt" \
  -F "expire_value=7" \
  -F "expire_style=day"

# 上传文件（可下载10次）
curl -X POST "http://localhost:12345/share/file/" \
  -F "file=@/path/to/file.txt" \
  -F "expire_value=10" \
  -F "expire_style=count"

# 需要认证时
curl -X POST "http://localhost:12345/share/file/" \
  -H "Authorization: Bearer xxx.xxx.xxx" \
  -F "file=@/path/to/file.txt"
```

**响应示例：**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "code": "abc123",
    "name": "example.txt"
  }
}
```

### 获取文件信息

**GET** `/share/select/`

通过分享码获取文件信息（直接下载文件）。

**请求参数：**

| 参数名 | 类型 | 必填 | 描述 |
|-------|------|------|------|
| code | string | 是 | 文件分享码 |

**cURL 示例：**

```bash
# 通过取件码下载文件
curl -L "http://localhost:12345/share/select/?code=abc123" -o downloaded_file
```

**响应示例：**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "code": "abc123",
    "name": "example.txt",
    "size": 1024,
    "text": "文件内容或下载链接"
  }
}
```

### 选择文件

**POST** `/share/select/`

通过分享码选择文件。

**请求参数：**

| 参数名 | 类型 | 必填 | 描述 |
|-------|------|------|------|
| code | string | 是 | 文件分享码 |

**响应示例：**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "code": "abc123",
    "name": "example.txt",
    "size": 1024,
    "text": "文件内容或下载链接"
  }
}
```

### 下载文件

**GET** `/share/download`

下载分享的文件。

**请求参数：**

| 参数名 | 类型 | 必填 | 描述 |
|-------|------|------|------|
| key | string | 是 | 下载密钥 |
| code | string | 是 | 文件分享码 |

## 管理接口

### 管理员登录

**POST** `/admin/login`

管理员登录获取token。

**请求参数：**

| 参数名 | 类型 | 必填 | 描述 |
|-------|------|------|------|
| password | string | 是 | 管理员密码 |

### 仪表盘数据

**GET** `/admin/dashboard`

获取系统仪表盘数据。

**响应示例：**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "totalFiles": 100,
    "storageUsed": "1.5GB",
    "sysUptime": "10天",
    "yesterdayCount": 50,
    "yesterdaySize": "500MB",
    "todayCount": 30,
    "todaySize": "300MB"
  }
}
```

### 文件列表

**GET** `/admin/file/list`

获取系统中的文件列表。

**请求参数：**

| 参数名 | 类型 | 必填 | 默认值 | 描述 |
|-------|------|------|--------|------|
| page | integer | 否 | 1 | 当前页码 |
| size | integer | 否 | 10 | 每页数量 |
| keyword | string | 否 | "" | 搜索关键词 |

**响应示例：**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "page": 1,
    "size": 10,
    "total": 100,
    "data": [
      {
        "id": 1,
        "name": "example.txt",
        "size": 1024,
        "created_at": "2024-01-01 12:00:00"
      }
    ]
  }
}
```

### 删除文件

**DELETE** `/admin/file/delete`

删除系统中的文件。

**请求参数：**

| 参数名 | 类型 | 必填 | 描述 |
|-------|------|------|------|
| id | integer | 是 | 文件ID |

### 获取配置

**GET** `/admin/config/get`

获取系统配置信息。

### 更新配置

**PATCH** `/admin/config/update`

更新系统配置信息。

## 错误响应

当发生错误时，API会返回对应的错误信息：

```json
{
  "code": 422,
  "detail": [
    {
      "loc": ["body", "password"],
      "msg": "密码不能为空",
      "type": "value_error"
    }
  ]
}
```

## 状态码说明

- 200: 请求成功
- 401: 未授权
- 403: 禁止访问
- 404: 资源不存在
- 422: 请求参数验证错误
- 500: 服务器内部错误 