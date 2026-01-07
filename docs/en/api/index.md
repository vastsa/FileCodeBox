# FileCodeBox API Documentation

## API Version: 2.1.0

## Table of Contents
- [Authentication](#authentication)
- [Share API](#share-api)
- [Admin API](#admin-api)

## Authentication

Some APIs require `Authorization` header for authentication:

```
Authorization: Bearer <token>
```

### Get Token

When guest upload is disabled in admin panel (`openUpload=0`), you need to login first:

```bash
curl -X POST "http://localhost:12345/admin/login" \
  -H "Content-Type: application/json" \
  -d '{"password": "FileCodeBox2023"}'
```

**Response Example:**

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

## Share API

### Share Text

**POST** `/share/text/`

Share text content and get a share code.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| text | string | Yes | - | Text content to share |
| expire_value | integer | No | 1 | Expiration time value |
| expire_style | string | No | "day" | Expiration time unit(day/hour/minute/count/forever) |

**cURL Example:**

```bash
# Guest upload (when openUpload=1)
curl -X POST "http://localhost:12345/share/text/" \
  -F "text=This is the text content to share" \
  -F "expire_value=1" \
  -F "expire_style=day"

# When authentication required (openUpload=0)
curl -X POST "http://localhost:12345/share/text/" \
  -H "Authorization: Bearer xxx.xxx.xxx" \
  -F "text=This is the text content to share"
```

**Response Example:**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "code": "abc123"
  }
}
```

### Share File

**POST** `/share/file/`

Upload and share a file, get a share code.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| file | file | Yes | - | File to upload |
| expire_value | integer | No | 1 | Expiration time value |
| expire_style | string | No | "day" | Expiration time unit(day/hour/minute/count/forever) |

**cURL Example:**

```bash
# Upload file (default 1 day expiration)
curl -X POST "http://localhost:12345/share/file/" \
  -F "file=@/path/to/file.txt"

# Upload file (7 days expiration)
curl -X POST "http://localhost:12345/share/file/" \
  -F "file=@/path/to/file.txt" \
  -F "expire_value=7" \
  -F "expire_style=day"

# Upload file (10 downloads limit)
curl -X POST "http://localhost:12345/share/file/" \
  -F "file=@/path/to/file.txt" \
  -F "expire_value=10" \
  -F "expire_style=count"

# When authentication required
curl -X POST "http://localhost:12345/share/file/" \
  -H "Authorization: Bearer xxx.xxx.xxx" \
  -F "file=@/path/to/file.txt"
```

**Response Example:**

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

### Get File Info

**GET** `/share/select/`

Get file information by share code (direct file download).

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| code | string | Yes | File share code |

**cURL Example:**

```bash
# Download file by extraction code
curl -L "http://localhost:12345/share/select/?code=abc123" -o downloaded_file
```

**Response Example:**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "code": "abc123",
    "name": "example.txt",
    "size": 1024,
    "text": "File content or download link"
  }
}
```

### Select File

**POST** `/share/select/`

Select file by share code.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| code | string | Yes | File share code |

**Response Example:**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "code": "abc123",
    "name": "example.txt",
    "size": 1024,
    "text": "File content or download link"
  }
}
```

### Download File

**GET** `/share/download`

Download shared file.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| key | string | Yes | Download key |
| code | string | Yes | File share code |

## Admin API

### Admin Login

**POST** `/admin/login`

Admin login to get token.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| password | string | Yes | Admin password |

### Dashboard Data

**GET** `/admin/dashboard`

Get system dashboard data.

**Response Example:**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "totalFiles": 100,
    "storageUsed": "1.5GB",
    "sysUptime": "10 days",
    "yesterdayCount": 50,
    "yesterdaySize": "500MB",
    "todayCount": 30,
    "todaySize": "300MB"
  }
}
```

### File List

**GET** `/admin/file/list`

Get system file list.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| page | integer | No | 1 | Current page |
| size | integer | No | 10 | Page size |
| keyword | string | No | "" | Search keyword |

**Response Example:**

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

### Delete File

**DELETE** `/admin/file/delete`

Delete file from system.

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| id | integer | Yes | File ID |

### Get Config

**GET** `/admin/config/get`

Get system configuration.

### Update Config

**PATCH** `/admin/config/update`

Update system configuration.

## Error Response

When an error occurs, the API will return corresponding error message:

```json
{
  "code": 422,
  "detail": [
    {
      "loc": ["body", "password"],
      "msg": "Password cannot be empty",
      "type": "value_error"
    }
  ]
}
```

## Status Codes

- 200: Success
- 401: Unauthorized
- 403: Forbidden
- 404: Not Found
- 422: Validation Error
- 500: Internal Server Error 