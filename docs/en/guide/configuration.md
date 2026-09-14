# Configuration Guide

FileCodeBox provides rich configuration options. Prefer the admin panel; directly editing the database can introduce invalid types or break security settings.

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
| `server_host` | string | `0.0.0.0` | Service listening address |
| `server_port` | int | `12345` | Service listening port |
| `server_workers` | int | `1` | Worker count; keep one worker for SQLite deployments |

### Notification Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `notify_title` | string | `系统通知` | Notification title |
| `notify_content` | string | Welcome message | Notification content, supports HTML |
| `page_explain` | string | Legal disclaimer | Footer explanation text |
| `robots_text` | string | `User-agent: *\nDisallow: /` | robots.txt content |

## Upload Settings

### File Upload Limits

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `open_upload` | int | `1` | Enable upload functionality (1=enabled, 0=disabled) |
| `upload_size` | int | `10485760` | Maximum single file upload size (bytes), default 10MB |
| `enable_chunk` | int | `0` | Enable chunked upload (1=enabled, 0=disabled) |
| `allowed_file_types` | list | `["*"]` | Allowed extensions; `*` allows every file type |

::: warning Note
`upload_size` is in bytes. 10MB = 10 * 1024 * 1024 = 10485760 bytes
:::

### Upload Rate Limiting

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `upload_minute` | int | `1` | Upload limit time window (minutes) |
| `upload_count` | int | `10` | Maximum uploads allowed within the time window |

Example: Default configuration allows up to 10 uploads per minute.


### File Expiration Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `expire_style` | list | `["day","hour","minute","forever","count"]` | Available expiration methods |
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
| `themes_select` | string | `themes/2024` | Currently active theme |
| `themes_choices` | list | See below | Available themes list |

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
| `admin_token` | string | Set during setup | Admin login password |
| `show_admin_addr` | int | `0` | Show admin panel entry on homepage (1=show, 0=hide) |
| `admin_session_expire` | int | `2592000` | Admin session lifetime in seconds (30 days) |

::: danger Security Warning
The setup page is shown automatically while the system is uninitialized. Complete setup before exposing a production service to the public internet.
:::

## Security Settings

### Error Rate Limiting

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `error_minute` | int | `1` | Error limit time window (minutes) |
| `error_count` | int | `10` | Maximum errors allowed within the time window |
| `trusted_proxies` | list | `[]` | Trusted reverse-proxy IPs used to resolve client addresses |

This setting prevents brute-force attacks on extraction codes.

## Storage Settings

### Storage Type

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `file_storage` | string | `local` | Storage backend type |
| `storage_path` | string | `""` | Custom storage path |
| `storage_limit` | int | `0` | Total storage quota in bytes; 0 means unlimited |

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
    "upload_size": 52428800,        # 50MB
    "upload_minute": 5,             # 5 minutes
    "upload_count": 20,             # Max 20 uploads
    "expire_style": ["day", "hour", "forever"],
    "show_admin_addr": 1
}
```

### Example 2: Public Service

Suitable for public services requiring stricter limits:

```python
{
    "name": "Public File Box",
    "upload_size": 10485760,        # 10MB
    "upload_minute": 1,             # 1 minute
    "upload_count": 5,              # Max 5 uploads
    "error_minute": 5,              # 5 minutes
    "error_count": 3,               # Max 3 errors
    "expire_style": ["hour", "minute", "count"],
    "max_save_seconds": 86400,     # Max retention 1 day
    "show_admin_addr": 0
}
```

### Example 3: Enterprise Internal Use

Suitable for enterprise internal use with large file and chunked upload support:

```python
{
    "name": "Enterprise File Transfer",
    "upload_size": 1073741824,      # 1GB
    "enable_chunk": 1,              # Enable chunked upload
    "upload_minute": 10,            # 10 minutes
    "upload_count": 100,            # Max 100 uploads
    "expire_style": ["day", "forever"],
    "file_storage": "s3",          # Use S3 storage
    "show_admin_addr": 1
}
```

::: warning Configuration examples
These dictionaries illustrate combinations of values; they are not editable configuration files. Set the admin password through first-run setup or the admin panel.
:::

## Next Steps

- [Storage Configuration](/en/guide/storage) - Learn how to configure different storage backends
- [Security Settings](/en/guide/security) - Learn how to enhance system security
- [File Sharing](/en/guide/share) - Learn about file sharing features
