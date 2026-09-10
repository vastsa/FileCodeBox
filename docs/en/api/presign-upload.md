# Presigned Upload API

## Overview

The presigned upload feature provides a unified file upload interface that automatically picks the optimal upload method based on the configured storage backend:

- **S3 storage**: returns a presigned URL so the client uploads directly to S3 (reduces server bandwidth usage)
- **Other storage**: returns a proxy upload URL and the file is transferred through the server

## Upload Flow

### Flow Diagram

```
┌─────────┐   1. Initialize upload   ┌─────────┐
│  Client │ ───────────────────────▶ │  Server │
└─────────┘                          └─────────┘
     │                                  │
     │◀──── upload_url + mode ──────────┤
     │                                  │
     │  ┌─────────────────────────────────────────┐
     │  │ if mode == "direct" (S3 storage)        │
     │  │   2a. PUT file to upload_url (S3)       │
     │  │   3a. POST /confirm to finish           │
     │  │                                         │
     │  │ if mode == "proxy" (other storage)      │
     │  │   2b. PUT file to upload_url (server)   │
     │  │   (share code returned automatically,   │
     │  │    no confirmation needed)              │
     │  └─────────────────────────────────────────┘
     │
     ▼
  Get share code
```

---

## API Endpoints

### 1. Initialize Upload

Initialize a presigned upload session and get the upload URL and mode.

**Request**

```
POST /presign/upload/init
Content-Type: application/json
```

**Request Body**

| Field        | Type    | Required | Default | Description                             |
| ------------ | ------- | -------- | ------- | --------------------------------------- |
| file_name    | string  | ✅       | -       | File name (with extension)              |
| file_size    | integer | ✅       | -       | File size in bytes                      |
| expire_value | integer | ❌       | 1       | Expiration time value                   |
| expire_style | string  | ❌       | "day"   | Expiration type: day/hour/minute/forever/count |

**Request Example**

```json
{
  "file_name": "document.pdf",
  "file_size": 1048576,
  "expire_value": 7,
  "expire_style": "day"
}
```

**Response**

```json
{
  "code": 200,
  "detail": {
    "upload_id": "a1b2c3d4e5f6...",
    "upload_url": "https://bucket.s3.amazonaws.com/path?X-Amz-Signature=...",
    "mode": "direct",
    "expires_in": 900
  }
}
```

**Response Fields**

| Field      | Type    | Description                                                     |
| ---------- | ------- | --------------------------------------------------------------- |
| upload_id  | string  | Upload session ID, required by all subsequent operations        |
| upload_url | string  | Target upload URL                                               |
| mode       | string  | Upload mode: `direct` (direct to S3) or `proxy` (via server)    |
| expires_in | integer | URL validity in seconds, default 900 seconds (15 minutes)       |

In `proxy` mode the response also includes `proxy_upload_url` (and `legacy_proxy_upload_url`); `upload_url` equals the proxy URL.

**Error Responses**

| Status | Description                                        |
| ------ | -------------------------------------------------- |
| 400    | Invalid expiration type                            |
| 403    | File size exceeds limit / IP rate limit exceeded   |

---

### 2a. Direct Mode - Upload File to S3

When `mode == "direct"`, the client PUTs the file directly to the returned presigned URL.

**Request**

```
PUT {upload_url}
Content-Type: application/octet-stream

[binary file content]
```

**Notes**

- Use the returned `upload_url` as-is, do not modify it
- `application/octet-stream` is the recommended Content-Type
- The request goes directly to S3, it does not pass through the server

**JavaScript Example**

```javascript
const response = await fetch(uploadUrl, {
  method: 'PUT',
  body: file,
  headers: {
    'Content-Type': 'application/octet-stream',
  },
})

if (response.ok) {
  // Upload succeeded, call the confirm endpoint
}
```

---

### 2b. Proxy Mode - Upload File to Server

When `mode == "proxy"`, the client PUTs the file to the server proxy endpoint.

**Request**

```
PUT /presign/upload/proxy/{upload_id}
Content-Type: multipart/form-data

file: [file]
```

**Path Parameters**

| Parameter | Description                                     |
| --------- | ----------------------------------------------- |
| upload_id | Upload session ID returned by the init endpoint |

**Response**

```json
{
  "code": 200,
  "detail": {
    "code": "123456",
    "name": "document.pdf"
  }
}
```

**Note**: In proxy mode the share code is returned immediately after upload; no confirmation call is needed.

**Error Responses**

| Status | Description                                                        |
| ------ | ------------------------------------------------------------------ |
| 400    | File size mismatches declared size / session does not support proxy |
| 404    | Upload session does not exist or has expired                       |
| 500    | Failed to save file                                                |

---

### 3. Confirm Upload (direct mode only)

In direct mode, call this endpoint after the S3 upload completes to obtain the share code.

**Request**

```
POST /presign/upload/confirm/{upload_id}
Content-Type: application/json
```

**Path Parameters**

| Parameter | Description                                     |
| --------- | ----------------------------------------------- |
| upload_id | Upload session ID returned by the init endpoint |

**Response**

```json
{
  "code": 200,
  "detail": {
    "code": "123456",
    "name": "document.pdf"
  }
}
```

**Error Responses**

| Status | Description                                                                     |
| ------ | ------------------------------------------------------------------------------- |
| 400    | Session does not support direct confirmation                                    |
| 404    | Upload session does not exist or has expired / file not uploaded or upload failed |

---

### 4. Query Upload Status

Query the current state of an upload session.

**Request**

```
GET /presign/upload/status/{upload_id}
```

**Response**

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

**Error Responses**

| Status | Description                        |
| ------ | ---------------------------------- |
| 404    | Upload session does not exist      |

---

### 5. Cancel Upload

Cancel an upload session and clean up related resources.

**Request**

```
DELETE /presign/upload/{upload_id}
```

**Response**

```json
{
  "code": 200,
  "detail": {
    "message": "Upload session cancelled"
  }
}
```

**Error Responses**

| Status | Description                        |
| ------ | ---------------------------------- |
| 404    | Upload session does not exist      |

---

## Frontend Integration Example

### Complete Upload Flow (JavaScript/TypeScript)

```typescript
interface PresignInitResponse {
  upload_id: string
  upload_url: string
  mode: 'direct' | 'proxy'
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
  // 1. Initialize upload
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

  // 2. Upload file based on mode
  if (mode === 'direct') {
    // Direct mode: upload to S3
    const uploadResponse = await fetch(upload_url, {
      method: 'PUT',
      body: file,
      headers: { 'Content-Type': 'application/octet-stream' },
    })

    if (!uploadResponse.ok) {
      throw new Error('S3 upload failed')
    }

    // 3. Confirm upload
    const confirmResponse = await fetch(
      `/presign/upload/confirm/${upload_id}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      }
    )

    const confirmData = await confirmResponse.json()
    if (confirmData.code !== 200) {
      throw new Error(confirmData.detail)
    }

    return confirmData.detail
  } else {
    // Proxy mode: upload through the server
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

// Usage example
const file = document.querySelector('input[type="file"]').files[0]
const result = await uploadFile(file, 7, 'day')
console.log('Share code:', result.code)
```

---

## Notes

1. **Session validity**: upload sessions expire after 15 minutes by default; complete the upload within the window
2. **File size limit**: bounded by the `upload_size` system setting
3. **Expiration types**: `day`, `hour`, `minute`, `forever`, `count`
4. **CORS**: in direct mode, S3 must have a proper CORS policy configured
5. **Retry**: implement upload retry logic on the client side for failed uploads
