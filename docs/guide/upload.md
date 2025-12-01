# 文件上传

FileCodeBox 提供了多种灵活的文件上传方式，支持普通上传和分片上传，满足不同场景的需求。

## 上传方式

FileCodeBox 支持以下几种上传方式：

### 拖拽上传

将文件直接拖拽到上传区域即可开始上传。这是最便捷的上传方式。

1. 打开 FileCodeBox 首页
2. 将文件从文件管理器拖拽到上传区域
3. 松开鼠标，文件开始上传
4. 上传完成后获取提取码

::: tip 提示
拖拽上传支持同时拖拽多个文件（取决于主题支持）。
:::

### 点击上传

点击上传区域，通过系统文件选择器选择文件。

1. 点击上传区域的「选择文件」按钮
2. 在弹出的文件选择器中选择要上传的文件
3. 确认选择后文件开始上传
4. 上传完成后获取提取码

### 粘贴上传

支持从剪贴板直接粘贴图片进行上传（部分主题支持）。

1. 复制图片到剪贴板（截图或复制图片）
2. 在上传区域使用 `Ctrl+V`（Windows/Linux）或 `Cmd+V`（macOS）粘贴
3. 图片自动开始上传
4. 上传完成后获取提取码

::: warning 注意
粘贴上传仅支持图片格式，不支持其他文件类型。具体支持情况取决于所使用的主题。
:::

## 文件大小限制

### 默认限制

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `uploadSize` | 10MB | 单文件最大上传大小 |

### 修改上传限制

管理员可以通过管理面板或配置文件修改上传大小限制：

```python
# 设置最大上传大小为 100MB
uploadSize = 104857600  # 100 * 1024 * 1024
```

::: info 说明
`uploadSize` 的单位是字节。常用换算：
- 10MB = 10485760
- 50MB = 52428800
- 100MB = 104857600
- 500MB = 524288000
- 1GB = 1073741824
:::

### 超出限制的处理

当上传文件超过大小限制时，系统会返回 403 错误：

```json
{
  "detail": "大小超过限制,最大为10.00 MB"
}
```

## 普通上传 API

### 文件上传接口

**POST** `/share/file/`

Content-Type: `multipart/form-data`

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | file | 是 | 要上传的文件 |
| `expire_value` | int | 否 | 过期数值，默认 1 |
| `expire_style` | string | 否 | 过期方式，默认 `day` |

**过期方式选项：**

| 值 | 说明 |
|----|------|
| `day` | 按天过期 |
| `hour` | 按小时过期 |
| `minute` | 按分钟过期 |
| `forever` | 永不过期 |
| `count` | 按下载次数过期 |

**响应示例：**

```json
{
  "code": 200,
  "detail": {
    "code": "654321",
    "name": "example.pdf"
  }
}
```

**cURL 示例：**

```bash
curl -X POST "http://localhost:12345/share/file/" \
  -F "file=@/path/to/file.pdf" \
  -F "expire_value=7" \
  -F "expire_style=day"
```

## 分片上传 API

对于大文件，FileCodeBox 支持分片上传功能。分片上传将大文件分割成多个小块分别上传，支持断点续传。

::: warning 前提条件
分片上传功能需要管理员启用：`enableChunk=1`
:::

### 分片上传流程

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  初始化上传  │ ──▶ │  上传分片   │ ──▶ │  完成上传   │
│   /init/    │     │  /chunk/    │     │ /complete/  │
└─────────────┘     └─────────────┘     └─────────────┘
                          │
                          ▼
                    ┌───────────┐
                    │ 循环上传  │
                    │ 每个分片  │
                    └───────────┘
```

### 1. 初始化上传

**POST** `/chunk/upload/init/`

**请求参数：**

```json
{
  "file_name": "large_file.zip",
  "file_size": 104857600,
  "chunk_size": 5242880,
  "file_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_name` | string | 是 | - | 文件名 |
| `file_size` | int | 是 | - | 文件总大小（字节） |
| `chunk_size` | int | 否 | 5MB | 分片大小（字节） |
| `file_hash` | string | 是 | - | 文件的 SHA256 哈希值 |

**响应示例：**

```json
{
  "code": 200,
  "detail": {
    "existed": false,
    "upload_id": "abc123def456789",
    "chunk_size": 5242880,
    "total_chunks": 20,
    "uploaded_chunks": []
  }
}
```

| 字段 | 说明 |
|------|------|
| `existed` | 文件是否已存在（秒传） |
| `upload_id` | 上传会话 ID |
| `chunk_size` | 分片大小 |
| `total_chunks` | 总分片数 |
| `uploaded_chunks` | 已上传的分片索引列表 |

### 2. 上传分片

**POST** `/chunk/upload/chunk/{upload_id}/{chunk_index}`

**路径参数：**

| 参数 | 说明 |
|------|------|
| `upload_id` | 初始化时返回的上传会话 ID |
| `chunk_index` | 分片索引，从 0 开始 |

**请求体：**

Content-Type: `multipart/form-data`

| 参数 | 类型 | 说明 |
|------|------|------|
| `chunk` | file | 分片数据 |

**响应示例：**

```json
{
  "code": 200,
  "detail": {
    "chunk_hash": "a1b2c3d4e5f6..."
  }
}
```

**cURL 示例：**

```bash
# 上传第一个分片（索引为 0）
curl -X POST "http://localhost:12345/chunk/upload/chunk/abc123def456789/0" \
  -F "chunk=@/path/to/chunk_0"
```

### 3. 完成上传

**POST** `/chunk/upload/complete/{upload_id}`

**路径参数：**

| 参数 | 说明 |
|------|------|
| `upload_id` | 上传会话 ID |

**请求参数：**

```json
{
  "expire_value": 7,
  "expire_style": "day"
}
```

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `expire_value` | int | 是 | 过期数值 |
| `expire_style` | string | 是 | 过期方式 |

**响应示例：**

```json
{
  "code": 200,
  "detail": {
    "code": "789012",
    "name": "large_file.zip"
  }
}
```

### 断点续传

分片上传支持断点续传。当上传中断后：

1. 使用相同的 `file_hash` 重新调用初始化接口
2. 服务器返回 `uploaded_chunks` 列表，包含已上传的分片索引
3. 客户端只需上传不在列表中的分片
4. 所有分片上传完成后调用完成接口

**示例流程：**

```javascript
// 1. 初始化上传
const initResponse = await fetch('/chunk/upload/init/', {
  method: 'POST',
  body: JSON.stringify({
    file_name: 'large_file.zip',
    file_size: fileSize,
    chunk_size: 5 * 1024 * 1024,
    file_hash: fileHash
  })
});
const { upload_id, uploaded_chunks, total_chunks } = await initResponse.json();

// 2. 上传未完成的分片
for (let i = 0; i < total_chunks; i++) {
  if (!uploaded_chunks.includes(i)) {
    const chunk = file.slice(i * chunkSize, (i + 1) * chunkSize);
    await fetch(`/chunk/upload/chunk/${upload_id}/${i}`, {
      method: 'POST',
      body: chunk
    });
  }
}

// 3. 完成上传
await fetch(`/chunk/upload/complete/${upload_id}`, {
  method: 'POST',
  body: JSON.stringify({
    expire_value: 7,
    expire_style: 'day'
  })
});
```

## 错误处理

### 常见错误

| HTTP 状态码 | 错误信息 | 原因 | 解决方案 |
|-------------|----------|------|----------|
| 403 | 大小超过限制 | 文件超过 `uploadSize` 限制 | 减小文件大小或联系管理员调整限制 |
| 403 | 上传频率限制 | 超过 IP 上传频率限制 | 等待限制时间窗口后重试 |
| 400 | 过期时间类型错误 | `expire_style` 值不在允许列表中 | 使用有效的过期方式 |
| 404 | 上传会话不存在 | `upload_id` 无效或已过期 | 重新初始化上传 |
| 400 | 无效的分片索引 | `chunk_index` 超出范围 | 检查分片索引是否正确 |
| 400 | 分片不完整 | 完成上传时分片数量不足 | 确保所有分片都已上传 |

### 频率限制

系统对上传操作有频率限制，防止滥用：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `uploadMinute` | 1 | 限制时间窗口（分钟） |
| `uploadCount` | 10 | 时间窗口内最大上传次数 |

当超过频率限制时，需要等待时间窗口过后才能继续上传。

### 错误响应格式

```json
{
  "detail": "错误信息描述"
}
```

## 上传配置

### 相关配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `openUpload` | int | 1 | 是否开放上传（1=开放，0=关闭） |
| `uploadSize` | int | 10485760 | 最大上传大小（字节） |
| `enableChunk` | int | 0 | 是否启用分片上传（1=启用，0=禁用） |
| `uploadMinute` | int | 1 | 上传频率限制时间窗口（分钟） |
| `uploadCount` | int | 10 | 时间窗口内最大上传次数 |
| `expireStyle` | list | ["day","hour","minute","forever","count"] | 允许的过期方式 |

### 配置示例

```python
# 允许上传 100MB 文件，启用分片上传
uploadSize = 104857600
enableChunk = 1

# 放宽上传频率限制：每 5 分钟最多 50 次
uploadMinute = 5
uploadCount = 50

# 只允许按天和按次数过期
expireStyle = ["day", "count"]
```

## 下一步

- [文件分享](/guide/share) - 了解完整的分享流程
- [配置说明](/guide/configuration) - 了解所有配置选项
- [存储配置](/guide/storage) - 了解文件存储方式
- [安全设置](/guide/security) - 了解安全相关配置
