# 预签名上传 API 文档

## 概述

预签名上传功能提供统一的文件上传接口，根据后端存储类型自动选择最优上传方式：

- **S3 存储**: 返回预签名 URL，客户端直传 S3（减少服务器带宽压力）
- **其他存储**: 返回代理上传 URL，通过服务器中转上传

## 上传流程

### 流程图

```
┌─────────┐     1. 初始化上传      ┌─────────┐
│  客户端  │ ──────────────────────▶ │  服务器  │
└─────────┘                        └─────────┘
     │                                  │
     │◀─────── 返回 upload_url + mode ──┤
     │                                  │
     │  ┌─────────────────────────────────────────┐
     │  │ if mode == "direct" (S3存储)            │
     │  │   2a. PUT 文件到 upload_url (S3)        │
     │  │   3a. POST /confirm 确认上传            │
     │  │                                         │
     │  │ if mode == "proxy" (其他存储)           │
     │  │   2b. PUT 文件到 upload_url (服务器)    │
     │  │   (自动返回分享码，无需确认)            │
     │  └─────────────────────────────────────────┘
     │
     ▼
  获取分享码
```

---

## API 端点

### 1. 初始化上传

初始化预签名上传会话，获取上传 URL 和模式。

**请求**

```
POST /presign/upload/init
Content-Type: application/json
```

**请求体**

| 字段         | 类型    | 必填 | 默认值 | 说明                                    |
| ------------ | ------- | ---- | ------ | --------------------------------------- |
| file_name    | string  | ✅   | -      | 文件名（含扩展名）                      |
| file_size    | integer | ✅   | -      | 文件大小（字节）                        |
| expire_value | integer | ❌   | 1      | 过期时间值                              |
| expire_style | string  | ❌   | "day"  | 过期类型：day/hour/minute/forever/count |

**请求示例**

```json
{
  "file_name": "document.pdf",
  "file_size": 1048576,
  "expire_value": 7,
  "expire_style": "day"
}
```

**响应**

```json
{
  "code": 200,
  "detail": {
    "upload_id": "a1b2c3d4e5f6...",
    "upload_url": "https://bucket.s3.amazonaws.com/path?X-Amz-Signature=...",
    "mode": "direct",
    "save_path": "share/data/2024/01/01/uuid/document.pdf",
    "expires_in": 900
  }
}
```

**响应字段说明**

| 字段       | 类型    | 说明                                                  |
| ---------- | ------- | ----------------------------------------------------- |
| upload_id  | string  | 上传会话 ID，后续操作需要                             |
| upload_url | string  | 上传目标 URL                                          |
| mode       | string  | 上传模式：`direct`（直传 S3）或 `proxy`（服务器代理） |
| save_path  | string  | 文件存储路径                                          |
| expires_in | integer | URL 有效期（秒），默认 900 秒（15 分钟）              |

**错误响应**

| 状态码 | 说明                           |
| ------ | ------------------------------ |
| 400    | 过期时间类型错误               |
| 403    | 文件大小超过限制 / IP 频率限制 |

---

### 2a. 直传模式 - 上传文件到 S3

当 `mode == "direct"` 时，客户端直接将文件 PUT 到返回的预签名 URL。

**请求**

```
PUT {upload_url}
Content-Type: application/octet-stream

[文件二进制内容]
```

**注意事项**

- 直接使用返回的 `upload_url`，不要修改
- Content-Type 建议使用 `application/octet-stream`
- 这是直接请求 S3，不经过服务器

**JavaScript 示例**

```javascript
const response = await fetch(uploadUrl, {
  method: 'PUT',
  body: file,
  headers: {
    'Content-Type': 'application/octet-stream',
  },
})

if (response.ok) {
  // 上传成功，调用确认接口
}
```

---

### 2b. 代理模式 - 上传文件到服务器

当 `mode == "proxy"` 时，客户端将文件 PUT 到服务器代理端点。

**请求**

```
PUT /presign/upload/proxy/{upload_id}
Content-Type: multipart/form-data

file: [文件]
```

**路径参数**

| 参数      | 说明                      |
| --------- | ------------------------- |
| upload_id | 初始化时返回的上传会话 ID |

**响应**

```json
{
  "code": 200,
  "detail": {
    "code": "123456",
    "name": "document.pdf"
  }
}
```

**注意**: 代理模式上传成功后直接返回分享码，无需调用确认接口。

**错误响应**

| 状态码 | 说明                                    |
| ------ | --------------------------------------- |
| 400    | 文件大小与声明不符 / 会话不支持代理上传 |
| 404    | 上传会话不存在或已过期                  |
| 500    | 文件保存失败                            |

---

### 3. 确认上传（仅直传模式）

直传模式下，客户端完成 S3 上传后调用此接口确认并获取分享码。

**请求**

```
POST /presign/upload/confirm/{upload_id}
Content-Type: application/json
```

**路径参数**

| 参数      | 说明                      |
| --------- | ------------------------- |
| upload_id | 初始化时返回的上传会话 ID |

**请求体**

| 字段         | 类型    | 必填 | 默认值 | 说明       |
| ------------ | ------- | ---- | ------ | ---------- |
| expire_value | integer | ❌   | 1      | 过期时间值 |
| expire_style | string  | ❌   | "day"  | 过期类型   |

**请求示例**

```json
{
  "expire_value": 7,
  "expire_style": "day"
}
```

**响应**

```json
{
  "code": 200,
  "detail": {
    "code": "123456",
    "name": "document.pdf"
  }
}
```

**错误响应**

| 状态码 | 说明                                          |
| ------ | --------------------------------------------- |
| 400    | 会话不支持直传确认                            |
| 404    | 上传会话不存在或已过期 / 文件未上传或上传失败 |

---

### 4. 查询上传状态

查询上传会话的当前状态。

**请求**

```
GET /presign/upload/status/{upload_id}
```

**响应**

```json
{
  "code": 200,
  "detail": {
    "upload_id": "a1b2c3d4e5f6...",
    "file_name": "document.pdf",
    "file_size": 1048576,
    "mode": "direct",
    "created_at": "2024-01-01T12:00:00",
    "expires_at": "2024-01-01T12:15:00",
    "is_expired": false
  }
}
```

**错误响应**

| 状态码 | 说明           |
| ------ | -------------- |
| 404    | 上传会话不存在 |

---

### 5. 取消上传

取消上传会话并清理相关资源。

**请求**

```
DELETE /presign/upload/{upload_id}
```

**响应**

```json
{
  "code": 200,
  "detail": {
    "message": "上传会话已取消"
  }
}
```

**错误响应**

| 状态码 | 说明           |
| ------ | -------------- |
| 404    | 上传会话不存在 |

---

## 前端集成示例

### 完整上传流程（JavaScript/TypeScript）

```typescript
interface PresignInitResponse {
  upload_id: string
  upload_url: string
  mode: 'direct' | 'proxy'
  save_path: string
  expires_in: number
}

interface UploadResult {
  code: string
  name: string
}

async function uploadFile(
  file: File,
  expireValue: number = 1,
  expireStyle: string = 'day'
): Promise<UploadResult> {
  // 1. 初始化上传
  const initResponse = await fetch('/presign/upload/init', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      file_name: file.name,
      file_size: file.size,
      expire_value: expireValue,
      expire_style: expireStyle,
    }),
  })

  const initData = await initResponse.json()
  if (initData.code !== 200) {
    throw new Error(initData.detail)
  }

  const { upload_id, upload_url, mode } = initData.detail as PresignInitResponse

  // 2. 根据模式上传文件
  if (mode === 'direct') {
    // 直传模式：上传到S3
    const uploadResponse = await fetch(upload_url, {
      method: 'PUT',
      body: file,
      headers: { 'Content-Type': 'application/octet-stream' },
    })

    if (!uploadResponse.ok) {
      throw new Error('S3上传失败')
    }

    // 3. 确认上传
    const confirmResponse = await fetch(
      `/presign/upload/confirm/${upload_id}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expire_value: expireValue,
          expire_style: expireStyle,
        }),
      }
    )

    const confirmData = await confirmResponse.json()
    if (confirmData.code !== 200) {
      throw new Error(confirmData.detail)
    }

    return confirmData.detail
  } else {
    // 代理模式：上传到服务器
    const formData = new FormData()
    formData.append('file', file)

    const uploadResponse = await fetch(upload_url, {
      method: 'PUT',
      body: formData,
    })

    const uploadData = await uploadResponse.json()
    if (uploadData.code !== 200) {
      throw new Error(uploadData.detail)
    }

    return uploadData.detail
  }
}

// 使用示例
const file = document.querySelector('input[type="file"]').files[0]
const result = await uploadFile(file, 7, 'day')
console.log('分享码:', result.code)
```

### Vue 3 组件示例

```vue
<template>
  <div>
    <input type="file" @change="handleFileSelect" />
    <button @click="upload" :disabled="!selectedFile || uploading">
      {{ uploading ? '上传中...' : '上传' }}
    </button>
    <div v-if="shareCode">分享码: {{ shareCode }}</div>
    <div v-if="error" class="error">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const shareCode = ref('')
const error = ref('')

function handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  selectedFile.value = input.files?.[0] || null
}

async function upload() {
  if (!selectedFile.value) return

  uploading.value = true
  error.value = ''

  try {
    const result = await uploadFile(selectedFile.value)
    shareCode.value = result.code
  } catch (e) {
    error.value = e.message
  } finally {
    uploading.value = false
  }
}
</script>
```

---

## 注意事项

1. **会话有效期**: 上传会话默认 15 分钟后过期，请在有效期内完成上传
2. **文件大小限制**: 受系统配置 `uploadSize` 限制
3. **过期类型**: 支持 `day`、`hour`、`minute`、`forever`、`count`
4. **CORS**: 直传模式下，S3 需要配置正确的 CORS 策略
5. **重试机制**: 建议实现上传失败重试逻辑
