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

## Share API

### Share Text

**POST** `/share/text/`

Share text content and get a share code.

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| text | string | Yes | - | Text content to share |
| expire_value | integer | No | 1 | Expiration time value |
| expire_style | string | No | "day" | Expiration time unit(day/hour/minute) |

**Response Example:**

```json
{
  "code": 200,
  "msg": "success",
  "detail": {
    "code": "abc123",
    "name": "text.txt"
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
| expire_style | string | No | "day" | Expiration time unit(day/hour/minute) |

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

Get file information by share code.

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