# Configuration Guide

FileCodeBox provides rich configuration options that can be customized through the admin panel or by directly modifying the configuration. This document details all available configuration options.

## Configuration Methods

FileCodeBox supports two configuration methods:

1. **Admin Panel Configuration** (Recommended): Access `/admin` to enter the admin panel and modify settings on the settings page
2. **Database Configuration**: Configuration is stored in the `data/filecodebox.db` database

::: tip Note
On first startup, the system uses default configuration from `core/settings.py`. Modified configurations are saved to the database.
:::

## Basic Settings

### Site Information

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `name` | string | `文件快递柜 - FileCodeBox` | Site name, displayed in page title and navigation bar |
| `description` | string | `开箱即用的文件快传系统` | Site description, used for SEO |
| `keywords` | string | `FileCodeBox, 文件快递柜...` | Site keywords, used for SEO |
| `port` | int | `12345` | Service listening port |

### Notification Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `notify_title` | string | `系统通知` | Notification title |
| `notify_content` | string | Welcome message | Notification content, supports HTML |
| `page_explain` | string | Legal disclaimer | Footer explanation text |
| `robotsText` | string | `User-agent: *\nDisallow: /` | robots.txt content |

## Upload Settings

### File Upload Limits

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `openUpload` | int | `1` | Enable upload functionality (1=enabled, 0=disabled) |
| `uploadSize` | int | `10485760` | Maximum single file upload size (bytes), default 10MB |
| `enableChunk` | int | `0` | Enable chunked upload (1=enabled, 0=disabled) |

::: warning Note
`uploadSize` is in bytes. 10MB = 10 * 1024 * 1024 = 10485760 bytes
:::

### Upload Rate Limiting

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `uploadMinute` | int | `1` | Upload limit time window (minutes) |
| `uploadCount` | int | `10` | Maximum uploads allowed within the time window |

Example: Default configuration allows up to 10 uploads per minute.


### File Expiration Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `expireStyle` | list | `["day","hour","minute","forever","count"]` | Available expiration methods |
| `max_save_seconds` | int | `0` | Maximum file retention time (seconds), 0 means no limit |

Expiration methods explained:
- `day` - Expire by days
- `hour` - Expire by hours
- `minute` - Expire by minutes
- `forever` - Never expire
- `count` - Expire by download count

## Theme Settings

### Theme Selection

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `themesSelect` | string | `themes/2024` | Currently active theme |
| `themesChoices` | list | See below | Available themes list |

Default available themes:
```json
[
  {
    "name": "2023",
    "key": "themes/2023",
    "author": "Lan",
    "version": "1.0"
  },
  {
    "name": "2024",
    "key": "themes/2024",
    "author": "Lan",
    "version": "1.0"
  }
]
```

### Interface Style

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `opacity` | float | `0.9` | Interface opacity (0-1) |
| `background` | string | `""` | Custom background image URL, empty uses default background |

## Admin Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `admin_token` | string | `FileCodeBox2023` | Admin login password |
| `showAdminAddr` | int | `0` | Show admin panel entry on homepage (1=show, 0=hide) |

::: danger Security Warning
Always change the default `admin_token` in production environments! Using the default password poses serious security risks.
:::

## Security Settings

### Error Rate Limiting

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `errorMinute` | int | `1` | Error limit time window (minutes) |
| `errorCount` | int | `1` | Maximum errors allowed within the time window |

This setting prevents brute-force attacks on extraction codes.

## Storage Settings

### Storage Type

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `file_storage` | string | `local` | Storage backend type |
| `storage_path` | string | `""` | Custom storage path |

Supported storage types:
- `local` - Local storage
- `s3` - S3-compatible storage (AWS S3, Aliyun OSS, MinIO, etc.)
- `onedrive` - OneDrive storage
- `webdav` - WebDAV storage
- `opendal` - OpenDAL storage

For detailed storage configuration, see [Storage Configuration](/en/guide/storage).

## Configuration Examples

### Example 1: Small Personal Use

Suitable for personal or small team use with relaxed limits:

```python
{
    "name": "My File Share",
    "uploadSize": 52428800,        # 50MB
    "uploadMinute": 5,             # 5 minutes
    "uploadCount": 20,             # Max 20 uploads
    "expireStyle": ["day", "hour", "forever"],
    "admin_token": "your-secure-password",
    "showAdminAddr": 1
}
```

### Example 2: Public Service

Suitable for public services requiring stricter limits:

```python
{
    "name": "Public File Box",
    "uploadSize": 10485760,        # 10MB
    "uploadMinute": 1,             # 1 minute
    "uploadCount": 5,              # Max 5 uploads
    "errorMinute": 5,              # 5 minutes
    "errorCount": 3,               # Max 3 errors
    "expireStyle": ["hour", "minute", "count"],
    "max_save_seconds": 86400,     # Max retention 1 day
    "admin_token": "very-secure-password-123",
    "showAdminAddr": 0
}
```

### Example 3: Enterprise Internal Use

Suitable for enterprise internal use with large file and chunked upload support:

```python
{
    "name": "Enterprise File Transfer",
    "uploadSize": 1073741824,      # 1GB
    "enableChunk": 1,              # Enable chunked upload
    "uploadMinute": 10,            # 10 minutes
    "uploadCount": 100,            # Max 100 uploads
    "expireStyle": ["day", "forever"],
    "file_storage": "s3",          # Use S3 storage
    "admin_token": "enterprise-secure-token",
    "showAdminAddr": 1
}
```

## Next Steps

- [Storage Configuration](/en/guide/storage) - Learn how to configure different storage backends
- [Security Settings](/en/guide/security) - Learn how to enhance system security
- [File Sharing](/en/guide/share) - Learn about file sharing features
